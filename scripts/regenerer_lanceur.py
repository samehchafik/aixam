"""Regenere le lanceur des fenetres depuis le releve courant de l'API.

Ce que fait Reglages > Ecrans > « Generer le script », sans navigateur : utile
en SSH, apres un changement de moniteur, pour redeposer demarrage/ sans passer
par le back-office. Le premier ecran releve devient le tactile, le second le
grand ecran -- l'ordre du releve, de gauche a droite.

    .venv/Scripts/python.exe scripts/regenerer_lanceur.py      (depuis la racine)
    .venv/bin/python scripts/regenerer_lanceur.py

Il exige une API lancee dans la session ouverte : lancee en SSH, elle ne
releve qu'un ecran virtuel, et ce script refuse de continuer.
"""
import json
import pathlib
import urllib.request

RACINE = pathlib.Path(__file__).resolve().parents[1]
ROLES = [("Tactile", "/kiosk/", "tactile"), ("Grand ecran", "/kiosk/#/display", "grand-ecran")]


def env(cle):
    for ligne in (RACINE / ".env").read_text(encoding="utf-8").splitlines():
        if ligne.startswith(cle + "="):
            return ligne.split("=", 1)[1].strip()
    raise SystemExit(f"{cle} absent de .env")


def poster(url, corps, jeton=None):
    entetes = {"Content-Type": "application/json"}
    if jeton:
        entetes["Authorization"] = "Bearer " + jeton
    req = urllib.request.Request(url, data=json.dumps(corps).encode(), headers=entetes)
    return json.load(urllib.request.urlopen(req, timeout=20))


HOTE = "http://localhost:8080"
jeton = poster(f"{HOTE}/api/auth/login",
               {"email": env("ADMIN_EMAIL"), "password": env("ADMIN_PASSWORD")})["access_token"]

req = urllib.request.Request(f"{HOTE}/api/admin/materiel", headers={"Authorization": "Bearer " + jeton})
releve = json.load(urllib.request.urlopen(req, timeout=20))
ecrans = releve["ecrans"]
for e in ecrans:
    print("  ecran :", e["peripherique"], f'{e["largeur"]}x{e["hauteur"]}', f'en {e["x"]},{e["y"]}')
if len(ecrans) < 2 or any(e["peripherique"] == "WinDisc" for e in ecrans):
    raise SystemExit(f"{len(ecrans)} ecran(s) releve(s), dont un virtuel : l'API doit tourner dans la session ouverte (tache aixam-api).")

corps = {
    "hote": HOTE,
    "systeme": releve["systeme"],
    "ecrans": [
        {"peripherique": e["peripherique"], "libelle": r[0], "x": e["x"], "y": e["y"],
         "largeur": e["largeur"], "hauteur": e["hauteur"], "chemin": r[1], "profil": r[2]}
        for e, r in zip(ecrans, ROLES)
    ],
}
d = poster(f"{HOTE}/api/admin/materiel/lanceur", corps, jeton)
(RACINE / "demarrage").mkdir(exist_ok=True)
cible = RACINE / "demarrage" / "launch-kiosk-genere.ps1"
cible.write_text(d["script"], encoding="utf-8")
print("ecrit :", cible, len(d["script"]), "octets")
