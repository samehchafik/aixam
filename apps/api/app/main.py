from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from app.api import admin, auth, kiosk, relay, sync, ws
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.deps import require_kiosk_basic_auth
from app.models import AdminUser, Kiosk
from app.security import hash_secret
from app.services import materiel

STATIC = Path(settings.static_dir)
MEDIA = Path(settings.media_dir)
RENDERS = MEDIA / "renders"


# Colonnes ajoutees apres coup. `create_all` ne sait que creer des tables : il
# ignore une colonne manquante sur une table existante, et l'API tomberait au
# premier SELECT. Un outil de migration a lancer a la main se serait oublie
# entre le `git pull` et le redemarrage -- ces ALTER sont additifs, idempotents
# et instantanes, donc ils tiennent leur place ici.
COLONNES_AJOUTEES = (
    "ALTER TABLE designs ADD COLUMN IF NOT EXISTS moderation VARCHAR(12) NOT NULL DEFAULT 'pending'",
    "ALTER TABLE designs ADD COLUMN IF NOT EXISTS moderated_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS ix_designs_moderation ON designs (moderation)",
    "ALTER TABLE designs ADD COLUMN IF NOT EXISTS skin VARCHAR(80)",
    "CREATE INDEX IF NOT EXISTS ix_designs_skin ON designs (skin)",
    # Les calques citaient le catalogue par identifiant : un fond renomme et la
    # creation devenait irreconstituable. On ne les a jamais relus pour
    # re-rendre, et le PNG -- produit une fois, a la validation -- est
    # desormais ce qui voyage et ce qu'on garde. Cette recette qu'on ne peut
    # plus suivre n'a plus lieu d'etre.
    "ALTER TABLE designs DROP COLUMN IF EXISTS layers",
)


def bootstrap() -> None:
    """Cree les tables, le compte admin et une premiere borne au premier demarrage."""
    Base.metadata.create_all(engine)
    with engine.begin() as connexion:
        for ordre in COLONNES_AJOUTEES:
            connexion.execute(text(ordre))
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
    # Le releve des ecrans, pour le back-office local du stand. Sans effet
    # ailleurs -- sur le serveur Linux il ecrit simplement « indisponible ».
    try:
        materiel.ecrire()
    except Exception as exc:  # noqa: BLE001 -- accessoire : jamais au prix du demarrage
        print(f"releve des ecrans non ecrit : {exc}")
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

# La remontee des donnees du stand. Meme principe, role distinct : accepter
# des visiteurs nominatifs n'est pas accepter de poster un email.
if settings.sync_server_enabled:
    app.include_router(sync.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


class FichiersCaches(StaticFiles):
    """StaticFiles qui dit au navigateur combien de temps garder ce qu'il recoit.

    Sans `Cache-Control`, une reponse qui porte seulement `Last-Modified` est
    soumise a la FRAICHEUR HEURISTIQUE : le navigateur s'autorise a la garder
    sans rien redemander, couramment un dixieme de son age. Un element du
    catalogue vieux d'un mois est donc tenu pour frais pendant trois jours. Un
    deploiement corrigeait le fichier sur le serveur sans que personne le voie.
    """

    def __init__(self, *args, cache: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cache = cache

    def file_response(self, *args, **kwargs) -> Response:
        reponse = super().file_response(*args, **kwargs)
        reponse.headers["Cache-Control"] = self._cache
        return reponse


MEDIA.mkdir(parents=True, exist_ok=True)
RENDERS.mkdir(parents=True, exist_ok=True)

# Le nom d'une creation ne designera jamais une autre image : les PNG portent
# l'empreinte de leur contenu, les JPEG d'avant un identifiant unique. Elles se
# gardent donc sans limite et sans jamais redemander. Monte AVANT /media : la
# route la plus precise doit gagner.
app.mount(
    "/media/renders",
    FichiersCaches(directory=RENDERS, cache="public, max-age=31536000, immutable"),
    name="renders",
)
# Le catalogue, lui, change sous le meme nom : fond_3.svg d'aujourd'hui n'est
# pas celui d'hier. `no-cache` ne dit pas « ne garde rien », il dit « redemande
# avant de servir » -- avec l'ETag, un 304 de quelques octets quand rien n'a
# bouge, et le nouveau fichier le jour ou il bouge.
app.mount(
    "/media",
    FichiersCaches(directory=MEDIA, cache="no-cache"),
    name="media",
)


def _serve_spa(root: Path, sub_path: str) -> FileResponse:
    """Sert un fichier statique s'il existe, sinon index.html (routage cote client).

    Deux regimes de cache, parce que les deux natures de fichiers n'ont pas les
    memes besoins.

    Les fichiers compiles portent une empreinte dans leur nom : leur contenu ne
    changera jamais, on les garde donc un an sans jamais revenir demander.

    index.html, lui, garde le meme nom et designe ces empreintes. Sans en-tete,
    le navigateur decide seul combien de temps le garder, et peut resservir
    l'ancien longtemps apres un deploiement -- la borne montre alors une
    version perimee sans que rien ne l'indique. On demande donc a le revalider
    a chaque fois : c'est un seul aller-retour, et il rend la mise a jour
    immediate.
    """
    if not root.is_dir():
        raise HTTPException(503, "Front non compile. Lancer `bin/build.sh --all`.")

    candidate = (root / sub_path).resolve()
    if root.resolve() in candidate.parents and candidate.is_file():
        fige = candidate.parent.name == "assets"
        cache = "public, max-age=31536000, immutable" if fige else "no-cache"
        return FileResponse(candidate, headers={"Cache-Control": cache})

    return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})


# La borne. Protegee par HTTP Basic quand KIOSK_BASIC_USER est defini, ce qui
# permet d'exposer le lien https pendant le developpement.
#
# La barre oblique finale n'est pas cosmetique : le bundle est compile en
# chemins relatifs (`base: './'`, pour tourner aussi bien sous /kiosk/ que
# depuis un fichier local en mode Tauri). Servi a /kiosk, `./assets/x.js` se
# resout donc a /assets/x.js -- ou c'est le back-office qui repond son
# index.html. Le navigateur refuse d'executer du HTML comme script, et la
# borne reste blanche sans rien dire. On redirige plutot que de servir.
@app.get("/kiosk", dependencies=[Depends(require_kiosk_basic_auth)])
def kiosk_racine() -> RedirectResponse:
    return RedirectResponse("/kiosk/", status_code=308)


@app.get("/kiosk/{sub_path:path}", dependencies=[Depends(require_kiosk_basic_auth)])
def kiosk_spa(sub_path: str = "") -> FileResponse:
    return _serve_spa(STATIC / "kiosk", sub_path)


# Le back-office.
@app.get("/")
@app.get("/{sub_path:path}")
def admin_spa(sub_path: str = "") -> FileResponse:
    return _serve_spa(STATIC / "admin", sub_path)
