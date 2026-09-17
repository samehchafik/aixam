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

Write-Host "`n[5] Docker au demarrage" -ForegroundColor White
# Docker Desktop est une application de bureau : rien ne repart sans une
# session ouverte, et son propre reglage « AutoStart » peut etre a false sans
# que l'entree de demarrage disparaisse -- la borne revient alors d'un
# redemarrage avec l'API eteinte et personne pour s'en apercevoir.
# OpenUIOnStartupDisabled compte autant qu'AutoStart : sans lui, le tableau de
# bord de Docker s'ouvre en grand a chaque demarrage, devant les visiteurs et a
# portee de quelqu'un qui n'a aucune raison d'y toucher -- arreter un conteneur
# depuis cette fenetre prend un clic, et arrete l'animation.
$reglages = Join-Path $env:APPDATA "Docker\settings-store.json"
$voulu = @{ AutoStart = $true; OpenUIOnStartupDisabled = $true }
$dejaLa = (Test-Path $reglages) -and $(
  $j = Get-Content $reglages -Raw | ConvertFrom-Json
  -not ($voulu.Keys | Where-Object { $j.$_ -ne $voulu[$_] })
)
Etat $dejaLa "Docker Desktop : demarre seul, sans ouvrir sa fenetre" {
  if (-not (Test-Path $reglages)) { throw "Docker Desktop jamais lance : l'ouvrir une fois, puis relancer ce script." }
  $j = Get-Content $reglages -Raw | ConvertFrom-Json
  foreach ($c in $voulu.Keys) {
    if (-not $j.PSObject.Properties.Name.Contains($c)) { $j | Add-Member -NotePropertyName $c -NotePropertyValue $false }
    $j.$c = $voulu[$c]
  }
  $j | ConvertTo-Json -Depth 20 | Set-Content $reglages -Encoding UTF8
}

$docker = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
Etat ([bool](Get-ScheduledTask -TaskName aixam-docker -ErrorAction SilentlyContinue)) `
     "tache aixam-docker, a l'ouverture de session" {
       if (-not (Test-Path $docker)) { throw "Docker Desktop absent : winget install --id Docker.DockerDesktop -e" }
       # Ceinture et bretelles : le reglage d'AutoStart se perd a une mise a
       # jour de Docker Desktop, la tache non. Lancer deux fois est sans effet,
       # l'application n'admet qu'une instance. Trente secondes de delai : au
       # demarrage, WSL2 et le reseau ne sont pas encore prets.
       Tache "aixam-docker" $docker "-Autostart" "PT30S"
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
  - Docker Desktop : « Start Docker Desktop when you log in », moteur WSL 2,
    et le compte dans le groupe docker-users.
  - AnyDesk : mot de passe d'acces non surveille, sinon chaque prise en main
    demande un clic sur place.
  - Reservation DHCP de l'adresse de la borne dans la box.
  - La cle publique du poste d'administration dans
    C:\ProgramData\ssh\administrators_authorized_keys (droits Administrateurs
    et SYSTEME seuls, voir README).
"@

if ($Verifier) { Write-Host "`n$script:Manques point(s) a regler.`n" }
else { Write-Host "`nBorne prete. Relancer avec -Verifier pour controler.`n" }
