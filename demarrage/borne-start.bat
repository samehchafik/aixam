@echo off
setlocal
rem Demarrage de la borne, au choix : un ecran, ou les deux.
rem
rem   demarrage\borne-start.bat -b=all       les deux fenetres, posees chacune
rem                                          sur son moniteur par le lanceur
rem                                          engendre (launch-kiosk-genere.ps1)
rem   demarrage\borne-start.bat -b=tactile   le tactile seul, sur l'ecran par
rem                                          defaut
rem   demarrage\borne-start.bat -b=grand     le grand ecran seul, sur l'ecran
rem                                          par defaut
rem
rem Sans parametre : all. C'est start.bat qui reste le point d'entree de la
rem tache planifiee ; celui-ci sert a la main, quand on n'a qu'un ecran sous
rem le coude -- un poste de developpement, un test sur le portable, une
rem demonstration sans le second moniteur.
rem
rem Un seul ecran n'a rien a placer : Chrome ouvre son plein ecran sur le
rem moniteur principal, et la fenetre, derniere ouverte, prend le focus qui
rem fait passer la barre des taches derriere. Le veilleur arret-clavier.ps1
rem reaffirme ensuite le premier plan chaque seconde, et Ctrl+Q ferme tout.
rem
rem Meme profil que le lanceur engendre (%LOCALAPPDATA%\aixam-kiosk\<role>) :
rem un Chrome deja ouvert avec ce profil recevrait la commande par delegation,
rem d'ou la fermeture prealable, comme dans start.bat.

set "RACINE=%~dp0.."
set "PORT=8080"
for /f "usebackq tokens=1,* delims==" %%a in ("%RACINE%\.env") do if /i "%%a"=="API_PORT" set "PORT=%%b"
set "HOTE=http://localhost:%PORT%"
set "JOURNAL=%RACINE%\.run\demarrage.log"
if not exist "%RACINE%\.run" mkdir "%RACINE%\.run"

rem -b=tactile | -b=grand | -b=all. Le signe = est un SEPARATEUR pour cmd :
rem tape nu, -b=tactile arrive en %1=-b et %2=tactile ; entre guillemets, il
rem arrive entier. On accepte les deux, et -b tactile par la meme occasion.
set "B=all"
if "%~1"=="" goto choisi
if /i "%~1"=="-b" (
  set "B=%~2"
) else (
  for /f "tokens=1,* delims==" %%a in ("%~1") do (
    if /i not "%%a"=="-b" goto usage
    set "B=%%b"
  )
)
if "%B%"=="" goto usage
:choisi
if /i "%B%"=="tactile" (set "ROLE=tactile" & set "CHEMIN=/kiosk/") else (
if /i "%B%"=="grand"   (set "ROLE=grand-ecran" & set "CHEMIN=/kiosk/#/display") else (
if /i not "%B%"=="all" goto usage))

echo ---- %DATE% %TIME% (borne-start -b=%B%) ---->> "%JOURNAL%"

call :dire "== fermeture de tout Chrome"
taskkill /IM chrome.exe /F /T >nul 2>&1
call "%~dp0stop-clavier.bat"

rem Un journal neuf a chaque lancement : l'ancien fut ecrit en UTF-16 par un
rem Tee-Object, puis complete en UTF-8 -- deux encodages dans un fichier, et
rem plus rien de lisible. Le precedent est garde une fois, en .ancien.
if exist "%RACINE%\.run\arret-clavier.log" move /y "%RACINE%\.run\arret-clavier.log" "%RACINE%\.run\arret-clavier.log.ancien" >nul 2>&1
call :dire "== Ctrl+Q fermera la borne, et le topmost sera maintenu"
start "" /b powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "& '%RACINE%\scripts\arret-clavier.ps1' -FichierPid '%RACINE%\.run\arret-clavier.pid' *>&1 | Out-File -FilePath '%RACINE%\.run\arret-clavier.log' -Append -Encoding utf8"

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
ping -n 3 127.0.0.1 >nul
goto attente

:prete
if /i "%B%"=="all" goto tous

rem Un seul ecran : Chrome directement, sans placement. Memes options que le
rem lanceur engendre -- kiosque, pas de premier lancement, rien en fond, et les
rem trois qui gardent la fenetre vive meme sans le focus.
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  call :dire "Chrome introuvable : fenetre non ouverte."
  exit /b 1
)
call :dire "== API prete, ouverture du %ROLE% sur l'ecran par defaut"
start "" "%CHROME%" --kiosk --no-first-run --no-default-browser-check --disable-translate ^
  --overscroll-history-navigation=0 --disable-pinch ^
  --noerrdialogs --disable-session-crashed-bubble ^
  --autoplay-policy=no-user-gesture-required ^
  --disable-background-networking --disable-sync --disable-component-update ^
  --disable-background-timer-throttling --disable-backgrounding-occluded-windows ^
  --disable-renderer-backgrounding ^
  --user-data-dir="%LOCALAPPDATA%\aixam-kiosk\%ROLE%" ^
  --app=%HOTE%%CHEMIN%
call :dire "%ROLE% ouvert : %HOTE%%CHEMIN%"
exit /b 0

:tous
call :dire "== API prete, ouverture des deux fenetres"
if not exist "%~dp0launch-kiosk-genere.ps1" (
  call :dire "lanceur absent : le generer depuis Reglages > Ecrans, ou scripts\regenerer_lanceur.py"
  exit /b 1
)
rem Pas Tee-Object : il ecrit en UTF-16, illisible avec les lignes de ce .bat.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0launch-kiosk-genere.ps1' *>&1 | ForEach-Object { $_; [IO.File]::AppendAllText('%JOURNAL%', \"$_`r`n\", [Text.Encoding]::UTF8) }"
exit /b 0

:usage
echo usage : %~nx0 [-b=all ^| -b=tactile ^| -b=grand]
echo    all      les deux fenetres, chacune sur son moniteur (defaut)
echo    tactile  l'ecran tactile seul, sur l'ecran par defaut
echo    grand    le grand ecran seul, sur l'ecran par defaut
exit /b 2

:dire
echo %~1
echo %TIME% %~1>> "%JOURNAL%"
goto :eof
