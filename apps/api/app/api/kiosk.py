"""Endpoints appeles par la borne.

Tous authentifies par le header `X-Kiosk-Token`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import current_kiosk
from app.models import (
    Design,
    DesignStatus,
    Event,
    Kiosk,
    Moderation,
    VerificationCode,
    Visitor,
)
from app.schemas import (
    DesignIn,
    DesignOut,
    EventIn,
    MaterielIn,
    RegisterIn,
    RegisterOut,
    VerifyIn,
    VerifyOut,
)
from app.security import generate_numeric_code, hash_secret, verify_secret
from app.services import mailer, materiel
from app.services.assets import load_catalog
from app.services.renderer import render_design, skin_present, skin_url
from app.services.settings_store import get_setting

router = APIRouter(prefix="/api/kiosk", tags=["kiosk"])


def _log(db: Session, kiosk: Kiosk, name: str, **kwargs) -> None:
    db.add(Event(kiosk_id=kiosk.id, name=name, **kwargs))


@router.post("/materiel")
def materiel_pousse(
    payload: MaterielIn,
    kiosk: Kiosk = Depends(current_kiosk),
    db: Session = Depends(get_db),
) -> dict:
    """La machine du stand annonce ses ecrans, et les reannonce quand ils changent.

    Un releve ecrit une fois pour toutes serait une photo : debrancher un
    moniteur et le rebrancher sur une autre prise la rendrait fausse sans que
    rien ne le signale. C'est donc la machine qui pilote les ecrans qui pousse,
    et elle repousse des que Windows change de disposition.
    """
    releve = {
        "releve_le": datetime.now(UTC).isoformat(),
        "systeme": payload.systeme,
        "ecrans": [e.model_dump() for e in payload.ecrans],
        "indisponible": None if payload.ecrans else "Aucun ecran detecte.",
    }
    materiel.ecrire(releve)
    _log(db, kiosk, "materiel_releve", payload={"ecrans": len(payload.ecrans)})
    db.commit()
    return releve


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
            # La borne dessine autant de cases que le code a de chiffres.
            "verification_code_length": settings.verification_code_length,
        },
    }


@router.post("/register", response_model=RegisterOut)
def register(
    payload: RegisterIn,
    kiosk: Kiosk = Depends(current_kiosk),
    db: Session = Depends(get_db),
) -> RegisterOut:
    try:
        return _enregistrer(payload, kiosk, db)
    except IntegrityError:
        # Deux bornes ont inscrit la meme adresse au meme instant : la
        # contrainte d'unicite a tranche. Au second passage, le SELECT trouve
        # la ligne et l'on emprunte le chemin « visiteur connu ».
        db.rollback()
        return _enregistrer(payload, kiosk, db)


def _enregistrer(payload: RegisterIn, kiosk: Kiosk, db: Session) -> RegisterOut:
    now = datetime.now(UTC)
    email = payload.email.strip().lower()

    # L'email identifie la personne. Sans cette recherche, une deuxieme
    # inscription creait une deuxieme ligne et un deuxieme code : le visiteur
    # recevait deux emails identiques, en tapait un au hasard, et brulait ses
    # essais jusqu'au 429 sans issue possible depuis la borne.
    visitor = db.scalar(
        select(Visitor).where(Visitor.email == email).order_by(Visitor.created_at.desc())
    )
    connu = visitor is not None

    if visitor is None:
        visitor = Visitor(email=email)
        db.add(visitor)

    visitor.first_name = payload.first_name.strip()
    visitor.last_name = payload.last_name.strip()
    visitor.postal_code = payload.postal_code.strip()
    if payload.consent_marketing and not visitor.consent_marketing:
        visitor.consent_at = now
    visitor.consent_marketing = payload.consent_marketing
    db.flush()

    bypass = bool(get_setting(db, "verification_bypass", settings.allow_verification_bypass))
    # Deja verifie lors d'un passage precedent : on ne redemande pas un code
    # pour une adresse dont on sait qu'elle lui appartient.
    deja_verifie = visitor.email_verified_at is not None
    if bypass and not deja_verifie:
        visitor.email_verified_at = now

    verification_requise = not bypass and not deja_verifie
    if verification_requise:
        # Un seul code valable a la fois : les precedents sont retires, pour
        # qu'un ancien email dans la boite du visiteur ne puisse plus egarer.
        for ancien in db.scalars(
            select(VerificationCode).where(
                VerificationCode.visitor_id == visitor.id,
                VerificationCode.consumed_at.is_(None),
            )
        ):
            ancien.consumed_at = now

        code = generate_numeric_code(settings.verification_code_length)
        db.add(
            VerificationCode(
                visitor_id=visitor.id,
                code_hash=hash_secret(code),
                expires_at=now + timedelta(seconds=settings.verification_code_ttl_seconds),
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

    _log(
        db,
        kiosk,
        "visitor_returned" if connu else "visitor_registered",
        visitor_id=visitor.id,
        session_id=payload.session_id,
    )
    db.commit()
    return RegisterOut(visitor_id=visitor.id, verification_required=verification_requise)


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
    # exclude_none : l'ABSENCE d'echelle est le signal « ce fond couvre la
    # planche ». La serialiser a None la transformerait en valeur, que le rendu
    # lirait comme une echelle nulle.
    #
    # Ces calques ne sont pas conserves. Ils citent le catalogue par
    # identifiant : le jour ou un fond change de nom, ils ne decrivent plus
    # rien. Ce qu'on garde, c'est l'image qu'ils produisent ici.
    calques = {"layers": [layer.model_dump(exclude_none=True) for layer in payload.layers]}

    design = Design(
        visitor_id=payload.visitor_id,
        kiosk_id=kiosk.id,
        session_id=payload.session_id,
        status=DesignStatus.submitted,
    )
    db.add(design)
    db.flush()

    try:
        out = render_design(calques)
        design.skin = out.name
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
        render_url=skin_url(design.skin, design.render_path),
    )


@router.get("/designs/recent")
def creations_recentes(
    limit: int = Query(24, ge=1, le=60),
    kiosk: Kiosk = Depends(current_kiosk),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Les dernieres creations a montrer sur le grand ecran.

    Uniquement celles que l'animateur a approuvees : le diaporama tourne en
    public sur le stand, une creation n'y parait pas avant d'avoir ete vue.
    """
    lignes = db.scalars(
        select(Design)
        .where(
            Design.status == DesignStatus.rendered,
            Design.moderation == Moderation.approved.value,
            # Une creation d'avant n'a pas de skin mais un render_path ; une
            # creation remontee d'une borne a l'inverse. Il en faut un des deux.
            or_(Design.skin.isnot(None), Design.render_path.isnot(None)),
        )
        .order_by(Design.created_at.desc())
        .limit(limit)
    ).all()
    # Un chemin en base ne garantit pas le fichier : on ecarte les rendus
    # disparus plutot que d'envoyer au grand ecran une image qui ne chargera
    # pas -- le mockup du studio laisserait alors paraitre, en public, sa
    # plaque « Placer le design ici ».
    return [
        {"id": str(d.id), "render_url": skin_url(d.skin, d.render_path)}
        for d in lignes
        if skin_present(d.skin, d.render_path)
    ]


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
