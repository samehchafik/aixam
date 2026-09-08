"""Endpoints appeles par la borne.

Tous authentifies par le header `X-Kiosk-Token`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import current_kiosk
from app.models import (
    Design,
    DesignStatus,
    Event,
    Kiosk,
    VerificationCode,
    Visitor,
)
from app.schemas import (
    DesignIn,
    DesignOut,
    EventIn,
    RegisterIn,
    RegisterOut,
    VerifyIn,
    VerifyOut,
)
from app.security import generate_numeric_code, hash_secret, verify_secret
from app.services import mailer
from app.services.assets import load_catalog
from app.services.renderer import render_design
from app.services.settings_store import get_setting

router = APIRouter(prefix="/api/kiosk", tags=["kiosk"])


def _log(db: Session, kiosk: Kiosk, name: str, **kwargs) -> None:
    db.add(Event(kiosk_id=kiosk.id, name=name, **kwargs))


@router.get("/bootstrap")
def bootstrap(kiosk: Kiosk = Depends(current_kiosk), db: Session = Depends(get_db)) -> dict:
    """Tout ce dont le front a besoin au demarrage : catalogue + reglages a chaud."""
    return {
        "kiosk": {"id": str(kiosk.id), "name": kiosk.name},
        "catalog": load_catalog(),
        "settings": {
            "verification_bypass": bool(
                get_setting(db, "verification_bypass", settings.allow_verification_bypass)
            ),
            "idle_timeout_seconds": int(get_setting(db, "idle_timeout_seconds", 90)),
            "attract_interval_seconds": int(get_setting(db, "attract_interval_seconds", 6)),
        },
    }


@router.post("/register", response_model=RegisterOut)
def register(
    payload: RegisterIn,
    kiosk: Kiosk = Depends(current_kiosk),
    db: Session = Depends(get_db),
) -> RegisterOut:
    visitor = Visitor(
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        email=payload.email.lower(),
        postal_code=payload.postal_code.strip(),
        consent_marketing=payload.consent_marketing,
        consent_at=datetime.now(UTC) if payload.consent_marketing else None,
    )
    db.add(visitor)
    db.flush()

    bypass = bool(get_setting(db, "verification_bypass", settings.allow_verification_bypass))
    if bypass:
        visitor.email_verified_at = datetime.now(UTC)
    else:
        code = generate_numeric_code()
        db.add(
            VerificationCode(
                visitor_id=visitor.id,
                code_hash=hash_secret(code),
                expires_at=datetime.now(UTC)
                + timedelta(seconds=settings.verification_code_ttl_seconds),
            )
        )
        mailer.queue_email(
            db,
            to_email=visitor.email,
            subject="Votre code de verification AIXAM",
            body_html=mailer.render_template(
                "verification.html", first_name=visitor.first_name, code=code
            ),
        )

    _log(db, kiosk, "visitor_registered", visitor_id=visitor.id, session_id=payload.session_id)
    db.commit()
    return RegisterOut(visitor_id=visitor.id, verification_required=not bypass)


@router.post("/verify", response_model=VerifyOut)
def verify(
    payload: VerifyIn,
    kiosk: Kiosk = Depends(current_kiosk),
    db: Session = Depends(get_db),
) -> VerifyOut:
    visitor = db.get(Visitor, payload.visitor_id)
    if not visitor:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Visiteur inconnu")
    if visitor.email_verified_at:
        return VerifyOut(verified=True, remaining_attempts=settings.verification_max_attempts)

    entry = db.scalar(
        select(VerificationCode)
        .where(
            VerificationCode.visitor_id == visitor.id,
            VerificationCode.consumed_at.is_(None),
        )
        .order_by(VerificationCode.created_at.desc())
    )
    if not entry:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Aucun code en attente")

    now = datetime.now(UTC)
    if entry.expires_at < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code expire")
    if entry.attempts >= settings.verification_max_attempts:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Trop de tentatives")

    entry.attempts += 1
    if not verify_secret(payload.code.strip(), entry.code_hash):
        _log(db, kiosk, "verification_failed", visitor_id=visitor.id)
        db.commit()
        return VerifyOut(
            verified=False,
            remaining_attempts=settings.verification_max_attempts - entry.attempts,
        )

    entry.consumed_at = now
    visitor.email_verified_at = now
    _log(db, kiosk, "verification_succeeded", visitor_id=visitor.id)
    db.commit()
    return VerifyOut(verified=True, remaining_attempts=settings.verification_max_attempts)


@router.post("/designs", response_model=DesignOut)
def save_design(
    payload: DesignIn,
    kiosk: Kiosk = Depends(current_kiosk),
    db: Session = Depends(get_db),
) -> DesignOut:
    """Enregistre la creation, la rend en JPEG et met l'email en file."""
    design = Design(
        visitor_id=payload.visitor_id,
        kiosk_id=kiosk.id,
        session_id=payload.session_id,
        layers={"layers": [layer.model_dump() for layer in payload.layers]},
        status=DesignStatus.submitted,
    )
    db.add(design)
    db.flush()

    try:
        out = render_design(design.layers)
        design.render_path = str(out)
        design.status = DesignStatus.rendered
    except Exception as exc:  # le visiteur ne doit jamais rester bloque
        design.status = DesignStatus.failed
        _log(db, kiosk, "render_failed", session_id=payload.session_id, payload={"error": str(exc)})

    if design.visitor_id and design.status == DesignStatus.rendered:
        visitor = db.get(Visitor, design.visitor_id)
        if visitor:
            mailer.queue_email(
                db,
                to_email=visitor.email,
                subject="Votre creation EASY",
                body_html=mailer.render_template(
                    "creation.html",
                    first_name=visitor.first_name,
                    base_url=settings.public_base_url,
                ),
                attachment_path=design.render_path,
            )

    _log(db, kiosk, "design_submitted", visitor_id=payload.visitor_id, session_id=payload.session_id)
    db.commit()

    return DesignOut(
        id=design.id,
        status=design.status.value,
        # Les rendus sont servis en statique depuis /media : le nom de fichier est
        # un UUID, et un <img src> ne peut de toute facon pas porter de header.
        render_url=f"/{design.render_path}" if design.render_path else None,
    )


@router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
def track(
    payload: EventIn,
    kiosk: Kiosk = Depends(current_kiosk),
    db: Session = Depends(get_db),
):
    db.add(
        Event(
            kiosk_id=kiosk.id,
            visitor_id=payload.visitor_id,
            session_id=payload.session_id,
            name=payload.name,
            payload=payload.payload,
        )
    )
    db.commit()
