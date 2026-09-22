@echo off
setlocal
rem Demarrage de la borne, au choix : un ecran, ou les deux.
rem
rem   demarrage\borne-start.bat -b=all       les deux fenetres, posees chacune
rem                                          sur son moniteur par le lanceur
rem                                          engendre (launch-borne-genere.ps1)
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
rem Un seul ecran n'a rien a placer : borne.exe s'ouvre sur l'ecran principal,
rem plein ecran, sans bord et au premier plan. Alt+F4 ferme la fenetre et
rem termine le programme ; Ctrl+Q les ferme toutes (arret-clavier.ps1).

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

call :dire "== fermeture des fenetres en cours"
rem borne.exe d'abord : c'est lui qui sert desormais. Chrome reste ferme aussi,
rem le temps que toutes les bornes soient passees a borne.exe.
taskkill /IM borne.exe /F /T >nul 2>&1
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

rem Un seul ecran : borne.exe directement, sur l'ecran principal.
set "BORNE=%RACINE%\bin\win\borne.exe"
if not exist "%BORNE%" set "BORNE=%~dp0borne.exe"
if not exist "%BORNE%" (
  call :dire "borne.exe introuvable : le compiler (voir README) et le deposer dans bin\win\."
  exit /b 1
)
call :dire "== API prete, ouverture du %ROLE% sur l'ecran par defaut"
start "" "%BORNE%" %HOTE%%CHEMIN% --ecran principal --titre "AIXAM %ROLE%"
call :dire "%ROLE% ouvert : %HOTE%%CHEMIN%"
exit /b 0

:tous
call :dire "== API prete, ouverture des deux fenetres"
rem Le lanceur des fenetres borne.exe. Repli sur l'ancien lanceur Chrome tant
rem qu'il n'a pas ete regenere : une borne ne doit pas rester noire parce qu'un
rem fichier a change de nom.
set "LANCEUR=%~dp0launch-borne-genere.ps1"
if not exist "%LANCEUR%" (
  if exist "%~dp0launch-kiosk-genere.ps1" (
    set "LANCEUR=%~dp0launch-kiosk-genere.ps1"
    call :dire "launch-borne-genere.ps1 absent : repli sur l'ancien lanceur Chrome. Le regenerer depuis Reglages puis Ecrans."
  ) else (
    call :dire "lanceur absent : le generer depuis Reglages puis Ecrans, ou scripts\regenerer_lanceur.py"
    exit /b 1
  )
)
rem Pas Tee-Object : il ecrit en UTF-16, illisible avec les lignes de ce .bat.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%LANCEUR%' *>&1 | ForEach-Object { $_; [IO.File]::AppendAllText('%JOURNAL%', \"$_`r`n\", [Text.Encoding]::UTF8) }"
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
