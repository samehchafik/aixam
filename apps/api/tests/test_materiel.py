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
from dataclasses import asdict
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

print("\n[3 ter] Un releve impossible n'efface pas un releve valide")
# Sur le stand, l'API tourne en conteneur Linux : elle ne voit aucun moniteur,
# et c'est Windows qui remplit le fichier. Si le demarrage de l'API passait
# derriere pour y ecrire « aucun ecran detecte », le back-office perdrait le
# releve a chaque redemarrage, sans que personne ne comprenne pourquoi.
DEPUIS_WINDOWS = {
    "releve_le": "2026-09-17T08:00:00+00:00", "systeme": "Windows", "indisponible": None,
    "ecrans": [{"peripherique": r"\\.\DISPLAY1", "modele": "", "x": 0, "y": 0,
                "largeur": 1920, "hauteur": 1080, "principal": True}],
}
materiel.ecrire(DEPUIS_WINDOWS)
materiel.ecrire({"releve_le": "2026-09-17T09:00:00+00:00", "systeme": "Linux", "ecrans": [],
                 "indisponible": "Aucun environnement graphique"})
check("le releve de la machine hote survit au demarrage du conteneur",
      materiel.lire()["systeme"] == "Windows", materiel.lire()["systeme"])
check("et ses ecrans avec", len(materiel.lire()["ecrans"]) == 1)
materiel.ecrire({"releve_le": "2026-09-17T10:00:00+00:00", "systeme": "Windows",
                 "ecrans": DEPUIS_WINDOWS["ecrans"] * 2, "indisponible": None})
check("un releve valide, lui, remplace le precedent",
      len(materiel.lire()["ecrans"]) == 2)
materiel.chemin_fichier().unlink()

print("\n[3 quater] Ce que l'agent pousse a la meme forme que ce que l'API releve")
# L'agent Windows (scripts/agent-ecrans.ps1) annonce les ecrans par
# POST /api/kiosk/materiel. Si les deux formes divergeaient, le back-office
# afficherait des ecrans sans coordonnees, et le lanceur poserait ses fenetres
# n'importe ou.
from app.schemas import MaterielIn  # noqa: E402
POUSSE = MaterielIn(systeme="Windows", ecrans=[{
    "peripherique": r"\\.\DISPLAY1", "modele": "", "x": 0, "y": 0,
    "largeur": 1920, "hauteur": 1080, "principal": True}])
check("memes champs qu'un ecran releve",
      set(POUSSE.ecrans[0].model_dump()) == set(asdict(materiel.Ecran(
          peripherique="x", modele="", x=0, y=0, largeur=1, hauteur=1, principal=True))),
      set(POUSSE.ecrans[0].model_dump()))
check("un ecran sans moniteur se dit indisponible",
      MaterielIn(systeme="Windows").ecrans == [])

print("\n[3 bis] Ou se pose materiels.json")
# Le conteneur copie le code a plat sous /app : compter quatre parents y
# levait IndexError, et l'API ne demarrait plus du tout.
check("dans le depot, la racine du projet",
      materiel.racine_projet(Path(materiel.__file__).resolve())
      == Path(__file__).resolve().parents[3])
check("code copie a plat, sans marqueur : aucune racine, pas d'erreur",
      materiel.racine_projet(Path("/app/app/services/materiel.py"),
                             existe=lambda _: False) is None)
check("et alors le fichier se pose dans le repertoire de travail",
      materiel.chemin_fichier().is_absolute())

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
    if systeme == "Windows":
        # Sous Windows la fenetre est posee par le script, pas par Chrome :
        # un appel par ecran, avec le releve en secours.
        check(f"{systeme} : une fenetre par ecran", produit.count("Ouvrir-Fenetre -Profil") == 2)
        check(f"{systeme} : les coordonnees reelles",
              "-X 0 -Y 0 -Largeur 1920 -Hauteur 1080" in produit
              and "-X 1920 -Y 0 -Largeur 3840 -Hauteur 2160" in produit)
    else:
        check(f"{systeme} : une fenetre par ecran", produit.count("--window-position") == 2)
        check(f"{systeme} : les coordonnees reelles",
              "--window-position=0,0" in produit and "--window-position=1920,0" in produit)
    check(f"{systeme} : un profil par fenetre",
          "tactile" in produit and "grand-ecran" in produit)
    # Sans cela Chrome s'enregistre aupres de GCM et noie le journal du stand
    # sous des erreurs sans consequence.
    check(f"{systeme} : pas de trafic de fond", "--disable-background-networking" in produit)

# Les commentaires glisses dans le tableau de drapeaux ne doivent pas finir
# passes a Chrome comme des arguments.
for systeme in ("Darwin", "Linux"):
    produit = construire_lanceur(LanceurIn(hote="http://x", systeme=systeme, ecrans=ECRANS))
    debut = produit.index("COMMUN=(")
    bloc = produit[debut:produit.index(")\n", debut) + 1]
    rendu = subprocess.run(["bash", "-c", bloc + '\nprintf "%s\\n" "${COMMUN[@]}"'],
                           capture_output=True, text=True)
    drapeaux = rendu.stdout.split()
    check(f"{systeme} : le tableau ne contient que des drapeaux",
          drapeaux and all(d.startswith("--") for d in drapeaux),
          [d for d in drapeaux if not d.startswith("--")])

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
check("une fenetre par ecran", script.count("Ouvrir-Fenetre -Profil") == 2, script.count("Ouvrir-Fenetre -Profil"))
# `--kiosk` ignore `--window-position` sous Windows, et l'echelle d'affichage
# fausse les pixels : c'est le script qui pose la fenetre, par l'API Windows,
# sur l'ecran retrouve par son nom. Le releve ne sert que de secours.
check("l'ecran est retrouve par son nom", "[System.Windows.Forms.Screen]::AllScreens" in script)
check("le premier ecran nomme", '-Peripherique "\\\\.\\DISPLAY1"' in script)
check("le second ecran nomme", '-Peripherique "\\\\.\\DISPLAY2"' in script)
check("le releve en secours", "-X 1920 -Y 0 -Largeur 3840 -Hauteur 2160" in script)
check("meme repere que le releve : pixels physiques", "SetProcessDPIAware()" in script)
check("la fenetre est posee puis relue", "SetWindowPos(" in script and "GetWindowRect(" in script)
# La barre des taches est « toujours au premier plan » : seule une fenetre
# HWND_TOPMOST passe devant. Et Chrome refait sa fenetre en finissant son
# plein ecran, apres qu'on l'a posee : un topmost pose une seule fois ne tenait
# pas au redemarrage. Il est reaffirme pendant vingt secondes, sans toucher a
# la position ni au focus, puis le focus revient au tactile.
check("toujours au premier plan", "[AixamWin]::TOPMOST" in script and "new IntPtr(-1)" in script)
check("reaffirme apres l'ouverture, sans bouger ni activer",
      "SetWindowPos($h, [AixamWin]::TOPMOST, 0, 0, 0, 0, 0x0013)" in script
      and script.rindex("Ouvrir-Fenetre -Profil") < script.index("0x0013"))
check("le focus revient a l'ecran principal",
      "PrimaryScreen.DeviceName" in script and "SetForegroundWindow(" in script)
check("un refus de SetWindowPos est dit", "GetLastError()" in script)
check("chaque fenetre a son profil", 'Ouvrir-Fenetre -Profil "tactile"' in script
      and 'Ouvrir-Fenetre -Profil "grand-ecran"' in script)
check("les adresses ouvertes", '-Chemin "/kiosk/"' in script and '-Chemin "/kiosk/#/display"' in script)
check("mode kiosque", '"--kiosk"' in script)
check("l'hote est parametrable", 'param([string]$ApiHost = "http://localhost:8080"' in script)

print("\n[4 ter] Un Chrome deja lance est repris, pas double")
# Relancer le script pendant que Chrome tourne : la nouvelle instance delegue a
# l'ancienne et sort sans fenetre. MainWindowHandle rend $null, que
# « -eq [IntPtr]::Zero » ne voit pas, et SetWindowPos echouait sur un handle
# vide -- tout en annonçant un succes, le rectangle jamais rempli valant 0,0.
script = construire_lanceur(LanceurIn(systeme="Windows", ecrans=ECRANS))
check("cherche un chrome du meme profil", "Win32_Process" in script and "--user-data-dir=" in script)
check("sans confondre le navigateur et ses rendus", "-notlike \"*--type=*\"" in script)
check("un handle vide est vide", "if (-not $h)" in script)
check("le succes exige une lecture reussie", "GetWindowRect($h, [ref]$r) -and" in script)

print("\n[4 bis] Le lanceur attend l'API avant d'ouvrir quoi que ce soit")
# Au demarrage de la borne, l'API et le lanceur sont deux taches planifiees :
# rien ne garantit l'ordre. Sans attente, Chrome s'ouvre en plein ecran sur une
# page d'erreur, devant les visiteurs et sans clavier pour recharger.
for systeme in ("Windows", "Darwin", "Linux"):
    script = construire_lanceur(LanceurIn(systeme=systeme, hote="http://localhost:8080", ecrans=ECRANS))
    check(f"{systeme} : interroge /healthz", "/healthz" in script)
    check(f"{systeme} : l'attente precede l'ouverture",
          script.index("/healthz") < script.index("--app"))

print("\n[5] Ce qui n'est pas eprouve ici")
if platform.system() != "Windows":
    print("      L'enumeration Windows (user32) demande Windows : non couverte sur ce poste.")
print("      Le PowerShell engendre n'est pas execute ici : sa syntaxe n'est"
      " verifiee qu'au premier lancement sur le poste du stand.")

sys.exit(report())
