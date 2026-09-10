"""Le relais de mailing, vu du back-office qui EXPEDIE pour les autres.

Couvre ce qui empeche la plateforme de devenir un relais ouvert : le token et
sa forme, les quotas, les tailles, l'expediteur impose, l'idempotence et la
revocation. Le trajet complet entre deux back-offices est teste separement,
dans test_relay_chain.py.

    ../../.venv/bin/python tests/test_relay.py     (depuis apps/api)
"""

import base64
import os
import sys
import tempfile
import uuid

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from _harness import check, on_path, report, reset_database

DB = reset_database("aixam_test_relay")

os.environ.update(
    DATABASE_URL=DB,
    RELAY_SERVER_ENABLED="true",
    MAIL_TRANSPORT="smtp",
    SMTP_HOST="smtp.example.invalid",
    ADMIN_EMAIL="admin@aixam-test.fr",
    ADMIN_PASSWORD="test-password",
    MEDIA_DIR=tempfile.mkdtemp(prefix="aixam-media-"),
    STATIC_DIR=tempfile.mkdtemp(prefix="aixam-static-"),
    RELAY_MAX_BODY_BYTES="2048",
    RELAY_MAX_ATTACHMENT_BYTES="1024",
)
on_path()

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app, bootstrap
from app.db import SessionLocal
from app.models import EmailOutbox, RelayClient
from app.security import token_indice
from app.services.transports import PermanentSendError
from app.services.transports import relay as relay_transport

bootstrap()
client = TestClient(app)

# --- admin ---
r = client.post("/api/auth/login", json={"email": "admin@aixam-test.fr", "password": "test-password"})
admin = {"Authorization": f"Bearer {r.json()['access_token']}"}
check("login admin", r.status_code == 200, r.text[:200])

print("\n[1] Creation d'un client de relais")
r = client.post("/api/admin/relay-clients", json={"name": "Borne salon", "daily_quota": 5}, headers=admin)
check("cree", r.status_code == 201, r.text[:300])
created = r.json()
token = created["token"]
cid = created["id"]
check("token de la forme axr_<prefixe>_<secret>", token.startswith("axr_") and token.count("_") >= 2, token[:20])
check("prefixe expose, secret non", created["token_prefix"] in token and created["token_prefix"] != token)

with SessionLocal() as db:
    row = db.get(RelayClient, uuid.UUID(cid))
    check("secret jamais stocke en clair", token.split("_", 2)[2] not in row.token_hash)
    check("hash argon2", row.token_hash.startswith("$argon2"))

r = client.get("/api/admin/relay-clients", headers=admin)
check("la liste ne rend jamais le token", "token" not in r.json()[0], str(r.json()[0]))

relay = {"Authorization": f"Bearer {token}"}

print("\n[1 bis] Montrer un jeton sans le livrer")
check("l'indice s'arrete au prefixe", token_indice(token) == f"axr_{created['token_prefix']}",
      token_indice(token))
# Le secret est du base64url et contient des « _ » : c'est la premiere
# coupure qui compte, pas la derniere.
check("le secret n'y figure pas", token.split("_", 2)[2] not in token_indice(token))
check("pas de jeton, pas d'indice", token_indice("") == "")
check("d'une forme inattendue, quatre caracteres au plus",
      len(token_indice("vieux-jeton-saisi-a-la-main")) == 4)

print("\n[2] Authentification")
check("ping accepte", client.get("/api/relay/ping", headers=relay).status_code == 200)
check("sans token -> 401", client.get("/api/relay/ping").status_code == 401)
check("token bidon -> 401", client.get("/api/relay/ping", headers={"Authorization": "Bearer axr_deadbeef_x"}).status_code == 401)
check("forme invalide -> 401", client.get("/api/relay/ping", headers={"Authorization": "Bearer nimportequoi"}).status_code == 401)
bad = token[:-4] + "AAAA"
check("bon prefixe + mauvais secret -> 401", client.get("/api/relay/ping", headers={"Authorization": f"Bearer {bad}"}).status_code == 401)

print("\n[3] Envoi et idempotence")
msg = {"message_id": "m-1", "to": "visiteur@example.com", "subject": "Votre creation", "body_html": "<p>bonjour</p>"}
r = client.post("/api/relay/send", json=msg, headers=relay)
check("accepte", r.status_code == 200 and r.json()["accepted"], r.text[:300])
first = r.json()
check("quota decompte (5 -> 4)", first["remaining_today"] == 4, first)

with SessionLocal() as db:
    item = db.get(EmailOutbox, uuid.UUID(first["outbox_id"]))
    check("ligne dans l'outbox du serveur", item is not None and item.to_email == "visiteur@example.com")

r2 = client.post("/api/relay/send", json=msg, headers=relay)
check("rejeu -> doublon reconnu", r2.json()["duplicate"] is True, r2.text[:200])
check("rejeu -> meme outbox_id", r2.json()["outbox_id"] == first["outbox_id"])
check("rejeu -> quota non reconsomme", r2.json()["remaining_today"] == 4, r2.json())
with SessionLocal() as db:
    n = db.scalar(select(func.count()).select_from(EmailOutbox))
    check("un seul email en file apres le rejeu", n == 1, f"n={n}")

print("\n[4] Expediteur impose par le serveur")
r = client.post("/api/relay/send", json={**msg, "message_id": "m-2", "from": "pirate@ailleurs.com",
                                          "sender": {"email": "pirate@ailleurs.com"}}, headers=relay)
check("champ expediteur ignore (schema ferme)", r.status_code == 200)
with SessionLocal() as db:
    item = db.get(EmailOutbox, uuid.UUID(r.json()["outbox_id"]))
    from app.services.transports import Outgoing
    from app.services.transports.smtp import build_message
    check("From = celui du serveur", "pirate" not in build_message(Outgoing.from_outbox(item))["From"])

print("\n[5] Un seul destinataire")
r = client.post("/api/relay/send", json={**msg, "message_id": "m-3", "to": ["a@b.com", "c@d.com"]}, headers=relay)
check("liste de destinataires refusee -> 422", r.status_code == 422, r.status_code)

print("\n[6] Tailles plafonnees")
r = client.post("/api/relay/send", json={**msg, "message_id": "m-4", "body_html": "x" * 3000}, headers=relay)
check("corps trop gros -> 413", r.status_code == 413, r.text[:200])
big = base64.b64encode(b"y" * 2000).decode()
r = client.post("/api/relay/send", json={**msg, "message_id": "m-5",
    "attachment": {"filename": "gros.jpg", "content_type": "image/jpeg", "content_b64": big}}, headers=relay)
check("piece jointe trop grosse -> 413", r.status_code == 413, r.text[:200])
r = client.post("/api/relay/send", json={**msg, "message_id": "m-6",
    "attachment": {"filename": "x.jpg", "content_type": "image/jpeg", "content_b64": "pas du base64!!"}}, headers=relay)
check("base64 invalide -> 422", r.status_code == 422, r.text[:200])

print("\n[7] Piece jointe valide et traversee de dossier")
content = b"\xff\xd8\xff-jpeg-de-test"
r = client.post("/api/relay/send", json={**msg, "message_id": "m-7",
    "attachment": {"filename": "../../../../etc/evil.jpg", "content_type": "image/jpeg",
                   "content_b64": base64.b64encode(content).decode()}}, headers=relay)
check("acceptee", r.status_code == 200, r.text[:300])
with SessionLocal() as db:
    item = db.get(EmailOutbox, uuid.UUID(r.json()["outbox_id"]))
    path = item.attachment_path
    check("ecrite sous media/relay/<client>", f"relay/{cid}" in path, path)
    check("aucun ../ dans le chemin", ".." not in path, path)
    check("contenu intact", open(path, "rb").read() == content)

print("\n[8] Quota journalier")
r = client.patch(f"/api/admin/relay-clients/{cid}", json={"daily_quota": 1}, headers=admin)
check("quota abaisse a 1", r.json()["daily_quota"] == 1)
r = client.post("/api/relay/send", json={**msg, "message_id": "m-8"}, headers=relay)
check("au-dela du quota -> 429", r.status_code == 429, r.text[:200])
check("Retry-After present", "retry-after" in {k.lower() for k in r.headers})
r = client.post("/api/relay/send", json=msg, headers=relay)  # m-1, deja connu
check("un doublon passe meme quota plein", r.status_code == 200 and r.json()["duplicate"], r.status_code)

print("\n[9] Revocation")
client.patch(f"/api/admin/relay-clients/{cid}", json={"is_active": False}, headers=admin)
check("client desactive -> 401", client.get("/api/relay/ping", headers=relay).status_code == 401)
client.patch(f"/api/admin/relay-clients/{cid}", json={"is_active": True, "daily_quota": 50}, headers=admin)
check("reactive -> 200", client.get("/api/relay/ping", headers=relay).status_code == 200)

print("\n[10] Pas de relais en cascade")
client.put("/api/admin/mail", json={"transport": "relay"}, headers=admin)
r = client.post("/api/relay/send", json={**msg, "message_id": "m-9"}, headers=relay)
check("serveur lui-meme en mode relais -> 503", r.status_code == 503, r.text[:200])
client.put("/api/admin/mail", json={"transport": "smtp"}, headers=admin)

print("\n[11] Config d'envoi cote admin")
r = client.put("/api/admin/mail", json={"transport": "relay", "relay_url": "https://bo.aixam.fr",
                                        "relay_token": "axr_abc_secret"}, headers=admin)
cfg = r.json()
check("transport enregistre", cfg["transport"] == "relay", cfg)
check("url enregistree", cfg["relay_url"] == "https://bo.aixam.fr")
check("token marque comme pose", cfg["relay_token_set"] is True)
check("token jamais rendu", "axr_abc_secret" not in r.text, r.text[:300])
r = client.put("/api/admin/mail", json={"relay_url": "https://autre.fr"}, headers=admin)
check("token conserve si absent du corps", r.json()["relay_token_set"] is True)
r = client.put("/api/admin/mail", json={"transport": "nimporte-quoi"}, headers=admin)
check("transport inconnu -> 422", r.status_code == 422, r.status_code)

print("\n[12] Refus du relais en clair (cote client)")
for url, should_raise in [("http://bo.aixam.fr", True), ("https://bo.aixam.fr", False),
                          ("http://localhost:8080", False), ("ftp://x", True)]:
    try:
        relay_transport.check_url(url); raised = False
    except PermanentSendError:
        raised = True
    check(f"{url} {'refuse' if should_raise else 'accepte'}", raised == should_raise)

print("\n[13] Test de liaison depuis l'admin")
client.put("/api/admin/mail", json={"relay_url": "https://relais.invalid", "relay_token": "axr_a_b"}, headers=admin)
r = client.post("/api/admin/mail/test-relay", headers=admin)
check("distant injoignable -> diagnostic, pas une 500", r.status_code == 200 and r.json()["ok"] is False, r.text[:200])

sys.exit(report())
