# Demarre docker dans WSL2 et expose l'API sur le reseau.
#
# Lance par la tache aixam-docker a l'ouverture de session. Deux choses :
#
# 1. Demarrer la distribution : systemd y demarre dockerd, et les conteneurs
#    reviennent seuls (restart: unless-stopped).
#
# 2. Rendre l'API joignable depuis le reseau. Docker publie bien 0.0.0.0:8080,
#    mais dans la VM WSL2, qui a son propre reseau NAT : Windows ne relaie vers
#    elle que ce qui s'adresse a localhost. Ce qui arrive sur l'adresse de la
#    machine n'y entre pas -- avant, Docker Desktop faisait ce pont lui-meme.
#    Une redirection de port Windows le remplace. L'IP de la VM change a
#    chaque demarrage, d'ou son recalcul ici plutot qu'une valeur figee.
#
#   powershell -ExecutionPolicy Bypass -File scripts\demarrer-docker.ps1
param(
  [string]$Distro = $(if ($env:AIXAM_WSL_DISTRO) { $env:AIXAM_WSL_DISTRO } else { "Ubuntu-24.04" })
)

$racine = Split-Path -Parent $PSScriptRoot
$port = 8080
$env_fichier = Join-Path $racine ".env"
if (Test-Path $env_fichier) {
  $ligne = Select-String -Path $env_fichier -Pattern "^API_PORT=(\d+)" | Select-Object -First 1
  if ($ligne) { $port = [int]$ligne.Matches[0].Groups[1].Value }
}

Write-Host "demarrage de $Distro"
wsl.exe -d $Distro -u root -e /bin/true

# dockerd met quelques secondes apres systemd ; on attend qu'il reponde.
$pret = $false
for ($i = 0; $i -lt 30 -and -not $pret; $i++) {
  $pret = (wsl.exe -d $Distro -u root -e sh -c "docker info >/dev/null 2>&1 && echo oui") -match "oui"
  if (-not $pret) { Start-Sleep -Seconds 2 }
}
if (-not $pret) { Write-Warning "dockerd ne repond pas apres 60 s" }

$ip = ((wsl.exe -d $Distro -u root -e sh -c "hostname -I") -replace "`0", "").Trim().Split(" ")[0]
if (-not $ip) { throw "adresse de la VM WSL introuvable" }

# `delete` echoue si la redirection n'existe pas encore : sans importance.
netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$port 2>&1 | Out-Null
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$port connectaddress=$ip connectport=$port | Out-Null
Write-Host "0.0.0.0:$port -> ${ip}:$port"

if (-not (Get-NetFirewallRule -Name aixam-api-$port -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -Name aixam-api-$port -DisplayName "AIXAM API $port" -Direction Inbound `
    -Protocol TCP -LocalPort $port -Action Allow -Profile Any | Out-Null
}
