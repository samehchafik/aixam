"""Les deux SPA sont servies a la bonne adresse.

Le piege : le bundle de la borne est compile en chemins relatifs (`base:
'./'`, pour tourner aussi bien sous /kiosk/ qu'en mode Tauri). Servi a
/kiosk sans barre finale, `./assets/x.js` se resout a /assets/x.js -- ou
c'est le back-office qui repond son index.html. Le navigateur refuse
d'executer du HTML comme script et la borne reste blanche, sans erreur
serveur : rien dans les journaux n'accuse la cause.

    ../../.venv/bin/python tests/test_routes_spa.py     (depuis apps/api)
"""

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import check, on_path, report, reset_database

STATIC = Path(tempfile.mkdtemp())
for nom, marque in (("admin", "BACK-OFFICE"), ("kiosk", "BORNE")):
    (STATIC / nom / "assets").mkdir(parents=True)
    (STATIC / nom / "index.html").write_text(
        f'<!doctype html><title>{marque}</title><script type="module" src="./assets/{nom}.js"></script>'
    )
    (STATIC / nom / "assets" / f"{nom}.js").write_text(f"// {marque}")

os.environ.update(
    DATABASE_URL=reset_database("aixam_test_routes"),
    STATIC_DIR=str(STATIC), MEDIA_DIR=tempfile.mkdtemp(),
    KIOSK_BASIC_USER="", ADMIN_EMAIL="a@aixam-test.fr", ADMIN_PASSWORD="x",
)
on_path()

from fastapi.testclient import TestClient

from app.main import app, bootstrap

bootstrap()
c = TestClient(app)

print("\n[1] Chaque SPA a son adresse")
check("/ sert le back-office", "BACK-OFFICE" in c.get("/").text)
check("/kiosk/ sert la borne", "BORNE" in c.get("/kiosk/").text)

print("\n[2] /kiosk sans barre finale redirige, il ne sert pas")
r = c.get("/kiosk", follow_redirects=False)
check("redirection permanente", r.status_code == 308, r.status_code)
check("vers /kiosk/", r.headers.get("location") == "/kiosk/", r.headers.get("location"))
check("en suivant, on obtient la borne", "BORNE" in c.get("/kiosk").text)

print("\n[3] Le script de la borne se charge depuis /kiosk/")
# C'est le test qui aurait attrape la panne : le chemin relatif resolu
# depuis /kiosk/ doit rendre du JavaScript, pas la page du back-office.
page = c.get("/kiosk/").text
relatif = re.search(r'src="\./([^"]+)"', page).group(1)
r = c.get(f"/kiosk/{relatif}")
check("le script existe", r.status_code == 200, r.status_code)
check("c'est bien celui de la borne", "BORNE" in r.text, r.text[:40])

# Ce que le navigateur aurait demande sans la barre finale.
r = c.get(f"/{relatif}")
check("a la racine, ce chemin ne rend PAS le script de la borne", "BORNE" not in r.text)

sys.exit(report())
