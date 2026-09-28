"""Rend transparents le tour et l'encoche des creations deja rendues.

Jusqu'au 28 septembre 2026, le rendu peignait un fond bleu nuit autour de la
planche et dans l'encoche de la console. Pose sur la photo du tableau de bord,
ce fond faisait une bande sombre a droite de la console. Les nouveaux rendus
sont transparents la ; ceux d'avant se corrigent ici, une fois.

    docker compose run --rm api python -m app.tools.detourer_rendus --dry-run
    docker compose run --rm api python -m app.tools.detourer_rendus

Le fichier est reecrit sous son nom : ce nom est cite par la base et par les
autres back-offices, et le contenu du skin lui-meme ne change pas -- seul ce
qui l'entoure devient transparent. Un rendu deja transparent est laisse tel
quel, on peut donc relancer sans risque.
"""

from __future__ import annotations

import sys

from PIL import Image

from app.services.assets import load_catalog
from app.services.renderer import RENDERS
from app.services.shape import build_mask


def detourer(chemin, forme: dict, essai: bool) -> str:
    image = Image.open(chemin).convert("RGBA")
    largeur, hauteur = int(forme["width"]), int(forme["height"])
    pad = (image.width - largeur) // 2
    if pad < 0 or image.height != hauteur + 2 * pad:
        return "ignore : pas aux dimensions d'un rendu"
    if image.getchannel("A").getextrema()[0] < 255:
        return "deja transparent"
    if essai:
        return "a detourer"
    alpha = Image.new("L", image.size, 0)
    alpha.paste(build_mask(forme, largeur, hauteur), (pad, pad))
    image.putalpha(alpha)
    image.save(chemin, "PNG", optimize=True)
    return "detoure"


def main() -> None:
    essai = "--dry-run" in sys.argv
    forme = load_catalog()["shape"]
    bilan: dict[str, int] = {}
    for chemin in sorted(RENDERS.glob("*.png")):
        verdict = detourer(chemin, forme, essai)
        bilan[verdict] = bilan.get(verdict, 0) + 1
        print(f"{chemin.name}  {verdict}")
    print(", ".join(f"{n} {v}" for v, n in bilan.items()) or "aucun rendu")


if __name__ == "__main__":
    main()
