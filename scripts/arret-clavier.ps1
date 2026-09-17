# Ferme la borne au clavier : Ctrl+Q ferme tout Chrome. Et tant qu'il veille,
# il garde les fenetres de la borne « toujours au premier plan ».
#
# Pourquoi un veilleur : Chrome sous Windows n'a pas de Ctrl+Q (c'est un
# raccourci macOS et Linux), et les fenetres du kiosque sont posees au-dessus
# de tout, barre des taches comprise -- il faut un geste sur qui rende la main.
# RegisterHotKey enregistre la combinaison aupres de Windows, qui la remet a ce
# script AVANT toute fenetre : elle marche quelle que soit celle qui a le
# focus, et Chrome ne la voit jamais.
#
# Le topmost : Chrome n'a aucune option pour ca (verifie dans la liste complete
# de ses options), seule l'API Windows le pose sur la fenetre -- et Chrome le
# perd en refaisant sa fenetre, a sa transition plein ecran ou plus tard. Le
# lanceur le pose ; ce veilleur le reaffirme chaque seconde, sans toucher a la
# position ni au focus, tant que la borne tourne.
#
# Lance par demarrage\start.bat, sans fenetre ; s'arrete de lui-meme apres
# avoir ferme Chrome, start.bat en relance un a chaque demarrage.
#
#   powershell -ExecutionPolicy Bypass -File scripts\arret-clavier.ps1 [-Touche Q] [-Modif Ctrl|Ctrl+Alt]
param(
  [string]$Touche = "Q",
  [string]$Modif = "Ctrl",
  [string]$Pid = ""
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class RaccourciWin {
  [DllImport("user32.dll")] public static extern bool RegisterHotKey(IntPtr h, int id, uint mod, uint vk);
  [DllImport("user32.dll")] public static extern bool UnregisterHotKey(IntPtr h, int id);
  [StructLayout(LayoutKind.Sequential)]
  public struct MSG { public IntPtr hwnd; public uint message; public IntPtr wParam; public IntPtr lParam; public uint time; public int x; public int y; }
  [DllImport("user32.dll")] public static extern int GetMessage(out MSG m, IntPtr h, uint min, uint max);
  [DllImport("user32.dll")] public static extern UIntPtr SetTimer(IntPtr h, UIntPtr id, uint ms, IntPtr proc);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr z, int x, int y, int w, int hh, uint f);
  public static readonly IntPtr TOPMOST = new IntPtr(-1);
}
"@

$MOD = @{ Alt = 0x0001; Ctrl = 0x0002; Shift = 0x0004; Win = 0x0008 }
$modificateurs = 0x4000   # MOD_NOREPEAT : une frappe, un evenement
foreach ($m in $Modif -split "\+") { $modificateurs = $modificateurs -bor $MOD[$m] }
$vk = [int][char]$Touche.ToUpper()
$WM_HOTKEY = 0x0312
$WM_TIMER = 0x0113

if ($Pid) { Set-Content -Path $Pid -Value $PID }
if (-not [RaccourciWin]::RegisterHotKey([IntPtr]::Zero, 1, $modificateurs, $vk)) {
  throw "$Modif+$Touche est deja pris par un autre programme."
}
Write-Host "$Modif+$Touche ferme la borne (veilleur pid $PID)"
# Un minuteur de fil, sans fenetre : WM_TIMER arrive dans la meme boucle que
# le raccourci.
[RaccourciWin]::SetTimer([IntPtr]::Zero, [UIntPtr]::Zero, 1000, [IntPtr]::Zero) | Out-Null

$msg = New-Object RaccourciWin+MSG
while ([RaccourciWin]::GetMessage([ref]$msg, [IntPtr]::Zero, 0, 0) -gt 0) {
  if ($msg.message -eq $WM_TIMER) {
    # SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE : seul l'ordre change.
    Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
      [RaccourciWin]::SetWindowPos($_.MainWindowHandle, [RaccourciWin]::TOPMOST, 0, 0, 0, 0, 0x0013) | Out-Null
    }
    continue
  }
  if ($msg.message -eq $WM_HOTKEY) {
    Write-Host "$(Get-Date -Format HH:mm:ss) $Modif+$Touche : fermeture de Chrome"
    taskkill /IM chrome.exe /F /T 2>&1 | Out-Null
    break
  }
}
[RaccourciWin]::UnregisterHotKey([IntPtr]::Zero, 1) | Out-Null
if ($Pid) { Remove-Item $Pid -ErrorAction SilentlyContinue }
