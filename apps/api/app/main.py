from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api import admin, auth, kiosk, relay, ws
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.deps import require_kiosk_basic_auth
from app.models import AdminUser, Kiosk
from app.security import hash_secret

STATIC = Path(settings.static_dir)
MEDIA = Path(settings.media_dir)


def bootstrap() -> None:
    """Cree les tables, le compte admin et une premiere borne au premier demarrage."""
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(AdminUser).limit(1)):
            db.add(
                AdminUser(
                    email=settings.admin_email.lower(),
                    password_hash=hash_secret(settings.admin_password),
                )
            )
        if not db.scalar(select(Kiosk).limit(1)):
            db.add(Kiosk(name="Borne salon 1", token=settings.default_kiosk_token))
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap()
    yield


app = FastAPI(title="AIXAM x BIG - Animation EASY", version="0.1.0", lifespan=lifespan)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(kiosk.router)
app.include_router(admin.router)
app.include_router(ws.router)

# Le relais de mailing n'existe que sur le back-office qui a accepte ce role.
# Volontairement pilote par le `.env` et non par les reglages a chaud : ouvrir
# une plateforme a l'envoi pour autrui ne doit pas tenir a une case cochee par
# erreur dans l'admin d'une machine posee sur un stand.
if settings.relay_server_enabled:
    app.include_router(relay.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


MEDIA.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA), name="media")


def _serve_spa(root: Path, sub_path: str) -> FileResponse:
    """Sert un fichier statique s'il existe, sinon index.html (routage cote client)."""
    if not root.is_dir():
        raise HTTPException(503, "Front non compile. Lancer `make build-front`.")
    candidate = (root / sub_path).resolve()
    if root.resolve() in candidate.parents and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(root / "index.html")


# La borne. Protegee par HTTP Basic quand KIOSK_BASIC_USER est defini, ce qui
# permet d'exposer le lien https pendant le developpement.
@app.get("/kiosk", dependencies=[Depends(require_kiosk_basic_auth)])
@app.get("/kiosk/{sub_path:path}", dependencies=[Depends(require_kiosk_basic_auth)])
def kiosk_spa(sub_path: str = "") -> FileResponse:
    return _serve_spa(STATIC / "kiosk", sub_path)


# Le back-office.
@app.get("/")
@app.get("/{sub_path:path}")
def admin_spa(sub_path: str = "") -> FileResponse:
    return _serve_spa(STATIC / "admin", sub_path)
