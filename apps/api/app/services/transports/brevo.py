"""Envoi par l'API HTTP de Brevo (transactional email v3).

Interet par rapport au relais SMTP de Brevo : tout passe en HTTPS sur le 443.
Beaucoup de reseaux de salon laissent passer le web et filtrent le 587 ; ce
transport evite d'avoir a negocier une ouverture de port avec l'exposant.
"""

from __future__ import annotations

import base64

import httpx

from app.config import settings

from . import Outgoing, PermanentSendError, SendError

# 401/403 : mauvaise cle. 400 : charge utile refusee. Rien de tout cela ne
# s'arrangera au dixieme essai. 429 et 5xx, si.
_PERMANENT = {400, 401, 403}


def build_payload(message: Outgoing) -> dict:
    payload = {
        "sender": {"name": settings.mail_from_name, "email": settings.mail_from},
        "to": [{"email": message.to_email}],
        "subject": message.subject,
        "htmlContent": message.body_html,
    }
    if message.attachment:
        payload["attachment"] = [
            {
                "name": message.attachment.filename,
                "content": base64.b64encode(message.attachment.content).decode(),
            }
        ]
    return payload


def send(message: Outgoing) -> None:
    if not settings.brevo_api_key:
        raise PermanentSendError("BREVO_API_KEY non configuree")

    try:
        response = httpx.post(
            settings.brevo_api_url,
            json=build_payload(message),
            headers={
                "api-key": settings.brevo_api_key,
                "accept": "application/json",
                "content-type": "application/json",
            },
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise SendError(f"Brevo injoignable : {exc}") from exc

    if response.is_success:
        return
    detail = response.text[:500]
    if response.status_code in _PERMANENT:
        raise PermanentSendError(f"Brevo a refuse l'envoi ({response.status_code}) : {detail}")
    raise SendError(f"Brevo HTTP {response.status_code} : {detail}")
