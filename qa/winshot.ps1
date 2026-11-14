# QA helper: capture only the windows of one process (by PrintWindow, never the whole desktop).
# usage: winshot.ps1 -ProcessId 123 -OutDir C:\path [-Resize 1440x900] [-Prefix name]
param([int]$ProcessId, [string]$OutDir, [string]$Resize = '', [string]$Prefix = 'win')
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System; using System.Collections.Generic; using System.Runtime.InteropServices; using System.Text;
public class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int hh, bool r);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  public static List<IntPtr> ForPid(uint pid) { var l = new List<IntPtr>(); EnumWindows((h, p) => { uint x; GetWindowThreadProcessId(h, out x); if (x == pid && IsWindowVisible(h)) l.Add(h); return true; }, IntPtr.Zero); return l; }
  public static string Title(IntPtr h) { var s = new StringBuilder(256); GetWindowText(h, s, 256); return s.ToString(); }
}
'@
New-Item -ItemType Directory -Force $OutDir | Out-Null
$i = 0
foreach ($h in [W]::ForPid($ProcessId)) {
    $t = [W]::Title($h)
    if ($Resize -and $t -eq 'Playnite') { $s = $Resize -split 'x'; [void][W]::MoveWindow($h, 0, 0, [int]$s[0], [int]$s[1], $true); Start-Sleep -Milliseconds 900 }
    $r = New-Object W+RECT; [void][W]::GetWindowRect($h, [ref]$r)
    $w = $r.R - $r.L; $hh = $r.B - $r.T
    if ($w -lt 50 -or $hh -lt 50) { continue }
    $bmp = New-Object System.Drawing.Bitmap $w, $hh
    $g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
    [void][W]::PrintWindow($h, $dc, 2); $g.ReleaseHdc($dc); $g.Dispose()
    $i++
    $f = Join-Path $OutDir ("{0}-{1}.png" -f $Prefix, $i)
    $bmp.Save($f, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    "$f | title='$t' | ${w}x${hh}"
}
