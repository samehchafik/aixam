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

import math
import uuid
from pathlib import Path

from PIL import Image

from app.config import settings
from app.services.assets import load_catalog
from app.services.shape import build_mask

MEDIA = Path(settings.media_dir)
RENDERS = MEDIA / "renders"

BACKDROP = (24, 22, 40)  # fond du JPEG autour de la planche


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _asset_index(catalog: dict) -> dict[str, str]:
    return {
        item["id"]: item["image"]
        for group in ("backgrounds", "objects")
        for item in catalog.get(group, [])
    }


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
    rad = math.radians(float(layer.get("rotation", 0) or 0))
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

    return {**layer, "scale": echelle, "x": 0.5 + rx / width, "y": 0.5 + ry / height}


def _paste_sprite(canvas: Image.Image, sprite: Image.Image, layer: dict, width: int, height: int) -> None:
    target_w = max(1, int(width * float(layer.get("scale", 0.2))))
    target_h = max(1, int(sprite.height * target_w / sprite.width))
    sprite = sprite.resize((target_w, target_h), Image.LANCZOS)

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

    `/media` est monte sur MEDIA_DIR : l'URL est donc le chemin RELATIF a ce
    dossier. Coller le chemin stocke marchait tant que MEDIA_DIR restait
    relatif (`media`, le cas du conteneur) et produisait `//Users/...` des
    qu'on lui donnait un chemin absolu.
    """
    if not path:
        return None
    chemin = Path(path)
    try:
        chemin = chemin.relative_to(MEDIA)
    except ValueError:
        pass
    return f"/media/{chemin.as_posix()}"


def render_design(layers: dict, *, quality: int = 92, padding: float = 0.04) -> Path:
    """Compose les calques, applique le masque, ecrit un JPEG."""
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
            rel = assets.get(layer.get("assetId", ""))
            if not rel:
                continue
            sprite = Image.open(MEDIA / rel).convert("RGBA")
            if kind == "background":
                layer = cadrer_fond(layer, sprite.width / sprite.height, width, height)
            _paste_sprite(canvas, sprite, layer, width, height)

    canvas.putalpha(build_mask(shape, width, height))

    pad = int(width * padding)
    out_img = Image.new("RGB", (width + 2 * pad, height + 2 * pad), BACKDROP)
    out_img.paste(canvas, (pad, pad), canvas)

    RENDERS.mkdir(parents=True, exist_ok=True)
    out = RENDERS / f"{uuid.uuid4().hex}.jpg"
    out_img.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out
