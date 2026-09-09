"""Fusionne les visiteurs en double, puis pose la contrainte d'unicite.

A lancer une fois sur une base existante : `create_all` ne sait creer que des
tables, il n'ajoute pas une contrainte a une table deja la.

    docker compose run --rm api python -m app.tools.dedupe_visitors --dry-run
    docker compose run --rm api python -m app.tools.dedupe_visitors

Regle de fusion : on garde la ligne la PLUS ANCIENNE -- c'est celle vers
laquelle les creations pointent le plus probablement, et son `created_at` est
la vraie date de premiere venue. Elle herite de ce que les autres avaient de
plus : la verification si l'une d'elles etait verifiee, le consentement si
l'une l'avait donne, et les nom/prenom/code postal de la plus recente, qui
sont la derniere correction du visiteur.

Rien n'est perdu : creations et evenements sont rattaches avant suppression.
"""

from __future__ import annotations

import sys

from sqlalchemy import func, select, text, update

from app.db import SessionLocal
from app.models import Design, Event, Visitor


def doublons(db) -> list[str]:
    return list(
        db.scalars(
            select(Visitor.email).group_by(Visitor.email).having(func.count() > 1)
        )
    )


def fusionner(db, email: str, *, sec: bool) -> int:
    lignes = db.scalars(
        select(Visitor).where(Visitor.email == email).order_by(Visitor.created_at)
    ).all()
    garde, autres = lignes[0], lignes[1:]
    recente = lignes[-1]

    print(f"  {email} : {len(lignes)} lignes -> on garde {garde.id} du {garde.created_at:%d/%m %H:%M}")
    for a in autres:
        print(f"      absorbe {a.id} du {a.created_at:%d/%m %H:%M}")

    if sec:
        return len(autres)

    ids = [a.id for a in autres]
    # Rattacher AVANT de supprimer : la cle etrangere est en ON DELETE SET
    # NULL, une suppression seche anonymiserait les creations.
    db.execute(update(Design).where(Design.visitor_id.in_(ids)).values(visitor_id=garde.id))
    db.execute(update(Event).where(Event.visitor_id.in_(ids)).values(visitor_id=garde.id))

    garde.first_name = recente.first_name
    garde.last_name = recente.last_name
    garde.postal_code = recente.postal_code
    verifs = [l.email_verified_at for l in lignes if l.email_verified_at]
    if verifs:
        garde.email_verified_at = min(verifs)
    if any(l.consent_marketing for l in lignes):
        garde.consent_marketing = True
        consentements = [l.consent_at for l in lignes if l.consent_at]
        garde.consent_at = min(consentements) if consentements else None

    for a in autres:
        db.delete(a)
    return len(autres)


def main() -> int:
    sec = "--dry-run" in sys.argv
    with SessionLocal() as db:
        emails = doublons(db)
        if not emails:
            print("Aucun doublon.")
        else:
            print(f"{len(emails)} adresse(s) en double :")
            total = sum(fusionner(db, e, sec=sec) for e in emails)
            if sec:
                print(f"\n[--dry-run] {total} ligne(s) seraient supprimees. Rien n'a ete modifie.")
                return 0
            db.commit()
            print(f"\n{total} ligne(s) supprimee(s).")

        if sec:
            print("[--dry-run] la contrainte d'unicite n'a pas ete posee.")
            return 0

        # Meme nom que celui qu'aurait cree `create_all` sur une base neuve :
        # les deux chemins convergent, et `\d visitors` se lit pareil partout.
        # L'index existant n'est pas unique -- il faut le remplacer, pas
        # l'ignorer. Rejouable : DROP IF EXISTS puis CREATE.
        db.execute(text("DROP INDEX IF EXISTS ix_visitors_email"))
        db.execute(text("CREATE UNIQUE INDEX ix_visitors_email ON visitors (email)"))
        db.commit()
        print("Contrainte d'unicite en place sur visitors.email.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
