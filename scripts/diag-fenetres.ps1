# Ou en sont les fenetres de la borne, vu de l'interieur de la session.
#
# A lancer sur la borne pendant que les fenetres sont ouvertes : pour chaque
# fenetre Chrome, son rectangle reel, si l'attribut « toujours au premier plan »
# est pose, et si elle couvre l'ecran entier ou s'arrete a la zone de travail
# (l'ecran moins la barre des taches). Depuis SSH on ne voit rien de tout ca :
# une session reseau n'a ni fenetres ni moniteurs.
#
#   powershell -ExecutionPolicy Bypass -File scripts\diag-fenetres.ps1
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class DiagWin {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern IntPtr FindWindow(string c, string t);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
}
"@
[DiagWin]::SetProcessDPIAware() | Out-Null
$GWL_EXSTYLE = -20; $WS_EX_TOPMOST = 0x8
$devant = [DiagWin]::GetForegroundWindow()

"--- ecrans (pixels physiques) ---"
foreach ($e in [System.Windows.Forms.Screen]::AllScreens) {
  "{0,-14} ecran {1}  zone de travail {2}  principal={3}" -f $e.DeviceName, $e.Bounds, $e.WorkingArea, $e.Primary
}

"--- barre des taches ---"
$barre = [DiagWin]::FindWindow("Shell_TrayWnd", $null)
$r = New-Object DiagWin+RECT; [DiagWin]::GetWindowRect($barre, [ref]$r) | Out-Null
"rect {0},{1} -> {2},{3}  topmost={4}" -f $r.L, $r.T, $r.R, $r.B, (([DiagWin]::GetWindowLong($barre, $GWL_EXSTYLE) -band $WS_EX_TOPMOST) -ne 0)

"--- fenetres chrome ---"
Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
  $h = $_.MainWindowHandle
  $r = New-Object DiagWin+RECT; [DiagWin]::GetWindowRect($h, [ref]$r) | Out-Null
  $ex = [DiagWin]::GetWindowLong($h, $GWL_EXSTYLE)
  $ecran = [System.Windows.Forms.Screen]::FromHandle($h)
  $couvre = if ($r.B -ge $ecran.Bounds.Bottom -and $r.R -ge $ecran.Bounds.Right) { "ecran ENTIER" }
            elseif ($r.B -ge $ecran.WorkingArea.Bottom) { "zone de travail seulement" } else { "moins que la zone de travail" }
  "pid {0,-6} {1}  rect {2},{3} -> {4},{5}  topmost={6}  focus={7}  couvre : {8}  titre « {9} »" -f `
    $_.Id, $ecran.DeviceName, $r.L, $r.T, $r.R, $r.B, (($ex -band $WS_EX_TOPMOST) -ne 0), ($h -eq $devant), $couvre, $_.MainWindowTitle
}
