# =====================================================================
#  Genera preview.png per i temi Windowsarchy: applica a turno SOLO la
#  barra YASB, la fotografa sul monitor principale e alla fine rimette
#  i file di partenza. Bordi di komorebi e launcher non vengono toccati.
#
#  Uso:
#      make-theme-previews.ps1                    tutti i temi
#      make-theme-previews.ps1 windowsarchy ubuntu-yaru  solo questi
#
#  L'anteprima sono due ritagli 1:1 della barra vera, uno per lato:
#  a sinistra workspace e layout, a destra widget e tray.
# =====================================================================

param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Solo)

$ErrorActionPreference = 'Stop'
$Base    = Join-Path $env:USERPROFILE '.config\windowsarchy'
$TemiDir = Join-Path $Base 'themes'
$YasbDir = Join-Path $env:USERPROFILE '.config\yasb'
$Log     = Join-Path $YasbDir 'yasb.log'
$CropW   = 640

Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public class BarFinder {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public static int[] Find(uint[] pids, int sl, int st, int sw) {
    int[] best = null;
    EnumWindows(delegate (IntPtr h, IntPtr l) {
      if (!IsWindowVisible(h)) return true;
      uint pid; GetWindowThreadProcessId(h, out pid);
      if (Array.IndexOf(pids, pid) < 0) return true;
      RECT r; GetWindowRect(h, out r);
      int w = r.R - r.L, hh = r.B - r.T;
      if (r.T >= st && r.T <= st + 40 && r.L >= sl && r.L <= sl + 40 && w >= sw * 0.85 && hh >= 16 && hh <= 90) best = new int[] { r.L, r.T, w, hh };
      return true;
    }, IntPtr.Zero);
    return best;
  }
}
'@
[void][BarFinder]::SetProcessDPIAware()
Add-Type -AssemblyName System.Drawing, System.Windows.Forms

function Attendi-Yasb([datetime]$dopo) {
    # YASB scrive "Created file watcher" ogni volta che ricarica la barra
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 250
        foreach ($r in (Get-Content -LiteralPath $Log -Tail 12 -ErrorAction SilentlyContinue)) {
            if ($r -match '^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ .*Created file watcher') {
                if ([datetime]::ParseExact($matches[1], 'yyyy-MM-dd HH:mm:ss', $null) -ge $dopo) {
                    Start-Sleep -Milliseconds 2000   # animazione di comparsa e primo disegno dei widget
                    return $true
                }
            }
        }
    }
    return $false
}

function Metti-Barra([string]$dir) {
    Start-Sleep -Milliseconds 1100   # cosi' il ricaricamento cade in un secondo diverso dal precedente
    $t = Get-Date; $t = $t.AddMilliseconds(-$t.Millisecond)
    Copy-Item -LiteralPath (Join-Path $dir 'config.yaml') -Destination (Join-Path $YasbDir 'config.yaml') -Force
    Copy-Item -LiteralPath (Join-Path $dir 'styles.css')  -Destination (Join-Path $YasbDir 'styles.css')  -Force
    if (-not (Attendi-Yasb $t)) { Write-Host "  [!] YASB non ha confermato il ricaricamento, scatto comunque" -ForegroundColor Yellow }
}

if (-not (Get-Process yasb -ErrorAction SilentlyContinue)) { throw 'YASB non e'' in esecuzione' }

$temi = Get-ChildItem -LiteralPath $TemiDir -Directory | Sort-Object Name
if ($Solo) { $temi = $temi | Where-Object { $Solo -contains $_.Name } }

$salva = Join-Path $env:TEMP ('yasb-prima-anteprime-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $salva | Out-Null
Copy-Item -LiteralPath (Join-Path $YasbDir 'config.yaml'), (Join-Path $YasbDir 'styles.css') -Destination $salva

$pri = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
try {
    foreach ($t in $temi) {
        Write-Host "  $($t.Name)..." -NoNewline
        Metti-Barra $t.FullName
        $pids = [uint32[]]@(Get-Process yasb | ForEach-Object { $_.Id })
        $r = [BarFinder]::Find($pids, $pri.Left, $pri.Top, $pri.Width)
        if (-not $r) {
            $rifiutato = Get-Content -LiteralPath $Log -Tail 80 | Where-Object { $_ -match 'contains validation errors' } | Select-Object -Last 1
            if ($rifiutato) { Write-Host " YASB ha rifiutato il config di questo tema (errori di validazione, vedi yasb.log)" -ForegroundColor Red }
            else { Write-Host " barra non trovata sul monitor principale" -ForegroundColor Red }
            continue
        }

        $shot = New-Object System.Drawing.Bitmap $r[2], $r[3]
        $g = [System.Drawing.Graphics]::FromImage($shot)
        $g.CopyFromScreen($r[0], $r[1], 0, 0, $shot.Size)
        $g.Dispose()

        $cw  = [Math]::Min($CropW, [int]($r[2] / 2))
        $h   = $r[3]
        $gap = 6
        $out = New-Object System.Drawing.Bitmap $cw, ($h * 2 + $gap)
        $g = [System.Drawing.Graphics]::FromImage($out)
        $g.Clear([System.Drawing.Color]::FromArgb(17, 17, 17))
        $g.DrawImage($shot, (New-Object System.Drawing.Rectangle 0, 0, $cw, $h), (New-Object System.Drawing.Rectangle 0, 0, $cw, $h), [System.Drawing.GraphicsUnit]::Pixel)
        $g.DrawImage($shot, (New-Object System.Drawing.Rectangle 0, ($h + $gap), $cw, $h), (New-Object System.Drawing.Rectangle ($r[2] - $cw), 0, $cw, $h), [System.Drawing.GraphicsUnit]::Pixel)
        $g.Dispose()
        $dest = Join-Path $t.FullName 'preview.png'
        $out.Save($dest, [System.Drawing.Imaging.ImageFormat]::Png)
        $out.Dispose(); $shot.Dispose()
        Write-Host " ok (barra $($r[2])x$h)" -ForegroundColor Green
    }
}
finally {
    Write-Host "  rimetto la barra di partenza..." -NoNewline
    Metti-Barra $salva
    Remove-Item -LiteralPath $salva -Recurse -Force
    Write-Host " ok" -ForegroundColor Green
}
