@echo off
rem Arret de la borne : ferme tout Chrome et le veilleur Ctrl+Q.
rem
rem Le pendant de start.bat, pour un shell ou une session SSH -- le clavier de
rem la borne, lui, fait la meme chose avec Ctrl+Q.
rem
rem   demarrage\stop.bat
echo == fermeture des fenetres de la borne
taskkill /IM borne.exe /F /T >nul 2>&1
taskkill /IM chrome.exe /F /T >nul 2>&1
call "%~dp0stop-clavier.bat"
echo termine.
