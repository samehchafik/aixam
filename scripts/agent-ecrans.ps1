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

Add-Type -AssemblyName System.Windows.Forms

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
  [System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
    [ordered]@{
      peripherique = $_.DeviceName
      modele       = ""
      x            = $_.Bounds.X
      y            = $_.Bounds.Y
      largeur      = $_.Bounds.Width
      hauteur      = $_.Bounds.Height
      principal    = [bool]$_.Primary
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
