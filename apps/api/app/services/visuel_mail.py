"""Le visuel de l'e-mail : l'ecran 7 de la borne, sans son bouton -- la
creation posee sur le tableau de bord, le ruban, le logo et la grande
planche a plat. C'est l'image du corps de l'e-mail et sa piece jointe.

Meme composition que l'ecran 7 (`ReviewStep`), avec les memes fichiers :

    photo (`media/mockup/`)
    [skin projete + ombrage] decoupes ensemble par le masque (`SkinMockup`)
    ruban et logo (`templates/ecran7/habillage.png`, voir
        scripts/habillage_ecran7.py : ils ne dependent pas de la creation)
    planche a plat et son contour blanc (`PLANCHE` de ReviewStep)

Compose au moment de l'envoi, a partir du skin de la ligne d'outbox, par le
back-office qui prepare le message -- la borne, qui confie ensuite le tout au
relais. Pillow seul, sans numpy ni OpenCV ni Cairo : la borne du salon tourne
sous Windows.

On compose en 4K, la resolution des fichiers du studio, puis on reduit une
seule fois. Tout ce qui est hors du rectangle du masque est la photo telle
quelle : le travail se fait donc dans ce rectangle seulement.
"""

from __future__ import annotations

import io
import json
from functools import lru_cache

from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

from app.services.assets import load_catalog
from app.services.renderer import MEDIA

MOCKUP = MEDIA / "mockup"
HABILLAGE = Path(__file__).resolve().parent.parent / "templates" / "ecran7" / "habillage.png"

# La planche du bas de l'ecran 7, en pixels de scene (1920 de large) : la
# meme que `PLANCHE` dans ReviewStep.tsx.
PLANCHE = {"x": 103, "y": 747, "largeur": 1714, "contour": 4}

# Largeur du visuel. L'e-mail l'affiche sur 456 px : 1600 reste net sur un
# ecran haute densite comme a l'agrandissement, pour un PNG d'environ 1,4 Mo.
LARGEUR = 1600

# Fond perdu du skin, comme le filtre `#skin-fond-perdu` de la borne : flou de
# 16 px, puis opaque des que l'alpha depasse 1/20.
FLOU_FOND_PERDU = 16
SEUIL_FOND_PERDU = 255 // 20 + 1


def _resoudre(a: list[list[float]], b: list[float]) -> list[float]:
    """Systeme lineaire 8x8, pivot de Gauss -- comme `projection.ts`."""
    n = len(b)
    for i in range(n):
        pivot = max(range(i, n), key=lambda r: abs(a[r][i]))
        a[i], a[pivot] = a[pivot], a[i]
        b[i], b[pivot] = b[pivot], b[i]
        for r in range(n):
            if r != i and a[r][i]:
                f = a[r][i] / a[i][i]
                a[r] = [x - f * y for x, y in zip(a[r], a[i])]
                b[r] -= f * b[i]
    return [b[i] / a[i][i] for i in range(n)]


def homographie(depart: list[tuple[float, float]], arrivee: list[tuple[float, float]]) -> list[float]:
    """Les 8 coefficients menant quatre points vers quatre autres."""
    a, b = [], []
    for (u, v), (x, y) in zip(depart, arrivee):
        a.append([u, v, 1, 0, 0, 0, -u * x, -v * x])
        b.append(x)
        a.append([0, 0, 0, u, v, 1, -u * y, -v * y])
        b.append(y)
    return _resoudre(a, b)


def appliquer(m: list[float], point: tuple[float, float]) -> tuple[float, float]:
    x, y = point
    w = m[6] * x + m[7] * y + 1
    return (m[0] * x + m[1] * y + m[2]) / w, (m[3] * x + m[4] * y + m[5]) / w


def _fond_perdu(skin: Image.Image) -> Image.Image:
    """Prolonge les couleurs du bord du skin d'une trentaine de pixels."""
    # Flou en alpha premultiplie, comme feGaussianBlur : sans cela, le noir des
    # pixels transparents assombrirait le bord.
    flou = skin.convert("RGBa").filter(ImageFilter.GaussianBlur(FLOU_FOND_PERDU)).convert("RGBA")
    flou.putalpha(flou.getchannel("A").point(lambda a: 255 if a >= SEUIL_FOND_PERDU else 0))
    flou.alpha_composite(skin)
    return flou


def composer(skin_png: bytes, *, largeur: int = LARGEUR) -> bytes:
    """Le PNG du visuel : la photo du tableau de bord, la creation posee."""
    index = json.loads((MOCKUP / "index.json").read_text(encoding="utf-8"))
    photo = Image.open(MOCKUP / index["decor"]).convert("RGBA")
    # Les coordonnees de index.json sont celles de la scene de la borne
    # (1920 de large) ; les fichiers du studio sont en 4K.
    k = photo.width / index["width"]

    # Le rectangle du masque, en pixels de la photo.
    masque = Image.open(MOCKUP / index["masque"]).convert("RGBA").getchannel("A")
    mx, my = (round(c * k) for c in index["maskOrigin"])
    if index.get("maskSize"):
        taille = tuple(round(c * k) for c in index["maskSize"])
        if masque.size != taille:
            masque = masque.resize(taille, Image.LANCZOS)
    zone_l, zone_h = masque.size

    # Le skin et sa marge transparente : la borne pose la planche sur les
    # coins, et la marge suit la meme projection.
    shape = load_catalog()["shape"]
    pw, ph = float(shape["width"]), float(shape["height"])
    brut = Image.open(io.BytesIO(skin_png)).convert("RGBA")
    skin = _fond_perdu(brut)
    marge = (skin.width - pw) / 2

    coins = [(x * k - mx, y * k - my) for x, y in index["corners"]]
    vers_zone = homographie([(0, 0), (pw, 0), (pw, ph), (0, ph)], coins)
    bords = [(-marge, -marge), (pw + marge, -marge), (pw + marge, ph + marge), (-marge, ph + marge)]
    arrivee = [appliquer(vers_zone, p) for p in bords]

    # Reduit d'abord a peu pres a sa taille d'arrivee : la projection seule,
    # en bicubique, crenelerait une image plus de 1,3 fois plus grande.
    f = min(1.0, (arrivee[1][0] - arrivee[0][0]) / skin.width)
    if f < 1:
        skin = skin.resize((max(1, round(skin.width * f)), max(1, round(skin.height * f))), Image.LANCZOS)
    depart = [(0, 0), (skin.width, 0), (skin.width, skin.height), (0, skin.height)]
    # Pillow demande l'inverse : pour chaque pixel d'arrivee, ou lire.
    zone = skin.transform((zone_l, zone_h), Image.PERSPECTIVE, homographie(arrivee, depart), Image.BICUBIC)

    # L'ombrage repose sur le skin ; le masque decoupe les deux ensemble.
    ombrage = Image.open(MOCKUP / index["ombrage"]).convert("RGBA")
    if ombrage.size != photo.size:
        ombrage = ombrage.resize(photo.size, Image.LANCZOS)
    zone.alpha_composite(ombrage.crop((mx, my, mx + zone_l, my + zone_h)))
    zone.putalpha(Image.composite(zone.getchannel("A"), Image.new("L", zone.size, 0), masque))

    photo.alpha_composite(zone, (mx, my))

    # Le ruban et le logo, puis la planche a plat, par-dessus.
    habillage = Image.open(HABILLAGE).convert("RGBA")
    if habillage.size != photo.size:
        habillage = habillage.resize(photo.size, Image.LANCZOS)
    photo.alpha_composite(habillage)
    planche, position = _planche(brut, pw, ph, k)
    photo.alpha_composite(planche, position)

    hauteur = round(photo.height * largeur / photo.width)
    visuel = photo.convert("RGB").resize((largeur, hauteur), Image.LANCZOS)
    tampon = io.BytesIO()
    # Sans `optimize` : il ne gagne que 3 % de poids, pour quatre fois plus de
    # temps -- les deux tiers de la composition. Le PNG reste sans perte.
    visuel.save(tampon, "PNG")
    return tampon.getvalue()


def _planche(skin: Image.Image, pw: float, ph: float, k: float) -> tuple[Image.Image, tuple[int, int]]:
    """La planche a plat de l'ecran 7 et son contour blanc, avec sa position.

    Le contour est a cheval sur le bord, comme le trace de la borne : moitie
    dehors, moitie sur la planche.
    """
    marge = (skin.width - pw) / 2
    planche = skin.crop((round(marge), round(marge), round(marge + pw), round(marge + ph)))
    largeur = round(PLANCHE["largeur"] * k)
    planche = planche.resize((largeur, round(largeur * ph / pw)), Image.LANCZOS)

    e = max(1, round(PLANCHE["contour"] * k / 2))
    toile = Image.new("RGBA", (planche.width + 2 * e, planche.height + 2 * e), (0, 0, 0, 0))
    toile.alpha_composite(planche, (e, e))
    forme = toile.getchannel("A")
    trait = ImageChops.subtract(forme.filter(ImageFilter.MaxFilter(2 * e + 1)),
                                forme.filter(ImageFilter.MinFilter(2 * e + 1)))
    blanc = Image.new("RGBA", toile.size, (255, 255, 255, 255))
    blanc.putalpha(trait)
    toile.alpha_composite(blanc)
    return toile, (round(PLANCHE["x"] * k) - e, round(PLANCHE["y"] * k) - e)


@lru_cache(maxsize=8)
def visuel(skin_png: bytes) -> bytes:
    """Le visuel d'un skin. Garde en memoire : un envoi retente apres une
    coupure ne le recompose pas."""
    return composer(skin_png)
