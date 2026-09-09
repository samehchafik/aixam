"""La galerie des creations dans le back-office : filtre, tri, agrandissement.

Ce qui se joue ici : sur le stand, on cherche la creation d'une personne qui
la reclame -- au nom, au prenom, ou a l'adresse qu'elle vient d'epeler. Le
piege est la creation anonymisee (purge RGPD) : elle n'a plus d'auteur, et ni
le tri ni le filtre ne doivent la faire disparaitre au mauvais moment.

    ../../.venv/bin/python tests/test_designs_listing.py        (depuis apps/api)
"""

import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import check, on_path, report, reset_database

os.environ.update(
    DATABASE_URL=reset_database("aixam_test_creations"),
    MAIL_TRANSPORT="smtp", SMTP_HOST="",
    DEFAULT_KIOSK_TOKEN="jeton-borne",
    ADMIN_EMAIL="admin@aixam-test.fr", ADMIN_PASSWORD="x",
    MEDIA_DIR=tempfile.mkdtemp(), STATIC_DIR=tempfile.mkdtemp(),
)
on_path()

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app, bootstrap
from app.models import Design, DesignStatus, Visitor

bootstrap()
c = TestClient(app)
jeton = c.post(
    "/api/auth/login", json={"email": "admin@aixam-test.fr", "password": "x"}
).json()["access_token"]
H = {"Authorization": f"Bearer {jeton}"}

T0 = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)

# Prenoms et casse volontairement bigarres : un tri qui ne normalise pas la
# casse mettrait « bernard » apres « Zidane ».
GENS = [
    ("Zoe", "bernard", "zoe.bernard@example.com", 0),
    ("Alice", "Zidane", "alice.zidane@example.com", 1),
    ("Bruno", "Alvarez", "bruno.ALVAREZ@example.com", 2),
    ("Chloe", "alvarez", "chloe.alvarez@example.com", 3),
]

with SessionLocal() as db:
    for prenom, nom, email, rang in GENS:
        v = Visitor(first_name=prenom, last_name=nom, email=email, postal_code="75011")
        db.add(v)
        db.flush()
        db.add(Design(visitor_id=v.id, session_id=f"sess-{rang}", layers={},
                      status=DesignStatus.rendered, render_path="renders/x.jpg",
                      created_at=T0 + timedelta(minutes=rang)))
    # La creation dont l'auteur a exerce son droit a l'effacement.
    db.add(Design(visitor_id=None, session_id="sess-orpheline", layers={},
                  status=DesignStatus.rendered, render_path="renders/y.jpg",
                  created_at=T0 + timedelta(minutes=10)))
    db.commit()


def lister(**params):
    r = c.get("/api/admin/designs", params=params, headers=H)
    assert r.status_code == 200, (r.status_code, r.text)
    return r.json()


def noms(res):
    return [item["visitor_name"] for item in res["items"]]


print("\n[1] Par defaut, les plus recentes d'abord")
res = lister()
check("les 5 creations sont la", res["total"] == 5, res["total"])
check("l'orpheline est en tete", noms(res)[0] is None, noms(res))
check("puis l'ordre antichronologique",
      noms(res)[1:] == ["Chloe alvarez", "Bruno Alvarez", "Alice Zidane", "Zoe bernard"], noms(res))

print("\n[2] Tri par date croissante")
check("la plus ancienne d'abord", noms(lister(sort="date_asc"))[0] == "Zoe bernard",
      noms(lister(sort="date_asc")))

print("\n[3] Tri par nom, insensible a la casse")
res = lister(sort="name_asc")
check("Alvarez avant Zidane et bernard",
      noms(res)[:4] == ["Bruno Alvarez", "Chloe alvarez", "Zoe bernard", "Alice Zidane"], noms(res))
check("l'anonyme est releguee a la fin", noms(res)[4] is None, noms(res))

res = lister(sort="name_desc")
check("Z -> A commence par Zidane", noms(res)[0] == "Alice Zidane", noms(res))
check("et l'anonyme reste a la fin, pas en tete", noms(res)[4] is None, noms(res))

print("\n[4] Filtre : nom, prenom, email")
check("par nom de famille", noms(lister(search="alvarez")) and
      sorted(n for n in noms(lister(search="alvarez"))) == ["Bruno Alvarez", "Chloe alvarez"],
      noms(lister(search="alvarez")))
check("par prenom", noms(lister(search="zoe")) == ["Zoe bernard"], noms(lister(search="zoe")))
check("par fragment d'email", noms(lister(search="alice.zidane@")) == ["Alice Zidane"],
      noms(lister(search="alice.zidane@")))
check("l'email en majuscules se trouve quand meme",
      noms(lister(search="BRUNO.alvarez")) == ["Bruno Alvarez"], noms(lister(search="BRUNO.alvarez")))
check("sans correspondance, liste vide", lister(search="personne")["items"] == [])

print("\n[5] Le total suit le filtre")
res = lister(search="alvarez")
check("total == nombre de lignes rendues", res["total"] == len(res["items"]) == 2, res["total"])

print("\n[6] Filtre et tri se combinent")
check("tri par nom sur un filtre",
      noms(lister(search="alvarez", sort="name_asc")) == ["Bruno Alvarez", "Chloe alvarez"],
      noms(lister(search="alvarez", sort="name_asc")))

print("\n[7] La creation agrandie a de quoi s'afficher")
premiere = lister(sort="date_asc")["items"][0]
check("une URL de rendu", premiere["render_url"] == "/media/renders/x.jpg", premiere["render_url"])
check("un auteur et une adresse", premiere["visitor_email"] == "zoe.bernard@example.com", premiere)

print("\n[8] Un tri inconnu est refuse, pas silencieusement ignore")
r = c.get("/api/admin/designs", params={"sort": "'; DROP TABLE designs; --"}, headers=H)
check("422", r.status_code == 422, r.status_code)
check("la table est toujours la", lister()["total"] == 5)

sys.exit(report())
