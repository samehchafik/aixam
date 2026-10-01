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


# Le gabarit ecrit <img src="cid:creation">. Ce n'est pas une adresse : `cid:`
# designe une partie du message lui-meme. L'image est donc DANS l'email, et
# s'affiche hors ligne, sans rien demander a un serveur -- la ou un lien http
# serait bloque par defaut par la plupart des messageries, expirerait avec le
# serveur, et dirait a qui l'a envoye quand le visiteur l'a ouvert.
#
# Le transport remplace ce marqueur par l'identifiant reel de la partie. Celui
# qui ne sait pas faire d'image liee retire la balise : mieux vaut pas d'image
# qu'un cadre casse, la piece jointe restant la.
CID_CREATION = "creation"
# Le visuel de l'ecran 7 -- la creation posee sur le tableau de bord. Il ne
# vient pas de la ligne d'outbox : le transport le compose a partir de la piece
# jointe, au moment d'envoyer (`visuel_mail.py`).
CID_VISUEL = "visuel"
_CREATION = (CID_CREATION, CID_VISUEL)

_IMAGE_LIEE = re.compile(
    r"""<img\b[^>]*\bsrc=["']cid:(?:""" + "|".join(_CREATION) + r""")["'][^>]*>""", re.IGNORECASE
)


def retirer_image_liee(html_source: str) -> str:
    return _IMAGE_LIEE.sub("", html_source)


# Les pictos du gabarit (reseaux sociaux) suivent le meme principe : le
# gabarit ecrit <img src="cid:instagram">, et le fichier est
# `templates/images/instagram.png`. Ils voyagent dans le message comme la
# creation, sans rien demander a un serveur -- y compris quand le message passe
# par le relais : celui-ci a les memes fichiers.
IMAGES_GABARIT = Path(__file__).resolve().parent.parent.parent / "templates" / "images"

_IMAGE_CID = re.compile(r"""<img\b[^>]*\bsrc=["']cid:([\w-]+)["'][^>]*>""", re.IGNORECASE)
_ALT = re.compile(r"""\balt=["']([^"']*)["']""", re.IGNORECASE)


def images_du_gabarit(html_source: str) -> dict[str, bytes]:
    """Les pictos que le corps cite et que ce back-office possede."""
    trouvees = {}
    for nom in dict.fromkeys(m.group(1) for m in _IMAGE_CID.finditer(html_source)):
        fichier = IMAGES_GABARIT / f"{nom}.png"
        if nom not in _CREATION and fichier.is_file():
            trouvees[nom] = fichier.read_bytes()
    return trouvees


def images_en_texte(html_source: str) -> str:
    """Remplace chaque image liee restante par son texte alternatif.

    Pour qui ne sait pas lier d'image (l'API Brevo), ou pour un picto absent
    de ce back-office : « Instagram » reste un lien cliquable, la ou une
    balise orpheline ferait un cadre casse.
    """
    return _IMAGE_CID.sub(lambda m: "" if m.group(1) in _CREATION else _alt(m), html_source)


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
    """Relit la piece jointe que la ligne d'outbox designe.

    Un chemin sans fichier leve, il ne s'ignore pas. On renvoyait le mail sans
    la piece, en se disant qu'un rendu purge ne devait pas bloquer la file --
    sauf que le corps du message annonce « votre creation est en piece
    jointe ». Le visiteur recevait donc une promesse vide, et rien nulle part
    n'en gardait trace : ni journal, ni ligne en echec, ni compteur.

    C'est ce silence qui a laissé passer un dossier que le worker ne voyait
    pas. Mieux vaut une ligne rouge dans l'ecran Emails : le worker retente
    avec son backoff, abandonne au bout de ses essais, et l'animateur voit
    laquelle des creations n'est pas partie.
    """
    if not path:
        return None
    file = Path(path)
    if not file.is_file():
        raise SendError(
            f"piece jointe introuvable : {path} "
            "(ce processus ne voit pas le dossier ou elle a ete ecrite ?)"
        )
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


# Un lien garde son adresse, sans quoi la version texte perdrait les liens
# vers les reseaux sociaux ; un picto, son nom.
_LIEN = re.compile(r"""(?is)<a\b[^>]*\bhref=["']([^"']+)["'][^>]*>(.*?)</a>""")
_CELLULE = re.compile(r"(?i)</td>")


_IMAGE = re.compile(r"(?i)<img\b[^>]*>")


def _alt(m: re.Match) -> str:
    alt = _ALT.search(m.group(0))
    return alt.group(1) if alt else ""


def _lien_en_texte(m: re.Match) -> str:
    adresse = m.group(1)
    libelle = _BALISES.sub("", _IMAGE.sub(_alt, m.group(2))).strip()
    return f"{libelle} : {adresse}" if libelle and libelle != adresse else adresse


def html_vers_texte(html_source: str) -> str:
    """Une version texte lisible du corps HTML."""
    texte = _INVISIBLE.sub("", html_source)
    texte = _LIEN.sub(_lien_en_texte, texte)
    texte = _CELLULE.sub("\n", texte)
    texte = _PARAGRAPHES.sub("\n\n", texte)
    texte = _LIGNES.sub("\n", texte)
    texte = _BALISES.sub("", texte)
    texte = html.unescape(texte)
    texte = "\n".join(ligne.strip() for ligne in texte.splitlines())
    return _LIGNES_VIDES.sub("\n\n", texte).strip() + "\n"
