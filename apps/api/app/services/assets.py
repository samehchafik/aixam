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

import hashlib
import json
from functools import lru_cache
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
    #: Empreinte du contenu, collee a l'URL par le front pour qu'un element
    #: modifie ne puisse pas etre servi depuis un cache.
    version: str
    thumbVersion: str


@lru_cache(maxsize=256)
def _empreinte(chemin: str, signature: tuple[int, int]) -> str:
    """Empreinte courte du contenu d'un fichier du catalogue.

    `signature` (taille, date) ne sert qu'a invalider ce cache : elle est dans
    la cle, pas dans le calcul. Deux deploiements qui ne changent pas un
    fichier lui laissent donc la meme empreinte, et le navigateur garde ce
    qu'il a.
    """
    del signature
    return hashlib.sha256(Path(chemin).read_bytes()).hexdigest()[:10]


def _version(chemin: Path) -> str:
    """Jeton a coller a l'URL d'un element, pour que son URL change avec lui.

    Un element du catalogue change sous le MEME nom : fond_3.svg d'aujourd'hui
    n'est pas celui d'hier. Un navigateur qui en detient une copie n'a alors
    aucune raison de la redemander, et montre l'ancien dessin longtemps apres
    le deploiement -- c'est ce qui a laisse « pa » a l'ecran des jours apres sa
    correction. Une URL qui porte l'empreinte du contenu supprime la question :
    un fichier different est une autre URL, qu'aucun cache ne detient.
    """
    try:
        etat = chemin.stat()
    except OSError:
        return "0"
    return _empreinte(str(chemin), (etat.st_size, etat.st_mtime_ns))


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
        nom_vignette = vignette or raw["file"]
        items.append(
            {
                "id": raw["id"],
                "file": raw["file"],
                "image": f"{folder}/{raw['file']}",
                "thumb": f"{folder}/{nom_vignette}",
                # Le chemin reste nu : le rendu serveur le lit sur le disque.
                # C'est le front qui colle la version a l'URL.
                "version": _version(MEDIA / folder / raw["file"]),
                "thumbVersion": _version(MEDIA / folder / nom_vignette),
                "width": float(raw.get("width") or 1),
                "height": float(raw.get("height") or 1),
                "label": raw.get("label", {}),
            }
        )
    return items


def _mockup() -> dict | None:
    """Le decor du diaporama, ou None s'il n'a pas ete importe.

    Les chemins sont rendus relatifs a /media, comme pour le reste : le front
    n'a jamais a savoir comment les dossiers sont ranges.
    """
    brut = _read_json(MEDIA / "mockup" / "index.json", {})
    if not brut:
        return None
    return {
        **brut,
        **{
            cle: f"mockup/{brut[cle]}"
            for cle in ("decor", "masque", "ombrage")
            if cle in brut
        },
        "version": _version(MEDIA / "mockup" / brut.get("decor", "")),
    }


def load_catalog() -> dict:
    return {
        "shape": _read_json(MEDIA / "base" / "shape.json", DEFAULT_SHAPE),
        "mockup": _mockup(),
        "backgrounds": _load_index("backgrounds"),
        "objects": _load_index("objects"),
    }
