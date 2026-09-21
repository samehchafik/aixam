"""Envoi SMTP : boite OVH, relais Brevo, ou n'importe quel serveur classique.

OVH : `ssl0.ovh.net`, port 587 en STARTTLS ou 465 en SSL direct, et le nom
d'utilisateur est l'adresse complete de la boite.
Brevo (relais SMTP) : `smtp-relay.brevo.com`, port 587, l'identifiant du
compte en utilisateur et une cle SMTP en mot de passe.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from datetime import datetime, timezone

from app.config import settings

from . import (
    CID_CREATION,
    Outgoing,
    PermanentSendError,
    SendError,
    html_vers_texte,
    retirer_image_liee,
)


def build_message(message: Outgoing) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = message.subject
    msg["From"] = f"{settings.mail_from_name} <{settings.mail_from}>"
    msg["To"] = message.to_email
    # Date et Message-ID sont exiges par la RFC 5322 et leur absence est
    # sanctionnee telle quelle par les filtres (MISSING_DATE, MISSING_MID).
    # Python ne les ajoute pas, et smtplib non plus : certains serveurs les
    # rattrapent, l'API Brevo non. On ne compte donc sur personne.
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = make_msgid(domain=settings.mail_from.rpartition("@")[2] or None)
    if settings.mail_reply_to:
        msg["Reply-To"] = settings.mail_reply_to
    # L'identifiant de la partie image se fabrique ici, au moment ou la partie
    # existe. Le gabarit ne peut ecrire qu'un marqueur : il est rendu a la mise
    # en file, bien avant qu'on sache comment le message sera decoupe.
    corps = message.body_html
    lien = None
    if message.attachment and f"cid:{CID_CREATION}" in corps:
        lien = make_msgid(domain=settings.mail_from.rpartition("@")[2] or None)
        corps = corps.replace(f"cid:{CID_CREATION}", f"cid:{lien[1:-1]}")
    else:
        # Rien a lier : la balise designerait une partie absente, et le
        # visiteur verrait un cadre casse a la place de sa creation.
        corps = retirer_image_liee(corps)

    msg.set_content(html_vers_texte(corps), subtype="plain", charset="utf-8")
    msg.add_alternative(corps, subtype="html", charset="utf-8")

    if message.attachment:
        if lien:
            # Attachee au HTML, pas au message : c'est ce qui fait un
            # multipart/related, et ce qui permet au <img> de la trouver.
            #
            # `disposition="attachment"` malgre l'affichage dans le corps :
            # une partie citee par un cid: est rendue de toute facon, et cette
            # disposition la garde en plus dans la liste des pieces jointes --
            # le visiteur doit pouvoir enregistrer sa creation, pas seulement
            # la regarder.
            msg.get_payload()[-1].add_related(
                message.attachment.content,
                maintype=message.attachment.maintype,
                subtype=message.attachment.subtype,
                cid=lien,
                filename=message.attachment.filename,
                disposition="attachment",
            )
        else:
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
