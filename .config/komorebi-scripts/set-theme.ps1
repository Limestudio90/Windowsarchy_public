# =====================================================================
#  Applica un tema Windowsarchy per intero, come omarchy-theme-set:
#  barra YASB, bordi di komorebi e colori del launcher insieme.
#
#  Uso:
#      set-theme.ps1              elenca i temi, con quello attivo
#      set-theme.ps1 windowsarchy        applica il tema
#
#  Oppure dal menu: Win+Ctrl+Shift+Space (theme-menu.ps1)
#
#  I temi stanno in %USERPROFILE%\.config\windowsarchy\themes\<nome>\
#      config.yaml, styles.css   la barra YASB
#      theme.json                colori di komorebi e del launcher
#      preview.png               anteprima per il menu (make-theme-previews.ps1)
# =====================================================================

param(
    [Parameter(Position = 0)][string]$Tema,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$Base     = Join-Path $env:USERPROFILE '.config\windowsarchy'
$TemiDir  = Join-Path $Base 'themes'
$Current  = Join-Path $Base 'current-theme'
$FlowTpl  = Join-Path $Base 'flow-launcher.template.xaml'
$YasbDir  = Join-Path $env:USERPROFILE '.config\yasb'
$KomoHome = if ($env:KOMOREBI_CONFIG_HOME) { $env:KOMOREBI_CONFIG_HOME } else { Join-Path $env:USERPROFILE '.config\komorebi' }
$KomoJson = Join-Path $KomoHome 'komorebi.json'
$FlowXaml = Join-Path $env:APPDATA 'FlowLauncher\Themes\Omarchy.xaml'
$FlowExe  = Join-Path $env:LOCALAPPDATA 'FlowLauncher\Flow.Launcher.exe'
$Utf8     = New-Object System.Text.UTF8Encoding $false

function Say($testo, $colore = 'Gray') { if (-not $Quiet) { Write-Host $testo -ForegroundColor $colore } }

if (-not (Test-Path -LiteralPath $TemiDir)) { throw "cartella temi non trovata: $TemiDir" }
$attivo = if (Test-Path -LiteralPath $Current) { (Get-Content -LiteralPath $Current -Raw).Trim() } else { '' }

if (-not $Tema) {
    Write-Host "`nTemi disponibili:`n" -ForegroundColor Cyan
    foreach ($d in Get-ChildItem -LiteralPath $TemiDir -Directory | Sort-Object Name) {
        $etichetta = $d.Name
        $metaPath = Join-Path $d.FullName 'theme.json'
        if (Test-Path -LiteralPath $metaPath) {
            $m = Get-Content -LiteralPath $metaPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $etichetta = "{0,-24} {1} - {2}" -f $d.Name, $m.name, $m.subtitle
        }
        if ($d.Name -eq $attivo) { Write-Host "  * $etichetta   <- attivo" -ForegroundColor Green }
        else { Write-Host "    $etichetta" }
    }
    Write-Host "`nPer applicarne uno:  set-theme.ps1 <nome>   oppure Win+Ctrl+Shift+Space`n" -ForegroundColor DarkGray
    return
}

$dir = Join-Path $TemiDir $Tema
if (-not (Test-Path -LiteralPath $dir)) { throw "tema '$Tema' inesistente in $TemiDir" }
$metaPath = Join-Path $dir 'theme.json'
$meta = $null
if (Test-Path -LiteralPath $metaPath) { $meta = Get-Content -LiteralPath $metaPath -Raw -Encoding UTF8 | ConvertFrom-Json }

# --- 1. barra YASB ------------------------------------------------------
# Un solo salvataggio a rotazione (.precedente): cambiando tema spesso dal
# menu, una copia datata per volta riempirebbe la cartella di YASB.
foreach ($f in 'config.yaml', 'styles.css') {
    $src = Join-Path $dir $f
    if (-not (Test-Path -LiteralPath $src)) { throw "manca $f nel tema $Tema" }
    $vivo = Join-Path $YasbDir $f
    if (Test-Path -LiteralPath $vivo) { Copy-Item -LiteralPath $vivo -Destination "$vivo.precedente" -Force }
    Copy-Item -LiteralPath $src -Destination $vivo -Force
}
Say "  barra YASB     -> $Tema (rilegge da sola)" Green

if ($meta) {
    # --- 2. bordi di komorebi -------------------------------------------
    # Si sostituisce solo il blocco border_colours: ConvertTo-Json di
    # PowerShell 5.1 riformatterebbe l'intero file.
    $k = $meta.komorebi
    $blocco = "`"border_colours`": {`n" +
              "    `"single`": `"$($k.single)`",`n" +
              "    `"stack`": `"$($k.stack)`",`n" +
              "    `"monocle`": `"$($k.monocle)`",`n" +
              "    `"floating`": `"$($k.floating)`",`n" +
              "    `"unfocused`": `"$($k.unfocused)`"`n" +
              "  }"
    $json  = [IO.File]::ReadAllText($KomoJson)
    $nuovo = [regex]::Replace($json, '"border_colours"\s*:\s*\{[^}]*\}', { param($m) $blocco })
    if ($nuovo -ne $json) { [IO.File]::WriteAllText($KomoJson, $nuovo, $Utf8) }
    if (Get-Process komorebi -ErrorAction SilentlyContinue) {
        $kc = (Get-Command komorebic -ErrorAction SilentlyContinue).Source
        if (-not $kc) { $kc = 'C:\Program Files\komorebi\bin\komorebic.exe' }
        & $kc reload-configuration 2>&1 | Out-Null
        Say "  bordi komorebi -> $($k.single) (ricaricato)" Green
    } else {
        Say "  bordi komorebi -> $($k.single) (komorebi spento: valgono al prossimo avvio)" Yellow
    }

    # --- 3. launcher ----------------------------------------------------
    if (Test-Path -LiteralPath $FlowTpl) {
        $p = $meta.palette
        $xaml = [IO.File]::ReadAllText($FlowTpl)
        foreach ($c in @(@('BG', $p.bg), @('SURFACE', $p.surface), @('TEXT', $p.text), @('SUBTEXT', $p.subtext), @('ACCENT', $p.accent))) {
            $xaml = $xaml.Replace('{{' + $c[0] + '}}', ([string]$c[1]).TrimStart('#'))
        }
        [IO.File]::WriteAllText($FlowXaml, $xaml, $Utf8)
        # Flow Launcher legge il tema solo all'avvio
        $flow = Get-Process 'Flow.Launcher' -ErrorAction SilentlyContinue
        if ($flow) {
            $flow | Stop-Process -Force
            for ($i = 0; $i -lt 30 -and (Get-Process 'Flow.Launcher' -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 100 }
            Start-Process $FlowExe
            Say "  launcher       -> accento $($p.accent) (Flow riavviato)" Green
        } else {
            Say "  launcher       -> accento $($p.accent) (Flow spento: vale al prossimo avvio)" Yellow
        }
    } else {
        Say "  [!] modello del launcher mancante: $FlowTpl" Yellow
    }
} else {
    Say "  [!] $Tema non ha theme.json: cambiata solo la barra, bordi e launcher restano come sono" Yellow
}

[IO.File]::WriteAllText($Current, $Tema, $Utf8)
Say "`nTema '$Tema' applicato.`n" Cyan
