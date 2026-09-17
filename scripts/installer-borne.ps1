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

Write-Host "`n[5] Docker, dans WSL2" -ForegroundColor White
# Pourquoi pas Docker Desktop : c'est une application de bureau, qui s'affiche
# quand elle le decide -- ecran d'accueil, invitation a creer un compte, mise a
# jour -- devant les visiteurs, et ou un clic arrete un conteneur. Meme reglee
# pour demarrer reduite, elle finit par ouvrir une fenetre. Docker Engine dans
# WSL2 est un service Linux : aucune interface, jamais.
$distro = $env:AIXAM_WSL_DISTRO; if (-not $distro) { $distro = "Ubuntu-24.04" }

Etat ((wsl.exe -l -q 2>$null) -replace "`0", "" -contains $distro) `
     "distribution $distro installee" {
       wsl.exe --install -d $distro --no-launch
       wsl.exe -d $distro -u root -e true
     }

# systemd, parce que c'est lui qui relancera dockerd a chaque demarrage de la
# distribution, sans que personne n'ait rien a lancer.
Etat ((wsl.exe -d $distro -u root -e sh -c "grep -q systemd=true /etc/wsl.conf 2>/dev/null && echo oui") -match "oui") `
     "systemd actif dans $distro" {
       wsl.exe -d $distro -u root -e sh -c "printf '[boot]\nsystemd=true\n\n[user]\ndefault=root\n' > /etc/wsl.conf"
       wsl.exe --shutdown
     }

Etat ((wsl.exe -d $distro -u root -e sh -c "command -v docker >/dev/null && systemctl is-enabled docker 2>/dev/null") -match "enabled") `
     "docker installe et lance au demarrage de $distro" {
       wsl.exe -d $distro -u root -e sh -c "export DEBIAN_FRONTEND=noninteractive; apt-get update -qq && apt-get install -y -qq docker.io docker-compose-v2 curl && systemctl enable --now docker"
     }

# Une tache suffit a tout relancer : demarrer la distribution demarre systemd,
# qui demarre dockerd, qui relance les conteneurs (restart: unless-stopped).
Etat ([bool](Get-ScheduledTask -TaskName aixam-docker -ErrorAction SilentlyContinue)) `
     "tache aixam-docker : demarre WSL a l'ouverture de session" {
       Tache "aixam-docker" "wsl.exe" "-d $distro -u root -e /bin/true" "PT15S"
     }

# Docker Desktop, s'il reste installe, ne doit surtout pas se lancer a cote :
# deux moteurs se disputeraient le port 8080, et sa fenetre reviendrait.
$reglages = Join-Path $env:APPDATA "Docker\settings-store.json"
if (Test-Path $reglages) {
  $j = Get-Content $reglages -Raw | ConvertFrom-Json
  $lancee = (Get-ItemProperty "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -ErrorAction SilentlyContinue).PSObject.Properties.Name -contains "Docker Desktop"
  Etat ((-not $j.AutoStart) -and (-not $lancee)) "Docker Desktop ne demarre plus" {
    Copy-Item $reglages "$reglages.avant-aixam" -Force
    $j.AutoStart = $false
    # Jamais Set-Content -Encoding UTF8 : il ajoute un BOM sous PowerShell 5.1,
    # Docker refuse alors de lire ses reglages et repart sur ses valeurs par
    # defaut, AutoStart compris.
    [System.IO.File]::WriteAllText($reglages, ($j | ConvertTo-Json -Depth 20),
                                   (New-Object System.Text.UTF8Encoding($false)))
    Remove-ItemProperty "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "Docker Desktop" -ErrorAction SilentlyContinue
  }
}

Write-Host "`n[6] Taches de la session ouverte" -ForegroundColor White
# Ni l'agent des ecrans ni le navigateur ne peuvent etre lances par SSH : une
# session reseau ne voit qu'un ecran virtuel 1024x768. Une tache /it, elle,
# s'execute dans la session de l'utilisateur, donc sur les vrais moniteurs.
$agent = Join-Path $Racine "scripts\agent-ecrans.ps1"
Etat ([bool](Get-ScheduledTask -TaskName aixam-ecrans -ErrorAction SilentlyContinue)) `
     "tache aixam-ecrans, a l'ouverture de session" {
       # Apres Docker : l'agent pousse son releve a l'API, autant qu'elle
       # ecoute. S'il pousse trop tot, il retentera cinq secondes plus tard.
       Tache "aixam-ecrans" "powershell.exe" `
         "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$agent`"" "PT1M"
     }

Write-Host "`n--- Reste a faire a la main ---" -ForegroundColor White
Write-Host @"
  - Ouverture de session automatique : netplwiz, apres avoir mis a 0
    HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device
    \DevicePasswordLessBuildVersion. Sans elle, une coupure de courant laisse
    la borne sur l'ecran de connexion.
  - Rien a faire pour docker : il tourne dans WSL2, en service, et la tache
    aixam-docker demarre la distribution a l'ouverture de session.
  - AnyDesk : mot de passe d'acces non surveille, sinon chaque prise en main
    demande un clic sur place.
  - Reservation DHCP de l'adresse de la borne dans la box.
  - La cle publique du poste d'administration dans
    C:\ProgramData\ssh\administrators_authorized_keys (droits Administrateurs
    et SYSTEME seuls, voir README).
"@

if ($Verifier) { Write-Host "`n$script:Manques point(s) a regler.`n" }
else { Write-Host "`nBorne prete. Relancer avec -Verifier pour controler.`n" }
