"""Le script qui ouvre un navigateur plein ecran par moniteur.

Chromium place une fenetre par ses coordonnees : `--window-position=x,y`. Les
lanceurs livres avec le projet les devinaient -- un « 1920,0 » ecrit en dur,
juste tant que les ecrans sont deux, alignes et dans cet ordre. Ici elles
viennent du releve fait par la machine elle-meme.

Un script par systeme : PowerShell sous Windows, shell ailleurs. Ce qui change
n'est pas le principe mais l'intendance -- ou trouver le navigateur, ou poser
les profils, comment lancer en arriere-plan.
"""

from __future__ import annotations

from datetime import datetime

# Un profil par fenetre, partout : sans cela le navigateur ouvre un onglet
# dans l'instance existante, et le plein ecran se perd.

_WINDOWS = {
    "extension": "ps1",
    "entete": """# Genere par le back-office AIXAM le {date}.
# Un Chrome plein ecran par moniteur, place par ses coordonnees reelles.
#
# Regenerer depuis Reglages > Ecrans apres tout changement de disposition :
# debrancher un ecran ou en intervertir deux change les coordonnees.
#
#   powershell -ExecutionPolicy Bypass -File {fichier}
param([string]$ApiHost = "{hote}")

$chrome = @(
  "$env:ProgramFiles\\Google\\Chrome\\Application\\chrome.exe",
  "${{env:ProgramFiles(x86)}}\\Google\\Chrome\\Application\\chrome.exe"
) | Where-Object {{ Test-Path $_ }} | Select-Object -First 1
if (-not $chrome) {{ throw "Chrome introuvable" }}

$commun = @(
  "--kiosk", "--no-first-run", "--no-default-browser-check", "--disable-translate",
  "--overscroll-history-navigation=0", "--disable-pinch",
  "--noerrdialogs", "--disable-session-crashed-bubble",
  "--autoplay-policy=no-user-gesture-required",
  # Un stand n'a rien a synchroniser ni a mettre a jour pendant l'animation.
  # Sans cela Chrome tente de s'enregistrer aupres des serveurs de notification
  # de Google et remplit le journal d'erreurs sans consequence.
  "--disable-background-networking", "--disable-sync", "--disable-component-update",
  # La fenetre du grand ecran n'a jamais le focus : sans ces trois-la, Chrome
  # ralentit ses minuteries et le defilement des images se met a saccader.
  "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows",
  "--disable-renderer-backgrounding"
)
""",
    "fenetre": """
# {libelle} — {peripherique} ({largeur}x{hauteur} en {x},{y})
Start-Process $chrome -ArgumentList ($commun + @(
  "--user-data-dir=$env:LOCALAPPDATA\\aixam-kiosk\\{profil}",
  "--window-position={x},{y}",
  "--app=$ApiHost{chemin}"))
""",
    "pied": "",
}

_SHELL_ENTETE = """#!/usr/bin/env bash
# Genere par le back-office AIXAM le {date}.
# Un navigateur plein ecran par moniteur, place par ses coordonnees reelles.
#
# Regenerer depuis Reglages > Ecrans apres tout changement de disposition :
# debrancher un ecran ou en intervertir deux change les coordonnees.
#
#   bash {fichier}
set -euo pipefail

HOTE="${{HOTE:-{hote}}}"
PROFILS="${{PROFILS:-$HOME/.aixam-kiosk}}"
JOURNAUX="${{JOURNAUX:-$PROFILS/journaux}}"
mkdir -p "$JOURNAUX"

for candidat in {candidats}; do
  if [ -x "$candidat" ] || command -v "$candidat" >/dev/null 2>&1; then
    NAVIGATEUR="$candidat"
    break
  fi
done
: "${{NAVIGATEUR:?Chrome ou Chromium introuvable}}"

COMMUN=(--kiosk --no-first-run --no-default-browser-check --disable-translate
        --overscroll-history-navigation=0 --disable-pinch
        --noerrdialogs --disable-session-crashed-bubble
        --autoplay-policy=no-user-gesture-required
        # Un stand n'a rien a synchroniser ni a mettre a jour pendant
        # l'animation. Sans cela Chrome tente de s'enregistrer aupres des
        # serveurs de notification de Google et remplit le journal d'erreurs
        # sans consequence.
        --disable-background-networking --disable-sync --disable-component-update
        # La fenetre du grand ecran n'a jamais le focus : sans ces trois-la,
        # Chrome ralentit ses minuteries et le defilement se met a saccader.
        --disable-background-timer-throttling --disable-backgrounding-occluded-windows
        --disable-renderer-backgrounding
        {supplement})
"""

_SHELL_FENETRE = """
# {libelle} — {peripherique} ({largeur}x{hauteur} en {x},{y})
"$NAVIGATEUR" "${{COMMUN[@]}}" \\
  --user-data-dir="$PROFILS/{profil}" \\
  --window-position={x},{y} \\
  --app="$HOTE{chemin}" >>"$JOURNAUX/{profil}.log" 2>&1 &
"""

_SHELL_PIED = """
echo "Fenetres ouvertes. Journaux : $JOURNAUX"
# Les fenetres tournent en arriere-plan : on attend, sinon fermer ce terminal
# les emporterait avec lui.
wait
"""

_MACOS = {
    "extension": "sh",
    "entete": _SHELL_ENTETE,
    "fenetre": _SHELL_FENETRE,
    "pied": _SHELL_PIED,
    "candidats": '"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" '
                 '"/Applications/Chromium.app/Contents/MacOS/Chromium"',
    "supplement": "--use-mock-keychain",
}

_LINUX = {
    "extension": "sh",
    "entete": _SHELL_ENTETE,
    "fenetre": _SHELL_FENETRE,
    "pied": _SHELL_PIED,
    "candidats": "google-chrome chromium chromium-browser",
    "supplement": "--password-store=basic",
}

MODELES = {"Windows": _WINDOWS, "Darwin": _MACOS, "Linux": _LINUX}


def nom_fichier(systeme: str) -> str:
    return f"launch-kiosk-genere.{MODELES.get(systeme, _LINUX)['extension']}"


def construire_lanceur(payload) -> str:
    """Assemble le script. `payload` est un `LanceurIn` (schemas.py)."""
    modele = MODELES.get(payload.systeme, _LINUX)
    fichier = nom_fichier(payload.systeme)

    morceaux = [modele["entete"].format(
        date=datetime.now().strftime("%d/%m/%Y %H:%M"),
        hote=payload.hote,
        fichier=fichier,
        candidats=modele.get("candidats", ""),
        supplement=modele.get("supplement", ""),
    )]
    for i, ecran in enumerate(payload.ecrans, start=1):
        morceaux.append(modele["fenetre"].format(
            libelle=ecran.libelle or f"Ecran {i}",
            peripherique=ecran.peripherique,
            largeur=ecran.largeur, hauteur=ecran.hauteur,
            x=ecran.x, y=ecran.y,
            profil=ecran.profil,
            chemin=ecran.chemin,
        ))
    morceaux.append(modele["pied"])
    return "".join(morceaux)
