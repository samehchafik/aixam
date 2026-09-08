import base64
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, date, datetime

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import AdminUser, Kiosk, RelayClient
from app.security import decode_access_token, split_relay_token, verify_secret


def current_admin(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AdminUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    payload = decode_access_token(authorization.split(" ", 1)[1])
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = db.get(AdminUser, uuid.UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def current_kiosk(
    x_kiosk_token: str | None = Header(default=None, alias="X-Kiosk-Token"),
    db: Session = Depends(get_db),
) -> Kiosk:
    if not x_kiosk_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing kiosk token")
    kiosk = db.scalar(select(Kiosk).where(Kiosk.token == x_kiosk_token, Kiosk.is_active.is_(True)))
    if not kiosk:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown kiosk")
    kiosk.last_seen_at = datetime.now(UTC)
    db.commit()
    return kiosk


def require_kiosk_basic_auth(request: Request) -> None:
    """Protege le lien https de dev de la borne.

    Desactive si KIOSK_BASIC_USER est vide (cas du salon, ou la borne tourne en
    local et n'a pas a demander un mot de passe a chaque redemarrage).
    """
    if not settings.kiosk_basic_user:
        return

    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1]).decode()
            user, _, password = decoded.partition(":")
        except Exception:
            user, password = "", ""
        if secrets.compare_digest(user, settings.kiosk_basic_user) and secrets.compare_digest(
            password, settings.kiosk_basic_password
        ):
            return

    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Authentification requise",
        headers={"WWW-Authenticate": 'Basic realm="AIXAM Kiosk"'},
    )


# Fenetre glissante par client, en memoire. Un compteur en base par requete
# serait une ecriture de plus sur le chemin chaud pour une limite qui n'a
# besoin d'etre qu'approximative ; le quota journalier, lui, est en base et
# reste exact. Si l'API est repliquee un jour, cette limite devient « par
# replique » -- le quota journalier reste la vraie barriere.
_relay_hits: dict[uuid.UUID, deque[float]] = defaultdict(deque)


def _check_relay_rate(client: RelayClient) -> None:
    limit = settings.relay_rate_limit_per_minute
    if limit <= 0:
        return
    now = time.monotonic()
    hits = _relay_hits[client.id]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Trop de requetes ({limit}/minute). Reessayer dans une minute.",
            headers={"Retry-After": "60"},
        )
    hits.append(now)


def current_relay_client(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> RelayClient:
    """Authentifie un back-office qui demande a faire expedier ses emails.

    Le refus est volontairement muet sur la cause (token inconnu ? revoque ?) :
    la reponse ne doit rien apprendre a qui essaie des tokens au hasard.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de relais manquant")

    parts = split_relay_token(authorization.split(" ", 1)[1])
    if not parts:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de relais invalide")
    prefix, secret = parts

    client = db.scalar(select(RelayClient).where(RelayClient.token_prefix == prefix))
    if not client or not client.is_active or not verify_secret(secret, client.token_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de relais invalide")

    _check_relay_rate(client)

    today = date.today()
    if client.quota_day != today:
        client.quota_day = today
        client.sent_today = 0
    client.last_seen_at = datetime.now(UTC)
    db.commit()
    return client
