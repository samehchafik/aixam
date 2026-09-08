"""Le back-office recoit les donnees d'un autre back-office.

Sens unique, par construction : le stand produit, le serveur consolide. Le
serveur ne modifie jamais ces lignes de son cote, il les accumule -- ce qui
evite d'avoir a arbitrer entre deux versions d'une meme ligne, et supprime la
categorie de bugs qui fait echouer les synchronisations bidirectionnelles.

Monte seulement si `SYNC_SERVER_ENABLED=true`, separement du relais d'emails :
recevoir des visiteurs nominatifs n'est pas le meme engagement que poster un
message pour autrui.

Renvoyer deux fois le meme lot est sans effet : `visitors` et `designs` se
reinserent-ou-se-mettent-a-jour sur leur cle UUID, `events` se dedoublonne sur
(session_id, name, created_at). Une remontee interrompue se relance donc sans
precaution.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_relay_client
from app.models import Design, Event, RelayClient, Visitor
from app.schemas import SyncPushIn, SyncPushOut

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/status")
def status(
    client: RelayClient = Depends(current_relay_client),
    db: Session = Depends(get_db),
) -> dict:
    """De quoi verifier la liaison, et voir ce que le serveur detient deja."""
    count = lambda m: db.scalar(select(func.count()).select_from(m)) or 0  # noqa: E731
    return {
        "ok": True,
        "client": client.name,
        "visitors": count(Visitor),
        "designs": count(Design),
        "events": count(Event),
    }


@router.post("/push", response_model=SyncPushOut)
def push(
    payload: SyncPushIn,
    client: RelayClient = Depends(current_relay_client),
    db: Session = Depends(get_db),
) -> SyncPushOut:
    out = SyncPushOut()

    # Les visiteurs d'abord : les creations y font reference.
    if payload.visitors:
        rows = [v.model_dump() for v in payload.visitors]
        for row in rows:
            row["email"] = row["email"].lower()
        stmt = insert(Visitor).values(rows)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[Visitor.id],
                set_={
                    c: stmt.excluded[c]
                    for c in (
                        "first_name", "last_name", "email", "postal_code",
                        "email_verified_at", "consent_marketing", "consent_at",
                    )
                },
            )
        )
        out.visitors = len(rows)

    if payload.designs:
        # kiosk_id reste vide : la borne n'existe pas dans cette base, et la
        # cle etrangere refuserait un identifiant inconnu.
        rows = [d.model_dump() | {"kiosk_id": None, "render_path": None} for d in payload.designs]
        stmt = insert(Design).values(rows)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[Design.id],
                set_={
                    c: stmt.excluded[c]
                    for c in ("visitor_id", "session_id", "layers", "status",
                              "shared_hint", "updated_at")
                },
            )
        )
        out.designs = len(rows)

    if payload.events:
        # Cle entiere : on ne peut pas s'appuyer sur l'identifiant. On demande
        # a la base lesquels de ces triplets elle connait deja, en une requete
        # plutot qu'une par evenement.
        cles = [(e.session_id, e.name, e.created_at) for e in payload.events]
        connus = set(
            db.execute(
                select(Event.session_id, Event.name, Event.created_at).where(
                    tuple_(Event.session_id, Event.name, Event.created_at).in_(cles)
                )
            ).all()
        )
        nouveaux = [
            e.model_dump() | {"kiosk_id": None}
            for e in payload.events
            if (e.session_id, e.name, e.created_at) not in connus
        ]
        if nouveaux:
            db.execute(insert(Event).values(nouveaux))
        out.events = len(nouveaux)
        out.events_ignores = len(payload.events) - len(nouveaux)

    client.last_seen_at = func.now()
    db.commit()
    return out
