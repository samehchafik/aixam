# Lancement de la borne en Chromium kiosque (Windows).
#   $env:HOST="http://192.168.1.10:8080"; .\scripts\launch-kiosk.ps1
param(
  [string]$ApiHost = $(if ($env:HOST) { $env:HOST } else { "http://localhost:8080" }),
  [string]$TouchPos = "0,0",
  [string]$DisplayPos = "1920,0"
)

$chrome = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $chrome) { throw "Chrome introuvable" }

$common = @(
  "--kiosk", "--no-first-run", "--disable-translate",
  "--overscroll-history-navigation=0", "--disable-pinch",
  "--noerrdialogs", "--disable-session-crashed-bubble"
)

Start-Process $chrome -ArgumentList ($common + @(
  "--user-data-dir=$env:LOCALAPPDATA\aixam-kiosk\display",
  "--window-position=$DisplayPos",
  "--app=$ApiHost/kiosk/#/display"))

Start-Process $chrome -ArgumentList ($common + @(
  "--user-data-dir=$env:LOCALAPPDATA\aixam-kiosk\touch",
  "--window-position=$TouchPos",
  "--app=$ApiHost/kiosk/"))
