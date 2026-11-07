# =====================================================================
#  Equalizzatore di sistema - cambio preset (Equalizer APO)
#
#  Uso:  eq.ps1                  passa al preset successivo (ciclo)
#        eq.ps1 -Toggle          spegne, o riaccende l'ultimo preset usato
#        eq.ps1 -Edit            apre l'editor grafico SUL PRESET ATTIVO
#        eq.ps1 -Preset cuffie   sceglie un preset per nome
#        eq.ps1 -Status          dice soltanto quale preset e' attivo
#        eq.ps1 -List            elenca i preset disponibili
#        eq.ps1 ... -Quiet       niente riquadro a schermo
#
#  COME FUNZIONA
#  Equalizer APO non e' un'applicazione: e' un APO che Windows carica
#  dentro audiodg.exe. Non c'e' niente da avviare o fermare, si cambia
#  soltanto il file di configurazione, che lui rilegge a caldo.
#
#  Il watcher pero' guarda SOLO la cartella config\ dell'installazione:
#  un Include: verso un file altrove funziona, ma le modifiche a quel
#  file non fanno scattare il ricaricamento. Per questo scriviamo
#  direttamente <install>\config\config.txt, che contiene una sola riga
#  Include: verso il preset scelto in config\windowsarchy\.
#
#  PERCHE' NON SERVE L'AMMINISTRATORE
#  Durante il setup la sola cartella config\ riceve il permesso di
#  modifica per l'utente (vedi README). Il resto dell'installazione
#  resta di sistema: i .dll non sono scrivibili.
# =====================================================================

param(
    [string]$Preset,
    [switch]$Toggle,
    [switch]$Edit,
    [switch]$Status,
    [switch]$List,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

$SottoCartella = 'windowsarchy'
$Bypass        = 'bypass'
$FileUltimo    = Join-Path $env:USERPROFILE '.config\eq-ultimo.txt'

# ---------------------------------------------------------------------
#  Dove sta installato Equalizer APO
# ---------------------------------------------------------------------
function Trova-EqApo {
    $cand = @()
    $reg = Get-ItemProperty 'HKLM:\SOFTWARE\EqualizerAPO' -ErrorAction SilentlyContinue
    if ($reg -and $reg.InstallPath) { $cand += $reg.InstallPath }
    $cand += (Join-Path $env:ProgramFiles 'EqualizerAPO')
    if (${env:ProgramFiles(x86)}) { $cand += (Join-Path ${env:ProgramFiles(x86)} 'EqualizerAPO') }
    foreach ($c in $cand) {
        if ($c -and (Test-Path -LiteralPath (Join-Path $c 'config'))) { return $c }
    }
    return $null
}

$Install = Trova-EqApo
if (-not $Install) {
    Write-Host 'Equalizer APO non risulta installato.' -ForegroundColor Red
    Write-Host 'Prendilo da https://sourceforge.net/projects/equalizerapo/ e poi rilancia restore.ps1.'
    exit 1
}

$DirConfig  = Join-Path $Install 'config'
$DirPreset  = Join-Path $DirConfig $SottoCartella
$FileConfig = Join-Path $DirConfig 'config.txt'

if (-not (Test-Path -LiteralPath $DirPreset)) {
    Write-Host "Manca $DirPreset : lancia restore.ps1 per copiarci i preset." -ForegroundColor Red
    exit 1
}

# I preset hanno un prefisso numerico che ne fissa l'ordine nel ciclo
# (0-bypass, 1-cuffie, ...). Il nome vero e' quello dopo il trattino.
$elenco = @(Get-ChildItem -LiteralPath $DirPreset -Filter '*.txt' | Sort-Object Name | ForEach-Object {
    [pscustomobject]@{
        Nome = ($_.BaseName -replace '^\d+-', '')
        File = $_.Name
    }
})
if ($elenco.Count -eq 0) {
    Write-Host "Nessun preset in $DirPreset." -ForegroundColor Red
    exit 1
}

function Preset-Attivo {
    if (-not (Test-Path -LiteralPath $FileConfig)) { return $null }
    $riga = Select-String -LiteralPath $FileConfig -Pattern "Include:\s*$SottoCartella\\(.+\.txt)" -ErrorAction SilentlyContinue |
            Select-Object -First 1
    if (-not $riga) { return $null }
    $file = $riga.Matches[0].Groups[1].Value.Trim()
    $p = $elenco | Where-Object { $_.File -eq $file } | Select-Object -First 1
    if ($p) { return $p.Nome }
    return $null
}

# ---------------------------------------------------------------------
#  Riquadro a schermo: compare e sparisce, non lascia niente nel centro
#  notifiche. Se il font del rice non c'e', ripiega su Segoe UI.
# ---------------------------------------------------------------------
function Mostra-Osd($testo) {
    if ($Quiet) { return }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $famiglia = 'Segoe UI'
    if ([System.Drawing.FontFamily]::Families.Name -contains 'JetBrainsMono NFP') { $famiglia = 'JetBrainsMono NFP' }

    $f = New-Object System.Windows.Forms.Form
    $f.FormBorderStyle = 'None'
    $f.StartPosition   = 'Manual'
    $f.TopMost         = $true
    $f.ShowInTaskbar   = $false
    $f.BackColor       = [System.Drawing.ColorTranslator]::FromHtml('#1e1e2e')
    $f.Opacity         = 0.92

    $l = New-Object System.Windows.Forms.Label
    $l.Text      = $testo
    $l.Font      = New-Object System.Drawing.Font($famiglia, 13)
    $l.ForeColor = [System.Drawing.ColorTranslator]::FromHtml('#cdd6f4')
    $l.AutoSize  = $true
    $l.Location  = New-Object System.Drawing.Point(22, 16)
    $f.Controls.Add($l)

    $f.Show()   # serve a far calcolare la dimensione reale del testo
    $f.Size = New-Object System.Drawing.Size(($l.Width + 44), ($l.Height + 32))
    $area = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $f.Location = New-Object System.Drawing.Point(
        ($area.X + [int](($area.Width - $f.Width) / 2)),
        ($area.Y + $area.Height - $f.Height - 90)
    )

    $t = New-Object System.Windows.Forms.Timer
    $t.Interval = 1200
    $t.Add_Tick({ $t.Stop(); $f.Close() })
    $t.Start()
    [System.Windows.Forms.Application]::Run($f)
    $f.Dispose()
}

function Ultimo-Usato {
    $u = $null
    if (Test-Path -LiteralPath $FileUltimo) { $u = (Get-Content -LiteralPath $FileUltimo -Raw).Trim() }
    if (-not $u -or -not ($elenco.Nome -contains $u)) {
        $u = ($elenco | Where-Object { $_.Nome -ne $Bypass } | Select-Object -First 1).Nome
    }
    return $u
}

function Applica($nome) {
    $p = $elenco | Where-Object { $_.Nome -eq $nome } | Select-Object -First 1
    if (-not $p) {
        Write-Host "Preset '$nome' inesistente. Disponibili: $(($elenco.Nome) -join ', ')" -ForegroundColor Red
        exit 1
    }
    # ASCII e non UTF-16: PowerShell 5 scriverebbe Unicode di default, e il
    # parser di Equalizer APO leggerebbe una riga di caratteri nulli.
    $testo = @(
        '# Generato da eq.ps1 (Windowsarchy). Non modificarlo a mano:',
        '# viene riscritto al primo cambio di preset.',
        ('# I preset veri stanno in ' + $SottoCartella + '\'),
        '',
        "Include: $SottoCartella\$($p.File)"
    )
    Set-Content -LiteralPath $FileConfig -Value $testo -Encoding ASCII

    if ($p.Nome -ne $Bypass) {
        $dir = Split-Path -Parent $FileUltimo
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Set-Content -LiteralPath $FileUltimo -Value $p.Nome -Encoding ASCII
    }

    Write-Host "EQ: $($p.Nome)"
    if ($p.Nome -eq $Bypass) { Mostra-Osd 'EQ  spento' } else { Mostra-Osd "EQ  $($p.Nome)" }
}

# ---------------------------------------------------------------------
$attivo = Preset-Attivo

if ($List) {
    foreach ($p in $elenco) {
        $segno = ' '
        if ($p.Nome -eq $attivo) { $segno = '*' }
        "$segno $($p.Nome)"
    }
    exit 0
}

if ($Status) {
    if ($attivo) { "EQ: $attivo" } else { 'EQ: configurazione non gestita da eq.ps1' }
    exit 0
}

if ($Edit) {
    # Apre l'editor SUL FILE DEL PRESET, mai su config.txt: quello e' generato
    # da questo script e verrebbe riscritto al primo cambio di preset, buttando
    # via la curva appena disegnata.
    #
    # Se l'EQ e' spento accendiamo prima l'ultimo preset usato: 'bypass' e' il
    # riferimento vuoto (non c'e' niente da modificare), e soprattutto con l'EQ
    # spento non sentiresti le modifiche mentre trascini i punti.
    $nome = $attivo
    if (-not $nome -or $nome -eq $Bypass) {
        $nome = Ultimo-Usato
        Applica $nome
    }
    $p = $elenco | Where-Object { $_.Nome -eq $nome } | Select-Object -First 1
    $file = Join-Path $DirPreset $p.File

    $editor = Join-Path $Install 'Editor.exe'
    if (-not (Test-Path -LiteralPath $editor)) {
        $editor = (Get-ChildItem -LiteralPath $Install -Filter '*.exe' -ErrorAction SilentlyContinue |
                   Where-Object { $_.BaseName -match 'edit' } | Select-Object -First 1).FullName
    }
    if (-not $editor) {
        Write-Host "Non trovo l'editor grafico dentro $Install." -ForegroundColor Red
        exit 1
    }

    # Il percorso viene stampato apposta: se l'editor dovesse ignorare
    # l'argomento e aprire config.txt, e' quello da aprire a mano.
    Write-Host "Editor su: $file"

    # -WorkingDirectory NON e' un dettaglio: l'editor e' un'applicazione Qt e
    # cerca il plugin di piattaforma in qt\platforms\qwindows.dll a partire
    # dalla cartella di lavoro. Lanciato dal menu Start quella e' la cartella
    # di EqualizerAPO; lanciato da whkd sarebbe un'altra, e Qt muore con
    # "no Qt platform plugin could be initialized" prima ancora di aprirsi.
    Start-Process -FilePath $editor -WorkingDirectory $Install -ArgumentList "`"$file`""
    exit 0
}

if ($Preset) { Applica $Preset; exit 0 }

if ($Toggle) {
    if ($attivo -ne $Bypass) { Applica $Bypass } else { Applica (Ultimo-Usato) }
    exit 0
}

# senza argomenti: avanti di uno nel ciclo
$i = 0
if ($attivo) {
    $idx = [array]::IndexOf($elenco.Nome, $attivo)
    if ($idx -ge 0) { $i = ($idx + 1) % $elenco.Count }
}
Applica $elenco[$i].Nome
