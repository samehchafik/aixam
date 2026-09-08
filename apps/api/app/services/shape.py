"""Masque de la planche de bord.

Un rectangle tres allonge aux angles arrondis, avec une encoche centrale en
bas (l'emplacement des commandes). Meme geometrie que `src/skin/shape.ts`
cote front : les deux lisent `media/base/shape.json`.
"""

from __future__ import annotations

from PIL import Image, ImageDraw


def build_mask(shape: dict, width: int, height: int) -> Image.Image:
    """Masque L (255 = visible) aux dimensions demandees."""
    sx, sy = width / shape["width"], height / shape["height"]
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=int(shape["cornerRadius"] * sx), fill=255)

    notch = shape["notch"]
    nw, nh, nr = notch["width"] * sx, notch["height"] * sy, notch["radius"] * sx
    left = (width - nw) / 2
    top = height - nh
    # L'encoche est ouverte vers le bas : on la dessine plus haute que la
    # planche pour que ses angles inferieurs restent droits.
    draw.rounded_rectangle((left, top, left + nw, height + nr * 2), radius=int(nr), fill=0)
    return mask
