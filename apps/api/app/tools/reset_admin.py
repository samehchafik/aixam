"""Remet le compte d'administration d'aplomb.

`bootstrap()` ne cree un administrateur que s'il n'en existe AUCUN : changer
ADMIN_EMAIL ou ADMIN_PASSWORD dans .env apres le premier demarrage reste donc
sans effet, et l'on se retrouve enferme dehors sans qu'aucun message ne le
dise. C'est ce que cette commande repare.

    docker compose run --rm api python -m app.tools.reset_admin
    python -m app.tools.reset_admin --email vous@exemple.fr --password '...'

Sans arguments, reprend ADMIN_EMAIL et ADMIN_PASSWORD du .env. Le compte est
cree s'il manque, mis a jour et reactive s'il existe.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import AdminUser
from app.security import hash_secret


def main() -> int:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--email", default=settings.admin_email)
    parseur.add_argument("--password", default=settings.admin_password)
    parseur.add_argument("--list", action="store_true", help="affiche les comptes, sans rien changer")
    args = parseur.parse_args()

    with SessionLocal() as db:
        comptes = db.scalars(select(AdminUser).order_by(AdminUser.created_at)).all()

        if args.list:
            if not comptes:
                print("Aucun compte d'administration.")
            for c in comptes:
                print(f"  {c.email:35} {'actif' if c.is_active else 'desactive'}  cree le {c.created_at:%d/%m/%Y}")
            return 0

        email = args.email.strip().lower()
        if not args.password:
            print("Mot de passe vide : renseigner ADMIN_PASSWORD ou passer --password", file=sys.stderr)
            return 1
        # Les noms reserves passent la creation mais pas la connexion : autant
        # le dire ici plutot que de laisser chercher un 422 a l'ecran.
        if email.rsplit(".", 1)[-1] in ("local", "test", "invalid", "example"):
            print(f"« {email} » a un domaine reserve : la connexion le refusera.", file=sys.stderr)
            return 1

        compte = db.scalar(select(AdminUser).where(AdminUser.email == email)) or (
            comptes[0] if comptes else None
        )
        if compte is None:
            db.add(AdminUser(email=email, password_hash=hash_secret(args.password)))
            action = "cree"
        else:
            action = "mis a jour" if compte.email == email else f"renomme depuis {compte.email}"
            compte.email = email
            compte.password_hash = hash_secret(args.password)
            compte.is_active = True
        db.commit()

    print(f"Compte {email} {action}. Le mot de passe n'est pas affiche.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
