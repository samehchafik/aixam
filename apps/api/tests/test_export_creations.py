"""Le classeur Excel des creations : l'auteur, le nom du fichier, l'apercu.

Sans base de donnees : on lui passe des creations fabriquees, dont une sans
auteur (anonymisee) et une dont le fichier manque. On relit ensuite le .xlsx
comme ce qu'il est, une archive : feuille, images, textes.

    ../../.venv/bin/python tests/test_export_creations.py     (depuis apps/api)
"""

import io
import os
import re
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import API_DIR, check, on_path, report

os.environ.setdefault("MEDIA_DIR", str(API_DIR / "media"))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x@127.0.0.1/x")
on_path()

from app.schemas import Layer
from app.services.export_creations import classeur_creations
from app.services.renderer import render_design

# Une vraie creation, rendue pour l'occasion : l'apercu doit venir d'un vrai PNG.
skin = render_design({"layers": [Layer(type="background", hex="#E6B6B4").model_dump(exclude_none=True)]}).name

creation = lambda nom, verdict: SimpleNamespace(  # noqa: E731
    skin=nom, moderation=verdict, created_at=datetime(2026, 10, 12, 14, 30, tzinfo=UTC)
)
anne = SimpleNamespace(first_name="Anne", last_name="Martin", email="anne@example.fr", postal_code="75011")

contenu = classeur_creations([
    (creation(skin, "approved"), anne),
    (creation(skin, "pending"), None),                           # anonymisee
    (creation("0" * 32 + ".png", "rejected"), anne),             # fichier absent
], adresse_images="https://aixam.exemple/media/renders/", filtres="Filtres : créations validées")

print("\n[1] Un vrai classeur")
archive = zipfile.ZipFile(io.BytesIO(contenu))
noms = archive.namelist()
check("c'est une archive xlsx", "xl/workbook.xml" in noms, noms[:5])

print("\n[2] L'apercu est dans la feuille, pas un lien")
# Une image identique n'est stockee qu'une fois : on compte les images POSEES.
dessin = archive.read("xl/drawings/drawing1.xml").decode("utf-8")
check("un fichier image au moins dans l'archive", any(n.startswith("xl/media/") for n in noms))
check("deux apercus poses (le fichier absent n'en a pas)", dessin.count("<xdr:pic>") == 2, dessin.count("<xdr:pic>"))

print("\n[3] Les textes attendus")
partages = archive.read("xl/sharedStrings.xml").decode("utf-8")
for texte in ("Fichier", skin, "Anne", "Martin", "anne@example.fr", "75011", "Validée", "En attente",
              "Rejetée", "image absente"):
    check(f"« {texte} »", texte in partages)

print("\n[4] La date, a l'heure de Paris")
feuille = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
# 14 h 30 UTC le 12 octobre = 16 h 30 a Paris ; Excel stocke une fraction de jour.
# Les donnees commencent en ligne 5, sous l'en-tete explicatif.
valeurs = [float(v) for v in re.findall(r'<c r="G(?:[5-9]|\d{2,})"[^>]*><v>([\d.]+)</v>', feuille)]
heure = round((valeurs[0] % 1) * 24, 2) if valeurs else None
check("16 h 30 et non 14 h 30", heure == 16.5, heure)

print("\n[5] L'en-tete explique la feuille et dit ou sont les images")
for texte in ("Une ligne par création (3)", "apps/api/media/renders/", "C:\\aixam\\apps\\api\\media\\renders\\",
              "https://aixam.exemple/media/renders/", "Filtres : créations validées"):
    check(f"« {texte} »", texte in partages)

print("\n[6] Chaque nom de fichier ouvre son image")
liens = archive.read("xl/worksheets/_rels/sheet1.xml.rels").decode("utf-8")
check("lien vers l'image", f"https://aixam.exemple/media/renders/{skin}" in liens)

sys.exit(report())
