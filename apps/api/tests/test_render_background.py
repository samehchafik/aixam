"""Le fond doit couvrir toute la planche.

Un fond que le visiteur n'a pas manipule n'a pas d'echelle : c'est l'ABSENCE
de `scale` qui signifie « couvre la planche ». Le front et le rendu suivent la
meme regle, mais un defaut dans le schema de l'API la detruisait en chemin --
le fond partait a 20 % de la largeur, et la creation recue par mail ne
ressemblait pas a ce que le visiteur avait vu.

On regarde donc les pixels, seule facon d'attraper ce genre de regression.

    ../../.venv/bin/python tests/test_render_background.py     (depuis apps/api)
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import API_DIR, check, on_path, report

os.environ.setdefault("MEDIA_DIR", str(API_DIR / "media"))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x@127.0.0.1/x")
on_path()

from PIL import Image

from app.schemas import Layer
from app.services.assets import load_catalog
from app.services.renderer import render_design

catalogue = load_catalog()
FOND = catalogue["backgrounds"][0]["id"]
forme = catalogue["shape"]
W, H = int(forme["width"]), int(forme["height"])
PAD = int(W * 0.04)          # meme padding que render_design
BLANC = (255, 255, 255)


def rendre(*calques: Layer) -> Image.Image:
    """Passe par le schema, comme une vraie soumission de la borne."""
    charge = {"layers": [c.model_dump(exclude_none=True) for c in calques]}
    return Image.open(render_design(charge)).convert("RGB")


def couleur(img: Image.Image, fraction_x: float) -> tuple[int, int, int]:
    """Un pixel a x% de la largeur de la planche.

    Pris au quart de la hauteur, pas au milieu : l'encoche des commandes
    (510x170, centree en bas) mord le centre, et un pixel pris la rend la
    couleur de fond de l'image -- ce qui ferait echouer le test pour une
    raison qui n'a rien a voir avec le calque.
    """
    return img.getpixel((PAD + int(W * fraction_x), PAD + H // 4))


def proche(a, b, tolerance=12) -> bool:
    return all(abs(x - y) <= tolerance for x, y in zip(a, b))


print("\n[1] Fond sans echelle : il couvre la planche")
img = rendre(Layer(type="background", assetId=FOND))
gauche, milieu, droite = couleur(img, 0.02), couleur(img, 0.5), couleur(img, 0.98)
check("bord gauche couvert", not proche(gauche, BLANC), gauche)
check("centre couvert", not proche(milieu, BLANC), milieu)
check("bord droit couvert", not proche(droite, BLANC), droite)

print("\n[2] L'echelle d'un fond ne descend jamais sous la couverture")
# Un fond plus petit que la planche laisserait du blanc : ce n'est plus un
# fond. En revanche l'agrandir reste permis -- le visiteur zoome dans le motif.
from app.services.assets import load_catalog as _c
from app.services.renderer import MEDIA, cadrer_fond
from PIL import Image as _I

source = _I.open(MEDIA / next(b["image"] for b in catalogue["backgrounds"] if b["id"] == FOND))
ratio = source.width / source.height
couverture = cadrer_fond({}, ratio, W, H)["scale"]
check("un fond sans echelle prend la couverture", couverture >= 1.0, couverture)
check("une echelle plus petite est relevee",
      cadrer_fond({"scale": 0.5}, ratio, W, H)["scale"] == couverture)
check("une echelle plus grande est respectee",
      cadrer_fond({"scale": 2.0}, ratio, W, H)["scale"] == 2.0)
check("le centre est ramene dans les bornes",
      cadrer_fond({"x": 0.0}, ratio, W, H)["x"] == 0.5, cadrer_fond({"x": 0.0}, ratio, W, H)["x"])

print("\n[3] Aplat de couleur : toute la planche")
img = rendre(Layer(type="background", hex="#D42B1E"))
attendu = (212, 43, 30)
for fraction, nom in ((0.02, "bord gauche"), (0.5, "centre"), (0.98, "bord droit")):
    check(f"{nom} a la bonne couleur", proche(couleur(img, fraction), attendu), couleur(img, fraction))

print("\n[4] Un fond deplace ou reduit couvre quand meme")
# L'echelle « couvre » vaut exactement la largeur de la planche : sans
# bornage, un fond deplace d'un cheveu laissait une marge blanche sur un
# bord -- et le visiteur ne voyait qu'un motif legerement decale.
from app.services.shape import build_mask

masque = build_mask(forme, W, H)


def colonnes_blanches(img: Image.Image) -> int:
    """Colonnes VISIBLES (hors encoche et angles) entierement blanches."""
    total = 0
    for x in range(W):
        pixels = [img.getpixel((PAD + x, PAD + y)) for y in range(H) if masque.getpixel((x, y)) > 200]
        if pixels and all(proche(c, BLANC, 4) for c in pixels):
            total += 1
    return total


for titre, calque in (
    ("centre", Layer(type="background", assetId=FOND)),
    ("deplace a gauche", Layer(type="background", assetId=FOND, x=0.42)),
    ("pousse a fond a gauche", Layer(type="background", assetId=FOND, x=0.0)),
    ("pousse a fond a droite", Layer(type="background", assetId=FOND, x=1.0)),
    ("reduit sous la couverture", Layer(type="background", assetId=FOND, scale=0.5)),
    ("agrandi et decale", Layer(type="background", assetId=FOND, scale=1.4, x=0.9, y=0.9)),
):
    n = colonnes_blanches(rendre(calque))
    check(f"{titre} : aucune marge", n == 0, f"{n} colonne(s)")

print("\n[5] Un objet garde bien son echelle")
objet = catalogue["objects"][0]["id"]
img = rendre(Layer(type="background", hex="#FFFFFF"), Layer(type="object", assetId=objet, scale=0.05, z=1))
check("l'objet n'a pas envahi la planche", proche(couleur(img, 0.02), BLANC), couleur(img, 0.02))

sys.exit(report())
