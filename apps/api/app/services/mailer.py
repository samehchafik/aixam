"""Mise en file et envoi des emails.

Aucune requete HTTP n'envoie d'email en direct : on ecrit dans `email_outbox`
et le worker se debrouille. Une coupure reseau sur le stand ne bloque donc
jamais un visiteur devant la borne.

La facon dont l'email sort ensuite (SMTP OVH, API Brevo, ou relais vers un
autre back-office) est le seul choix configurable ici -- la file, le backoff
et l'admin sont identiques dans les trois cas. Voir `services/transports/`.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.config import settings
from app.models import EmailOutbox
from app.services.settings_store import get_setting
from app.services.transports import Outgoing, PermanentSendError, SendError
from app.services.transports import brevo as brevo_transport
from app.services.transports import relay as relay_transport
from app.services.transports import smtp as smtp_transport

TRANSPORTS = ("smtp", "brevo", "relay")

_TEMPLATES = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent.parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


def render_template(name: str, **context) -> str:
    return _TEMPLATES.get_template(name).render(**context)


def current_transport(db: Session) -> str:
    """Le reglage a chaud gagne sur le `.env` : on rebascule un stand sur le
    relais (ou sur son propre SMTP) sans redemarrer quoi que ce soit."""
    name = str(get_setting(db, "mail_transport", settings.mail_transport) or "smtp").lower()
    return name if name in TRANSPORTS else "smtp"


def queue_email(
    db: Session,
    *,
    to_email: str,
    subject: str,
    body_html: str,
    attachment_path: str | None = None,
) -> EmailOutbox:
    item = EmailOutbox(
        to_email=to_email,
        subject=subject,
        body_html=body_html,
        attachment_path=attachment_path,
    )
    db.add(item)
    db.flush()
    return item


def send_now(db: Session, item: EmailOutbox) -> None:
    """Envoi synchrone via le transport courant.

    Leve `SendError` -> le worker retentera avec backoff.
    Leve `PermanentSendError` -> le worker abandonne tout de suite.
    """
    message = Outgoing.from_outbox(item)
    transport = current_transport(db)
    if transport == "relay":
        relay_transport.send(db, message)
    elif transport == "brevo":
        brevo_transport.send(message)
    else:
        smtp_transport.send(message)


__all__ = [
    "PermanentSendError",
    "SendError",
    "TRANSPORTS",
    "current_transport",
    "queue_email",
    "render_template",
    "send_now",
]
