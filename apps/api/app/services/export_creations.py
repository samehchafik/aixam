"""Le classeur Excel des creations : une ligne par creation, son auteur, le nom
de son fichier et son apercu dans la cellule.

XlsxWriter n'est importe qu'ici, au moment de l'export : sur une borne dont
l'environnement Python n'aurait pas ete mis a jour, l'API demarre quand meme,
et seul l'export refuse, en le disant.
"""

from __future__ import annotations

import io
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image

from app.services.renderer import skin_path

# Largeur de l'apercu dans la cellule, en pixels d'ecran. La planche est tres
# allongee (3218 x 325) : a cette largeur, elle fait une soixantaine de pixels
# de haut, assez pour la reconnaitre sans alourdir le classeur.
APERCU = 360
MARGE = 6
VERDICTS = {"pending": "En attente", "approved": "Validée", "rejected": "Rejetée"}


class ExportIndisponible(RuntimeError):
    """XlsxWriter manque : l'environnement Python n'est pas a jour."""


def _heure_de_paris():
    # Windows n'a pas de base de fuseaux : c'est le paquet tzdata (dans
    # requirements.txt) qui la fournit. S'il manque, on reste en UTC plutot que
    # de faire echouer l'export.
    try:
        return ZoneInfo("Europe/Paris"), "Date"
    except ZoneInfoNotFoundError:
        return None, "Date (UTC)"


def _apercu(nom: str | None) -> tuple[io.BytesIO, int] | None:
    """La vignette PNG d'une creation, et sa hauteur ; rien si le fichier manque."""
    if not nom:
        return None
    try:
        image = Image.open(skin_path(nom))
    except (ValueError, OSError):
        return None
    hauteur = max(1, round(image.height * APERCU / image.width))
    tampon = io.BytesIO()
    image.convert("RGBA").resize((APERCU, hauteur), Image.LANCZOS).save(tampon, "PNG", optimize=True)
    tampon.seek(0)
    return tampon, hauteur


# Le dossier des images, relatif a la racine du projet : c'est le meme sur le
# serveur, sur la borne et dans le conteneur -- le chemin absolu, lui, varie.
DOSSIER_IMAGES = "apps/api/media/renders/"


def classeur_creations(lignes, *, adresse_images: str = "", filtres: str = "") -> bytes:
    """`lignes` : des couples (Design, Visitor ou None), dans l'ordre voulu.

    `adresse_images` : l'URL du dossier des images en ligne (se terminant par
    « / »), qui rend chaque nom de fichier cliquable. `filtres` : ce que
    l'ecran affichait, rappele en tete de feuille.
    """
    try:
        import xlsxwriter
    except ImportError as exc:
        raise ExportIndisponible(
            "XlsxWriter manque : pip install -r apps/api/requirements.txt, puis redemarrer l'API"
        ) from exc

    lignes = list(lignes)
    fuseau, titre_date = _heure_de_paris()
    sortie = io.BytesIO()
    classeur = xlsxwriter.Workbook(sortie, {"in_memory": True})
    feuille = classeur.add_worksheet("Créations")

    entete = classeur.add_format({"bold": True, "bg_color": "#1F2847", "font_color": "#FFFFFF",
                                  "valign": "vcenter", "border": 1})
    titre = classeur.add_format({"bold": True, "font_size": 14, "font_color": "#1F2847"})
    note = classeur.add_format({"text_wrap": True, "valign": "top", "font_color": "#444444"})
    lien = classeur.add_format({"valign": "vcenter", "font_color": "#1A6FB0", "underline": 1})
    texte = classeur.add_format({"valign": "vcenter", "text_wrap": True})
    date = classeur.add_format({"valign": "vcenter", "num_format": "dd/mm/yyyy hh:mm"})

    colonnes = [
        ("Aperçu", APERCU / 7 + 2),
        ("Fichier", 40),
        ("Prénom", 16),
        ("Nom", 20),
        ("E-mail", 32),
        ("Code postal", 12),
        (titre_date, 17),
        ("Modération", 13),
    ]
    # En tete : ce que contient la feuille, et ou sont les images.
    maintenant = datetime.now(fuseau) if fuseau else datetime.now()
    feuille.merge_range(0, 0, 0, len(colonnes) - 1,
                        f"Créations EASY — export du {maintenant:%d/%m/%Y à %H:%M}", titre)
    dossier_windows = "C:\\aixam\\" + DOSSIER_IMAGES.replace("/", "\\")
    explication = (
        f"Une ligne par création ({len(lignes)}) : son aperçu, le nom de son fichier image, "
        "l'auteur (vide si ses données ont été effacées à sa demande), la date et la décision "
        "de modération." + (f" {filtres}." if filtres else "") + "\n"
        "Les fichiers images (PNG) sont sur la machine qui héberge le back-office, dans le dossier "
        f"« {DOSSIER_IMAGES} » du projet AIXAM (sur la borne du salon : {dossier_windows})."
        + (f" Ils sont aussi en ligne : {adresse_images}<nom du fichier> — un clic sur un nom "
           "de fichier l'ouvre." if adresse_images else "")
    )
    feuille.merge_range(1, 0, 1, len(colonnes) - 1, explication, note)
    feuille.set_row(1, 66)
    ENTETE = 3
    for i, (nom, largeur) in enumerate(colonnes):
        feuille.set_column(i, i, largeur)
        feuille.write(ENTETE, i, nom, entete)
    feuille.set_row(ENTETE, 22)
    feuille.freeze_panes(ENTETE + 1, 0)

    for n, (design, visiteur) in enumerate(lignes, start=ENTETE + 1):
        cree = design.created_at
        if fuseau and cree.tzinfo:
            cree = cree.astimezone(fuseau)
        if design.skin and adresse_images:
            feuille.write_url(n, 1, adresse_images + design.skin, lien, string=design.skin)
        else:
            feuille.write_string(n, 1, design.skin or "", texte)
        valeurs = [
            visiteur.first_name if visiteur else "",
            visiteur.last_name if visiteur else "",
            visiteur.email if visiteur else "",
            visiteur.postal_code if visiteur else "",
        ]
        for i, valeur in enumerate(valeurs, start=2):
            feuille.write_string(n, i, valeur, texte)
        feuille.write_datetime(n, 6, cree.replace(tzinfo=None) if isinstance(cree, datetime) else cree, date)
        feuille.write_string(n, 7, VERDICTS.get(design.moderation, design.moderation), texte)

        apercu = _apercu(design.skin)
        if apercu:
            image, hauteur = apercu
            # Hauteur de ligne en points : 3/4 de pixel.
            feuille.set_row(n, (hauteur + 2 * MARGE) * 0.75)
            feuille.insert_image(n, 0, design.skin, {
                "image_data": image, "x_offset": MARGE, "y_offset": MARGE, "object_position": 1,
            })
        else:
            feuille.set_row(n, 30)
            feuille.write_string(n, 0, "image absente", texte)

    feuille.autofilter(ENTETE, 0, ENTETE + max(1, len(lignes)), len(colonnes) - 1)
    classeur.close()
    return sortie.getvalue()
