from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import current_admin
from app.models import (
    AdminUser,
    Design,
    DesignStatus,
    EmailOutbox,
    Event,
    Kiosk,
    OutboxStatus,
    RelayClient,
    Visitor,
)
from app.schemas import (
    MailConfigIn,
    MailTestIn,
    RelayClientIn,
    RelayClientPatch,
    StatsOut,
)
from app.security import generate_relay_token, generate_token, hash_secret
from app.services import mailer
from app.services.settings_store import get_setting, set_setting
from app.services.transports import SendError
from app.services.transports import relay as relay_transport

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(current_admin)])


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)) -> StatsOut:
    scalar = lambda stmt: db.scalar(stmt) or 0  # noqa: E731
    return StatsOut(
        visitors_total=scalar(select(func.count()).select_from(Visitor)),
        visitors_verified=scalar(
            select(func.count()).select_from(Visitor).where(Visitor.email_verified_at.isnot(None))
        ),
        designs_total=scalar(select(func.count()).select_from(Design)),
        designs_rendered=scalar(
            select(func.count()).select_from(Design).where(Design.status == DesignStatus.rendered)
        ),
        emails_pending=scalar(
            select(func.count()).select_from(EmailOutbox).where(
                EmailOutbox.status == OutboxStatus.pending
            )
        ),
        emails_failed=scalar(
            select(func.count()).select_from(EmailOutbox).where(
                EmailOutbox.status == OutboxStatus.failed
            )
        ),
    )


@router.get("/timeline")
def timeline(hours: int = Query(24, ge=1, le=24 * 14), db: Session = Depends(get_db)) -> list[dict]:
    """Volume d'inscriptions et de creations par heure, pour le graphe du dashboard."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    bucket = func.date_trunc("hour", Event.created_at).label("bucket")
    rows = db.execute(
        select(bucket, Event.name, func.count())
        .where(Event.created_at >= since)
        .group_by(bucket, Event.name)
        .order_by(bucket)
    ).all()
    return [{"bucket": b.isoformat(), "name": name, "count": count} for b, name, count in rows]


@router.get("/visitors")
def visitors(
    limit: int = Query(50, le=500),
    offset: int = 0,
    search: str = "",
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Visitor).order_by(Visitor.created_at.desc())
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(Visitor.email).like(pattern)
            | func.lower(Visitor.last_name).like(pattern)
            | func.lower(Visitor.first_name).like(pattern)
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return {
        "total": total,
        "items": [
            {
                "id": str(v.id),
                "first_name": v.first_name,
                "last_name": v.last_name,
                "email": v.email,
                "postal_code": v.postal_code,
                "email_verified_at": v.email_verified_at.isoformat() if v.email_verified_at else None,
                "consent_marketing": v.consent_marketing,
                "created_at": v.created_at.isoformat(),
            }
            for v in rows
        ],
    }


@router.get("/visitors.csv")
def visitors_csv(consented_only: bool = True, db: Session = Depends(get_db)) -> StreamingResponse:
    """Export pour le CRM. Par defaut, uniquement les visiteurs ayant consenti."""
    stmt = select(Visitor).where(Visitor.email_verified_at.isnot(None))
    if consented_only:
        stmt = stmt.where(Visitor.consent_marketing.is_(True))

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["prenom", "nom", "email", "code_postal", "opt_in", "date"])
    for v in db.scalars(stmt.order_by(Visitor.created_at)):
        writer.writerow(
            [v.first_name, v.last_name, v.email, v.postal_code, int(v.consent_marketing),
             v.created_at.isoformat()]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="visiteurs.csv"'},
    )


@router.get("/designs")
def designs(limit: int = Query(60, le=300), offset: int = 0, db: Session = Depends(get_db)) -> dict:
    stmt = select(Design).order_by(Design.created_at.desc())
    total = db.scalar(select(func.count()).select_from(Design)) or 0
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return {
        "total": total,
        "items": [
            {
                "id": str(d.id),
                "status": d.status.value,
                "created_at": d.created_at.isoformat(),
                "visitor_id": str(d.visitor_id) if d.visitor_id else None,
                "render_url": f"/{d.render_path}" if d.render_path else None,
            }
            for d in rows
        ],
    }



@router.get("/emails")
def emails(status_filter: str = "", db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(EmailOutbox).order_by(EmailOutbox.created_at.desc()).limit(200)
    if status_filter:
        stmt = stmt.where(EmailOutbox.status == OutboxStatus(status_filter))
    return [
        {
            "id": str(e.id),
            "to": e.to_email,
            "subject": e.subject,
            "status": e.status.value,
            "attempts": e.attempts,
            "last_error": e.last_error,
            "created_at": e.created_at.isoformat(),
            "sent_at": e.sent_at.isoformat() if e.sent_at else None,
        }
        for e in db.scalars(stmt)
    ]


@router.post("/emails/retry-failed")
def retry_failed(db: Session = Depends(get_db)) -> dict:
    """Remet en file tous les emails en echec (typiquement apres retour du reseau)."""
    items = db.scalars(select(EmailOutbox).where(EmailOutbox.status == OutboxStatus.failed)).all()
    for item in items:
        item.status = OutboxStatus.pending
        item.attempts = 0
        item.next_attempt_at = datetime.now(UTC)
    db.commit()
    return {"requeued": len(items)}


@router.get("/kiosks")
def kiosks(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": str(k.id),
            "name": k.name,
            "token": k.token,
            "is_active": k.is_active,
            "last_seen_at": k.last_seen_at.isoformat() if k.last_seen_at else None,
        }
        for k in db.scalars(select(Kiosk).order_by(Kiosk.created_at))
    ]


@router.post("/kiosks")
def create_kiosk(name: str, db: Session = Depends(get_db)) -> dict:
    kiosk = Kiosk(name=name, token=generate_token())
    db.add(kiosk)
    db.commit()
    return {"id": str(kiosk.id), "name": kiosk.name, "token": kiosk.token}


@router.get("/settings")
def read_settings(db: Session = Depends(get_db)) -> dict:
    return {
        "verification_bypass": get_setting(db, "verification_bypass", False),
        "idle_timeout_seconds": get_setting(db, "idle_timeout_seconds", 90),
        "attract_interval_seconds": get_setting(db, "attract_interval_seconds", 6),
    }


@router.put("/settings")
def write_settings(payload: dict, db: Session = Depends(get_db)) -> dict:
    allowed = {"verification_bypass", "idle_timeout_seconds", "attract_interval_seconds"}
    for key, value in payload.items():
        if key in allowed:
            set_setting(db, key, value)
    db.commit()
    return read_settings(db)


@router.delete("/visitors/{visitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_visitor(visitor_id: uuid.UUID, db: Session = Depends(get_db)):
    """Droit a l'effacement RGPD. Les creations restent, anonymisees."""
    visitor = db.get(Visitor, visitor_id)
    if not visitor:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Visiteur inconnu")
    db.delete(visitor)
    db.commit()


# --- Envoi des emails ---
#
# Deux roles distincts sur le meme ecran d'admin :
#   * client  -- « par ou sortent MES emails » (SMTP, Brevo, ou un relais) ;
#   * serveur -- « qui a le droit de me confier LES SIENS » (les clients de
#     relais ci-dessous), section visible seulement si RELAY_SERVER_ENABLED.


@router.get("/mail")
def read_mail_config(db: Session = Depends(get_db)) -> dict:
    """L'etat de la configuration d'envoi. Ne rend jamais de secret."""
    return {
        "transport": mailer.current_transport(db),
        "transports": list(mailer.TRANSPORTS),
        "mail_from": settings.mail_from,
        "mail_from_name": settings.mail_from_name,
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_configured": bool(settings.smtp_host),
        "brevo_configured": bool(settings.brevo_api_key),
        "relay_url": relay_transport.relay_url(db),
        "relay_token_set": bool(relay_transport.relay_token(db)),
        "relay_server_enabled": settings.relay_server_enabled,
        "relay_default_daily_quota": settings.relay_default_daily_quota,
    }


@router.put("/mail")
def write_mail_config(payload: MailConfigIn, db: Session = Depends(get_db)) -> dict:
    if payload.transport is not None:
        set_setting(db, "mail_transport", payload.transport)
    if payload.relay_url is not None:
        set_setting(db, "mail_relay_url", payload.relay_url.strip())
    if payload.relay_token is not None:
        set_setting(db, "mail_relay_token", payload.relay_token.strip())
    db.commit()
    return read_mail_config(db)


@router.post("/mail/test-relay")
def test_relay(db: Session = Depends(get_db)) -> dict:
    """Interroge le back-office distant. A faire avant le salon, pas pendant."""
    try:
        return {"ok": True, "remote": relay_transport.ping(db)}
    except SendError as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/mail/test-send")
def test_send(payload: MailTestIn, db: Session = Depends(get_db)) -> dict:
    """Met un email de test dans la file : valide la chaine complete, worker compris."""
    item = mailer.queue_email(
        db,
        to_email=payload.to,
        subject="Test d'envoi AIXAM",
        body_html=mailer.render_template("test.html", transport=mailer.current_transport(db)),
    )
    db.commit()
    return {"queued": True, "outbox_id": str(item.id)}


# --- Clients de relais (role serveur) ---


def _relay_row(client: RelayClient) -> dict:
    return {
        "id": str(client.id),
        "name": client.name,
        "token_prefix": client.token_prefix,
        "is_active": client.is_active,
        "daily_quota": client.daily_quota,
        "sent_today": client.sent_today,
        "sent_total": client.sent_total,
        "last_seen_at": client.last_seen_at.isoformat() if client.last_seen_at else None,
        "created_at": client.created_at.isoformat(),
    }


@router.get("/relay-clients")
def relay_clients(db: Session = Depends(get_db)) -> list[dict]:
    return [
        _relay_row(c)
        for c in db.scalars(select(RelayClient).order_by(RelayClient.created_at))
    ]


@router.post("/relay-clients", status_code=status.HTTP_201_CREATED)
def create_relay_client(payload: RelayClientIn, db: Session = Depends(get_db)) -> dict:
    """Cree un client et rend son token -- la seule fois ou il sera lisible.

    Seul le hash est conserve : personne, admin compris, ne peut relire le
    token ensuite. Perdu, il se remplace en supprimant la ligne et en en
    recreant une.
    """
    token, prefix, secret = generate_relay_token()
    client = RelayClient(
        name=payload.name.strip(),
        token_prefix=prefix,
        token_hash=hash_secret(secret),
        daily_quota=payload.daily_quota or settings.relay_default_daily_quota,
    )
    db.add(client)
    db.commit()
    return {**_relay_row(client), "token": token}


@router.patch("/relay-clients/{client_id}")
def update_relay_client(
    client_id: uuid.UUID, payload: RelayClientPatch, db: Session = Depends(get_db)
) -> dict:
    client = db.get(RelayClient, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client de relais inconnu")
    if payload.is_active is not None:
        client.is_active = payload.is_active
    if payload.daily_quota is not None:
        client.daily_quota = payload.daily_quota
    db.commit()
    return _relay_row(client)


@router.delete("/relay-clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_relay_client(client_id: uuid.UUID, db: Session = Depends(get_db)):
    """Revoque un client. Les emails deja en file partent quand meme."""
    client = db.get(RelayClient, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client de relais inconnu")
    db.delete(client)
    db.commit()
