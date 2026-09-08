"""Le back-office du stand remonte ses donnees vers le serveur.

Sens unique : on envoie, on ne recoit pas. Le serveur ne modifie pas ces
lignes, donc il n'y a jamais deux versions d'une meme ligne a departager.

Trois curseurs, un par table, gardes dans `app_settings`. Un envoi interrompu
reprend ou il en etait ; un envoi rejoue ne cree pas de doublon, la
reinsertion-ou-mise-a-jour cote serveur s'en charge. Les curseurs ne sont
avances qu'apres un lot accepte -- une coupure reseau ne fait donc rien
perdre, elle fait recommencer.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Design, Event, Visitor
from app.services.settings_store import get_setting, set_setting
from app.services.transports import PermanentSendError, SendError
from app.services.transports import relay as relay_transport

# Table -> (modele, colonne d'horodatage, cle du curseur, nom dans la charge)
SOURCES = (
    (Visitor, Visitor.created_at, "sync_cursor_visitors", "visitors"),
    (Design, Design.updated_at, "sync_cursor_designs", "designs"),
    (Event, Event.created_at, "sync_cursor_events", "events"),
)

_CHAMPS = {
    "visitors": ("id", "first_name", "last_name", "email", "postal_code",
                 "email_verified_at", "consent_marketing", "consent_at", "created_at"),
    "designs": ("id", "visitor_id", "session_id", "layers", "status",
                "shared_hint", "created_at", "updated_at"),
    "events": ("session_id", "visitor_id", "name", "payload", "created_at"),
}


def remote_url(db: Session) -> str:
    valeur = get_setting(db, "sync_url", settings.sync_url)
    return str(valeur or relay_transport.relay_url(db) or "").rstrip("/")


def remote_token(db: Session) -> str:
    valeur = get_setting(db, "sync_token", settings.sync_token)
    return str(valeur or relay_transport.relay_token(db) or "")


def _serialiser(ligne, nom: str) -> dict:
    sortie = {}
    for champ in _CHAMPS[nom]:
        valeur = getattr(ligne, champ)
        if isinstance(valeur, enum.Enum):
            valeur = valeur.value
        elif isinstance(valeur, datetime):
            valeur = valeur.isoformat()
        elif isinstance(valeur, uuid.UUID):
            valeur = str(valeur)
        sortie[champ] = valeur
    return sortie


def _requete(db: Session, methode: str, chemin: str, json: dict | None = None) -> httpx.Response:
    url, token = remote_url(db), remote_token(db)
    if not url or not token:
        raise PermanentSendError("Remontee non configuree (adresse et jeton requis)")
    relay_transport.check_url(url)
    try:
        return httpx.request(
            methode, f"{url}{chemin}", json=json,
            headers={"Authorization": f"Bearer {token}"},
            timeout=settings.mail_relay_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise SendError(f"serveur {url} injoignable : {exc}") from exc


def _verifier(reponse: httpx.Response) -> None:
    if reponse.is_success:
        return
    detail = reponse.text[:500]
    try:
        detail = reponse.json().get("detail", detail)
    except ValueError:
        pass
    if reponse.status_code in (401, 403, 404, 413, 422):
        raise PermanentSendError(f"serveur : {detail}")
    raise SendError(f"serveur HTTP {reponse.status_code} : {detail}")


def status(db: Session) -> dict:
    reponse = _requete(db, "GET", "/api/sync/status")
    _verifier(reponse)
    return reponse.json()


def push(db: Session, *, tout: bool = False) -> dict:
    """Envoie ce qui a change depuis le dernier envoi. `tout` ignore les curseurs.

    Le renvoi complet sert a reparer : il est sans danger, mais il fait
    reapparaitre chez le serveur un visiteur qu'on y aurait efface -- c'est le
    prix d'un sens unique sans marqueurs de suppression.
    """
    lot = settings.sync_batch_size
    totaux = {"visitors": 0, "designs": 0, "events": 0, "events_ignores": 0, "envois": 0}

    while True:
        charge: dict[str, list[dict]] = {}
        fins: dict[str, datetime] = {}

        for modele, colonne, cle_curseur, nom in SOURCES:
            depuis = None if tout else get_setting(db, cle_curseur, None)
            requete = select(modele).order_by(colonne).limit(lot)
            if depuis:
                requete = requete.where(colonne > datetime.fromisoformat(depuis))
            lignes = db.scalars(requete).all()
            if lignes:
                charge[nom] = [_serialiser(l, nom) for l in lignes]
                fins[cle_curseur] = getattr(lignes[-1], colonne.key)

        if not charge:
            break

        reponse = _requete(db, "POST", "/api/sync/push", json=charge)
        _verifier(reponse)
        compte = reponse.json()
        for cle in ("visitors", "designs", "events", "events_ignores"):
            totaux[cle] += compte.get(cle, 0)
        totaux["envois"] += 1

        # Curseurs avances seulement maintenant : avant, une coupure aurait
        # fait sauter un lot.
        for cle_curseur, fin in fins.items():
            set_setting(db, cle_curseur, fin.isoformat())
        set_setting(db, "sync_last_push_at", datetime.now().astimezone().isoformat())
        db.commit()

        if all(len(v) < lot for v in charge.values()):
            break

    return totaux
