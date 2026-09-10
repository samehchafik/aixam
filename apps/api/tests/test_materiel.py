"""Le releve des ecrans, et le script de lancement qui en decoule.

Trois systemes, une seule forme de resultat. On eprouve ici ce qui est
eprouvable partout : l'analyse de la sortie de xrandr, la forme du releve, et
le script engendre. L'enumeration Windows par user32 ne peut l'etre que sur
Windows -- elle est signalee comme telle plutot que simulee.

    ../../.venv/bin/python tests/test_materiel.py     (depuis apps/api)
"""

import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import check, on_path, report

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x@127.0.0.1/x")
os.environ["MATERIEL_FILE"] = str(Path(tempfile.mkdtemp()) / "materiels.json")
on_path()

from app.schemas import EcranLanceurIn, LanceurIn
from app.services import materiel
from app.services.lanceur import construire_lanceur, nom_fichier

print("\n[1] Analyse de xrandr, sans Linux sous la main")
SORTIE = """Monitors: 3
 0: +*eDP-1 1920/344x1080/193+0+0  eDP-1
 1: +HDMI-1 3840/1600x2160/900+1920+0  HDMI-1
 2: +DP-2 1080/600x1920/340+5760+0  DP-2
"""
ecrans = materiel.analyser_xrandr(SORTIE)
check("trois ecrans", len(ecrans) == 3, len(ecrans))
check("nommes", [e.peripherique for e in ecrans] == ["eDP-1", "HDMI-1", "DP-2"])
check("les millimetres sont ignores", ecrans[0].largeur == 1920 and ecrans[0].hauteur == 1080)
check("positions lues", [(e.x, e.y) for e in ecrans] == [(0, 0), (1920, 0), (5760, 0)])
check("l'etoile marque le principal", [e.principal for e in ecrans] == [True, False, False])
check("un ecran pivote garde ses proportions", ecrans[2].largeur == 1080 and ecrans[2].hauteur == 1920)
check("tri de gauche a droite", ecrans == sorted(ecrans, key=lambda e: (e.x, e.y)))
check("une sortie vide ne rend rien", materiel.analyser_xrandr("") == [])
check("du bruit n'est pas lu comme un ecran",
      materiel.analyser_xrandr("Monitors: 0\nbla bla\n") == [])

print("\n[2] Le releve de CETTE machine")
r = materiel.relever()
check("le systeme est nomme", r["systeme"] == platform.system(), r["systeme"])
check("horodate", "releve_le" in r)
check("ecrans ou explication, jamais les deux vides sans raison",
      bool(r["ecrans"]) != bool(r["indisponible"]), (len(r["ecrans"]), r["indisponible"]))
for e in r["ecrans"]:
    check(f"« {e['modele']} » a une taille plausible",
          e["largeur"] > 0 and e["hauteur"] > 0, (e["largeur"], e["hauteur"]))

print("\n[3] Ecriture et relecture")
chemin = materiel.ecrire()
check("fichier ecrit", chemin.exists(), chemin)
relu = materiel.lire()
check("relu a l'identique", relu["systeme"] == r["systeme"])
chemin.unlink()
check("fichier absent : on releve a nouveau plutot que d'echouer",
      materiel.lire()["systeme"] == platform.system())

print("\n[4] Le script de lancement, selon le systeme")
ECRANS = [
    EcranLanceurIn(peripherique=r"\\.\DISPLAY1", libelle="Tactile", x=0, y=0,
                   largeur=1920, hauteur=1080, chemin="/kiosk/", profil="tactile"),
    EcranLanceurIn(peripherique=r"\\.\DISPLAY2", libelle="Grand ecran", x=1920, y=0,
                   largeur=3840, hauteur=2160, chemin="/kiosk/#/display", profil="grand-ecran"),
]

for systeme, extension, marqueur in (
    ("Windows", ".ps1", "Start-Process"),
    ("Darwin", ".sh", "/Applications/Google Chrome.app"),
    ("Linux", ".sh", "google-chrome chromium"),
):
    produit = construire_lanceur(LanceurIn(hote="http://x", systeme=systeme, ecrans=ECRANS))
    check(f"{systeme} : le bon nom de fichier", nom_fichier(systeme).endswith(extension), nom_fichier(systeme))
    check(f"{systeme} : la bonne facon de trouver le navigateur", marqueur in produit)
    check(f"{systeme} : une fenetre par ecran", produit.count("--window-position") == 2)
    check(f"{systeme} : les coordonnees reelles",
          "--window-position=0,0" in produit and "--window-position=1920,0" in produit)
    check(f"{systeme} : un profil par fenetre",
          "tactile" in produit and "grand-ecran" in produit)

# Un shell mal forme ne se verrait qu'au lancement, sur le stand.
for systeme in ("Darwin", "Linux"):
    chemin = Path(tempfile.mkdtemp()) / "essai.sh"
    chemin.write_text(construire_lanceur(LanceurIn(hote="http://x", systeme=systeme, ecrans=ECRANS)))
    rendu = subprocess.run(["bash", "-n", str(chemin)], capture_output=True, text=True)
    check(f"{systeme} : le shell engendre est syntaxiquement valide",
          rendu.returncode == 0, rendu.stderr[:120])

script = construire_lanceur(LanceurIn(hote="http://localhost:8080", systeme="Windows", ecrans=[
    EcranLanceurIn(peripherique=r"\\.\DISPLAY1", libelle="Tactile", x=0, y=0,
                   largeur=1920, hauteur=1080, chemin="/kiosk/", profil="tactile"),
    EcranLanceurIn(peripherique=r"\\.\DISPLAY2", libelle="Grand ecran", x=1920, y=0,
                   largeur=3840, hauteur=2160, chemin="/kiosk/#/display", profil="grand-ecran"),
]))
check("une fenetre par ecran", script.count("Start-Process") == 2, script.count("Start-Process"))
# Ce sont les coordonnees qui placent la fenetre : le lanteur livre les
# devinait, c'est precisement ce qu'on remplace.
check("la position du premier", '--window-position=0,0' in script)
check("celle du second", '--window-position=1920,0' in script)
check("chaque fenetre a son profil",
      "aixam-kiosk\\tactile" in script and "aixam-kiosk\\grand-ecran" in script)
check("les adresses ouvertes", '--app=$ApiHost/kiosk/"' in script and '--app=$ApiHost/kiosk/#/display"' in script)
check("mode kiosque", '"--kiosk"' in script)
check("l'hote est parametrable", 'param([string]$ApiHost = "http://localhost:8080")' in script)

print("\n[5] Ce qui n'est pas eprouve ici")
if platform.system() != "Windows":
    print("      L'enumeration Windows (user32) demande Windows : non couverte sur ce poste.")

sys.exit(report())
