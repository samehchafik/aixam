"""Synchronisation temps reel entre l'ecran tactile et le grand ecran.

Un canal par borne. L'ecran tactile publie l'etat de la composition, le grand
ecran s'y abonne. Le serveur ne fait que relayer et conserver le dernier etat,
pour qu'un ecran qui redemarre en pleine animation se resynchronise seul.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Kiosk

router = APIRouter(tags=["ws"])

_rooms: dict[str, set[WebSocket]] = defaultdict(set)
_last_state: dict[str, dict] = {}
_lock = asyncio.Lock()


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
        snapshot = _last_state.get(room)

    if snapshot is not None and role != "touch":
        await websocket.send_json(snapshot)

    try:
        while True:
            message = await websocket.receive_json()
            async with _lock:
                kind = message.get("type")
                if kind == "state":
                    _last_state[room] = message
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
