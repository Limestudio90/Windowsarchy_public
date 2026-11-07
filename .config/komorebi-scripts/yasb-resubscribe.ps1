# =====================================================================
#  Riaggancia YASB a komorebi quando la barra e' rimasta su "Komorebi Offline".
#
#  Succede se YASB parte o si ricarica (cambio tema, modifica del config)
#  mentre komorebi e' in PAUSA: in pausa komorebi ignora l'iscrizione al
#  named pipe, ma komorebic esce comunque con successo, quindi YASB si mette
#  ad aspettare su ConnectNamedPipe una connessione che non arrivera' mai.
#  Resta cosi' anche dopo aver tolto la pausa o riavviato komorebi, e in quello
#  stato non riesce nemmeno a chiudersi (per questo "yasbc reload" non basta).
#
#  Questo script legge dal log di YASB il pipe ancora in attesa e rifa'
#  l'iscrizione, se komorebi gira e non e' in pausa. Se YASB e' agganciato
#  non fa niente. Lo lanciano Win+P (whkd) e Start/Reload di komorebi nel
#  menu di YASB.
#
#  Uso:  yasb-resubscribe.ps1 [-Quiet] [-DryRun] [-Log <file>]
# =====================================================================

param(
    [int]$Grace = 12,        # YASB riprova da solo ogni 5 s: pipe piu' giovani di cosi' si lasciano a lui
    [string]$Log = (Join-Path $env:USERPROFILE '.config\yasb\yasb.log'),
    [switch]$Quiet,
    [switch]$DryRun
)

function Say($m) { if (-not $Quiet) { Write-Host $m } }

function Pendente {
    # Ultimo pipe creato da YASB senza un "connected" successivo con lo stesso nome
    $nome = $null; $quando = $null
    foreach ($r in (Get-Content -LiteralPath $Log -Tail 500 -ErrorAction SilentlyContinue)) {
        if ($r -match '^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ .*Created named pipe (yasb-[0-9a-f-]+)') {
            $nome = $matches[2]
            $quando = [datetime]::ParseExact($matches[1], 'yyyy-MM-dd HH:mm:ss', $null)
        } elseif ($nome -and $r -match ('Komorebi connected to named pipe: ' + [regex]::Escape($nome))) {
            $nome = $null
        }
    }
    if ($nome) { return [pscustomobject]@{ Nome = $nome; Quando = $quando } }
    return $null
}

if (-not (Test-Path -LiteralPath $Log)) { Say "log di YASB non trovato: $Log"; return }

$p = Pendente
if (-not $p) { Say "YASB e' agganciato a komorebi, niente da fare"; return }
Say "YASB aspetta sul pipe $($p.Nome) dalle $($p.Quando.ToString('HH:mm:ss'))"
if ($DryRun) { return }

if (-not (Get-Process yasb -ErrorAction SilentlyContinue)) { Say 'YASB non e'' in esecuzione'; return }
if (-not (Get-Process komorebi -ErrorAction SilentlyContinue)) { Say 'komorebi non e'' in esecuzione'; return }
$kc = (Get-Command komorebic -ErrorAction SilentlyContinue).Source
if (-not $kc) { $kc = 'C:\Program Files\komorebi\bin\komorebic.exe' }

# subito dopo "komorebic start" komorebi puo' non rispondere ancora
$state = $null
for ($i = 0; $i -lt 20 -and -not $state; $i++) {
    $state = (& $kc state 2>$null | Out-String) | ConvertFrom-Json -ErrorAction SilentlyContinue
    if (-not $state) { Start-Sleep -Milliseconds 500 }
}
if (-not $state) { Say 'komorebi non risponde'; return }
if ($state.is_paused) { Say 'komorebi e'' in pausa e in pausa ignora le iscrizioni: si riaggancia quando la togli con Win+P'; return }

$eta = ((Get-Date) - $p.Quando).TotalSeconds
if ($eta -lt $Grace) {
    Start-Sleep -Seconds ([Math]::Ceiling($Grace - $eta))
    $p = Pendente
    if (-not $p) { Say "YASB si e' riagganciato da solo"; return }
}

& $kc subscribe-pipe $p.Nome 2>&1 | Out-Null
Start-Sleep -Seconds 2
if (Pendente) { Say "iscrizione inviata a $($p.Nome), ma YASB non risulta ancora agganciato" }
else { Say "YASB riagganciato a komorebi ($($p.Nome))" }
