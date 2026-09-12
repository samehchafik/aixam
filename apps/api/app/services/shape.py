"""Masque de la planche de bord.

La silhouette vient du gabarit du studio (`Gabarit_skin.svg`), conservee en
points dans `media/base/shape.json` : une polyligne fermee de plus de 250
sommets. La planche n'est pas un rectangle arrondi, ses bords ondulent
legerement -- on ne la reconstruit donc pas, on la trace.

`src/skin/shape.ts` cote borne lit exactement les memes points.
"""

from __future__ import annotations

from PIL import Image, ImageDraw


def build_mask(shape: dict, width: int, height: int) -> Image.Image:
    """Masque L (255 = visible) aux dimensions demandees."""
    sx = width / shape["width"]
    sy = height / shape["height"]
    points = [(x * sx, y * sy) for x, y in shape["points"]]

    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask
