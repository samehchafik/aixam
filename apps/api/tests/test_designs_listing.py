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
    MEDIA_DIR=tempfile.mkdtemp(),
    STATIC_DIR=tempfile.mkdtemp(),
)

# Les rendus existent pour de vrai : depuis que la galerie verifie le disque
# avant de promettre une image, une base pleine et un dossier vide ne donnent
# plus d'URL du tout.
RENDUS = Path(os.environ["MEDIA_DIR"]) / "renders"
RENDUS.mkdir(parents=True)
(RENDUS / "x.jpg").write_bytes(b"jpeg")
(RENDUS / "y.jpg").write_bytes(b"jpeg")
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
        db.add(Design(visitor_id=v.id, session_id=f"sess-{rang}",
                      status=DesignStatus.rendered, render_path="renders/x.jpg",
                      created_at=T0 + timedelta(minutes=rang)))
    # Une creation d'avant les skins dont le JPEG a disparu du disque : sa
    # ligne a survecu au menage des rendus, pas son image.
    perdue_ligne = Design(visitor_id=None, session_id="sess-sans-image",
                          status=DesignStatus.rendered, render_path="renders/disparu.jpg",
                          created_at=T0 + timedelta(minutes=20))
    db.add(perdue_ligne)
    db.flush()
    sans_image = perdue_ligne.id
    # La creation dont l'auteur a exerce son droit a l'effacement.
    db.add(Design(visitor_id=None, session_id="sess-orpheline",
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
check("les 6 creations sont la", res["total"] == 6, res["total"])
# Deux creations sans auteur, les plus recentes : celle dont l'image a disparu
# et l'orpheline de la purge RGPD.
check("les anonymes en tete", noms(res)[:2] == [None, None], noms(res))
check("puis l'ordre antichronologique",
      noms(res)[2:] == ["Chloe alvarez", "Bruno Alvarez", "Alice Zidane", "Zoe bernard"], noms(res))

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

# Promettre l'URL d'un fichier absent donnait une vignette cassee : une carte
# sans image et sans explication, comme celle de l'onglet « Traitees ».
perdue = next(i for i in lister()["items"] if i["id"] == str(sans_image))
check("pas d'URL pour un fichier absent", perdue["render_url"] is None, perdue["render_url"])
check("la creation reste listee", perdue["status"] == "rendered")

print("\n[8] Un tri inconnu est refuse, pas silencieusement ignore")
r = c.get("/api/admin/designs", params={"sort": "'; DROP TABLE designs; --"}, headers=H)
check("422", r.status_code == 422, r.status_code)
check("la table est toujours la", lister()["total"] == 6)

print("\n[9] L'export Excel reprend les memes filtres")
import io
import zipfile

r = c.get("/api/admin/designs.xlsx", params={"search": "alvarez", "sort": "name_asc"}, headers=H)
check("200", r.status_code == 200, (r.status_code, r.text[:200]))
check("un classeur xlsx", r.headers["content-type"].startswith(
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"), r.headers["content-type"])
check("en piece jointe datee", 'filename="creations-' in r.headers.get("content-disposition", ""))
partages = zipfile.ZipFile(io.BytesIO(r.content)).read("xl/sharedStrings.xml").decode("utf-8")
check("le meme nombre de lignes que la liste", "Une ligne par création (2)" in partages,
      lister(search="alvarez")["total"])
check("les deux Alvarez, pas les autres", "Bruno" in partages and "Chloe" in partages and "Zoe" not in partages)
check("le filtre rappele en tete", "recherche « alvarez »" in partages)
check("sans session, refuse", c.get("/api/admin/designs.xlsx").status_code == 401)

print("\n[10] L'export des images : tout le dossier, sans filtre")
r = c.get("/api/admin/designs.zip", params={"search": "personne"}, headers=H)
check("200, meme avec un filtre sans resultat", r.status_code == 200, (r.status_code, r.text[:200]))
check("un zip", r.headers["content-type"] == "application/zip", r.headers["content-type"])
check("en piece jointe datee", 'filename="skins-' in r.headers.get("content-disposition", ""))
contenu = sorted(zipfile.ZipFile(io.BytesIO(r.content)).namelist())
check("toutes les images du dossier, dans skins/", contenu == ["skins/x.jpg", "skins/y.jpg"], contenu)
check("sans session, refuse", c.get("/api/admin/designs.zip").status_code == 401)
restes = list(Path(tempfile.gettempdir()).glob("skins-*.zip"))
check("le zip temporaire est efface apres l'envoi", not restes, restes)

sys.exit(report())
