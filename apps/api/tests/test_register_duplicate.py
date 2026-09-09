"""La meme personne s'inscrit deux fois.

Le cas est frequent sur un stand : quelqu'un recommence parce qu'il s'est
trompe, ou revient le lendemain. Il ne doit ni se dedoubler en base, ni se
retrouver bloque devant la borne.

    ../../.venv/bin/python tests/test_register_duplicate.py     (depuis apps/api)
"""

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import check, on_path, report, reset_database

os.environ.update(
    DATABASE_URL=reset_database("aixam_test_doublon"),
    MAIL_TRANSPORT="smtp", SMTP_HOST="",
    DEFAULT_KIOSK_TOKEN="jeton-borne",
    ADMIN_EMAIL="admin@aixam-test.fr", ADMIN_PASSWORD="x",
    MEDIA_DIR=tempfile.mkdtemp(), STATIC_DIR=tempfile.mkdtemp(),
)
on_path()

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app, bootstrap
from app.models import EmailOutbox, VerificationCode, Visitor

bootstrap()
c = TestClient(app)
H = {"X-Kiosk-Token": "jeton-borne"}
EMAIL = "meme.personne@example.com"


def inscrire(session: str, prenom: str = "Sameh", consent: bool = True):
    return c.post(
        "/api/kiosk/register",
        json={"first_name": prenom, "last_name": "Chafik", "email": EMAIL,
              "postal_code": "75018", "consent_marketing": consent, "session_id": session},
        headers=H,
    )


def dernier_code() -> str:
    with SessionLocal() as db:
        mail = db.scalars(select(EmailOutbox).order_by(EmailOutbox.created_at.desc())).first()
        return re.search(r">\s*(\d{6})\s*<", mail.body_html).group(1)


def compter(modele) -> int:
    with SessionLocal() as db:
        return len(db.scalars(select(modele)).all())


print("\n[1] Deuxieme inscription : la meme personne, pas une nouvelle")
r1 = inscrire("sess-0001")
v1, code1 = r1.json()["visitor_id"], dernier_code()
r2 = inscrire("sess-0002", prenom="Samehh")
v2, code2 = r2.json()["visitor_id"], dernier_code()
check("le visiteur est reutilise", v1 == v2, (v1, v2))
check("une seule ligne en base", compter(Visitor) == 1, compter(Visitor))
check("les infos sont mises a jour", True)
with SessionLocal() as db:
    check("le prenom corrige a bien remplace l'ancien",
          db.scalar(select(Visitor.first_name)) == "Samehh")

print("\n[2] L'ancien code ne peut plus egarer")
check("un nouveau code a ete envoye", code1 != code2, (code1, code2))
r = c.post("/api/kiosk/verify", json={"visitor_id": v1, "code": code1}, headers=H)
check("l'ancien code est refuse", r.json()["verified"] is False, r.json())
with SessionLocal() as db:
    restants = db.scalars(
        select(VerificationCode).where(VerificationCode.consumed_at.is_(None))
    ).all()
check("un seul code valable a la fois", len(restants) == 1, len(restants))

print("\n[3] Le nouveau code fonctionne")
r = c.post("/api/kiosk/verify", json={"visitor_id": v1, "code": code2}, headers=H)
check("verifie", r.json()["verified"] is True, r.json())

print("\n[4] Il revient plus tard : plus de code du tout")
r3 = inscrire("sess-0003")
check("meme visiteur", r3.json()["visitor_id"] == v1)
check("verification non demandee", r3.json()["verification_required"] is False, r3.json())
check("aucun email supplementaire", compter(EmailOutbox) == 2, compter(EmailOutbox))
check("toujours une seule ligne visiteur", compter(Visitor) == 1)

print("\n[5] Le cul-de-sac d'avant : essais brules, puis re-inscription")
inscrire("sess-0004")  # deja verifie -> aucun code
autre = "brule@example.com"


def inscrire_autre(session: str):
    return c.post(
        "/api/kiosk/register",
        json={"first_name": "Alex", "last_name": "Martin", "email": autre,
              "postal_code": "69003", "consent_marketing": False, "session_id": session},
        headers=H,
    )


va = inscrire_autre("sess-0005").json()["visitor_id"]
for _ in range(5):
    c.post("/api/kiosk/verify", json={"visitor_id": va, "code": "000000"}, headers=H)
r = c.post("/api/kiosk/verify", json={"visitor_id": va, "code": "000000"}, headers=H)
check("essais epuises -> 429", r.status_code == 429, r.status_code)

r = inscrire_autre("sess-0006")
check("se re-inscrire redonne un code", r.json()["verification_required"] is True, r.json())
r = c.post("/api/kiosk/verify", json={"visitor_id": va, "code": dernier_code()}, headers=H)
check("et le blocage est leve", r.json().get("verified") is True, (r.status_code, r.json()))

print("\n[6] Le consentement retire est pris en compte")
inscrire("sess-0007", consent=False)
with SessionLocal() as db:
    check("consent_marketing repasse a false",
          db.scalar(select(Visitor.consent_marketing).where(Visitor.email == EMAIL)) is False)



print("\n[7] La contrainte d'unicite, posee par l'outil de fusion")
from sqlalchemy import text

from app.models import Design
from app.tools import dedupe_visitors

# La base de test est neuve, donc deja contrainte. On revient au schema
# d'avant pour reproduire ce qu'une version anterieure a laisse en production.
with SessionLocal() as db:
    db.execute(text("DROP INDEX IF EXISTS ix_visitors_email"))
    db.execute(text("CREATE INDEX ix_visitors_email ON visitors (email)"))
    db.commit()

with SessionLocal() as db:
    garde = db.scalar(select(Visitor).where(Visitor.email == EMAIL))
    ancien_id = garde.id
    db.add(Design(visitor_id=garde.id, session_id="sess-0001", layers={}, status="draft"))
    doublon = Visitor(first_name="Sam", last_name="C", email=EMAIL, postal_code="75011",
                      consent_marketing=True)
    db.add(doublon)
    db.commit()
    doublon_id = doublon.id
    db.add(Design(visitor_id=doublon_id, session_id="sess-9999", layers={}, status="draft"))
    db.commit()
check("doublon fabrique", compter(Visitor) == 3, compter(Visitor))

with SessionLocal() as db:
    check("l'outil le voit", dedupe_visitors.doublons(db) == [EMAIL], dedupe_visitors.doublons(db))

dedupe_visitors.main()

with SessionLocal() as db:
    restants = db.scalars(select(Visitor).where(Visitor.email == EMAIL)).all()
    check("une seule ligne apres fusion", len(restants) == 1, len(restants))
    check("c'est la plus ancienne qui survit", restants[0].id == ancien_id)
    check("les nom/prenom les plus recents sont conserves", restants[0].first_name == "Sam")
    check("le consentement est conserve", restants[0].consent_marketing is True)
    check("la verification est conservee", restants[0].email_verified_at is not None)
    orphelines = db.scalars(select(Design).where(Design.visitor_id.is_(None))).all()
    check("aucune creation orpheline", len(orphelines) == 0, len(orphelines))
    rattachees = db.scalars(select(Design).where(Design.visitor_id == ancien_id)).all()
    check("les deux creations sont rattachees a la ligne gardee", len(rattachees) == 2, len(rattachees))

with SessionLocal() as db:
    try:
        db.add(Visitor(first_name="X", last_name="Y", email=EMAIL, postal_code="75001"))
        db.commit()
        check("la base refuse un doublon", False, "insertion acceptee")
    except Exception:
        db.rollback()
        check("la base refuse un doublon", True)

print("\n[8] L'outil est rejouable")
dedupe_visitors.main()
check("relance sans erreur, base inchangee", compter(Visitor) == 2, compter(Visitor))

sys.exit(report())
