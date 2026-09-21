"""Reporte dans .env les reglages saisis dans le back-office.

Pourquoi : les reglages « a chaud » -- jeton du relais d'emails, adresse du
relais, jeton de remontee -- vivent dans la base, pour qu'on puisse brancher
la borne sur un autre relais sans redemarrer. Le `.env` n'est que leur valeur
de repli. Si la base est recreee (reinstallation, migration, `--volumes`), les
reglages disparaissent et c'est le `.env` qui reprend la main : s'il porte une
valeur perimee, l'envoi des emails s'arrete sans que rien ne l'annonce, et il
faut retrouver un jeton qu'on croyait pose une fois pour toutes.

Ce script recopie donc la base vers le `.env`, pour que le secours soit vrai.
A lancer apres chaque changement de reglage dans le back-office.

    .venv/Scripts/python.exe scripts/reporter_reglages.py            (Windows)
    .venv/bin/python scripts/reporter_reglages.py                    (ailleurs)
    ... --verifier    ne modifie rien, dit seulement ce qui differe

Les valeurs ne sont jamais affichees : seules leurs empreintes le sont.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "apps" / "api"))

# Reglage du back-office -> variable du .env qui lui sert de repli.
REPORTS = {
    "mail_relay_url": "MAIL_RELAY_URL",
    "mail_relay_token": "MAIL_RELAY_TOKEN",
    "sync_url": "SYNC_URL",
    "sync_token": "SYNC_TOKEN",
}


def empreinte(valeur: str) -> str:
    return hashlib.md5(valeur.encode()).hexdigest()[:8] if valeur else "(vide)"


def lire_env(fichier: pathlib.Path) -> dict[str, str]:
    valeurs = {}
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        if "=" in ligne and not ligne.lstrip().startswith("#"):
            cle, _, valeur = ligne.partition("=")
            valeurs[cle.strip()] = valeur.strip()
    return valeurs


def ecrire_env(fichier: pathlib.Path, changements: dict[str, str]) -> None:
    """Remplace les lignes visees, ajoute celles qui manquent, garde le reste.

    Le fichier est reecrit en entier : commentaires, ordre et lignes vides
    survivent. C'est ce qui permet de le relire ensuite sans surprise.
    """
    lignes = fichier.read_text(encoding="utf-8").splitlines()
    restants = dict(changements)
    for i, ligne in enumerate(lignes):
        cle = ligne.partition("=")[0].strip()
        if cle in restants and not ligne.lstrip().startswith("#"):
            lignes[i] = f"{cle}={restants.pop(cle)}"
    for cle, valeur in restants.items():
        lignes.append(f"{cle}={valeur}")
    fichier.write_text("\n".join(lignes) + "\n", encoding="utf-8")


def main() -> int:
    verifier = "--verifier" in sys.argv
    from app.db import SessionLocal  # noqa: E402 -- apres l'ajout au sys.path
    from app.services.settings_store import get_setting  # noqa: E402

    fichier = RACINE / ".env"
    env = lire_env(fichier)
    db = SessionLocal()
    try:
        changements = {}
        for reglage, variable in REPORTS.items():
            en_base = str(get_setting(db, reglage, "") or "")
            dans_env = env.get(variable, "")
            if not en_base:
                etat = "pas de reglage en base, le .env fait foi"
            elif en_base == dans_env:
                etat = "identiques"
            else:
                etat = "A REPORTER"
                changements[variable] = en_base
            print(f"  {variable:<18} base {empreinte(en_base):<8} "
                  f".env {empreinte(dans_env):<8} {etat}")
    finally:
        db.close()

    if not changements:
        print("\n.env a jour : il peut servir de secours.")
        return 0
    if verifier:
        print(f"\n{len(changements)} reglage(s) a reporter. Relancer sans --verifier.")
        return 1

    # with_suffix() sur « .env » donne « .env.env… » : le nom se construit.
    sauvegarde = fichier.with_name(".env.avant-report")
    sauvegarde.write_bytes(fichier.read_bytes())
    ecrire_env(fichier, changements)
    print(f"\n{len(changements)} reglage(s) reporte(s) dans .env "
          f"(copie de l'ancien dans {sauvegarde.name}).")
    print("Sans effet immediat : la base reste la source, le .env est le repli.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
