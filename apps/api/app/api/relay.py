"""Le back-office joue le relais de mailing pour un autre back-office.

Monte seulement si `RELAY_SERVER_ENABLED=true` : accepter de poster pour
autrui est une decision de deploiement, pas une case a cocher dans l'admin
d'une machine posee sur un stand.

Ce qui empeche la plateforme de devenir un relais ouvert, dans l'ordre ou
c'est verifie :

1. un token par client, hashe en base et revocable (`deps.current_relay_client`) ;
2. une limite au debit, puis un quota journalier par client ;
3. l'expediteur est celui du serveur, jamais celui que demande le client ;
4. un seul destinataire par requete, taille du corps et de la piece plafonnee ;
5. idempotence sur `message_id` : le worker d'en face peut retenter sans
   qu'un visiteur recoive deux fois le meme email.

Une fois accepte, le message rejoint l'outbox du serveur : meme file, meme
backoff, meme page « Emails » que les envois locaux.
"""

from __future__ import annotations

import base64
import binascii
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import current_relay_client
from app.models import RelayClient, RelayMessage
from app.schemas import RelaySendIn, RelaySendOut
from app.services import mailer

router = APIRouter(prefix="/api/relay", tags=["relay"])

RELAY_MEDIA_SUBDIR = "relay"


def _remaining(client: RelayClient) -> int:
    return max(0, client.daily_quota - client.sent_today)


@router.get("/ping")
def ping(
    client: RelayClient = Depends(current_relay_client),
    db: Session = Depends(get_db),
) -> dict:
    """Verifie la liaison depuis le back-office client, avant le salon.

    Rend de quoi diagnostiquer sans ouvrir les logs : le nom sous lequel le
    client est enregistre, ce qu'il lui reste de quota, et par quoi le
    serveur expedie reellement.
    """
    return {
        "ok": True,
        "client": client.name,
        "mail_from": settings.mail_from,
        "transport": mailer.current_transport(db),
        "daily_quota": client.daily_quota,
        "sent_today": client.sent_today,
        "remaining_today": _remaining(client),
    }


@router.post("/send", response_model=RelaySendOut)
def send(
    payload: RelaySendIn,
    client: RelayClient = Depends(current_relay_client),
    db: Session = Depends(get_db),
) -> RelaySendOut:
    # Un relais qui relaie a son tour ferait tourner l'email en rond sans que
    # personne ne voie ou il s'est perdu.
    if mailer.current_transport(db) == "relay":
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Ce back-office est lui-meme en mode relais : il ne peut pas en servir.",
        )

    if len(payload.body_html.encode()) > settings.relay_max_body_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Corps trop volumineux (max {settings.relay_max_body_bytes} octets)",
        )

    content: bytes | None = None
    if payload.attachment:
        try:
            content = base64.b64decode(payload.attachment.content_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Piece jointe illisible (base64)"
            ) from exc
        if len(content) > settings.relay_max_attachment_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"Piece jointe trop volumineuse (max {settings.relay_max_attachment_bytes} octets)",
            )

    # Le doublon est reconnu avant le quota : un renvoi apres timeout ne doit
    # ni consommer un envoi, ni etre refuse une fois la journee pleine.
    existing = db.scalar(
        select(RelayMessage).where(
            RelayMessage.client_id == client.id,
            RelayMessage.message_id == payload.message_id,
        )
    )
    if existing and existing.outbox_id:
        return RelaySendOut(
            accepted=True,
            outbox_id=existing.outbox_id,
            duplicate=True,
            remaining_today=_remaining(client),
        )

    if _remaining(client) <= 0:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Quota journalier atteint ({client.daily_quota} envois). Reprise demain.",
            headers={"Retry-After": "3600"},
        )

    attachment_path = None
    if content is not None and payload.attachment:
        attachment_path = _store_attachment(client, payload.message_id, payload.attachment.filename, content)

    item = mailer.queue_email(
        db,
        to_email=payload.to,
        subject=payload.subject,
        body_html=payload.body_html,
        attachment_path=attachment_path,
    )

    db.add(RelayMessage(client_id=client.id, message_id=payload.message_id, outbox_id=item.id))
    client.sent_today += 1
    client.sent_total += 1
    try:
        db.commit()
    except IntegrityError:
        # Deux retries arrives en meme temps. L'autre a gagne : on rend sa ligne.
        db.rollback()
        winner = db.scalar(
            select(RelayMessage).where(
                RelayMessage.client_id == client.id,
                RelayMessage.message_id == payload.message_id,
            )
        )
        if not winner or not winner.outbox_id:
            raise
        return RelaySendOut(
            accepted=True,
            outbox_id=winner.outbox_id,
            duplicate=True,
            remaining_today=_remaining(client),
        )

    return RelaySendOut(
        accepted=True, outbox_id=item.id, duplicate=False, remaining_today=_remaining(client)
    )


def _store_attachment(client: RelayClient, message_id: str, filename: str, content: bytes) -> str:
    """Ecrit la piece jointe sur disque : l'outbox stocke un chemin, pas des octets.

    Le nom du fichier vient du client, donc on n'en garde que le suffixe et on
    nomme d'apres l'identifiant du message -- un `../` dans `filename` ne doit
    pas pouvoir designer un fichier hors du dossier.
    """
    directory = Path(settings.media_dir) / RELAY_MEDIA_SUBDIR / str(client.id)
    directory.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix[:12]
    safe_id = "".join(c for c in message_id if c.isalnum() or c in "-_")[:64] or "message"
    path = directory / f"{safe_id}{suffix}"
    path.write_bytes(content)
    return str(path)
