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
    CID_VISUEL,
    Outgoing,
    PermanentSendError,
    SendError,
    html_vers_texte,
    images_du_gabarit,
    images_en_texte,
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
    domaine = settings.mail_from.rpartition("@")[2] or None
    corps = message.body_html
    # Les images du corps : (identifiant, octets, type), chacune sa partie dans
    # le multipart/related.
    liees: list[tuple[str, bytes, str]] = []

    def lier(marqueur: str, contenu: bytes, subtype: str = "png") -> None:
        nonlocal corps
        cid = make_msgid(domain=domaine)
        corps = corps.replace(f"cid:{marqueur}", f"cid:{cid[1:-1]}")
        liees.append((cid, contenu, subtype))

    jointe = message.attachment
    if jointe and f"cid:{CID_VISUEL}" in corps:
        # Le visuel de l'ecran 7, compose a partir du skin joint. S'il ne peut
        # pas l'etre, c'est le skin lui-meme qui s'affiche.
        try:
            from app.services.visuel_mail import visuel

            lier(CID_VISUEL, visuel(jointe.content))
        except Exception:
            lier(CID_VISUEL, jointe.content, jointe.subtype)
    if jointe and f"cid:{CID_CREATION}" in corps:
        # Le skin lui-meme dans le corps (gabarit d'avant le visuel).
        lier(CID_CREATION, jointe.content, jointe.subtype)
    # Rien a lier : la balise designerait une partie absente, et le visiteur
    # verrait un cadre casse a la place de sa creation.
    corps = retirer_image_liee(corps)
    # Les pictos du gabarit. Celui que ce back-office n'a pas devient son
    # texte alternatif, toujours cliquable.
    for nom, contenu in images_du_gabarit(corps).items():
        lier(nom, contenu)
    corps = images_en_texte(corps)

    msg.set_content(html_vers_texte(corps), subtype="plain", charset="utf-8")
    msg.add_alternative(corps, subtype="html", charset="utf-8")
    # Apres le premier ajout, la partie HTML est devenue un multipart/related :
    # les suivantes s'y rangent, a cote d'elle. Sans nom de fichier ni
    # disposition « attachment » : ces images n'existent que pour le corps,
    # elles n'ont pas a paraitre dans la liste des fichiers.
    for cid, contenu, subtype in liees:
        msg.get_payload()[-1].add_related(contenu, maintype="image", subtype=subtype, cid=cid, disposition="inline")

    if jointe:
        # La creation elle-meme, en piece jointe au premier niveau : c'est la
        # que les messageries la listent de facon sure, enregistrable.
        #
        # Quand le corps montre la creation, c'est une seconde partie, voisine
        # du HTML dans le multipart/related : les clients ne resolvent un
        # `cid:` qu'entre voisins, et ne listent sur qu'une piece du premier
        # niveau. Une partie pour montrer, une partie pour garder.
        msg.add_attachment(
            jointe.content,
            maintype=jointe.maintype,
            subtype=jointe.subtype,
            filename=jointe.filename,
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
