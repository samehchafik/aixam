@echo off
rem Mise a jour de la borne : ferme les fenetres, recupere le code, recompile,
rem relance.
rem
rem A lancer sur la borne elle-meme -- double-clic, cmd ou PowerShell. L'API
rem doit repartir dans la session ouverte pour voir les ecrans : c'est la
rem tache aixam-api qui la relance, jamais une session SSH.
rem
rem   demarrage\mettre-a-jour.bat
setlocal
set "RACINE=%~dp0.."
set "BASH=%ProgramFiles%\Git\bin\bash.exe"
if not exist "%BASH%" (
  echo Git Bash introuvable : %BASH%
  pause
  exit /b 1
)

rem Les scripts bin\*.sh sont des scripts bash : on les confie au bash de Git.
rem CHERE_INVOKING : sans lui, le profil de Git Bash repart du dossier
rem personnel au lieu de rester dans celui de la borne.
rem Les fenetres d'abord : Windows refuse de remplacer bin\win\borne.exe tant
rem qu'il tourne, et le git pull echouerait. start.bat les rouvre a la fin.
echo == fermeture des fenetres de la borne
call "%~dp0stop.bat"
timeout /t 2 /nobreak >nul

echo == recuperation du code, compilation, arret de l'API
cd /d "%RACINE%"
set "CHERE_INVOKING=1"
"%BASH%" -lc "git pull && bin/build.sh --all --local && bin/stop.sh --local"
if errorlevel 1 (
  echo.
  echo La mise a jour a echoue : voir le message ci-dessus. Rien n'a ete relance.
  pause
  exit /b 1
)

echo == relance de l'API et du worker
schtasks /run /tn aixam-api
if errorlevel 1 (
  echo La tache aixam-api n'a pas pu etre lancee.
  pause
  exit /b 1
)

echo == ouverture des fenetres
call "%~dp0start.bat"
