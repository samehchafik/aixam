@echo off
rem Assistant d'identifiants docker qui ne connait personne -- voir
rem bin/plateforme.sh. Le CLI l'appelle a chaque acces au registre ; en
rem repondant des identifiants vides, il tire les images publiques sans
rem jamais ouvrir le coffre de Windows, inaccessible en session SSH.
if "%~1"=="get" (
  echo {"ServerURL":"","Username":"","Secret":""}
) else (
  echo {}
)
exit /b 0
