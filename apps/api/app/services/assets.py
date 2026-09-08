"""Catalogue des elements de composition.

Deux repertoires, chacun pilote par son propre `index.json` :

    media/backgrounds/index.json   fonds (ordre d'affichage, libelle par langue)
    media/objects/index.json       objets a poser
    media/base/shape.json          geometrie de la planche de bord (masque)

Format d'un index :
    {"items": [{"id": "sunburst", "file": "sunburst.jpg",
                "label": {"fr": "Soleil rétro", "en": "Retro sunburst", "es": "Sol retro"}}]}

L'ordre du tableau est l'ordre d'affichage. Le studio remplace les fichiers et
edite l'index sans redeploiement : le catalogue est relu a chaque bootstrap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from app.config import settings

MEDIA = Path(settings.media_dir)

DEFAULT_SHAPE = {
    "width": 3000,
    "height": 300,
    "cornerRadius": 95,
    "notch": {"width": 510, "height": 170, "radius": 34},
}


class CatalogItem(TypedDict):
    id: str
    file: str
    image: str
    label: dict[str, str]


def _read_json(path: Path, default: dict) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def _load_index(folder: str) -> list[CatalogItem]:
    index = _read_json(MEDIA / folder / "index.json", {"items": []})
    items: list[CatalogItem] = []
    for raw in index.get("items", []):
        if not (MEDIA / folder / raw["file"]).is_file():
            continue  # un fichier manquant ne doit pas casser la borne
        items.append(
            {
                "id": raw["id"],
                "file": raw["file"],
                "image": f"{folder}/{raw['file']}",
                "label": raw.get("label", {}),
            }
        )
    return items


def load_catalog() -> dict:
    return {
        "shape": _read_json(MEDIA / "base" / "shape.json", DEFAULT_SHAPE),
        "backgrounds": _load_index("backgrounds"),
        "objects": _load_index("objects"),
    }
