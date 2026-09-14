"""Synchronisation temps reel entre l'ecran tactile et le grand ecran.

Un canal par borne. L'ecran tactile publie l'etat de la composition, le grand
ecran s'y abonne. Le serveur ne fait que relayer et conserver le dernier etat,
pour qu'un ecran qui redemarre en pleine animation se resynchronise seul.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Kiosk

router = APIRouter(tags=["ws"])

_rooms: dict[str, set[WebSocket]] = defaultdict(set)
_last_state: dict[str, tuple[float, dict]] = {}
_lock = asyncio.Lock()

# Peremption de l'etat conserve.
#
# La borne renvoie « idle » d'elle-meme apres son delai d'inactivite, donc en
# temps normal cet etat ne survit pas a une session abandonnee. Mais ce minuteur
# vit dans la page : un onglet ferme, un plantage, la machine tactile qu'on
# redemarre, et plus personne n'envoie « idle ». Le serveur rejouerait alors la
# composition inachevee d'un visiteur a chaque ecran qui se connecte -- en
# public, indefiniment. Passe ce delai on considere la session perdue.
PEREMPTION_ETAT = 5 * 60


def _resolve_kiosk(token: str) -> str | None:
    with SessionLocal() as db:
        kiosk = db.scalar(select(Kiosk).where(Kiosk.token == token, Kiosk.is_active.is_(True)))
        return str(kiosk.id) if kiosk else None


@router.websocket("/ws/screens")
async def screens(websocket: WebSocket, token: str = Query(...), role: str = Query("display")):
    room = await asyncio.to_thread(_resolve_kiosk, token)
    if room is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    async with _lock:
        _rooms[room].add(websocket)
        garde = _last_state.get(room)
        if garde and time.monotonic() - garde[0] > PEREMPTION_ETAT:
            _last_state.pop(room, None)
            garde = None
        snapshot = garde[1] if garde else None

    if snapshot is not None and role != "touch":
        await websocket.send_json(snapshot)

    try:
        while True:
            message = await websocket.receive_json()
            async with _lock:
                kind = message.get("type")
                if kind == "state":
                    _last_state[room] = (time.monotonic(), message)
                elif kind in ("idle", "finished"):
                    # Fin de session : un ecran qui se (re)connecte ensuite ne
                    # doit pas recevoir la composition du visiteur precedent.
                    _last_state.pop(room, None)
                peers = [ws for ws in _rooms[room] if ws is not websocket]
            for peer in peers:
                try:
                    await peer.send_json(message)
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        async with _lock:
            _rooms[room].discard(websocket)
