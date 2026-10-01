"""La forme des emails, celle qui decide du dossier spam.

Ces defauts ne se voient jamais a l'ecran : le message part, le serveur SMTP
l'accepte, et il atterrit en indesirable chez le visiteur. Seul un examen des
en-tetes et des parties MIME les revele.

    ../../.venv/bin/python tests/test_email_format.py     (depuis apps/api)
"""

import io
import os
import re
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


print("\n[7] Le skin en piece jointe, le visuel de l'ecran 7 dans le corps")
# `cid:` n'est pas une adresse : elle designe une partie de CE message. L'image
# est donc dans l'email, affichee hors ligne, sans rien demander a un serveur.
# Un <img src="https://..."> serait bloque par defaut par la plupart des
# messageries, expirerait avec le serveur, et dirait a qui l'a envoye quand le
# visiteur l'a ouvert.
from PIL import Image
from app.services.transports import CID_VISUEL

vraie = render_template("creation.html", first_name="Camille", base_url="https://exemple.fr")
check("le gabarit pose le marqueur du visuel", f"cid:{CID_VISUEL}" in vraie, vraie[:200])
liee = build_message(Outgoing(message_id="z", to_email="v@example.com",
                              subject="Votre creation", body_html=vraie,
                              attachment=load_attachment(str(skin))))
check("structure multipart/mixed", liee.get_content_type() == "multipart/mixed",
      liee.get_content_type())
check("le corps et ses images forment un multipart/related",
      "multipart/related" in [p.get_content_type() for p in liee.walk()])
html_part = next(p for p in liee.walk() if p.get_content_type() == "text/html")
jointe = next(p for p in liee.walk() if p.get_content_disposition() == "attachment")
check("une seule piece jointe listee : le skin",
      [p.get_filename() for p in liee.iter_attachments()] == [skin.name],
      [p.get_filename() for p in liee.iter_attachments()])
check("la piece jointe porte les octets du skin", jointe.get_payload(decode=True) == skin.read_bytes())
lies = {p["Content-ID"][1:-1]: p for p in liee.walk() if p["Content-ID"]}
html_liee = html_part.get_content()
cites = re.findall(r'src="cid:([^"]+)"', html_liee)
# Le piege classique : une balise qui cite un identifiant que la partie ne
# porte pas. L'email est bien forme, et le visiteur voit un cadre casse.
check("chaque image citee designe une partie du message", cites and all(c in lies for c in cites), cites)
check("le marqueur a bien ete remplace", f"cid:{CID_VISUEL}" not in html_liee)
visuel_part = lies[cites[0]]
visuel_img = Image.open(io.BytesIO(visuel_part.get_payload(decode=True)))
check("la premiere image du corps est le visuel 16/9", visuel_img.width / visuel_img.height == 16 / 9,
      visuel_img.size)
check("le visuel ne se propose pas a enregistrer",
      visuel_part.get_filename() is None and visuel_part.get_content_disposition() == "inline")
check("aucune image chargee par http", 'src="http' not in html_liee)
check("le texte seul ne garde aucune balise",
      "<" not in next(p.get_content() for p in liee.walk() if p.get_content_type() == "text/plain"))

# Les gabarits d'avant le visuel (des lignes encore en file) citent le skin
# lui-meme : DEUX parties pour la meme image. Les deux economies ont ete
# essayees en vrai, chacune a manque une moitie : dans le seul
# multipart/related elle s'affichait sans etre enregistrable ; en seule piece
# jointe citee par un cid:, l'inverse.
ancien = build_message(Outgoing(message_id="z2", to_email="v@example.com", subject="s",
                                body_html=f'<p>x</p><img src="cid:{CID_CREATION}" alt="c">',
                                attachment=load_attachment(str(skin))))
copies = [p for p in ancien.walk() if p.get_content_type() == "image/png"
          and p.get_payload(decode=True) == skin.read_bytes()]
check("ancien gabarit : le skin montre et garde", sorted(p.get_content_disposition() for p in copies)
      == ["attachment", "inline"], [p.get_content_disposition() for p in copies])

print("\n[8] Pas d'image liee sans piece a lier")
# Sans piece jointe, la balise designerait une partie absente. Le transport la
# retire plutot que de montrer un cadre casse.
seul = build_message(Outgoing(message_id="w", to_email="v@example.com",
                              subject="Votre creation", body_html=vraie))
html_seul = next(p.get_content() for p in seul.walk() if p.get_content_type() == "text/html")
lies_seul = {p["Content-ID"][1:-1] for p in seul.walk() if p["Content-ID"]}
check("la balise est retiree", "tableau de bord" not in html_seul)
check("toute image restante designe une partie du message",
      all(c in lies_seul for c in re.findall(r'src="cid:([^"]+)"', html_seul)))
# L'API Brevo prend des pieces jointes, pas des images liees au corps.
check("Brevo retire aussi la balise",
      "cid:" not in build_payload(Outgoing(message_id="v", to_email="v@example.com",
                                           subject="s", body_html=vraie))["htmlContent"])
check("retirer_image_liee ne touche pas au reste",
      retirer_image_liee("<p>avant</p><img src=\'cid:creation\'><p>apres</p>")
      == "<p>avant</p><p>apres</p>")


print("\n[9] Le logo et les reseaux, en bas")
# Le logo mene au site ; Instagram, Facebook et TikTok. Dans le message, comme
# le visuel, et cliquables.
check("cinq images liees : le visuel, le logo et trois pictos", len(cites) == 5 and len(lies) == 5,
      (cites, list(lies)))
for adresse in ("https://www.instagram.com/aixam_officiel/", "https://www.facebook.com/aixam",
                "https://www.tiktok.com/@aixam_officiel", "https://www.aixam.com/"):
    check(f"lien {adresse}", f'href="{adresse}"' in html_liee)
texte_liee = next(p.get_content() for p in liee.walk() if p.get_content_type() == "text/plain")
check("la version texte garde le nom et l'adresse",
      "Instagram : https://www.instagram.com/aixam_officiel/" in texte_liee, texte_liee[-300:])
brevo = build_payload(Outgoing(message_id="u", to_email="v@example.com", subject="s", body_html=vraie))["htmlContent"]
check("Brevo : plus aucune image liee", "cid:" not in brevo)
check("Brevo : les pictos deviennent leur nom, toujours cliquable",
      re.search(r'href="https://www.tiktok.com/@aixam_officiel"[^>]*>\s*TikTok\s*</a>', brevo) is not None)
# Un back-office qui n'aurait pas les fichiers (relais pas a jour) : le texte
# alternatif plutot qu'un cadre casse.
import app.services.transports as transports
vrai_dossier = transports.IMAGES_GABARIT
transports.IMAGES_GABARIT = Path(tempfile.mkdtemp())
sans = build_message(Outgoing(message_id="t", to_email="v@example.com", subject="s", body_html=vraie,
                              attachment=load_attachment(str(skin))))
transports.IMAGES_GABARIT = vrai_dossier
html_sans = next(p.get_content() for p in sans.walk() if p.get_content_type() == "text/html")
check("picto absent : son nom a la place", ">Instagram" in html_sans.replace("\n", "").replace(" ", "")
      and "cid:instagram" not in html_sans)

print("\n[10] Le visuel de l'ecran 7")
from app.services.visuel_mail import LARGEUR, MOCKUP, composer
rouge = render_design({"layers": [Layer(type="background", hex="#FF0000").model_dump(exclude_none=True)]})
visuel = Image.open(io.BytesIO(composer(rouge.read_bytes()))).convert("RGB")
check("un PNG 16/9 a la largeur prevue", visuel.size == (LARGEUR, LARGEUR * 9 // 16), visuel.size)
k = LARGEUR / 1920
r, g, b = visuel.getpixel((round(1400 * k), round(500 * k)))
check("la creation est posee sur la planche", r > 120 and r > 2 * g and r > 2 * b, (r, g, b))
photo = Image.open(MOCKUP / "decor.png").convert("RGB").resize(visuel.size, Image.LANCZOS)
ciel = (round(1400 * k), round(250 * k))
check("hors du masque, la photo telle quelle", visuel.getpixel(ciel) == photo.getpixel(ciel),
      (visuel.getpixel(ciel), photo.getpixel(ciel)))


sys.exit(report())
