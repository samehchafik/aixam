"""Les ecrans relies a la machine, releves par l'API elle-meme.

L'API tourne sur le PC du stand en mode local (`bin/start.sh --local`) : elle
est donc la seule a voir le vrai materiel. Un navigateur ne verrait que les
ecrans de la machine qui l'affiche -- celle de l'animateur, pas celle du
stand -- et se tromperait sans que rien ne le signale.

Le releve part dans `materiels.json`, que le back-office lit pour proposer
l'affectation des ecrans et engendrer le script de lancement.

Windows par user32, macOS par CoreGraphics, Linux par xrandr -- trois voies,
une seule forme de resultat. Aucune dependance : ctypes pour les deux
premieres, une commande pour la troisieme. Quand rien n'est detectable, le
releve est vide et dit pourquoi, plutot que de faire semblant.
"""

from __future__ import annotations

import ctypes
import json
import platform
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings


@dataclass
class Ecran:
    """Un moniteur, tel que le lanceur en a besoin.

    `x`/`y` sont ce qui compte : Chromium les recoit en --window-position, et
    c'est ce que le lanceur devinait jusqu'ici avec un « 1920,0 » ecrit en dur.
    """

    peripherique: str          # \\.\DISPLAY1
    modele: str                # libelle lisible, quand Windows le donne
    x: int
    y: int
    largeur: int
    hauteur: int
    principal: bool


def _ecrans_windows() -> list[Ecran]:
    """Enumere les moniteurs via user32. Aucune dependance, ctypes suffit."""
    # Importe ici, pas en tete de module : `ctypes.wintypes` n'existe pas
    # partout, et le serveur Linux charge ce fichier comme les autres.
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    user32.SetProcessDPIAware()

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT),
                    ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                    ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                    ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]

    MONITORINFOF_PRIMARY = 1
    trouves: list[Ecran] = []

    PROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(RECT), ctypes.c_double
    )

    def rappel(hmonitor, _hdc, _rect, _param):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if not user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            return 1
        # DeviceString donne « Generic PnP Monitor » ou le nom du modele selon
        # le pilote : mieux que rien pour distinguer deux ecrans a l'ecran.
        appareil = DISPLAY_DEVICEW()
        appareil.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        modele = ""
        if user32.EnumDisplayDevicesW(info.szDevice, 0, ctypes.byref(appareil), 0):
            modele = appareil.DeviceString.strip()
        r = info.rcMonitor
        trouves.append(Ecran(
            peripherique=info.szDevice,
            modele=modele or info.szDevice,
            x=r.left, y=r.top,
            largeur=r.right - r.left, hauteur=r.bottom - r.top,
            principal=bool(info.dwFlags & MONITORINFOF_PRIMARY),
        ))
        return 1

    user32.EnumDisplayMonitors(0, None, PROC(rappel), 0)
    # De gauche a droite : c'est l'ordre dans lequel on les voit sur le stand.
    return sorted(trouves, key=lambda e: (e.x, e.y))


def _ecrans_macos() -> list[Ecran]:
    """Enumere via CoreGraphics. Meme approche que sous Windows : ctypes."""
    cg = ctypes.CDLL(
        "/System/Library/Frameworks/CoreGraphics.framework/Versions/A/CoreGraphics"
    )

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    class CGSize(ctypes.Structure):
        _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]

    class CGRect(ctypes.Structure):
        _fields_ = [("origin", CGPoint), ("size", CGSize)]

    cg.CGDisplayBounds.restype = CGRect
    cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
    cg.CGMainDisplayID.restype = ctypes.c_uint32

    maximum = 16
    identifiants = (ctypes.c_uint32 * maximum)()
    combien = ctypes.c_uint32()
    if cg.CGGetActiveDisplayList(maximum, identifiants, ctypes.byref(combien)) != 0:
        raise RuntimeError("CGGetActiveDisplayList a echoue")

    principal = cg.CGMainDisplayID()
    noms = _noms_macos(combien.value)
    trouves = []
    for i in range(combien.value):
        ident = identifiants[i]
        r = cg.CGDisplayBounds(ident)
        integre = bool(cg.CGDisplayIsBuiltin(ident))
        trouves.append(Ecran(
            peripherique=f"CGDisplay{ident}",
            modele=noms[i] if i < len(noms) else ("Ecran integre" if integre else f"Ecran {i + 1}"),
            x=int(r.origin.x), y=int(r.origin.y),
            largeur=int(r.size.width), hauteur=int(r.size.height),
            principal=ident == principal,
        ))
    return sorted(trouves, key=lambda e: (e.x, e.y))


def _noms_macos(attendus: int) -> list[str]:
    """Les noms commerciaux, quand system_profiler veut bien les donner.

    Best-effort : on ne s'en sert que si le compte correspond, sinon on
    prefere un libelle generique a un nom associe au mauvais ecran.
    """
    import subprocess

    try:
        sortie = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True, text=True, timeout=8, check=True,
        ).stdout
        noms: list[str] = []
        for carte in json.loads(sortie).get("SPDisplaysDataType", []):
            for ecran in carte.get("spdisplays_ndrvs", []):
                noms.append(str(ecran.get("_name", "")).strip())
        return noms if len(noms) == attendus else []
    except Exception:  # noqa: BLE001 -- un nom manquant n'est pas une panne
        return []


def _ecrans_linux() -> list[Ecran]:
    """Enumere via `xrandr --listmonitors`, la seule voie sans dependance.

    Une ligne ressemble a :
        0: +*eDP-1 1920/344x1080/193+0+0  eDP-1
    Sans serveur X -- un serveur en salle blanche, par exemple -- xrandr est
    absent ou muet, et l'on remonte l'absence plutot que d'inventer.
    """
    import subprocess

    return analyser_xrandr(subprocess.run(
        ["xrandr", "--listmonitors"], capture_output=True, text=True, timeout=8, check=True
    ).stdout)


# Une ligne de `xrandr --listmonitors` :
#     0: +*eDP-1 1920/344x1080/193+0+0  eDP-1
# L'etoile marque l'ecran principal, les /344 et /193 sont les millimetres --
# dont on n'a que faire, seuls les pixels placent une fenetre.
LIGNE_XRANDR = re.compile(
    r"^\s*\d+:\s+\+(?P<principal>\*)?(?P<nom>\S+)\s+"
    r"(?P<largeur>\d+)(?:/\d+)?x(?P<hauteur>\d+)(?:/\d+)?"
    r"\+(?P<x>-?\d+)\+(?P<y>-?\d+)"
)


def analyser_xrandr(sortie: str) -> list[Ecran]:
    """Separe de l'appel a la commande, pour etre eprouvable sans Linux."""
    trouves = []
    for ligne in sortie.splitlines():
        m = LIGNE_XRANDR.match(ligne)
        if not m:
            continue
        trouves.append(Ecran(
            peripherique=m["nom"],
            modele=m["nom"],
            x=int(m["x"]), y=int(m["y"]),
            largeur=int(m["largeur"]), hauteur=int(m["hauteur"]),
            principal=bool(m["principal"]),
        ))
    return sorted(trouves, key=lambda e: (e.x, e.y))


RELEVEURS = {
    "Windows": _ecrans_windows,
    "Darwin": _ecrans_macos,
    "Linux": _ecrans_linux,
}


def relever() -> dict:
    """Le releve, pret a etre ecrit ou servi."""
    systeme = platform.system()
    horodatage = datetime.now(UTC).isoformat()
    releveur = RELEVEURS.get(systeme)
    if releveur is None:
        return {"releve_le": horodatage, "systeme": systeme, "ecrans": [],
                "indisponible": f"Systeme non reconnu : {systeme}."}
    try:
        ecrans = releveur()
    except FileNotFoundError:
        # Cas typique d'un serveur sans serveur graphique : xrandr n'existe pas.
        return {"releve_le": horodatage, "systeme": systeme, "ecrans": [],
                "indisponible": "Aucun environnement graphique : cette machine ne pilote pas d'ecran."}
    except Exception as exc:  # noqa: BLE001 -- un releve rate n'empeche pas l'API de demarrer
        return {"releve_le": horodatage, "systeme": systeme, "ecrans": [],
                "indisponible": f"Releve impossible : {exc}"}
    if not ecrans:
        return {"releve_le": horodatage, "systeme": systeme, "ecrans": [],
                "indisponible": "Aucun ecran detecte."}
    return {"releve_le": horodatage, "systeme": systeme,
            "ecrans": [asdict(e) for e in ecrans], "indisponible": None}


def chemin_fichier() -> Path:
    """Ou vit `materiels.json` : a la racine du projet, a cote du lanceur."""
    if settings.materiel_file:
        return Path(settings.materiel_file)
    return Path(__file__).resolve().parents[4] / "materiels.json"


def ecrire(releve: dict | None = None) -> Path:
    """Ecrit le releve. Appele au demarrage, et a la demande depuis l'admin."""
    fichier = chemin_fichier()
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps(releve or relever(), indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    return fichier


def lire() -> dict:
    """Le dernier releve. Un fichier absent ou illisible n'est pas une panne."""
    fichier = chemin_fichier()
    try:
        return json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return relever()
