# Снимает скриншот окна приложения. Нужен, чтобы проверять интерфейс
# глазами, а не догадками по коду.
#   .\tools\shot.ps1 -Out имя.png
param([string]$Out = "shot.png", [string]$Title = "Downloader3000", [int]$Wait = 7)

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Shot {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
Start-Sleep -Seconds $Wait
$p = Get-Process | Where-Object { $_.ProcessName -eq "flet" -and $_.MainWindowTitle -eq $Title } | Select-Object -First 1
if (-not $p) { Write-Output "окно '$Title' не найдено"; exit 1 }
[void][Shot]::SetForegroundWindow($p.MainWindowHandle)
Start-Sleep -Milliseconds 1500
$r = New-Object Shot+RECT
[void][Shot]::GetWindowRect($p.MainWindowHandle, [ref]$r)
$w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output "снято ${w}x${h} -> $Out"
