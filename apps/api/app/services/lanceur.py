"""Le script PowerShell qui ouvre un Chromium plein ecran par moniteur.

Chromium place une fenetre par ses coordonnees : `--window-position=x,y`. Le
lanceur livre avec le projet les devinait -- « 1920,0 » ecrit en dur, juste
tant que les ecrans sont deux, alignes, et dans cet ordre. Ici elles viennent
du releve fait par la machine elle-meme.
"""

from __future__ import annotations

ENTETE = """# Genere par le back-office AIXAM le {date}.
# Un Chromium plein ecran par moniteur, place par ses coordonnees reelles.
#
# Regenerer depuis Reglages > Ecrans apres tout changement de disposition :
# debrancher un ecran ou en intervertir deux change les coordonnees.
param([string]$ApiHost = "{hote}")

$chrome = @(
  "$env:ProgramFiles\\Google\\Chrome\\Application\\chrome.exe",
  "${{env:ProgramFiles(x86)}}\\Google\\Chrome\\Application\\chrome.exe"
) | Where-Object {{ Test-Path $_ }} | Select-Object -First 1
if (-not $chrome) {{ throw "Chrome introuvable" }}

$commun = @(
  "--kiosk", "--no-first-run", "--disable-translate",
  "--overscroll-history-navigation=0", "--disable-pinch",
  "--noerrdialogs", "--disable-session-crashed-bubble",
  "--autoplay-policy=no-user-gesture-required"
)
"""

FENETRE = """
# {libelle} — {peripherique} ({largeur}x{hauteur} en {x},{y})
Start-Process $chrome -ArgumentList ($commun + @(
  "--user-data-dir=$env:LOCALAPPDATA\\aixam-kiosk\\{profil}",
  "--window-position={x},{y}",
  "--app=$ApiHost{chemin}"))
"""


def construire_lanceur(payload) -> str:
    """Assemble le script. `payload` est un `LanceurIn` (schemas.py)."""
    from datetime import datetime

    morceaux = [ENTETE.format(date=datetime.now().strftime("%d/%m/%Y %H:%M"), hote=payload.hote)]
    for i, ecran in enumerate(payload.ecrans, start=1):
        morceaux.append(FENETRE.format(
            libelle=ecran.libelle or f"Ecran {i}",
            peripherique=ecran.peripherique,
            largeur=ecran.largeur, hauteur=ecran.hauteur,
            x=ecran.x, y=ecran.y,
            # Un profil par fenetre : sans cela Chromium ouvre des onglets
            # dans la meme instance et le plein ecran se perd.
            profil=ecran.profil,
            chemin=ecran.chemin,
        ))
    return "".join(morceaux)
