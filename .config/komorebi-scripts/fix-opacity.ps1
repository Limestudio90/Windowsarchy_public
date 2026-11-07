# Forza l'opacita' al 100% su finestre lasciate bloccate in semi-trasparenza
# da Komorebi (tipico dopo il fullscreen: la finestra esce dalla gestione
# mentre e' ancora marcata "unfocused", quindi nessuno le rimette alpha 255).
#
# Uso:  powershell -NoProfile -File fix-opacity.ps1        # finestra in primo piano
#       powershell -NoProfile -File fix-opacity.ps1 -All   # tutte le finestre visibili
#
# Sicuro per YASB e per gli overlay (NVIDIA, Discord...): tocca solo le finestre
# la cui alpha e' impostata via SetLayeredWindowAttributes ed e' < 255, che e'
# esattamente il meccanismo usato da Komorebi. Gli overlay veri usano
# UpdateLayeredWindow e vengono ignorati automaticamente.

param([switch]$All)

Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class Opaque {
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
    [DllImport("user32.dll")] public static extern int SetWindowLong(IntPtr h, int i, int v);
    [DllImport("user32.dll")] public static extern bool SetLayeredWindowAttributes(IntPtr h, uint key, byte alpha, uint flags);
    [DllImport("user32.dll")] public static extern bool GetLayeredWindowAttributes(IntPtr h, out uint key, out byte alpha, out uint flags);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    const int GWL_EXSTYLE = -20;
    const int WS_EX_LAYERED = 0x00080000;
    const uint LWA_ALPHA = 0x2;

    public static string Title(IntPtr h) {
        var sb = new StringBuilder(512); GetWindowTextW(h, sb, 512); return sb.ToString();
    }
    public static uint Pid(IntPtr h) { uint p; GetWindowThreadProcessId(h, out p); return p; }

    // -1 = non layered / overlay UpdateLayeredWindow (da non toccare)
    public static int Alpha(IntPtr h) {
        if ((GetWindowLong(h, GWL_EXSTYLE) & WS_EX_LAYERED) == 0) return -1;
        uint key, flags; byte a;
        if (!GetLayeredWindowAttributes(h, out key, out a, out flags)) return -1;
        if ((flags & LWA_ALPHA) == 0) return -1;
        return a;
    }
    // Rimette alpha 255 e toglie il flag layered: Komorebi lo riapplichera' pulito.
    public static void Fix(IntPtr h) {
        int ex = GetWindowLong(h, GWL_EXSTYLE);
        SetLayeredWindowAttributes(h, 0, 255, LWA_ALPHA);
        SetWindowLong(h, GWL_EXSTYLE, ex & ~WS_EX_LAYERED);
    }
    public static List<IntPtr> Visible() {
        var r = new List<IntPtr>();
        EnumWindows((h, l) => { if (IsWindowVisible(h) && Title(h).Length > 0) r.Add(h); return true; }, IntPtr.Zero);
        return r;
    }
}
'@

$skip = @('yasb','komorebi','komorebi-bar','komorebi-shortcuts')

function Repair([IntPtr]$h) {
    if ($h -eq [IntPtr]::Zero) { return $null }
    $a = [Opaque]::Alpha($h)
    if ($a -lt 0 -or $a -ge 255) { return $null }
    $procId = [Opaque]::Pid($h)
    $name = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName
    if ($skip -contains $name) { return $null }
    [Opaque]::Fix($h)
    return "$name (alpha $a) - $([Opaque]::Title($h))"
}

if ($All) {
    $n = 0
    foreach ($h in [Opaque]::Visible()) {
        $r = Repair $h
        if ($r) { "opacizzata: $r"; $n++ }
    }
    if ($n -eq 0) { "nessuna finestra bloccata in trasparenza" }
} else {
    $r = Repair ([Opaque]::GetForegroundWindow())
    if ($r) { "opacizzata: $r" } else { "la finestra in primo piano era gia' opaca" }
}
