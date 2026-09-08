"""Le back-office local confie ses emails a un back-office distant.

Pourquoi : sur un stand, on ne veut ni poser les identifiants de la boite OVH
sur une machine que des prestataires manipulent, ni dependre d'un reseau
invite qui filtre le SMTP. Le back-office local ne connait donc qu'une URL et
un token ; c'est le back-office distant, deja configure et deja reconnu par
les fournisseurs de messagerie, qui expedie reellement.

Ce que la borne ne perd pas : le message est d'abord ecrit dans l'outbox
locale. Si le distant est injoignable, le visiteur n'attend pas -- le worker
retentera, et l'admin voit la file.

L'URL et le token vivent dans les reglages a chaud (`app_settings`), avec le
`.env` en valeur de repli : brancher une borne sur un autre relais se fait
depuis le back-office, sans redemarrer le conteneur.
"""

from __future__ import annotations

import base64
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.services.settings_store import get_setting

from . import Outgoing, PermanentSendError, SendError

# 401/403 : token invalide ou revoque. 413 : message trop gros. 422 : charge
# utile refusee. Retenter ne changerait rien. 429 (quota) et 5xx, si.
_PERMANENT = {401, 403, 413, 422}


def relay_url(db: Session) -> str:
    return str(get_setting(db, "mail_relay_url", settings.mail_relay_url) or "").rstrip("/")


def relay_token(db: Session) -> str:
    return str(get_setting(db, "mail_relay_token", settings.mail_relay_token) or "")


def check_url(url: str) -> None:
    """Un token qui voyage en clair sur le wifi d'un salon est un token perdu."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise PermanentSendError(f"URL de relais invalide : {url!r}")
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme == "http" and not local and not settings.mail_relay_allow_insecure:
        raise PermanentSendError(
            "relais en http:// refuse — le token transiterait en clair. "
            "Utiliser https://, ou MAIL_RELAY_ALLOW_INSECURE=true si le lien "
            "est deja protege (VPN, reseau prive)."
        )


def _request(db: Session, method: str, path: str, json: dict | None = None) -> httpx.Response:
    url, token = relay_url(db), relay_token(db)
    if not url or not token:
        raise PermanentSendError("Relais non configure (URL et token requis)")
    check_url(url)
    try:
        return httpx.request(
            method,
            f"{url}{path}",
            json=json,
            headers={"Authorization": f"Bearer {token}"},
            timeout=settings.mail_relay_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise SendError(f"relais {url} injoignable : {exc}") from exc


def _raise_for(response: httpx.Response) -> None:
    detail = response.text[:500]
    try:
        detail = response.json().get("detail", detail)
    except ValueError:
        pass
    if response.status_code in _PERMANENT:
        raise PermanentSendError(f"relais : {detail}")
    raise SendError(f"relais HTTP {response.status_code} : {detail}")


def send(db: Session, message: Outgoing) -> None:
    payload: dict = {
        # L'identifiant de NOTRE ligne d'outbox : c'est lui qui rend le
        # renvoi apres un timeout inoffensif cote distant.
        "message_id": message.message_id,
        "to": message.to_email,
        "subject": message.subject,
        "body_html": message.body_html,
    }
    if message.attachment:
        payload["attachment"] = {
            "filename": message.attachment.filename,
            "content_type": message.attachment.content_type,
            "content_b64": base64.b64encode(message.attachment.content).decode(),
        }

    response = _request(db, "POST", "/api/relay/send", json=payload)
    if not response.is_success:
        _raise_for(response)


def ping(db: Session) -> dict:
    """Verifie la liaison depuis le back-office local. Utilise par l'admin."""
    response = _request(db, "GET", "/api/relay/ping")
    if not response.is_success:
        _raise_for(response)
    return response.json()
