"""Les differentes facons de faire sortir un email.

Trois, interchangeables par configuration :

* `smtp`  -- une boite OVH (`ssl0.ovh.net`) ou le relais SMTP de Brevo ;
* `brevo` -- l'API HTTP de Brevo, qui sort en 443 la ou le 587 est parfois
  filtre par le reseau d'un salon ;
* `relay` -- on n'expedie pas soi-meme, on confie le message a un autre
  back-office AIXAM qui, lui, a une vraie configuration d'envoi.

Le worker d'outbox ne connait que ce module : changer de transport ne touche
ni la file, ni le backoff, ni l'admin.
"""

from __future__ import annotations

import html
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path


class SendError(RuntimeError):
    """Echec d'envoi. Le worker retentera."""


class PermanentSendError(SendError):
    """Echec dont on sait qu'il se reproduira a l'identique.

    Token refuse, adresse invalide, configuration absente : retenter huit
    fois avec un backoff n'apporte rien, sinon du bruit dans la file. Le
    worker marque directement en echec, l'admin voit pourquoi.
    """


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes
    content_type: str

    @property
    def maintype(self) -> str:
        return self.content_type.partition("/")[0]

    @property
    def subtype(self) -> str:
        return self.content_type.partition("/")[2]


@dataclass(frozen=True)
class Outgoing:
    """Un email pret a partir, independant de l'ORM.

    Volontairement mono-destinataire : c'est ce qu'envoie la borne, et c'est
    aussi ce qui rend le relais inexploitable pour du mailing de masse.
    """

    message_id: str
    to_email: str
    subject: str
    body_html: str
    attachment: Attachment | None = None

    @classmethod
    def from_outbox(cls, item) -> "Outgoing":
        return cls(
            message_id=str(item.id),
            to_email=item.to_email,
            subject=item.subject,
            body_html=item.body_html,
            attachment=load_attachment(item.attachment_path),
        )


def load_attachment(path: str | None) -> Attachment | None:
    if not path:
        return None
    file = Path(path)
    if not file.is_file():
        # Le rendu a pu etre purge : on envoie le mail sans la piece plutot
        # que de bloquer la file pour un fichier qui ne reviendra pas.
        return None
    ctype, _ = mimetypes.guess_type(file.name)
    return Attachment(
        filename=file.name,
        content=file.read_bytes(),
        content_type=ctype or "application/octet-stream",
    )


# --- Version texte ---
#
# Un corps texte reduit a « cet email necessite un client HTML » est un signal
# de spam a lui seul : les filtres comparent les deux versions et se mefient
# d'un message qui n'en propose qu'une vraie. On derive donc le texte du HTML,
# plutot que de le bacler.

# Un bloc ferme separe des paragraphes, une <br> une simple ligne : sans
# cette distinction, un HTML ecrit sans retours a la ligne donnait un pave.
_PARAGRAPHES = re.compile(r"(?i)</(p|div|tr|h[1-6])>")
_LIGNES = re.compile(r"(?i)<br\s*/?>")
_INVISIBLE = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_BALISES = re.compile(r"<[^>]+>")
_LIGNES_VIDES = re.compile(r"\n{3,}")


def html_vers_texte(html_source: str) -> str:
    """Une version texte lisible du corps HTML."""
    texte = _INVISIBLE.sub("", html_source)
    texte = _PARAGRAPHES.sub("\n\n", texte)
    texte = _LIGNES.sub("\n", texte)
    texte = _BALISES.sub("", texte)
    texte = html.unescape(texte)
    texte = "\n".join(ligne.strip() for ligne in texte.splitlines())
    return _LIGNES_VIDES.sub("\n\n", texte).strip() + "\n"
