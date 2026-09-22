# Ferme la borne au clavier : Ctrl+Q ferme toutes ses fenetres. Et tant qu'il
# veille, il garde celles de Chrome « toujours au premier plan ».
#
# Depuis borne.exe, le maintien au premier plan n'est plus de son ressort :
# l'executable tient sa propre fenetre, et Alt+F4 en ferme une. Ce veilleur
# garde deux roles : Ctrl+Q, qui les ferme TOUTES d'un geste quel que soit
# l'ecran qui a le focus, et le premier plan des fenetres Chrome tant qu'une
# borne n'est pas passee a borne.exe.
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
#
# Journal : demarrage\start.bat le repart a neuf a chaque lancement.
#
# Le fichier de pid s'appelle -FichierPid, pas -Pid : $PID est une variable
# reservee de PowerShell, et l'assigner est une erreur fatale des la premiere
# ligne -- le veilleur n'a jamais demarre tant qu'il s'appelait ainsi.
param(
  [string]$Touche = "Q",
  [string]$Modif = "Ctrl",
  [string]$FichierPid = ""
)

Add-Type @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class RaccourciWin {
  // Les fenetres visibles de Chrome par leur classe, comme « ahk_exe
  // chrome.exe » : Chrome refait parfois sa fenetre, et un handle memorise
  // pointe alors sur une fenetre morte.
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  public static List<IntPtr> FenetresChrome(HashSet<uint> pids) {
    var trouvees = new List<IntPtr>();
    EnumWindows((h, l) => {
      if (!IsWindowVisible(h)) return true;
      uint pid; GetWindowThreadProcessId(h, out pid);
      if (!pids.Contains(pid)) return true;
      var classe = new StringBuilder(64); GetClassName(h, classe, 64);
      if (classe.ToString() == "Chrome_WidgetWin_1") trouvees.Add(h);
      return true;
    }, IntPtr.Zero);
    return trouvees;
  }
  [DllImport("user32.dll")] public static extern bool RegisterHotKey(IntPtr h, int id, uint mod, uint vk);
  [DllImport("user32.dll")] public static extern bool UnregisterHotKey(IntPtr h, int id);
  [StructLayout(LayoutKind.Sequential)]
  public struct MSG { public IntPtr hwnd; public uint message; public IntPtr wParam; public IntPtr lParam; public uint time; public int x; public int y; }
  [DllImport("user32.dll")] public static extern int GetMessage(out MSG m, IntPtr h, uint min, uint max);
  [DllImport("user32.dll")] public static extern UIntPtr SetTimer(IntPtr h, UIntPtr id, uint ms, IntPtr proc);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr z, int x, int y, int w, int hh, uint f);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  public static readonly IntPtr TOPMOST = new IntPtr(-1);
  public static readonly IntPtr TOP = IntPtr.Zero;
  // Le clavier tactile de Windows est-il a l'ecran ? IFrameworkInputPane est
  // l'API prevue pour cela : elle rend le rectangle du clavier, vide s'il est
  // range. Elle vaut pour TabTip (Windows 10) comme pour TextInputHost
  // (Windows 11). A defaut, on cherche la fenetre de TabTip par sa classe.
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [ComImport, Guid("5752238B-24F0-495A-82F1-2FD593056796"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  public interface IFrameworkInputPane {
    [PreserveSig] int Advise([MarshalAs(UnmanagedType.IUnknown)] object w, [MarshalAs(UnmanagedType.IUnknown)] object h, out uint cookie);
    [PreserveSig] int AdviseWithHWND(IntPtr hwnd, [MarshalAs(UnmanagedType.IUnknown)] object h, out uint cookie);
    [PreserveSig] int Unadvise(uint cookie);
    [PreserveSig] int Location(out RECT r);
  }
  [ComImport, Guid("D5120AA3-46BA-44C5-822D-CA8092C1FC72")] public class FrameworkInputPane {}
  static IFrameworkInputPane pane; static bool paneEssaye;
  [DllImport("user32.dll")] public static extern IntPtr FindWindow(string classe, string titre);
  public static bool DetectionClavierDisponible() {
    if (!paneEssaye) { paneEssaye = true; try { pane = (IFrameworkInputPane)new FrameworkInputPane(); } catch { pane = null; } }
    return pane != null;
  }
  public static bool ClavierTactileVisible() {
    if (DetectionClavierDisponible()) {
      try { RECT r; if (pane.Location(out r) == 0) return (r.B - r.T) > 0 && (r.R - r.L) > 0; } catch { pane = null; }
    }
    var tabtip = FindWindow("IPTip_Main_Window", null);
    return tabtip != IntPtr.Zero && IsWindowVisible(tabtip);
  }
  // Un processus sans fenetre n'a pas le droit de donner le focus -- sauf s'il
  // vient de simuler une frappe. Une pression d'Alt, relachee aussitot, suffit.
  public static bool Activer(IntPtr h) {
    keybd_event(0x12, 0, 0, UIntPtr.Zero); keybd_event(0x12, 0, 2, UIntPtr.Zero);
    return SetForegroundWindow(h);
  }
}
"@
Add-Type -AssemblyName System.Windows.Forms

$MOD = @{ Alt = 0x0001; Ctrl = 0x0002; Shift = 0x0004; Win = 0x0008 }
$modificateurs = 0x4000   # MOD_NOREPEAT : une frappe, un evenement
foreach ($m in $Modif -split "\+") { $modificateurs = $modificateurs -bor $MOD[$m] }
$vk = [int][char]$Touche.ToUpper()
$WM_HOTKEY = 0x0312
$WM_TIMER = 0x0113

if ($FichierPid) { Set-Content -Path $FichierPid -Value $PID }
# Le raccourci peut etre refuse -- deja pris par un autre programme dans cette
# session. Ce n'est pas une raison de mourir : le maintien des fenetres au
# premier plan, lui, doit continuer. On le dit, et on veille quand meme.
$raccourci = [RaccourciWin]::RegisterHotKey([IntPtr]::Zero, 1, $modificateurs, $vk)
if ($raccourci) { Write-Host "$(Get-Date -Format HH:mm:ss) $Modif+$Touche ferme la borne (veilleur pid $PID)" }
else { Write-Warning "$Modif+$Touche est deja pris par un autre programme : pas de raccourci, mais les fenetres restent au premier plan (veilleur pid $PID)" }
# Un minuteur de fil, sans fenetre : WM_TIMER arrive dans la meme boucle que
# le raccourci.
[RaccourciWin]::SetTimer([IntPtr]::Zero, [UIntPtr]::Zero, 1000, [IntPtr]::Zero) | Out-Null

# La fenetre du profil « tactile », reconnue par le dossier de profil de son
# processus -- c'est l'ecran du visiteur, celle qu'il faut rendre active quand
# quelque chose lui a pris le focus.
$profilParPid = @{}
function Fenetre-Tactile($fenetres) {
  foreach ($h in $fenetres) {
    $pid = [uint32]0; [RaccourciWin]::GetWindowThreadProcessId($h, [ref]$pid) | Out-Null
    if (-not $profilParPid.ContainsKey($pid)) {
      $ligne = (Get-CimInstance Win32_Process -Filter "ProcessId = $pid" -ErrorAction SilentlyContinue).CommandLine
      $profilParPid[$pid] = if ($ligne -like "*\aixam-kiosk\tactile*") { "tactile" } elseif ($ligne -like "*\aixam-kiosk\*") { "autre" } else { "" }
    }
    if ($profilParPid[$pid] -eq "tactile") { return $h }
  }
  return [IntPtr]::Zero
}

# A qui donner le focus : la fenetre de l'ecran principal si l'on en a une --
# c'est la que vit la barre --, sinon celle du tactile, sinon la premiere.
# Le focus n'allait qu'a l'ecran principal ; sur un portable ferme dont les
# fenetres sont sur des moniteurs annexes, il n'y en a aucune, et le veilleur
# renoncait sans un mot. La barre gardait le dessus.
function Activer-Borne($fenetres, $raison) {
  $cible = [IntPtr]::Zero; $ou = ""
  foreach ($h in $fenetres) {
    if ([System.Windows.Forms.Screen]::FromHandle($h).Primary) { $cible = $h; $ou = "ecran principal"; break }
  }
  if ($cible -eq [IntPtr]::Zero) { $cible = Fenetre-Tactile $fenetres; if ($cible -ne [IntPtr]::Zero) { $ou = "tactile" } }
  if ($cible -eq [IntPtr]::Zero -and $fenetres.Count -gt 0) { $cible = $fenetres[0]; $ou = "premiere fenetre" }
  if ($cible -eq [IntPtr]::Zero) { Write-Warning "$(Get-Date -Format HH:mm:ss) $raison : aucune fenetre a activer"; return }
  $ok = [RaccourciWin]::Activer($cible)
  Write-Host "$(Get-Date -Format HH:mm:ss) $raison : focus a la fenetre ($ou) : $ok"
}

if ([RaccourciWin]::DetectionClavierDisponible()) { Write-Host "$(Get-Date -Format HH:mm:ss) clavier tactile : detection par IFrameworkInputPane" }
else { Write-Host "$(Get-Date -Format HH:mm:ss) clavier tactile : IFrameworkInputPane indisponible, repli sur la fenetre de TabTip" }

$premiereVue = $null; $focusDonne = $false; $clavierVisible = $false
$msg = New-Object RaccourciWin+MSG
while ([RaccourciWin]::GetMessage([ref]$msg, [IntPtr]::Zero, 0, 0) -gt 0) {
  if ($msg.message -eq $WM_TIMER) {
    $pids = New-Object 'System.Collections.Generic.HashSet[uint32]'
    Get-Process chrome -ErrorAction SilentlyContinue | ForEach-Object { [void]$pids.Add([uint32]$_.Id) }
    $fenetres = [RaccourciWin]::FenetresChrome($pids)
    foreach ($h in $fenetres) {
      # Dans la bande des « toujours au premier plan », c'est la derniere
      # fenetre ACTIVEE qui est dessus. Reaffirmer l'attribut ne remonte pas
      # une fenetre qui l'a deja : HWND_TOPMOST pose l'attribut, HWND_TOP la
      # remonte en tete de sa bande. SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE.
      [RaccourciWin]::SetWindowPos($h, [RaccourciWin]::TOPMOST, 0, 0, 0, 0, 0x0013) | Out-Null
      [RaccourciWin]::SetWindowPos($h, [RaccourciWin]::TOP, 0, 0, 0, 0, 0x0013) | Out-Null
    }
    # Le focus, une fois, quelques secondes apres l'apparition des fenetres :
    # Windows ne cache la barre que sous une fenetre plein ecran ACTIVE, et au
    # demarrage c'est le bureau qui l'a.
    if ($fenetres.Count -gt 0 -and -not $focusDonne) {
      if (-not $premiereVue) { $premiereVue = Get-Date }
      elseif (((Get-Date) - $premiereVue).TotalSeconds -ge 8) {
        Activer-Borne $fenetres "demarrage"
        $focusDonne = $true
      }
    } elseif ($fenetres.Count -eq 0) { $premiereVue = $null; $focusDonne = $false; $profilParPid.Clear() }
    # Le clavier tactile de Windows. Il se leve quand le visiteur touche un
    # champ du formulaire -- la borne n'a pas de clavier a elle. C'est une
    # fenetre « toujours au premier plan » qui active Explorer : la barre
    # remonte avec lui, et quand il se range, rien ne rendait le focus a la
    # borne. On le rend au moment ou il disparait.
    if ($fenetres.Count -gt 0) {
      $visible = [RaccourciWin]::ClavierTactileVisible()
      if ($clavierVisible -and -not $visible) { Activer-Borne $fenetres "clavier tactile range" }
      $clavierVisible = $visible
    }
    continue
  }
  if ($msg.message -eq $WM_HOTKEY) {
    Write-Host "$(Get-Date -Format HH:mm:ss) $Modif+$Touche : fermeture des fenetres"
    # borne.exe d'abord : c'est lui qui sert desormais. Alt+F4 ferme une
    # fenetre, Ctrl+Q les ferme toutes -- y compris celle qui n'a pas le focus.
    taskkill /IM borne.exe /F /T 2>&1 | Out-Null
    taskkill /IM chrome.exe /F /T 2>&1 | Out-Null
    break
  }
}
if ($raccourci) { [RaccourciWin]::UnregisterHotKey([IntPtr]::Zero, 1) | Out-Null }
if ($FichierPid) { Remove-Item $FichierPid -ErrorAction SilentlyContinue }
