"""Envoi SMTP : boite OVH, relais Brevo, ou n'importe quel serveur classique.

OVH : `ssl0.ovh.net`, port 587 en STARTTLS ou 465 en SSL direct, et le nom
d'utilisateur est l'adresse complete de la boite.
Brevo (relais SMTP) : `smtp-relay.brevo.com`, port 587, l'identifiant du
compte en utilisateur et une cle SMTP en mot de passe.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import settings

from . import Outgoing, PermanentSendError, SendError


def build_message(message: Outgoing) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = message.subject
    msg["From"] = f"{settings.mail_from_name} <{settings.mail_from}>"
    msg["To"] = message.to_email
    msg.set_content(
        "Cet email necessite un client compatible HTML.", subtype="plain", charset="utf-8"
    )
    msg.add_alternative(message.body_html, subtype="html", charset="utf-8")
    if message.attachment:
        msg.add_attachment(
            message.attachment.content,
            maintype=message.attachment.maintype,
            subtype=message.attachment.subtype,
            filename=message.attachment.filename,
        )
    return msg


def send(message: Outgoing) -> None:
    if not settings.smtp_host:
        raise PermanentSendError(
            "SMTP_HOST non configure (ou basculer MAIL_TRANSPORT sur brevo / relay)"
        )

    msg = build_message(message)
    try:
        if settings.smtp_use_ssl:
            client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20)
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        with client as smtp:
            if not settings.smtp_use_ssl and settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        # Des identifiants refuses le resteront : inutile de retenter.
        raise PermanentSendError(f"authentification SMTP refusee : {exc}") from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise PermanentSendError(f"destinataire refuse : {message.to_email}") from exc
    except OSError as exc:
        # Reseau coupe sur le stand : c'est exactement le cas que la file
        # d'attente est faite pour absorber.
        raise SendError(f"SMTP {settings.smtp_host}:{settings.smtp_port} injoignable : {exc}") from exc
