"""Catalogue des elements de composition.

Deux repertoires, chacun pilote par son propre `index.json` :

    media/backgrounds/index.json   fonds (ordre d'affichage, libelle par langue)
    media/objects/index.json       objets a poser
    media/base/shape.json          geometrie de la planche de bord (masque)

Format d'un index :
    {"items": [{"id": "fond-1", "file": "fond_1.svg", "thumb": "Vignette_fond_1.svg",
                "width": 3460, "height": 690,
                "label": {"fr": "Fond 1", "en": "Background 1", "es": "Fondo 1"}}]}

L'ordre du tableau est l'ordre d'affichage. Le studio remplace les fichiers et
edite l'index sans redeploiement : le catalogue est relu a chaque bootstrap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from app.config import settings

MEDIA = Path(settings.media_dir)

# Repli si le gabarit n'a pas encore ete importe : un simple rectangle.
DEFAULT_SHAPE = {
    "width": 3218,
    "height": 325,
    "points": [[0, 0], [3218, 0], [3218, 325], [0, 325]],
}


class CatalogItem(TypedDict):
    id: str
    file: str
    image: str
    """Vignette du panier. Un fond en a une, dessinee en 16:9 ; un objet est sa
    propre vignette."""
    thumb: str
    width: float
    height: float
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
        vignette = raw.get("thumb")
        if vignette and not (MEDIA / folder / vignette).is_file():
            vignette = None
        items.append(
            {
                "id": raw["id"],
                "file": raw["file"],
                "image": f"{folder}/{raw['file']}",
                "thumb": f"{folder}/{vignette}" if vignette else f"{folder}/{raw['file']}",
                "width": float(raw.get("width") or 1),
                "height": float(raw.get("height") or 1),
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
