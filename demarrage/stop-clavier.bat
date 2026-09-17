@echo off
rem Arrete le veilleur Ctrl+Q s'il tourne (voir scripts\arret-clavier.ps1).
set "FPID=%~dp0..\.run\arret-clavier.pid"
if exist "%FPID%" (
  for /f %%p in ('type "%FPID%"') do taskkill /PID %%p /F >nul 2>&1
  del "%FPID%" >nul 2>&1
)
