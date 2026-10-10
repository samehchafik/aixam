"""Qui appelle : borne.exe, ou un navigateur ordinaire ?

borne.exe ajoute `SAMS-Borne/<version>` a la fin de son agent utilisateur
(apps/borne/src/main.rs) ; sans cela il ressemblerait trait pour trait a
Microsoft Edge, dont il partage le moteur. Une marque, pas une preuve : un
navigateur peut l'imiter. Bonne pour des statistiques, pas pour un acces.
"""

from __future__ import annotations

import re

from fastapi import Request

_MARQUE = re.compile(r"\bSAMS-Borne/([\w.\-]+)")


def version_borne(request: Request) -> str | None:
    """La version de borne.exe, ou None pour un navigateur ordinaire."""
    m = _MARQUE.search(request.headers.get("user-agent", ""))
    return m.group(1) if m else None


def nature_client(request: Request) -> str:
    """« borne » ou « navigateur »."""
    return "borne" if version_borne(request) else "navigateur"
