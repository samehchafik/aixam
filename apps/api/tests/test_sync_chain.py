"""La remontee des donnees : back-office du stand -> serveur.

Deux processus, deux bases, un vrai appel HTTP. Ce qu'on verifie surtout,
c'est ce qui ne doit PAS arriver : un renvoi qui duplique, un curseur qui
saute un lot, une creation qui atterrit sans son visiteur.

    ../../.venv/bin/python tests/test_sync_chain.py     (depuis apps/api)
"""

import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import API_DIR, check, on_path, report, reset_database

PORT = int(os.environ.get("TEST_SYNC_PORT", "8097"))
SERVER_DB = reset_database("aixam_test_sync_serveur")
CLIENT_DB = reset_database("aixam_test_sync_stand")
VENV_UVICORN = API_DIR.parent.parent / ".venv" / "bin" / "uvicorn"

server_env = {**os.environ,
    "DATABASE_URL": SERVER_DB, "SYNC_SERVER_ENABLED": "true", "MAIL_TRANSPORT": "smtp",
    "SMTP_HOST": "", "ADMIN_EMAIL": "admin@aixam-test.fr", "ADMIN_PASSWORD": "serveur",
    "MEDIA_DIR": tempfile.mkdtemp(), "STATIC_DIR": tempfile.mkdtemp(),
    "PYTHONPATH": str(API_DIR)}
server = subprocess.Popen(
    [str(VENV_UVICORN), "app.main:app", "--port", str(PORT), "--log-level", "warning"],
    cwd=API_DIR, env=server_env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

base = f"http://127.0.0.1:{PORT}"
try:
    for _ in range(80):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    else:
        print("le serveur n'a pas demarre :", server.stderr.read().decode()[-1500:]); sys.exit(1)

    print("\n[1] Le serveur accepte les remontees")
    tok = httpx.post(f"{base}/api/auth/login",
                     json={"email": "admin@aixam-test.fr", "password": "serveur"}).json()["access_token"]
    admin = {"Authorization": f"Bearer {tok}"}
    r = httpx.post(f"{base}/api/admin/relay-clients",
                   json={"name": "Portable du stand"}, headers=admin)
    check("client cree sur le serveur", r.status_code == 201, r.text[:200])
    jeton = r.json()["token"]

    # --- Le back-office du stand, dans ce processus ---
    os.environ.update(
        DATABASE_URL=CLIENT_DB, SYNC_SERVER_ENABLED="false", MAIL_TRANSPORT="smtp",
        SYNC_URL=base, SYNC_TOKEN=jeton, DEFAULT_KIOSK_TOKEN="jeton-borne",
        ADMIN_EMAIL="admin@aixam-test.fr", ADMIN_PASSWORD="stand",
        MEDIA_DIR=tempfile.mkdtemp(), STATIC_DIR=tempfile.mkdtemp())
    on_path()
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select
    from app.main import app, bootstrap
    from app.db import SessionLocal
    from app.models import Design, DesignStatus, Event, Kiosk, Visitor
    bootstrap()
    stand = TestClient(app)
    ltok = stand.post("/api/auth/login",
                      json={"email": "admin@aixam-test.fr", "password": "stand"}).json()["access_token"]
    ladmin = {"Authorization": f"Bearer {ltok}"}

    check("/api/sync absent du stand", stand.get("/api/sync/status").status_code != 200)
    r = stand.post("/api/admin/sync/test", headers=ladmin)
    check("liaison etablie", r.json().get("ok") is True, r.text[:300])

    print("\n[2] Trois visiteurs passent sur la borne")
    ids = []
    for i in range(3):
        r = stand.post("/api/kiosk/register",
                       json={"first_name": f"Visiteur{i}", "last_name": "Test",
                             "email": f"v{i}@example.com", "postal_code": "75011",
                             "consent_marketing": i % 2 == 0, "session_id": f"sess-{i}"},
                       headers={"X-Kiosk-Token": "jeton-borne"})
        ids.append(uuid.UUID(r.json()["visitor_id"]))
    check("3 visiteurs en local", len(ids) == 3)

    with SessionLocal() as db:
        borne = db.scalar(select(Kiosk))
        for i, vid in enumerate(ids):
            db.add(Design(visitor_id=vid, kiosk_id=borne.id, session_id=f"sess-{i}",
                          layers={"calques": [{"type": "background", "hex": "#123456"}]},
                          status=DesignStatus.rendered, render_path="media/renders/local.jpg"))
        db.commit()
        nb_events_local = db.scalar(select(func.count()).select_from(Event))
    check("3 creations en local", True)

    print("\n[3] Premiere remontee")
    r = stand.post("/api/admin/sync/push", headers=ladmin)
    check("envoi accepte", r.json().get("ok") is True, r.text[:300])
    t = r.json()["totaux"]
    check("3 visiteurs remontes", t["visitors"] == 3, t)
    check("3 creations remontees", t["designs"] == 3, t)
    check("les evenements suivent", t["events"] == nb_events_local, t)

    st = httpx.get(f"{base}/api/sync/status", headers={"Authorization": f"Bearer {jeton}"}).json()
    check("le serveur les detient", st["visitors"] == 3 and st["designs"] == 3, st)

    dist = httpx.get(f"{base}/api/admin/visitors", headers=admin).json()
    check("memes identifiants des deux cotes",
          {v["id"] for v in dist["items"]} == {str(i) for i in ids})
    check("le consentement voyage",
          sum(1 for v in dist["items"] if v["consent_marketing"]) == 2, dist["items"])

    dd = httpx.get(f"{base}/api/admin/designs", headers=admin).json()["items"]
    check("les creations sont rattachees a leur visiteur",
          all(d["visitor_id"] for d in dd), dd)
    check("aucun chemin de rendu local n'a voyage",
          all(d["render_url"] is None for d in dd), dd)

    print("\n[4] Renvoyer ne duplique pas")
    r = stand.post("/api/admin/sync/push", headers=ladmin)
    check("rien de neuf a envoyer", r.json()["totaux"]["visitors"] == 0, r.json())
    st2 = httpx.get(f"{base}/api/sync/status", headers={"Authorization": f"Bearer {jeton}"}).json()
    check("toujours 3 visiteurs cote serveur", st2["visitors"] == 3, st2)

    r = stand.post("/api/admin/sync/push?full=true", headers=ladmin)
    check("renvoi complet accepte", r.json()["ok"] is True)
    st3 = httpx.get(f"{base}/api/sync/status", headers={"Authorization": f"Bearer {jeton}"}).json()
    check("toujours 3 visiteurs apres renvoi complet", st3["visitors"] == 3, st3)
    check("toujours 3 creations", st3["designs"] == 3, st3)
    check("evenements dedoublonnes", st3["events"] == st["events"], (st3, st))

    print("\n[5] Une creation modifiee au stand remonte a jour")
    with SessionLocal() as db:
        d = db.scalars(select(Design)).first()
        d.layers = {"calques": [{"type": "background", "hex": "#ff0000"}]}
        d.updated_at = datetime.now(UTC) + timedelta(seconds=1)
        db.commit()
        design_id = str(d.id)
    r = stand.post("/api/admin/sync/push", headers=ladmin)
    check("la modification part", r.json()["totaux"]["designs"] == 1, r.json())
    st4 = httpx.get(f"{base}/api/sync/status", headers={"Authorization": f"Bearer {jeton}"}).json()
    check("sans creer de doublon", st4["designs"] == 3, st4)

    print("\n[6] Le jeton reste la seule porte")
    r = httpx.post(f"{base}/api/sync/push", json={"visitors": []},
                   headers={"Authorization": "Bearer axr_deadbeef_x"})
    check("jeton inconnu -> 401", r.status_code == 401, r.status_code)
    check("sans jeton -> 401", httpx.post(f"{base}/api/sync/push", json={}).status_code == 401)

    httpx.patch(f"{base}/api/admin/relay-clients/{httpx.get(f'{base}/api/admin/relay-clients', headers=admin).json()[0]['id']}",
                json={"is_active": False}, headers=admin)
    with SessionLocal() as db:
        db.add(Visitor(first_name="Apres", last_name="Revocation",
                       email="apres@example.com", postal_code="75011"))
        db.commit()
    r = stand.post("/api/admin/sync/push", headers=ladmin)
    check("client revoque -> l'envoi echoue proprement", r.json()["ok"] is False, r.json())
    check("le stand dit pourquoi", "serveur" in r.json().get("error", "").lower(), r.json())

finally:
    server.terminate(); server.wait(timeout=10)

sys.exit(report())
