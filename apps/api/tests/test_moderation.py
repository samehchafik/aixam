"""Moderation des creations : ce que l'animateur valide part sur le grand ecran.

Le grand ecran du stand ne doit montrer que ce qu'un animateur a regarde. Le
defaut est donc « en attente », et rien ne bascule sans un clic.

    ../../.venv/bin/python tests/test_moderation.py     (depuis apps/api)
"""

import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import check, on_path, report, reset_database

os.environ.update(
    DATABASE_URL=reset_database("aixam_test_moderation"),
    MEDIA_DIR=tempfile.mkdtemp(), STATIC_DIR=tempfile.mkdtemp(),
    DEFAULT_KIOSK_TOKEN="jeton", ADMIN_EMAIL="a@aixam-test.fr", ADMIN_PASSWORD="x",
)
on_path()

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app, bootstrap
from app.models import Design, DesignStatus, Visitor

bootstrap()
c = TestClient(app)
tok = c.post("/api/auth/login", json={"email": "a@aixam-test.fr", "password": "x"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

with SessionLocal() as db:
    v = Visitor(first_name="Camille", last_name="Durand", email="c@example.com", postal_code="75011")
    db.add(v)
    db.flush()
    ids = []
    for i in range(3):
        d = Design(visitor_id=v.id, session_id=f"s-{i}", status=DesignStatus.rendered)
        db.add(d)
        db.flush()
        ids.append(str(d.id))
    db.commit()


def lister(**params) -> list[dict]:
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return c.get(f"/api/admin/designs?{q}", headers=H).json()["items"]


def compteurs(since: str = "", brut: bool = False) -> dict:
    # `quote` n'est pas cosmetique : l'horodatage porte un `+` pour son fuseau,
    # et un `+` non encode arrive en espace cote serveur. `brut` sert a verifier
    # que ce cas-la est rattrape quand meme.
    q = f"?since={since if brut else quote(since)}" if since else ""
    return c.get(f"/api/admin/designs/counts{q}", headers=H).json()


def verdicts() -> dict:
    """Les seuls compteurs de verdict, sans le repere du guet."""
    tous = compteurs()
    return {k: tous[k] for k in ("pending", "approved", "rejected")}


print("\n[1] Rien ne s'affiche sans avoir ete regarde")
check("tout arrive en attente", compteurs()["pending"] == 3, compteurs())
check("aucune validee", compteurs()["approved"] == 0)
check("l'etat voyage dans la liste",
      all(d["moderation"] == "pending" for d in lister()), lister()[:1])

print("\n[2] Le verdict de l'animateur")
r = c.post(f"/api/admin/designs/{ids[0]}/moderation", json={"decision": "approved"}, headers=H)
check("validation acceptee", r.status_code == 200, r.text[:200])
check("horodatee", r.json()["moderated_at"] is not None, r.json())
c.post(f"/api/admin/designs/{ids[1]}/moderation", json={"decision": "rejected"}, headers=H)
check("compteurs a jour", verdicts() == {"pending": 1, "approved": 1, "rejected": 1}, verdicts())

print("\n[3] Les onglets ne montrent que leur lot")
check("l'onglet a moderer n'a plus que la troisieme",
      [d["id"] for d in lister(moderation="pending")] == [ids[2]], lister(moderation="pending"))
check("le filtre validees ne rend que celle-la",
      [d["id"] for d in lister(moderation="approved")] == [ids[0]])
check("le filtre rejetees de meme",
      [d["id"] for d in lister(moderation="rejected")] == [ids[1]])
check("sans filtre, les trois", len(lister()) == 3)

print("\n[4] Un clic de travers se rattrape")
c.post(f"/api/admin/designs/{ids[1]}/moderation", json={"decision": "approved"}, headers=H)
check("la rejetee revient chez les validees",
      sorted(d["id"] for d in lister(moderation="approved")) == sorted([ids[0], ids[1]]))
r = c.post(f"/api/admin/designs/{ids[0]}/moderation", json={"decision": "pending"}, headers=H)
check("on peut remettre en attente", r.json()["moderation"] == "pending")
check("l'horodatage repart a zero", r.json()["moderated_at"] is None, r.json())

print("\n[5] Le filtre se combine avec la recherche")
check("recherche + verdict", len(lister(moderation="approved", search="camille")) == 1)
check("une recherche sans reponse ne rend rien",
      lister(moderation="approved", search="inconnu") == [])

print("\n[6] Refus des valeurs qui n'existent pas")
check("verdict inconnu -> 422",
      c.post(f"/api/admin/designs/{ids[0]}/moderation", json={"decision": "peut-etre"}, headers=H).status_code == 422)
check("filtre inconnu -> 422", c.get("/api/admin/designs?moderation=peut-etre", headers=H).status_code == 422)
check("un verdict inconnu parmi des valides -> 422",
      c.get("/api/admin/designs?moderation=approved,peut-etre", headers=H).status_code == 422)

print("\n[7] Plusieurs verdicts a la fois, pour des cases a cocher")
# Etat pose explicitement : les sections precedentes ont bouge les verdicts,
# et un test qui depend de leur ordre se casse au premier remaniement.
for design_id, verdict in zip(ids, ("approved", "rejected", "pending")):
    c.post(f"/api/admin/designs/{design_id}/moderation", json={"decision": verdict}, headers=H)
check("etat de depart", verdicts() == {"pending": 1, "approved": 1, "rejected": 1}, verdicts())
check("validees et rejetees ensemble", len(lister(moderation="approved,rejected")) == 2)
check("l'ordre des valeurs est indifferent", len(lister(moderation="rejected,approved")) == 2)
check("un seul verdict fonctionne toujours", len(lister(moderation="approved")) == 1)
check("les espaces sont tolerees", len(lister(moderation="approved, rejected")) == 2)
check("les trois d'un coup", len(lister(moderation="pending,approved,rejected")) == 3)
check("creation inconnue -> 404",
      c.post("/api/admin/designs/00000000-0000-0000-0000-000000000000/moderation",
             json={"decision": "approved"}, headers=H).status_code == 404)

print("\n[8] Le guet des arrivees")
# L'ecran ne se recharge pas tout seul : il compte ce qui est arrive depuis la
# creation la plus recente qu'il affiche, et propose. Sans ce comptage, une
# creation deposee pendant que l'animateur regarde l'ecran resterait invisible
# jusqu'a son prochain clic.
repere = compteurs()["latest"]
check("le repere est l'attente la plus recente", repere is not None, compteurs())
check("rien de neuf depuis le repere", compteurs(repere)["newer"] == 0, compteurs(repere))

with SessionLocal() as db:
    tardive = Design(visitor_id=v.id, session_id="s-tardive", status=DesignStatus.rendered)
    db.add(tardive)
    db.commit()
    id_tardive = str(tardive.id)

check("l'arrivee est comptee", compteurs(repere)["newer"] == 1, compteurs(repere))
# Que la grille ne bouge pas toute seule tient a l'ecran, pas au serveur : il
# ne recharge rien tant que l'animateur n'a pas clique. Ce qui se verifie ici,
# c'est que son clic la ramene bien -- en tete, puisque le tri est par date.
check("et le rafraichissement la ramene en tete",
      [d["id"] for d in lister(moderation="pending")][0] == id_tardive,
      lister(moderation="pending"))
check("le repere suit l'arrivee", compteurs()["latest"] > repere, compteurs())
check("et depuis CE repere, plus rien de neuf",
      compteurs(compteurs()["latest"])["newer"] == 0)

# Un repere absent veut dire qu'il n'y avait rien en attente au chargement :
# tout ce qui est en attente est donc arrive depuis.
check("sans repere, tout est nouveau", compteurs()["newer"] == compteurs()["pending"], compteurs())
check("un `+` non encode est rattrape",
      compteurs(repere, brut=True).get("newer") == 1, compteurs(repere, brut=True))
check("un repere illisible -> 422",
      c.get("/api/admin/designs/counts?since=hier", headers=H).status_code == 422)

for design_id in (*ids, id_tardive):
    c.post(f"/api/admin/designs/{design_id}/moderation", json={"decision": "approved"}, headers=H)
check("plus rien en attente, plus de repere", compteurs()["latest"] is None, compteurs())
check("et rien a annoncer", compteurs()["newer"] == 0, compteurs())


sys.exit(report())
