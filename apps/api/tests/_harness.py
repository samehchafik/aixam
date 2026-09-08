"""Le strict necessaire pour ecrire un test ici : une base neuve, et `check`.

Pas de pytest : ces tests demandent un vrai PostgreSQL (les modeles utilisent
JSONB et le type UUID natif, SQLite ne les rend pas) et ils se lisent comme un
scenario. Une dependance de plus dans `requirements.txt` pour ca serait cher
paye -- `python tests/test_relay.py` suffit.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

API_DIR = Path(__file__).resolve().parent.parent

# Ou tourne le PostgreSQL de test. Sans base dediee, on prend celle du docker
# compose du projet -- d'ou le meme utilisateur par defaut.
BASE_URL = os.environ.get("TEST_PG_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432")


def db_url(name: str) -> str:
    parts = urlsplit(BASE_URL)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", "", ""))


def reset_database(name: str) -> str:
    """Repart d'une base vide. Un test qui ne se rejoue pas ne sert qu'une fois."""
    import psycopg

    dsn = db_url("postgres").replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
    return db_url(name)


_ok = 0
_fail = 0


def check(label: str, condition: object, extra: object = "") -> None:
    global _ok, _fail
    if condition:
        _ok += 1
        print(f"  OK   {label}")
    else:
        _fail += 1
        print(f"  ECHEC {label} {extra}")


def report() -> int:
    print(f"\n=== {_ok} OK, {_fail} echec(s) ===")
    return 1 if _fail else 0


def on_path() -> None:
    sys.path.insert(0, str(API_DIR))
