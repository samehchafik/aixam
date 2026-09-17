@echo off
rem Demarrage de la borne : ferme tout Chrome, attend l'API, ouvre les fenetres.
rem
rem Point d'entree unique -- la tache planifiee aixam-borne l'appelle a
rem l'ouverture de session, et c'est lui qu'on relance a la main si une
rem fenetre a ete fermee. Il part toujours d'un bureau vide : un Chrome deja
rem ouvert avec le meme profil recevrait la commande par delegation et le
rem lanceur n'aurait plus de fenetre a placer.
rem
rem   demarrage\start.bat
setlocal
set "RACINE=%~dp0.."
set "PORT=8080"
for /f "usebackq tokens=1,* delims==" %%a in ("%RACINE%\.env") do if /i "%%a"=="API_PORT" set "PORT=%%b"
set "HOTE=http://localhost:%PORT%"

echo == fermeture de tout Chrome
taskkill /IM chrome.exe /F /T >nul 2>&1
call "%~dp0stop-clavier.bat"

echo == Ctrl+Q fermera la borne
start "" /b powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%RACINE%\scripts\arret-clavier.ps1" -Pid "%RACINE%\.run\arret-clavier.pid"

echo == attente de l'API sur %HOTE%
set /a ESSAIS=0
:attente
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri '%HOTE%/healthz' -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { $false }" | findstr /i true >nul
if %errorlevel%==0 goto prete
set /a ESSAIS+=1
if %ESSAIS% geq 90 (
  echo l'API ne repond pas apres trois minutes : fenetres non ouvertes.
  echo   verifier : schtasks /run /tn aixam-api   puis   .run\api.log
  exit /b 1
)
rem ping plutot que timeout : timeout refuse une entree standard redirigee.
ping -n 3 127.0.0.1 >nul
goto attente

:prete
echo == API prete, ouverture des fenetres
if not exist "%~dp0launch-kiosk-genere.ps1" (
  echo lanceur absent : le generer depuis Reglages ^> Ecrans, ou scripts\regenerer_lanceur.py
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-kiosk-genere.ps1"
