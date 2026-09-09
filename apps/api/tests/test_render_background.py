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

print("\n[2] Fond que le visiteur a reduit : son echelle est respectee")
img = rendre(Layer(type="background", assetId=FOND, scale=0.2))
check("le centre porte le fond", not proche(couleur(img, 0.5), BLANC))
check("les bords restent nus", proche(couleur(img, 0.02), BLANC), couleur(img, 0.02))

print("\n[3] Aplat de couleur : toute la planche")
img = rendre(Layer(type="background", hex="#D42B1E"))
attendu = (212, 43, 30)
for fraction, nom in ((0.02, "bord gauche"), (0.5, "centre"), (0.98, "bord droit")):
    check(f"{nom} a la bonne couleur", proche(couleur(img, fraction), attendu), couleur(img, fraction))

print("\n[4] Un objet garde bien son echelle")
objet = catalogue["objects"][0]["id"]
img = rendre(Layer(type="background", hex="#FFFFFF"), Layer(type="object", assetId=objet, scale=0.05, z=1))
check("l'objet n'a pas envahi la planche", proche(couleur(img, 0.02), BLANC), couleur(img, 0.02))

sys.exit(report())
