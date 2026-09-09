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
            if kind == "background" and layer.get("scale") is None:
                # Fond jamais manipule : on couvre toute la planche. `.get`
                # plutot que `in` : une valeur nulle explicite veut dire la
                # meme chose qu'une clef absente, et les deux nous arrivent.
                layer = {**layer, "scale": max(1.0, (sprite.width / sprite.height) * height / width)}
            _paste_sprite(canvas, sprite, layer, width, height)

    canvas.putalpha(build_mask(shape, width, height))

    pad = int(width * padding)
    out_img = Image.new("RGB", (width + 2 * pad, height + 2 * pad), BACKDROP)
    out_img.paste(canvas, (pad, pad), canvas)

    RENDERS.mkdir(parents=True, exist_ok=True)
    out = RENDERS / f"{uuid.uuid4().hex}.jpg"
    out_img.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out
