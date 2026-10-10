"""La sauvegarde prise d'office avant une remise a zero du back-office.

Vider les creations ou les visiteurs est definitif : avant d'effacer quoi que
ce soit, on met de cote ce qui va disparaitre, dans `backup/` (BACKUP_DIR),
sous un nom qui dit quoi et quand :

    sauve-after-reset-visiteur-2026-10-10-14-30.tar.gz
    sauve-after-reset-creation-2026-10-10-14-30.tar.gz

Une archive tar compressee (gzip) : plusieurs fichiers dans un seul .gz.

    visiteur : visiteurs.json et visiteurs.csv -- toutes les colonnes.
    creation : creations.json et creations.csv -- chaque creation avec son
               visiteur (identifiant, nom, prenom, e-mail, code postal,
               consentement), et images/ -- le PNG de chaque creation.

Si la sauvegarde echoue, l'exception remonte et rien n'est supprime : mieux
vaut un bouton qui refuse qu'une base videe sans filet.

Pour relire une archive : `tar xzf sauve-after-reset-....tar.gz`.
"""

from __future__ import annotations

import csv
import io
import json
import tarfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Design, Visitor
from app.services.renderer import skin_path

CHAMPS_VISITEUR = (
    "id", "first_name", "last_name", "email", "postal_code",
    "email_verified_at", "consent_marketing", "consent_at", "created_at",
)
CHAMPS_CREATION = (
    "id", "visitor_id", "kiosk_id", "session_id", "status", "skin", "render_path",
    "shared_hint", "moderation", "moderated_at", "created_at", "updated_at",
)


def dossier() -> Path:
    d = Path(settings.backup_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _maintenant() -> datetime:
    # L'heure de Paris dans le nom : c'est celle qu'on cherchera. Sans base de
    # fuseaux (tzdata absent sous Windows), l'heure locale de la machine.
    try:
        return datetime.now(ZoneInfo("Europe/Paris"))
    except ZoneInfoNotFoundError:
        return datetime.now()


def _chemin(quoi: str) -> Path:
    """Le fichier a ecrire ; jamais un ecrasement, meme a la meme minute."""
    base = f"sauve-after-reset-{quoi}-{_maintenant():%Y-%m-%d-%H-%M}"
    chemin = dossier() / f"{base}.tar.gz"
    n = 2
    while chemin.exists():
        chemin = dossier() / f"{base}-{n}.tar.gz"
        n += 1
    return chemin


def _valeur(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "value"):  # les enumerations
        return v.value
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


def _ligne(objet, champs) -> dict:
    return {c: _valeur(getattr(objet, c)) for c in champs}


def _csv(lignes: list[dict], champs: list[str]) -> bytes:
    tampon = io.StringIO()
    # Le BOM : Excel lit sinon le fichier en Windows-1252.
    tampon.write("﻿")
    w = csv.DictWriter(tampon, fieldnames=champs, delimiter=";", extrasaction="ignore")
    w.writeheader()
    w.writerows(lignes)
    return tampon.getvalue().encode("utf-8")


def _ajouter(archive: tarfile.TarFile, nom: str, contenu: bytes) -> None:
    info = tarfile.TarInfo(nom)
    info.size = len(contenu)
    info.mtime = int(time.time())
    archive.addfile(info, io.BytesIO(contenu))


def _ecrire(quoi: str, remplir) -> Path:
    """Ecrit l'archive a cote, puis la renomme : un fichier a moitie ecrit ne
    passe jamais pour une sauvegarde."""
    chemin = _chemin(quoi)
    provisoire = chemin.with_name(chemin.name + ".partiel")
    try:
        with tarfile.open(provisoire, "w:gz") as archive:
            remplir(archive)
        provisoire.replace(chemin)
    except BaseException:
        provisoire.unlink(missing_ok=True)
        raise
    return chemin


def sauver_visiteurs(db: Session) -> tuple[Path, int]:
    visiteurs = [_ligne(v, CHAMPS_VISITEUR) for v in db.scalars(select(Visitor).order_by(Visitor.created_at))]

    def remplir(archive):
        _ajouter(archive, "visiteurs.json", json.dumps(visiteurs, ensure_ascii=False, indent=2).encode())
        _ajouter(archive, "visiteurs.csv", _csv(visiteurs, list(CHAMPS_VISITEUR)))

    return _ecrire("visiteur", remplir), len(visiteurs)


def sauver_creations(db: Session) -> tuple[Path, int]:
    lignes = db.execute(
        select(Design, Visitor).outerjoin(Visitor, Design.visitor_id == Visitor.id).order_by(Design.created_at)
    ).all()
    creations, images = [], {}
    for design, visiteur in lignes:
        c = _ligne(design, CHAMPS_CREATION)
        c["visiteur"] = _ligne(visiteur, CHAMPS_VISITEUR) if visiteur else None
        c["image"] = None
        if design.skin:
            try:
                fichier = skin_path(design.skin)
            except ValueError:
                fichier = None
            if fichier and fichier.is_file():
                images[design.skin] = fichier
                c["image"] = f"images/{design.skin}"
        creations.append(c)

    # Le CSV a plat : les colonnes du visiteur a cote de celles de la creation.
    plates = [
        {**{k: v for k, v in c.items() if k != "visiteur"},
         **{f"visiteur_{k}": v for k, v in (c["visiteur"] or {}).items()}}
        for c in creations
    ]
    champs_csv = [*CHAMPS_CREATION, "image", *(f"visiteur_{k}" for k in CHAMPS_VISITEUR)]

    def remplir(archive):
        _ajouter(archive, "creations.json", json.dumps(creations, ensure_ascii=False, indent=2).encode())
        _ajouter(archive, "creations.csv", _csv(plates, champs_csv))
        for nom, fichier in images.items():
            archive.add(fichier, arcname=f"images/{nom}")

    return _ecrire("creation", remplir), len(creations)
