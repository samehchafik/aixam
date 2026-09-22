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
    "nom": "launch-borne-genere.ps1",
    "entete": """# Genere par le back-office AIXAM le {date}.
# Une fenetre borne.exe par moniteur.
#
# borne.exe est notre coquille : plein ecran, sans bord, toujours au premier
# plan, sur l'ecran demande. Ce script n'a donc plus rien a placer -- il
# attend l'API et lance une fenetre par ecran. Tout ce que l'ancien lanceur
# faisait a coups d'API Windows (poser la fenetre, la reposer quand Chrome
# refaisait la sienne, tenir le premier plan, rendre le focus) vit desormais
# dans l'executable, qui le refait tant qu'il tourne -- la ou un script ne
# pouvait agir qu'une fois, au lancement.
#
# L'ecran est designe par sa POSITION, pas par son nom : un moniteur
# debranche puis rebranche sur une autre prise change de numero, et
# \\\\.\\DISPLAY5 ne designe soudain plus rien. borne.exe cherche l'ecran a
# cette position, puis celui qui la contient, et retombe sur l'ecran
# principal -- il ne pose jamais une fenetre hors de tout ecran.
#
# Regenerer depuis Reglages > Ecrans apres un changement de disposition.
#
# Alt+F4 ferme une fenetre et termine son programme. Ctrl+Q les ferme toutes
# (scripts/arret-clavier.ps1, lance par demarrage/start.bat).
#
#   powershell -ExecutionPolicy Bypass -File {fichier}
param(
  [string]$ApiHost = "{hote}",
  [int]$AttenteMax = 180,
  [string]$Exe = ""
)

# borne.exe se compile sur le poste de developpement -- la borne n'a ni Rust
# ni les outils Microsoft -- et se depose dans bin\\win\\.
if (-not $Exe) {{
  $Exe = @(
    (Join-Path $PSScriptRoot "..\\bin\\win\\borne.exe"),
    (Join-Path $PSScriptRoot "borne.exe")
  ) | Where-Object {{ Test-Path $_ }} | Select-Object -First 1
}}
if (-not $Exe) {{
  throw "borne.exe introuvable. Le compiler (voir README) et le deposer dans bin\\win\\borne.exe."
}}
$Exe = (Resolve-Path $Exe).Path
Write-Host "borne : $Exe"

# Attendre l'API plutot que de parier sur un delai : au demarrage, l'API et ce
# script sont lances par deux taches, et rien ne garantit l'ordre. PostgreSQL
# froid, un disque occupe, et les fenetres s'ouvriraient sur une page d'erreur
# -- devant les visiteurs, sans clavier pour recharger.
Write-Host "attente de l'API sur $ApiHost"
$debut = Get-Date
while ($true) {{
  try {{
    Invoke-WebRequest -Uri "$ApiHost/healthz" -UseBasicParsing -TimeoutSec 3 | Out-Null
    break
  }} catch {{
    if (((Get-Date) - $debut).TotalSeconds -ge $AttenteMax) {{
      throw "l'API n'a pas repondu en $AttenteMax s : les fenetres ne sont pas ouvertes"
    }}
    Start-Sleep -Seconds 2
  }}
}}
Write-Host "API prete apres $([int]((Get-Date) - $debut).TotalSeconds) s"

# Une relance doublerait les fenetres : chaque borne.exe est un processus a
# lui, sans delegation a une instance existante -- contrairement a Chrome, qui
# demandait tout un detour par le profil pour eviter cela.
$anciennes = @(Get-Process borne -ErrorAction SilentlyContinue)
if ($anciennes.Count) {{
  Write-Host "fermeture de $($anciennes.Count) fenetre(s) deja ouverte(s)"
  $anciennes | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Milliseconds 500
}}

$script:Lances = @()

function Ouvrir-Borne {{
  param($Profil, $Libelle, $Chemin, $X, $Y)
  $url = "$ApiHost$Chemin"
  # Le titre porte le ROLE, pas le libelle du moniteur : il sert a reconnaitre
  # la fenetre dans un diagnostic, et un libelle peut etre vide ou changer
  # quand le studio rebranche un ecran.
  $p = Start-Process $Exe -PassThru -ArgumentList @(
    $url, "--ecran", "$X,$Y", "--titre", "AIXAM $Profil"
  )
  $script:Lances += $p
  Write-Host "$Profil ($Libelle) : pid $($p.Id), ecran $X,$Y, $url"
}}
""",
    "fenetre": """
# {libelle} -- {peripherique} ({largeur}x{hauteur} en {x},{y})
Ouvrir-Borne -Profil "{profil}" -Libelle "{libelle}" -Chemin "{chemin}" -X {x} -Y {y}
""",
    # Ce morceau n'est PAS formate (voir construire_lanceur) : accolades simples.
    "pied": """
# Une fenetre qui se referme aussitot -- WebView2 absent, url refusee -- ne
# doit pas passer pour un demarrage reussi. Le lanceur d'avant annoncait
# « Fenetres ouvertes » quoi qu'il arrive, et l'on cherchait la panne ailleurs
# pendant des jours.
Start-Sleep -Seconds 3
$morts = @($script:Lances | Where-Object { $_.HasExited })
if ($morts.Count) {
  Write-Warning "$($morts.Count) fenetre(s) sur $($script:Lances.Count) se sont refermees aussitot."
  Write-Warning "  Verifier que l'API repond et que le moteur WebView2 est installe."
  exit 1
}
Write-Host "$($script:Lances.Count) fenetre(s) ouvertes, au premier plan. Alt+F4 en ferme une, Ctrl+Q les ferme toutes."
""",
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

# Attendre l'API plutot que de parier sur un delai -- voir le lanceur Windows.
printf "attente de l'API sur %s\n" "$HOTE"
DEBUT=$(date +%s)
until curl -sf -o /dev/null --max-time 3 "$HOTE/healthz"; do
  if [ $(( $(date +%s) - DEBUT )) -ge "${{ATTENTE_MAX:-180}}" ]; then
    echo "l'API n'a pas repondu : les fenetres ne sont pas ouvertes" >&2
    exit 1
  fi
  sleep 2
done

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
    """Le nom du script engendre.

    Windows a le sien : il ne lance plus un navigateur mais borne.exe, et les
    deux doivent pouvoir cohabiter sur une machine le temps d'une bascule.
    """
    modele = MODELES.get(systeme, _LINUX)
    return modele.get("nom") or f"launch-kiosk-genere.{modele['extension']}"


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
