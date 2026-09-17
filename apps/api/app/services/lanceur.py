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
# Un Chrome plein ecran par moniteur, pose sur l'ecran releve.
#
# Sous Windows, `--kiosk` ne respecte pas `--window-position` : Chrome passe en
# plein ecran a la creation de la fenetre, souvent sur l'ecran principal, avant
# que la position soit appliquee. Et l'echelle d'affichage (125 %, 150 %) fait
# diverger les pixels physiques du releve des pixels logiques que Chrome lit.
# Ce script ne demande donc pas a Chrome de se placer : il ouvre la fenetre,
# l'attend, puis la pose lui-meme sur le rectangle exact du moniteur, retrouve
# par son nom de peripherique.
#
# Regenerer depuis Reglages > Ecrans si un ecran change de nom (un moniteur
# debranche puis rebranche sur une autre prise peut changer de numero).
#
#   powershell -ExecutionPolicy Bypass -File {fichier}
param([string]$ApiHost = "{hote}", [int]$AttenteMax = 180)

# Attendre l'API plutot que de parier sur un delai : au demarrage de la borne,
# l'API et ce script sont lances par deux taches, et rien ne garantit l'ordre.
# PostgreSQL froid, un disque occupe, et Chrome s'ouvrirait en plein ecran sur
# une page d'erreur -- devant les visiteurs, sans clavier pour recharger.
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

Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class AixamWin {{
  // Les fenetres visibles de Chrome, retrouvees par leur classe -- ce que fait
  // « ahk_exe chrome.exe » : Chrome refait parfois sa fenetre en passant en
  // plein ecran, et le MainWindowHandle du processus pointe alors sur une
  // fenetre morte.
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  public static List<IntPtr> FenetresChrome(HashSet<uint> pids) {{
    var trouvees = new List<IntPtr>();
    EnumWindows((h, l) => {{
      if (!IsWindowVisible(h)) return true;
      uint pid; GetWindowThreadProcessId(h, out pid);
      if (!pids.Contains(pid)) return true;
      var classe = new StringBuilder(64); GetClassName(h, classe, 64);
      if (classe.ToString() == "Chrome_WidgetWin_1") trouvees.Add(h);
      return true;
    }}, IntPtr.Zero);
    return trouvees;
  }}
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr z, int x, int y, int w, int hh, uint f);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [DllImport("kernel32.dll")] public static extern uint GetLastError();
  public static readonly IntPtr TOPMOST = new IntPtr(-1);
  public static readonly IntPtr TOP = IntPtr.Zero;
  // Un processus sans fenetre n'a pas le droit de donner le focus -- sauf s'il
  // vient de simuler une frappe. Une pression d'Alt, relachee aussitot, suffit.
  public static bool Activer(IntPtr h) {{
    keybd_event(0x12, 0, 0, UIntPtr.Zero); keybd_event(0x12, 0, 2, UIntPtr.Zero);
    return SetForegroundWindow(h);
  }}
  [StructLayout(LayoutKind.Sequential)] public struct RECT {{ public int L, T, R, B; }}
}}
"@
# Meme repere que le releve (pixels physiques) : sans cela Windows convertit
# nos coordonnees a l'echelle du bureau, et la fenetre tombe a cote.
[AixamWin]::SetProcessDPIAware() | Out-Null

$script:Fenetres = @{{}}

function Ouvrir-Fenetre {{
  param($Profil, $Chemin, $Peripherique, $X, $Y, $Largeur, $Hauteur)

  # L'ecran d'aujourd'hui, retrouve par son nom : le releve ne sert que de
  # secours si le nom a change depuis.
  $ecran = [System.Windows.Forms.Screen]::AllScreens | Where-Object {{ $_.DeviceName -eq $Peripherique }}
  if ($ecran) {{
    $X = $ecran.Bounds.X; $Y = $ecran.Bounds.Y
    $Largeur = $ecran.Bounds.Width; $Hauteur = $ecran.Bounds.Height
  }} else {{
    Write-Warning "$Peripherique introuvable : on prend les coordonnees du releve ($X,$Y). Regenerer le script."
  }}

  # Un Chrome deja lance avec ce profil -- relance du script, fenetre fermee a
  # la main et rouverte -- recevrait la commande par delegation, et le processus
  # qu'on vient de creer sortirait sans fenetre : MainWindowHandle rend alors
  # $null, que « -eq [IntPtr]::Zero » ne voit pas, et SetWindowPos echoue sur un
  # handle vide. On reprend donc l'instance existante et on la repositionne.
  # Le processus navigateur est celui SANS --type= : les autres sont ses
  # rendus et ses utilitaires, qui portent le meme --user-data-dir.
  $dossier = "$env:LOCALAPPDATA\\aixam-kiosk\\$Profil"
  $existant = Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" |
    Where-Object {{ $_.CommandLine -like "*--user-data-dir=`"$dossier`"*" -and $_.CommandLine -notlike "*--type=*" }} |
    Select-Object -First 1
  if ($existant) {{
    Write-Host "$Profil : Chrome deja lance (pid $($existant.ProcessId)), repositionne"
    $p = Get-Process -Id $existant.ProcessId
  }} else {{
    # Le chemin du profil est cite : LOCALAPPDATA peut contenir une espace.
    $p = Start-Process $chrome -PassThru -ArgumentList ($commun + @(
      "--user-data-dir=`"$dossier`"",
      "--window-position=$X,$Y", "--window-size=$Largeur,$Hauteur",
      "--app=$ApiHost$Chemin"))
  }}

  # La fenetre de CE Chrome : celle de classe Chrome_WidgetWin_1 visible dans
  # son processus, relue a chaque tour -- pas un handle memorise une fois.
  $pids = New-Object 'System.Collections.Generic.HashSet[uint32]'
  [void]$pids.Add([uint32]$p.Id)
  $h = [IntPtr]::Zero
  for ($i = 0; $i -lt 75 -and $h -eq [IntPtr]::Zero; $i++) {{
    Start-Sleep -Milliseconds 200
    $trouvees = [AixamWin]::FenetresChrome($pids)
    if ($trouvees.Count -gt 0) {{ $h = $trouvees[0] }}
  }}
  if ($h -eq [IntPtr]::Zero) {{ throw "Chrome n'a pas ouvert de fenetre pour $Profil" }}

  # On pose, on relit, on repose : Chrome finit parfois son plein ecran apres
  # coup et se recale sur l'ecran principal. Le succes n'est annonce que sur
  # une lecture reussie : un rectangle jamais rempli vaut 0,0, ce qui coincide
  # avec la position attendue du premier ecran.
  # HWND_TOPMOST : la barre des taches est elle-meme « toujours au premier
  # plan », une fenetre ordinaire ne passe jamais devant. Ctrl+Q reste le
  # geste qui ferme tout (scripts/arret-clavier.ps1), topmost ou non.
  $script:Fenetres[$Peripherique] = $h
  $r = New-Object AixamWin+RECT
  for ($i = 0; $i -lt 10; $i++) {{
    if (-not [AixamWin]::SetWindowPos($h, [AixamWin]::TOPMOST, $X, $Y, $Largeur, $Hauteur, 0x0040)) {{
      Write-Warning "SetWindowPos refuse pour $Profil (erreur Windows $([AixamWin]::GetLastError()))"
    }}
    Start-Sleep -Milliseconds 300
    if ([AixamWin]::GetWindowRect($h, [ref]$r) -and $r.L -eq $X -and $r.T -eq $Y) {{
      Write-Host "$Profil : sur $Peripherique en $X,$Y"
      return
    }}
  }}
  Write-Warning "$Profil n'est pas sur $Peripherique (fenetre en $($r.L),$($r.T), attendue en $X,$Y)"
}}
""",
    "fenetre": """
# {libelle} — {peripherique} ({largeur}x{hauteur} en {x},{y})
Ouvrir-Fenetre -Profil "{profil}" -Chemin "{chemin}" -Peripherique "{peripherique}" `
  -X {x} -Y {y} -Largeur {largeur} -Hauteur {hauteur}
""",
    # Ce morceau n'est PAS formate (voir construire_lanceur) : accolades simples.
    "pied": """
# Chrome finit sa transition plein ecran APRES qu'on l'a pose, et refait sa
# fenetre au passage : le topmost pose une seconde plus tot ne tenait pas, et
# la borne redemarree se retrouvait sous la barre des taches. On le reaffirme
# donc pendant vingt secondes, sans toucher a la position ni au focus
# (SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE), puis on rend le focus au
# tactile : Windows ne cache la barre que sous une fenetre plein ecran active.
$principal = [System.Windows.Forms.Screen]::PrimaryScreen.DeviceName
$fin = (Get-Date).AddSeconds(20)
$tous = New-Object 'System.Collections.Generic.HashSet[uint32]'
while ((Get-Date) -lt $fin) {
  # Toutes les fenetres Chrome visibles, relues a chaque tour : celle que
  # Chrome vient de refaire est prise aussi.
  Get-Process chrome -ErrorAction SilentlyContinue | ForEach-Object { [void]$tous.Add([uint32]$_.Id) }
  foreach ($h in [AixamWin]::FenetresChrome($tous)) {
    # L'attribut, puis la remontee en tete de la bande des topmost : c'est la
    # derniere fenetre ACTIVEE qui y est dessus, et au demarrage c'est la
    # barre des taches, la avant nous.
    [AixamWin]::SetWindowPos($h, [AixamWin]::TOPMOST, 0, 0, 0, 0, 0x0013) | Out-Null
    [AixamWin]::SetWindowPos($h, [AixamWin]::TOP, 0, 0, 0, 0, 0x0013) | Out-Null
  }
  Start-Sleep -Milliseconds 500
}
if ($script:Fenetres.ContainsKey($principal)) {
  $ok = [AixamWin]::Activer($script:Fenetres[$principal])
  Write-Host "focus a la fenetre de l'ecran principal ($principal) : $ok"
}
Write-Host "Fenetres ouvertes, toujours au premier plan."
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
