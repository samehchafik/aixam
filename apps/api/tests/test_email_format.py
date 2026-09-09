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
from app.services.transports import Outgoing, html_vers_texte, load_attachment
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
jpeg = render_design({"layers": [Layer(type="background", assetId="smileys").model_dump(exclude_none=True)]})
avec = build_message(Outgoing(message_id="y", to_email="v@example.com", subject="Votre creation",
                              body_html="<p>Voici votre skin</p>",
                              attachment=load_attachment(str(jpeg))))
check("structure multipart/mixed", avec.get_content_type() == "multipart/mixed", avec.get_content_type())
jointes = list(avec.iter_attachments())
check("une piece jointe", len(jointes) == 1, len(jointes))
check("en image/jpeg", jointes[0].get_content_type() == "image/jpeg")
check("un JPEG valide", jointes[0].get_payload(decode=True)[:3] == b"\xff\xd8\xff")
check("le corps garde ses deux versions",
      {"text/plain", "text/html"} <= {p.get_content_type() for p in avec.walk() if not p.is_multipart()})

print("\n[4] La conversion HTML -> texte")
check("les sauts de ligne survivent",
      html_vers_texte("<p>un</p><p>deux</p>").splitlines()[:3] == ["un", "", "deux"],
      html_vers_texte("<p>un</p><p>deux</p>").splitlines()[:3])
check("les entites sont decodees", "l'ete" in html_vers_texte("<p>l&#39;ete</p>"))
check("styles et scripts disparaissent",
      "rouge" not in html_vers_texte("<style>.a{color:rouge}</style><p>bonjour</p>"))

sys.exit(report())
