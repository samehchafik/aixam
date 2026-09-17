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
rem La tache planifiee lance ce script sans fenetre : sans journal, un echec
rem au demarrage ne laisse aucune trace.
set "JOURNAL=%RACINE%\.run\demarrage.log"
if not exist "%RACINE%\.run" mkdir "%RACINE%\.run"
echo ---- %DATE% %TIME% ---->> "%JOURNAL%"

call :dire "== fermeture de tout Chrome"
taskkill /IM chrome.exe /F /T >nul 2>&1
call "%~dp0stop-clavier.bat"

call :dire "== Ctrl+Q fermera la borne, et le topmost sera maintenu"
start "" /b powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%RACINE%\scripts\arret-clavier.ps1" -Pid "%RACINE%\.run\arret-clavier.pid"

call :dire "== attente de l'API sur %HOTE%"
set /a ESSAIS=0
:attente
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri '%HOTE%/healthz' -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { $false }" | findstr /i true >nul
if %errorlevel%==0 goto prete
set /a ESSAIS+=1
if %ESSAIS% geq 90 (
  call :dire "l'API ne repond pas apres trois minutes : fenetres non ouvertes."
  call :dire "  verifier : schtasks /run /tn aixam-api   puis   .run\api.log"
  exit /b 1
)
rem ping plutot que timeout : timeout refuse une entree standard redirigee.
ping -n 3 127.0.0.1 >nul
goto attente

:prete
call :dire "== API prete, ouverture des fenetres"
if not exist "%~dp0launch-kiosk-genere.ps1" (
  call :dire "lanceur absent : le generer depuis Reglages > Ecrans, ou scripts\regenerer_lanceur.py"
  exit /b 1
)
rem Pas Tee-Object : il ecrit en UTF-16, illisible avec les lignes du .bat.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0launch-kiosk-genere.ps1' 2>&1 | ForEach-Object { $_; [IO.File]::AppendAllText('%JOURNAL%', \"$_`r`n\", [Text.Encoding]::UTF8) }"
exit /b 0

:dire
echo %~1
echo %TIME% %~1>> "%JOURNAL%"
goto :eof
