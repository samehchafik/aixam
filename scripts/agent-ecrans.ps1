# Annonce a l'API les ecrans de CETTE machine, et les reannonce quand ils changent.
#
# Pourquoi un agent plutot qu'un releve : l'API tourne en conteneur Linux sur
# le stand et ne voit aucun moniteur. Un fichier ecrit une fois pour toutes
# serait une photo -- debrancher un ecran et le rebrancher sur une autre prise
# la rendrait fausse en silence, et le lanceur poserait ses fenetres sur des
# coordonnees qui n'existent plus. L'agent, lui, tient l'API a jour.
#
#   powershell -ExecutionPolicy Bypass -File scripts\agent-ecrans.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\agent-ecrans.ps1 -UneFois
#
# Il doit tourner dans la SESSION OUVERTE, comme les fenetres du navigateur :
# une session SSH ne voit qu'un ecran virtuel 1024x768. D'ou la tache planifiee
# a l'ouverture de session -- voir README, « Installation sur le salon ».
param(
  [string]$ApiHost,
  [string]$Token,
  [int]$Secondes = 5,
  [int]$Battement = 300,
  [switch]$UneFois
)

# Pourquoi user32 plutot que System.Windows.Forms : Screen::AllScreens met sa
# liste en cache dans le processus et ne l'invalide qu'en recevant un message
# Windows. Un script console n'a pas de pompe a messages -- l'agent interrogeait
# donc indefiniment la photo prise a son demarrage, et un ecran branche en cours
# de route n'apparaissait jamais. EnumDisplayMonitors, lui, demande au systeme a
# chaque appel.
#
# SetProcessDPIAware met les coordonnees en pixels PHYSIQUES, le meme repere que
# le releve de l'API (app/services/materiel.py) et que le lanceur engendre.
# Sans lui, un affichage a 150 % rendrait 2133x1333 la ou le lanceur attend
# 3200x2000, et les fenetres tomberaient a cote.
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public class MoniteursWin {
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left, Top, Right, Bottom; }

  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  public struct MONITORINFOEX {
    public int cbSize;
    public RECT rcMonitor;
    public RECT rcWork;
    public uint dwFlags;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string szDevice;
  }

  delegate bool Rappel(IntPtr hMonitor, IntPtr hdc, ref RECT rect, IntPtr donnee);

  [DllImport("user32.dll")]
  static extern bool EnumDisplayMonitors(IntPtr hdc, IntPtr clip, Rappel rappel, IntPtr donnee);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)]
  static extern bool GetMonitorInfo(IntPtr hMonitor, ref MONITORINFOEX info);
  [DllImport("user32.dll")]
  static extern bool SetProcessDPIAware();

  // « nom|x|y|largeur|hauteur|principal », une ligne par moniteur.
  public static List<string> Lister() {
    SetProcessDPIAware();
    var trouves = new List<string>();
    EnumDisplayMonitors(IntPtr.Zero, IntPtr.Zero,
      delegate (IntPtr hMonitor, IntPtr hdc, ref RECT rect, IntPtr donnee) {
        var info = new MONITORINFOEX();
        info.cbSize = Marshal.SizeOf(typeof(MONITORINFOEX));
        if (GetMonitorInfo(hMonitor, ref info)) {
          trouves.Add(string.Format("{0}|{1}|{2}|{3}|{4}|{5}",
            info.szDevice,
            info.rcMonitor.Left, info.rcMonitor.Top,
            info.rcMonitor.Right - info.rcMonitor.Left,
            info.rcMonitor.Bottom - info.rcMonitor.Top,
            (info.dwFlags & 1) != 0));
        }
        return true;
      }, IntPtr.Zero);
    return trouves;
  }
}
"@

$racine = Split-Path -Parent $PSScriptRoot
$env_fichier = Join-Path $racine ".env"

function Valeur-Env([string]$cle, [string]$defaut) {
  if (Test-Path $env_fichier) {
    $ligne = Select-String -Path $env_fichier -Pattern "^$cle=(.*)$" | Select-Object -First 1
    if ($ligne) { return $ligne.Matches[0].Groups[1].Value.Trim() }
  }
  return $defaut
}

if (-not $ApiHost) { $ApiHost = "http://localhost:$(Valeur-Env 'API_PORT' '8080')" }
if (-not $Token)   { $Token   = Valeur-Env 'DEFAULT_KIOSK_TOKEN' '' }
if (-not $Token)   { throw "Aucun jeton de borne : renseigner DEFAULT_KIOSK_TOKEN dans .env, ou passer -Token" }

function Releve-Ecrans {
  [MoniteursWin]::Lister() | ForEach-Object {
    $c = $_ -split "\|"
    [ordered]@{
      peripherique = $c[0]
      modele       = ""
      x            = [int]$c[1]
      y            = [int]$c[2]
      largeur      = [int]$c[3]
      hauteur      = [int]$c[4]
      principal    = [bool]::Parse($c[5])
    }
  }
}

function Pousser($ecrans) {
  # Un tableau d'un seul element se serialise en objet sous PowerShell 5.1 :
  # on assemble le corps nous-memes plutot que de dependre de ce piege.
  $liste = @($ecrans | ForEach-Object { $_ | ConvertTo-Json -Compress })
  $corps = "{""systeme"":""Windows"",""ecrans"":[$($liste -join ',')]}"
  Invoke-RestMethod -Method Post -Uri "$ApiHost/api/kiosk/materiel" `
    -Headers @{ "X-Kiosk-Token" = $Token } `
    -ContentType "application/json; charset=utf-8" -Body $corps | Out-Null
  Write-Host "$(Get-Date -Format 'HH:mm:ss') $($liste.Count) ecran(s) annonce(s) a $ApiHost"
}

# On interroge plutot que d'ecouter DisplaySettingsChanged : l'evenement
# demande une pompe a messages, qu'un script lance par une tache planifiee n'a
# pas toujours. Comparer une signature toutes les cinq secondes ne coute rien
# et ne rate aucun cas -- y compris ceux que l'evenement n'emet pas.
function Signature($ecrans) {
  ($ecrans | ForEach-Object { "$($_.peripherique):$($_.x),$($_.y),$($_.largeur)x$($_.hauteur)" }) -join "|"
}

$ecrans = Releve-Ecrans
Pousser $ecrans
if ($UneFois) { exit 0 }

$precedente = Signature $ecrans
$dernier = Get-Date
while ($true) {
  Start-Sleep -Seconds $Secondes
  $ecrans = Releve-Ecrans
  $courante = Signature $ecrans
  # Reannoncer meme sans changement, toutes les cinq minutes : c'est ce qui
  # distingue « rien n'a bouge » de « l'agent est mort ». Sans ce battement,
  # le back-office afficherait indefiniment le dernier releve connu, et une
  # borne dont l'agent s'est arrete ressemblerait a une borne en bon etat.
  $battu = ((Get-Date) - $dernier).TotalSeconds -ge $Battement
  if ($courante -ne $precedente -or $battu) {
    if ($courante -ne $precedente) { Write-Host "changement d'affichage detecte" }
    try { Pousser $ecrans; $precedente = $courante; $dernier = Get-Date }
    # L'API redemarre, le reseau hoquette : on retentera au tour suivant. Ne
    # pas avancer la signature, sinon le changement serait perdu.
    catch { Write-Warning "annonce refusee : $($_.Exception.Message)" }
  }
}
