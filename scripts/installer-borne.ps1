<#
Prepare un PC Windows pour tenir le role de borne, et le dit quand c'est deja fait.

Ce que ce script existe pour eviter : une borne reglee a la main un mois plus
tot, dont personne ne sait plus ce qui a ete touche. Tout ce qui suit a ete
necessaire sur la borne du Mondial 2026 ; le refaire doit prendre une commande,
pas une soiree.

    powershell -ExecutionPolicy Bypass -File scripts\installer-borne.ps1
    powershell -ExecutionPolicy Bypass -File scripts\installer-borne.ps1 -Verifier

-Verifier ne change rien : il dit seulement ce qui manque. Le script est
rejouable -- chaque etape regarde avant d'agir.

Demande une console ELEVEE (service SSH, registre, pare-feu, alimentation).

Ce qui n'est PAS ici, faute de pouvoir l'automatiser sans stocker un mot de
passe ou cliquer dans une interface, et qui est rappele a la fin :
ouverture de session automatique, demarrage de Docker Desktop a l'ouverture de
session, mot de passe d'acces non surveille d'AnyDesk, reservation DHCP.
#>
param(
  [switch]$Verifier,
  [string]$Compte = $env:USERNAME,
  [string]$Racine = (Split-Path -Parent $PSScriptRoot)
)

$script:Manques = 0

function Tache($nom, $exe, $arguments, $delai) {
  # Register-ScheduledTask plutot que schtasks : « C:\Program Files\... » passe
  # sans bataille de guillemets, la ou schtasks refuse l'argument.
  $action = New-ScheduledTaskAction -Execute $exe -Argument $arguments
  $declencheur = New-ScheduledTaskTrigger -AtLogOn -User $Compte
  if ($delai) { $declencheur.Delay = $delai }
  $qui = New-ScheduledTaskPrincipal -UserId $Compte -LogonType Interactive
  # Une borne tourne sur secteur et ne doit jamais etre arretee par les
  # reglages d'economie d'energie de Windows.
  $comment = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
  Register-ScheduledTask -TaskName $nom -Action $action -Trigger $declencheur `
    -Principal $qui -Settings $comment -Force | Out-Null
}

function Etat($fait, $quoi, $comment) {
  # Aucune valeur de retour : PowerShell imprimerait « True » sous chaque ligne.
  if ($fait) { Write-Host "  OK     $quoi" -ForegroundColor Green; return }
  $script:Manques++
  if ($Verifier) { Write-Host "  MANQUE $quoi" -ForegroundColor Yellow; return }
  Write-Host "  ...    $quoi" -ForegroundColor Cyan
  & $comment
  Write-Host "  FAIT   $quoi" -ForegroundColor Green
}

$eleve = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $eleve) {
  throw "Console non elevee. Ouvrir « Terminal (administrateur) » -- la barre de titre doit dire « Administrateur »."
}

Write-Host "`n[1] Serveur SSH" -ForegroundColor White
Etat ((Get-WindowsCapability -Online -Name OpenSSH.Server*).State -eq "Installed") `
     "OpenSSH Server installe" { Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
                                 Write-Warning "Redemarrage necessaire si l'etat reste « InstallPending »." }
Etat ((Get-Service sshd -ErrorAction SilentlyContinue).Status -eq "Running") `
     "service sshd demarre, au demarrage de Windows" { Set-Service sshd -StartupType Automatic; Start-Service sshd }

# Git Bash comme shell SSH : les scripts bin/*.sh s'y lancent tels quels, et
# `C:\aixam` s'y dit `/c/aixam`. Sans cela on tombe dans cmd.exe.
$bash = "C:\Program Files\Git\bin\bash.exe"
Etat ((Get-ItemProperty "HKLM:\SOFTWARE\OpenSSH" -ErrorAction SilentlyContinue).DefaultShell -eq $bash) `
     "Git Bash comme shell des sessions SSH" {
       if (-not (Test-Path $bash)) { throw "Git for Windows absent : winget install --id Git.Git -e" }
       New-ItemProperty "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value $bash -PropertyType String -Force | Out-Null
       New-ItemProperty "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShellCommandOption -Value "-c" -PropertyType String -Force | Out-Null
     }

Write-Host "`n[2] Reseau" -ForegroundColor White
# Un wifi classe « Public » bloque le 22 : la borne devient injoignable sans
# que rien ne le dise, et le diagnostic se perd dans les regles de pare-feu.
$profil = Get-NetConnectionProfile | Where-Object { $_.IPv4Connectivity -ne "Disconnected" } | Select-Object -First 1
Etat ($profil -and $profil.NetworkCategory -ne "Public") `
     "reseau « $($profil.Name) » en profil prive" { Set-NetConnectionProfile -InterfaceAlias $profil.InterfaceAlias -NetworkCategory Private }
Etat ([bool](Get-NetFirewallRule -Name sshd -ErrorAction SilentlyContinue)) `
     "pare-feu : port 22 ouvert" {
       New-NetFirewallRule -Name sshd -DisplayName "OpenSSH Server (sshd)" -Enabled True `
         -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -Profile Any | Out-Null
     }

Write-Host "`n[3] Mise en veille" -ForegroundColor White
# La panne numero un d'une borne : l'ecran s'eteint pendant la pause dejeuner.
# Les libelles de powercfg sont traduits : on lit les valeurs, pas les phrases.
# Les deux dernieres sont l'index secteur puis l'index batterie.
$index = @(powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE |
           Select-String "0x[0-9a-fA-F]{8}" -AllMatches |
           ForEach-Object { $_.Matches.Value })
$veille = $index.Count -ge 2 -and $index[-2] -eq "0x00000000"
Etat $veille "ecran, disque et session sans mise en veille" {
  powercfg /change monitor-timeout-ac 0; powercfg /change standby-timeout-ac 0
  powercfg /change disk-timeout-ac 0;    powercfg /change hibernate-timeout-ac 0
}

Write-Host "`n[4] Shell de travail" -ForegroundColor White
$bashrc = Join-Path $env:USERPROFILE ".bashrc"
$modele = Join-Path $PSScriptRoot "win\bashrc-borne"
Etat ((Test-Path $bashrc) -and ((Get-Content $bashrc -Raw) -eq (Get-Content $modele -Raw))) `
     "~/.bashrc : prompt, couleurs et raccourcis du depot" {
       Copy-Item $modele $bashrc -Force
       Set-Content (Join-Path $env:USERPROFILE ".bash_profile") '[ -f ~/.bashrc ] && . ~/.bashrc'
     }

Write-Host "`n[5] L'application, en local" -ForegroundColor White
# Pourquoi ni Docker Desktop ni WSL : sur la borne, l'API tourne en local. Une
# application de bureau s'affiche quand elle le decide devant les visiteurs,
# et une machine virtuelle impose des ponts reseau pour servir un site --
# trois couches pour deux processus et une base. En local, chaque piece est
# visible dans le gestionnaire des taches, et l'API voit les moniteurs
# elle-meme : plus d'agent des ecrans.
foreach ($paquet in @(
  @{ id = "Python.Python.3.12";      quoi = "Python 3.12";         test = { Get-Command py, python3.12, python -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike "*WindowsApps*" } } },
  @{ id = "OpenJS.NodeJS.LTS";       quoi = "Node.js (compile les fronts)"; test = { Get-Command npm -ErrorAction SilentlyContinue } },
  @{ id = "tschoonj.GTKForWindows";  quoi = "runtime GTK (cairo, pour le rendu des SVG)"; test = { Test-Path "C:\Program Files\GTK3-Runtime Win64\bin\libcairo-2.dll" } },
  @{ id = "PostgreSQL.PostgreSQL.16"; quoi = "PostgreSQL 16"; test = { Get-Service postgresql-x64-16 -ErrorAction SilentlyContinue } }
)) {
  $id = $paquet.id
  Etat ([bool](& $paquet.test)) $paquet.quoi { winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements | Out-Null }
}

$pg = Get-Service postgresql-x64-16 -ErrorAction SilentlyContinue
Etat ($pg -and $pg.StartType -eq "Automatic" -and $pg.Status -eq "Running") `
     "PostgreSQL demarre, au demarrage de Windows" { Set-Service postgresql-x64-16 -StartupType Automatic; Start-Service postgresql-x64-16 }

# Le runtime GTK n'est cherche que dans PATH : sans cette ligne, cairosvg ne
# trouve pas libcairo-2.dll et le rendu des creations echoue.
$gtk = "C:\Program Files\GTK3-Runtime Win64\bin"
Etat (([Environment]::GetEnvironmentVariable("Path", "Machine") -split ";") -contains $gtk) `
     "runtime GTK dans le PATH" {
       [Environment]::SetEnvironmentVariable("Path", ([Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + $gtk), "Machine")
     }

$venv = Join-Path $Racine ".venv\Scripts\uvicorn.exe"
Etat (Test-Path $venv) "environnement Python de l'API (.venv)" {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) { & py -3.12 -m venv (Join-Path $Racine ".venv") } else { & python -m venv (Join-Path $Racine ".venv") }
  & (Join-Path $Racine ".venv\Scripts\pip.exe") install -q -r (Join-Path $Racine "apps\api\requirements.txt")
}

# L'API et le worker : un seul lanceur, bin/start.sh --local, dans la session
# ouverte -- c'est de la que l'API voit les ecrans. Et le vestige de l'epoque
# docker ne doit plus rien lancer.
$bash = "C:\Program Files\Git\bin\bash.exe"
$tacheApi = Get-ScheduledTask -TaskName aixam-api -ErrorAction SilentlyContinue
Etat ($tacheApi -and ($tacheApi.Actions.Arguments -like "*start.sh*")) `
     "tache aixam-api : API et worker a l'ouverture de session" {
       $racineBash = "/" + ($Racine -replace ":", "" -replace "\\", "/")
       Tache "aixam-api" $bash "-lc `"cd '$racineBash' && bin/start.sh --all --local`"" "PT10S"
     }
foreach ($ancienne in "aixam-docker", "aixam-ecrans") {
  Etat (-not (Get-ScheduledTask -TaskName $ancienne -ErrorAction SilentlyContinue)) "plus de tache $ancienne" {
    Unregister-ScheduledTask -TaskName $ancienne -Confirm:$false
  }
}
Etat (-not ((netsh interface portproxy show v4tov4) -match "8080")) "plus de redirection de port" {
  netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=8080 | Out-Null
}
Etat ([bool](Get-NetFirewallRule -Name aixam-api-8080 -ErrorAction SilentlyContinue)) "pare-feu : port 8080 ouvert" {
  New-NetFirewallRule -Name aixam-api-8080 -DisplayName "AIXAM API 8080" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Any | Out-Null
}

$reglages = Join-Path $env:APPDATA "Docker\settings-store.json"
if (Test-Path $reglages) {
  $j = Get-Content $reglages -Raw | ConvertFrom-Json
  $lancee = (Get-ItemProperty "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -ErrorAction SilentlyContinue).PSObject.Properties.Name -contains "Docker Desktop"
  Etat ((-not $j.AutoStart) -and (-not $lancee)) "Docker Desktop ne demarre plus" {
    $j.AutoStart = $false
    [System.IO.File]::WriteAllText($reglages, ($j | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding($false)))
    Remove-ItemProperty "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "Docker Desktop" -ErrorAction SilentlyContinue
  }
}

Write-Host "`n--- Reste a faire a la main ---" -ForegroundColor White
Write-Host @"
  - Ouverture de session automatique : netplwiz, apres avoir mis a 0
    HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device
    \DevicePasswordLessBuildVersion. Sans elle, une coupure de courant laisse
    la borne sur l'ecran de connexion.
  - Dans .env : COMPOSE_PROFILES vide, POSTGRES_HOST=localhost, BUILD_MODE=local,
    et le role/base PostgreSQL crees (voir README, « Installation sur le salon »).
  - AnyDesk : mot de passe d'acces non surveille, sinon chaque prise en main
    demande un clic sur place.
  - Reservation DHCP de l'adresse de la borne dans la box.
  - La cle publique du poste d'administration dans
    C:\ProgramData\ssh\administrators_authorized_keys (droits Administrateurs
    et SYSTEME seuls, voir README).
"@

if ($Verifier) { Write-Host "`n$script:Manques point(s) a regler.`n" }
else { Write-Host "`nBorne prete. Relancer avec -Verifier pour controler.`n" }
