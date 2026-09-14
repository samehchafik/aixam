"""Le trajet complet : back-office LOCAL -> back-office DISTANT.

Deux processus, deux bases, un vrai appel HTTP entre les deux. C'est le test
qui repond a « est-ce que ca marchera sur le stand » : un visiteur s'inscrit
sur la borne, l'email part par le relais, le distant le recoit ; on coupe le
client, on le rouvre, on rejoue un message deja passe.

    ../../.venv/bin/python tests/test_relay_chain.py     (depuis apps/api)
"""

import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import API_DIR, check, on_path, report, reset_database

PORT = int(os.environ.get("TEST_RELAY_PORT", "8099"))
SERVER_DB = reset_database("aixam_test_bo_distant")
CLIENT_DB = reset_database("aixam_test_bo_local")
VENV_UVICORN = API_DIR.parent.parent / ".venv" / "bin" / "uvicorn"

# --- Le back-office DISTANT, dans son propre processus ---
server_env = {**os.environ,
    "DATABASE_URL": SERVER_DB, "RELAY_SERVER_ENABLED": "true", "MAIL_TRANSPORT": "smtp",
    "SMTP_HOST": "", "ADMIN_EMAIL": "admin@aixam-test.fr", "ADMIN_PASSWORD": "distant",
    "MEDIA_DIR": tempfile.mkdtemp(prefix="distant-media-"), "STATIC_DIR": tempfile.mkdtemp(),
    "PYTHONPATH": str(API_DIR)}
server = subprocess.Popen(
    [str(VENV_UVICORN), "app.main:app", "--port", str(PORT), "--log-level", "warning"],
    cwd=API_DIR, env=server_env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

base = f"http://127.0.0.1:{PORT}"
try:
    for _ in range(80):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200: break
        except httpx.HTTPError: pass
        time.sleep(0.25)
    else:
        print("le BO distant n'a pas demarre:", server.stderr.read().decode()[-2000:]); sys.exit(1)

    print("\n[1] Le BO distant est debout et expose le relais")
    check("healthz", httpx.get(f"{base}/healthz").json()["status"] == "ok")
    tok = httpx.post(f"{base}/api/auth/login",
                     json={"email": "admin@aixam-test.fr", "password": "distant"}).json()["access_token"]
    admin = {"Authorization": f"Bearer {tok}"}
    r = httpx.post(f"{base}/api/admin/relay-clients",
                   json={"name": "Borne Mondial 2026", "daily_quota": 100}, headers=admin)
    check("client de relais cree depuis le BO distant", r.status_code == 201, r.text[:200])
    relay_token = r.json()["token"]
    print(f"       token remis une seule fois : {relay_token[:16]}...")

    # --- Le back-office LOCAL, dans ce processus ---
    os.environ.update(
        DATABASE_URL=CLIENT_DB, RELAY_SERVER_ENABLED="false",
        MAIL_TRANSPORT="relay", MAIL_RELAY_URL=base, MAIL_RELAY_TOKEN=relay_token,
        ADMIN_EMAIL="admin@aixam-test.fr", ADMIN_PASSWORD="local",
        DEFAULT_KIOSK_TOKEN="jeton-borne-test",
        MEDIA_DIR=tempfile.mkdtemp(prefix="local-media-"), STATIC_DIR=tempfile.mkdtemp())
    on_path()
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from app.main import app, bootstrap
    from app.db import SessionLocal
    from app.models import EmailOutbox, OutboxStatus
    from app.workers.outbox import process_batch
    bootstrap()
    local = TestClient(app)

    print("\n[2] Le BO local voit la liaison")
    ltok = local.post("/api/auth/login",
                      json={"email": "admin@aixam-test.fr", "password": "local"}).json()["access_token"]
    ladmin = {"Authorization": f"Bearer {ltok}"}
    cfg = local.get("/api/admin/mail", headers=ladmin).json()
    check("transport = relay", cfg["transport"] == "relay", cfg)
    r = local.post("/api/admin/mail/test-relay", headers=ladmin)
    check("test de liaison OK", r.json().get("ok") is True, r.text[:300])
    check("le distant se presente", r.json()["remote"]["client"] == "Borne Mondial 2026", r.json())
    check("quota annonce", r.json()["remote"]["remaining_today"] == 100, r.json())
    check("relais non ouvert sur le BO local", cfg["relay_server_enabled"] is False)
    check("/api/relay absent du BO local", local.get("/api/relay/ping").status_code != 200)

    print("\n[3] Un visiteur s'inscrit sur la borne")
    r = local.post("/api/kiosk/register",
                   json={"first_name": "Camille", "last_name": "Durand",
                         "email": "camille.durand@example.com", "postal_code": "75011",
                         "consent_marketing": True, "session_id": "sess-test-1"},
                   headers={"X-Kiosk-Token": "jeton-borne-test"})
    check("inscription acceptee", r.status_code == 200, r.text[:300])
    check("verification demandee", r.json()["verification_required"] is True)
    with SessionLocal() as db:
        item = db.scalar(select(EmailOutbox))
        check("email en file LOCALE, pas encore parti", item is not None and item.status == OutboxStatus.pending)
        check("le visiteur n'a pas attendu le reseau", item.attempts == 0)
        local_id, subject = str(item.id), item.subject

    print("\n[4] Le worker local passe le relais")
    check("worker : 1 message traite", process_batch() == 1)
    with SessionLocal() as db:
        item = db.get(EmailOutbox, uuid.UUID(local_id))
        check("marque envoye cote local", item.status == OutboxStatus.sent, item.last_error)

    rows = httpx.get(f"{base}/api/admin/emails", headers=admin).json()
    check("arrive dans la file du BO DISTANT", len(rows) == 1, rows)
    check("bon destinataire", rows[0]["to"] == "camille.durand@example.com", rows[0])
    check("bon objet", rows[0]["subject"] == subject, rows[0])
    used = httpx.get(f"{base}/api/admin/relay-clients", headers=admin).json()[0]
    check("compteur du client incremente", used["sent_today"] == 1 and used["sent_total"] == 1, used)

    print("\n[5] Le distant coupe le client -> le local le voit, sans perdre le mail")
    cid = used["id"]
    httpx.patch(f"{base}/api/admin/relay-clients/{cid}", json={"is_active": False}, headers=admin)
    local.post("/api/kiosk/register",
               json={"first_name": "Alex", "last_name": "Martin", "email": "alex@example.com",
                     "postal_code": "69003", "consent_marketing": False, "session_id": "sess-test-2"},
               headers={"X-Kiosk-Token": "jeton-borne-test"})
    process_batch()
    with SessionLocal() as db:
        item = db.scalars(select(EmailOutbox).order_by(EmailOutbox.created_at.desc())).first()
        check("echec permanent, pas 8 essais inutiles", item.status == OutboxStatus.failed, item.status)
        check("l'admin lit la cause", "relais" in (item.last_error or "").lower(), item.last_error)
        failed_id = str(item.id)
    check("le distant n'a rien recu de plus",
          len(httpx.get(f"{base}/api/admin/emails", headers=admin).json()) == 1)

    print("\n[6] Le distant rouvre -> relance depuis le BO local")
    httpx.patch(f"{base}/api/admin/relay-clients/{cid}", json={"is_active": True}, headers=admin)
    local.post("/api/admin/emails/retry-failed", headers=ladmin)
    process_batch()
    with SessionLocal() as db:
        item = db.get(EmailOutbox, uuid.UUID(failed_id))
        check("parti a la relance", item.status == OutboxStatus.sent, item.last_error)
    check("2 emails cote distant", len(httpx.get(f"{base}/api/admin/emails", headers=admin).json()) == 2)

    print("\n[7] Idempotence de bout en bout : on rejoue un message deja passe")
    with SessionLocal() as db:
        item = db.get(EmailOutbox, uuid.UUID(local_id))
        item.status = OutboxStatus.pending
        db.commit()
    process_batch()
    check("toujours 2 emails cote distant (pas de doublon)",
          len(httpx.get(f"{base}/api/admin/emails", headers=admin).json()) == 2)
    used = httpx.get(f"{base}/api/admin/relay-clients", headers=admin).json()[0]
    check("quota non reconsomme par le rejeu", used["sent_today"] == 2, used)

finally:
    server.terminate(); server.wait(timeout=10)

sys.exit(report())
