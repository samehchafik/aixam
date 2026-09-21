"""La forme des emails, celle qui decide du dossier spam.

Ces defauts ne se voient jamais a l'ecran : le message part, le serveur SMTP
l'accepte, et il atterrit en indesirable chez le visiteur. Seul un examen des
en-tetes et des parties MIME les revele.

    ../../.venv/bin/python tests/test_email_format.py     (depuis apps/api)
"""

import os
import sys
import tempfile
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import API_DIR, check, on_path, report

os.environ.update(
    DATABASE_URL="postgresql+psycopg://x@127.0.0.1/x",
    MEDIA_DIR=str(API_DIR / "media"), STATIC_DIR=tempfile.mkdtemp(),
    MAIL_FROM="noreply@exemple.fr", MAIL_FROM_NAME="AIXAM",
    MAIL_REPLY_TO="contact@exemple.fr",
)
on_path()

from app.services.mailer import render_template
from app.services.transports import (
    CID_CREATION,
    Outgoing,
    SendError,
    html_vers_texte,
    load_attachment,
    retirer_image_liee,
)
from app.services.transports.brevo import build_payload
from app.services.transports.smtp import build_message
from app.services.renderer import render_design
from app.schemas import Layer

corps = render_template("verification.html", first_name="Camille", code="481902")
msg = build_message(Outgoing(message_id="x", to_email="visiteur@example.com",
                             subject="Votre code AIXAM", body_html=corps))

print("\n[1] Les en-tetes que les filtres reclament")
# Leur absence est sanctionnee telle quelle (MISSING_DATE, MISSING_MID) et
# Python ne les ajoute pas : ni EmailMessage, ni smtplib.
for entete in ("From", "To", "Subject", "Date", "Message-ID", "MIME-Version", "Reply-To"):
    check(f"{entete} present", msg[entete] is not None, "ABSENT")
check("Date analysable", parsedate_to_datetime(msg["Date"]) is not None)
check("Message-ID porte le domaine de l'expediteur",
      msg["Message-ID"].rstrip(">").endswith("@exemple.fr"), msg["Message-ID"])

print("\n[2] Deux versions reelles, pas une coquille")
parties = {p.get_content_type() for p in msg.walk() if not p.is_multipart()}
check("texte et HTML", {"text/plain", "text/html"} <= parties, parties)
texte = next(p.get_content() for p in msg.walk() if p.get_content_type() == "text/plain")
check("le texte porte le code", "481902" in texte, texte[:60])
check("le texte porte le prenom", "Camille" in texte)
check("aucune balise residuelle", "<" not in texte and "&nbsp;" not in texte)
# Un texte trop court face au HTML trahit la version bidon d'origine.
check("le texte n'est pas une coquille", len(texte.split()) > 25, len(texte.split()))

print("\n[3] La creation voyage en piece jointe")
skin = render_design({"layers": [Layer(type="background", assetId="smileys").model_dump(exclude_none=True)]})
avec = build_message(Outgoing(message_id="y", to_email="v@example.com", subject="Votre creation",
                              body_html="<p>Voici votre skin</p>",
                              attachment=load_attachment(str(skin))))
check("structure multipart/mixed", avec.get_content_type() == "multipart/mixed", avec.get_content_type())
jointes = list(avec.iter_attachments())
check("une piece jointe", len(jointes) == 1, len(jointes))
# PNG et non JPEG : le skin part en fabrication, une compression avec perte
# laisserait des artefacts sur ses aplats et son texte.
check("en image/png", jointes[0].get_content_type() == "image/png",
      jointes[0].get_content_type())
check("un PNG valide", jointes[0].get_payload(decode=True)[:8] == b"\x89PNG\r\n\x1a\n")
check("le corps garde ses deux versions",
      {"text/plain", "text/html"} <= {p.get_content_type() for p in avec.walk() if not p.is_multipart()})

print("\n[4] La conversion HTML -> texte")
check("les sauts de ligne survivent",
      html_vers_texte("<p>un</p><p>deux</p>").splitlines()[:3] == ["un", "", "deux"],
      html_vers_texte("<p>un</p><p>deux</p>").splitlines()[:3])
check("les entites sont decodees", "l'ete" in html_vers_texte("<p>l&#39;ete</p>"))
check("styles et scripts disparaissent",
      "rouge" not in html_vers_texte("<style>.a{color:rouge}</style><p>bonjour</p>"))

print("\n[5] L'image voyage en octets, jamais en lien")
# L'image doit etre DANS le message. Un <img src="https://..."> serait bloque
# par defaut par la plupart des messageries, expirerait avec le serveur, et
# dirait a qui l'ouvre quand il l'a ouvert. Le visiteur doit pouvoir garder sa
# creation hors ligne, des reception.
corps = "".join(
    p.get_content() for p in avec.walk()
    if p.get_content_type() in ("text/plain", "text/html")
)
check("aucun lien http vers l'image", "http" not in corps, corps[:120])
check("les octets du PNG sont bien dans le message",
      len(jointes[0].get_payload(decode=True)) > 1000,
      len(jointes[0].get_payload(decode=True)))

print("\n[6] Une piece jointe absente ne part pas en silence")
# Le corps annonce « votre creation est en piece jointe » : l'envoyer sans
# elle est une promesse vide, et le visiteur n'a aucun moyen de le signaler.
# C'est arrive -- l'API ecrivait la piece dans un dossier que le worker ne
# montait pas. La ligne doit echouer, visible dans l'ecran Emails.
try:
    load_attachment("media/renders/ce-fichier-n-existe-pas.png")
    check("un chemin sans fichier leve", False, "rien n'a ete leve")
except SendError as exc:
    check("un chemin sans fichier leve", True)
    check("le message dit quoi chercher", "introuvable" in str(exc), str(exc))
check("pas de chemin, pas de piece : ce cas reste normal",
      load_attachment(None) is None)


print("\n[7] La creation s'affiche dans le corps du message")
# `cid:` n'est pas une adresse : elle designe une partie de CE message. L'image
# est donc dans l'email, affichee hors ligne, sans rien demander a un serveur.
# Un <img src="https://..."> serait bloque par defaut par la plupart des
# messageries, expirerait avec le serveur, et dirait a qui l'a envoye quand le
# visiteur l'a ouvert.
vraie = render_template("creation.html", first_name="Camille", base_url="https://exemple.fr")
check("le gabarit pose le marqueur", f"cid:{CID_CREATION}" in vraie, vraie[:200])
liee = build_message(Outgoing(message_id="z", to_email="v@example.com",
                              subject="Votre creation", body_html=vraie,
                              attachment=load_attachment(str(skin))))

# DEUX parties pour la meme image. Les deux economies ont ete essayees en
# vrai, chacune a manque une moitie : dans le seul multipart/related elle
# s'affichait sans etre enregistrable ; en seule piece jointe citee par un
# cid:, l'inverse. Les clients ne resolvent le lien qu'entre voisins d'un
# related, et ne listent de facon sure qu'une piece du premier niveau.
check("structure multipart/mixed", liee.get_content_type() == "multipart/mixed",
      liee.get_content_type())
check("le corps et l'image liee forment un multipart/related",
      "multipart/related" in [p.get_content_type() for p in liee.walk()])
html_part = next(p for p in liee.walk() if p.get_content_type() == "text/html")
images = [p for p in liee.walk() if p.get_content_type() == "image/png"]
check("deux parties image : une pour montrer, une pour garder", len(images) == 2,
      [p.get_content_disposition() for p in images])
image = next(p for p in images if p["Content-ID"])
jointe = next(p for p in images if p.get_content_disposition() == "attachment")

# Une seule doit paraitre dans la liste des fichiers : celle qui n'existe que
# pour le <img> n'a ni nom ni disposition « attachment ».
check("une seule piece jointe listee",
      [p.get_filename() for p in liee.iter_attachments()] == [skin.name],
      [p.get_filename() for p in liee.iter_attachments()])
check("la copie du corps ne se propose pas a enregistrer",
      image.get_filename() is None and image.get_content_disposition() == "inline",
      (image.get_filename(), image.get_content_disposition()))
check("les deux portent bien les memes octets",
      image.get_payload(decode=True) == jointe.get_payload(decode=True))

# Le piege classique : une balise qui cite un identifiant que la partie ne
# porte pas. L'email est bien forme, et le visiteur voit un cadre casse.
check("l'image porte un Content-ID", image["Content-ID"] is not None)
check("le HTML cite exactement cet identifiant",
      f"cid:{image['Content-ID'][1:-1]}" in html_part.get_content(),
      (image["Content-ID"], html_part.get_content()[-300:]))
check("le marqueur a bien ete remplace",
      f"cid:{CID_CREATION}" not in html_part.get_content())
check("aucun lien http dans le corps", "http" not in html_part.get_content())

check("la piece jointe porte le nom du fichier", jointe.get_filename() == skin.name,
      jointe.get_filename())
check("le texte seul ne garde aucune balise",
      "<" not in next(p.get_content() for p in liee.walk() if p.get_content_type() == "text/plain"))

print("\n[8] Pas d'image liee sans piece a lier")
# Sans piece jointe, la balise designerait une partie absente. Le transport la
# retire plutot que de montrer un cadre casse.
seul = build_message(Outgoing(message_id="w", to_email="v@example.com",
                              subject="Votre creation", body_html=vraie))
check("la balise est retiree", "cid:" not in next(
    p.get_content() for p in seul.walk() if p.get_content_type() == "text/html"))
# L'API Brevo prend des pieces jointes, pas des images liees au corps.
check("Brevo retire aussi la balise",
      "cid:" not in build_payload(Outgoing(message_id="v", to_email="v@example.com",
                                           subject="s", body_html=vraie))["htmlContent"])
check("retirer_image_liee ne touche pas au reste",
      retirer_image_liee("<p>avant</p><img src=\'cid:creation\'><p>apres</p>")
      == "<p>avant</p><p>apres</p>")


sys.exit(report())
