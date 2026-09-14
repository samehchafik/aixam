"""Rendu serveur d'une creation.

Le canvas (Konva) et ce module interpretent le meme schema de calques en
coordonnees normalisees : le JPEG recu par mail correspond a ce que le
visiteur a vu, quelle que soit la resolution de la borne.

Schema d'un calque :
    {"type": "background", "assetId": "sunburst",       # ou "hex": "#D42B1E"
     "x": .5, "y": .5, "scale": 1, "rotation": 0}
    {"type": "object", "assetId": "heart-pink",
     "x": .5, "y": .4, "scale": .2, "rotation": 0, "opacity": 1, "z": 3}

x/y = centre de l'element en fraction de la largeur/hauteur de la planche.
scale = largeur de l'element en fraction de la largeur de la planche.
Le tout est ensuite decoupe par le masque de la planche de bord.
"""

from __future__ import annotations

import hashlib
import io
import math
from functools import lru_cache
from pathlib import Path

import cairosvg
from PIL import Image

from app.config import settings
from app.services.assets import load_catalog
from app.services.shape import build_mask

MEDIA = Path(settings.media_dir)
# Les skins des visiteurs. Hors de MEDIA, et hors de tout volume docker : le
# catalogue se refabrique depuis le depot, une creation non.
SKINS = Path(settings.skins_dir)
# Les JPEG d'avant, quand les rendus vivaient dans les medias. On n'y ecrit
# plus, mais les creations des salons passes s'y trouvent encore.
RENDERS = MEDIA / "renders"

BACKDROP = (24, 22, 40)  # fond du JPEG autour de la planche


@lru_cache(maxsize=64)
def _charger(rel: str, largeur: int) -> Image.Image:
    """Ouvre un element du catalogue, a la largeur demandee.

    Les elements sont livres en SVG : on les rasterise ici, a la taille ou ils
    seront reellement poses, plutot que de les agrandir depuis une image fixe.
    Le rendu garde donc la nettete du vectoriel quelle que soit la taille que
    le visiteur a choisie. Le cache evite de recommencer pour chaque creation.
    """
    chemin = MEDIA / rel
    if chemin.suffix.lower() == ".svg":
        png = cairosvg.svg2png(url=str(chemin), output_width=max(1, largeur))
        return Image.open(io.BytesIO(png)).convert("RGBA")
    return Image.open(chemin).convert("RGBA")


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _asset_index(catalog: dict) -> dict[str, dict]:
    """Les elements du catalogue, par identifiant."""
    return {
        item["id"]: item
        for group in ("backgrounds", "objects")
        for item in catalog.get(group, [])
    }


# Meme borne que la borne (MAX_ROTATION_FOND dans SkinCanvas) : un fond au-dela
# de quelques degres devrait etre enormement agrandi pour couvrir encore la
# planche. On la reapplique ici -- le rendu ne fait pas confiance a ce qu'on lui
# envoie.
MAX_ROTATION_FOND = 7.0


def cadrer_fond(layer: dict, sprite_ratio: float, width: int, height: int) -> dict:
    """Garantit qu'un fond couvre la planche, quoi qu'ait fait le visiteur.

    L'echelle « couvre » vaut exactement la largeur de la planche : au pixel
    pres. Deplacer le fond d'un cheveu decouvrait donc un bord, qui
    apparaissait en blanc sur la creation -- et le visiteur, lui, ne voyait
    qu'un fond legerement decale.

    On force donc deux choses : une echelle au moins egale a la couverture, et
    un centre assez rentre pour que la planche reste entierement dans l'image.

    Avec une rotation, la planche vue depuis le repere de l'image est un
    rectangle penche : on couvre son rectangle englobant (W|cos|+H|sin| par
    W|sin|+H|cos|) et on borne le decalage du centre dans ce meme repere.
    Un peu plus large que le strict necessaire, toujours suffisant. Meme
    calcul que `coverBackground` cote borne.

    `sprite_ratio` = largeur / hauteur de l'image source.
    """
    angle = float(layer.get("rotation", 0) or 0)
    angle = max(-MAX_ROTATION_FOND, min(MAX_ROTATION_FOND, angle))
    rad = math.radians(angle)
    c, s_ = abs(math.cos(rad)), abs(math.sin(rad))
    wp = width * c + height * s_
    hp = width * s_ + height * c

    couverture = max(wp / width, hp / (width / sprite_ratio))
    echelle = max(couverture, float(layer.get("scale") or 0.0))
    w = echelle * width
    h = w / sprite_ratio

    # Decalage du centre, tourne dans le repere de l'image, borne, puis ramene.
    dx = (float(layer.get("x", 0.5)) - 0.5) * width
    dy = (float(layer.get("y", 0.5)) - 0.5) * height
    cos, sin = math.cos(rad), math.sin(rad)
    lx = dx * cos + dy * sin
    ly = -dx * sin + dy * cos
    bx = max(-(w - wp) / 2, min((w - wp) / 2, lx))
    by = max(-(h - hp) / 2, min((h - hp) / 2, ly))
    rx = bx * cos - by * sin
    ry = bx * sin + by * cos

    return {**layer, "scale": echelle, "rotation": angle, "x": 0.5 + rx / width, "y": 0.5 + ry / height}


def _paste_sprite(canvas: Image.Image, sprite: Image.Image, layer: dict, width: int, height: int) -> None:
    rotation = float(layer.get("rotation", 0))
    if rotation:
        sprite = sprite.rotate(-rotation, expand=True, resample=Image.BICUBIC)

    opacity = float(layer.get("opacity", 1))
    if opacity < 1:
        sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * opacity)))

    cx = int(width * float(layer.get("x", 0.5)))
    cy = int(height * float(layer.get("y", 0.5)))
    canvas.alpha_composite(sprite, (cx - sprite.width // 2, cy - sprite.height // 2))


def render_url(path: str | None) -> str | None:
    """URL publique d'un rendu, quel que soit MEDIA_DIR.

    Deux racines sont servies : `/skins` pour les creations des visiteurs,
    `/media` pour le catalogue et les rendus des salons passes. L'URL est le
    chemin RELATIF a l'une ou l'autre. Coller le chemin stocke marchait tant
    que ces dossiers restaient relatifs (le cas du conteneur) et produisait
    `//Users/...` des qu'on leur donnait un chemin absolu.
    """
    if not path:
        return None
    chemin = Path(path)
    # Compare en absolu : le chemin stocke peut etre absolu la ou la racine est
    # relative, ou l'inverse. Les comparer tels quels produisait `//Users/...`.
    absolu = chemin if chemin.is_absolute() else Path.cwd() / chemin
    for racine, prefixe in ((SKINS, "/skins"), (MEDIA, "/media")):
        try:
            relatif = absolu.resolve().relative_to(racine.resolve())
        except (ValueError, OSError):
            continue
        return f"{prefixe}/{relatif.as_posix()}"
    # Chemin d'une autre epoque : on le sert depuis les medias, comme avant.
    return f"/media/{chemin.as_posix()}"


def render_present(path: str | None) -> bool:
    """Le fichier de rendu est-il encore la ?

    La base garde un chemin, pas le fichier. Les deux ont deja diverge : le
    dossier des rendus vivait dans un volume nomme, remplace par un volume
    vide, et chaque ligne pointait alors sur un fichier disparu. Un chemin
    stocke ne prouve donc rien -- on regarde le disque avant de promettre une
    image.
    """
    if not path:
        return False
    # Le chemin est stocke tel que render_design l'a produit : absolu, ou
    # relatif au dossier de travail -- comme MEDIA lui-meme. Il s'utilise donc
    # tel quel. On essaie malgre tout MEDIA / path, au cas ou une ligne ancienne
    # porterait un chemin relatif au dossier des medias.
    return Path(path).is_file() or (MEDIA / path).is_file() or (SKINS / path).is_file()


def render_design(layers: dict, *, padding: float = 0.04) -> Path:
    """Compose les calques, applique le masque, ecrit le PNG du skin.

    Appele une seule fois, quand le visiteur valide. Le fichier produit est la
    creation : ses calques citent le catalogue par identifiant, et un element
    renomme les rendrait illisibles. On ne re-rend donc jamais.
    """
    catalog = load_catalog()
    shape = catalog["shape"]
    width, height = int(shape["width"]), int(shape["height"])
    assets = _asset_index(catalog)

    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))

    for layer in sorted(layers.get("layers", []), key=lambda item: item.get("z", 0)):
        kind = layer.get("type")

        if kind == "background" and layer.get("hex"):
            canvas.alpha_composite(Image.new("RGBA", (width, height), (*_hex_to_rgb(layer["hex"]), 255)))
            continue

        if kind in ("background", "object"):
            element = assets.get(layer.get("assetId", ""))
            if not element:
                continue

            # Le rapport vient du catalogue, pas d'un fichier ouvert : on sait
            # donc a quelle largeur rasteriser AVANT de lire le SVG.
            ratio = element["width"] / element["height"]
            if kind == "background":
                layer = cadrer_fond(layer, ratio, width, height)
            largeur = max(1, round(width * float(layer.get("scale", 0.2))))
            _paste_sprite(canvas, _charger(element["image"], largeur), layer, width, height)

    canvas.putalpha(build_mask(shape, width, height))

    pad = int(width * padding)
    out_img = Image.new("RGB", (width + 2 * pad, height + 2 * pad), BACKDROP)
    out_img.paste(canvas, (pad, pad), canvas)

    # PNG : le skin part en fabrication, il ne doit pas trainer les artefacts
    # d'une compression avec perte sur des aplats et du texte.
    tampon = io.BytesIO()
    out_img.save(tampon, "PNG", optimize=True)
    octets = tampon.getvalue()

    # Le nom est l'empreinte du contenu. Deux consequences voulues : il ne
    # depend d'aucun compteur ni d'aucune horloge, donc un meme skin rendu deux
    # fois ne fait qu'un fichier ; et le nom ne dit rien du visiteur.
    SKINS.mkdir(parents=True, exist_ok=True)
    out = SKINS / f"{hashlib.sha256(octets).hexdigest()[:32]}.png"
    if not out.exists():
        out.write_bytes(octets)
    return out
