# =====================================================================
#  Menu dei temi Windowsarchy, come il "Theme menu" di Omarchy
#  (SUPER+SHIFT+CTRL+SPACE): elenco a sinistra, anteprima a destra.
#  Scorciatoia: Win+Ctrl+Shift+Space, lanciato da whkd.
#
#  Frecce o j/k   scegli        Invio o doppio clic   applica
#  Esc            chiudi        clic fuori            chiudi
#
#  Il menu stesso si colora con il tema attivo, come Walker su Omarchy.
#  Gli errori finiscono in %USERPROFILE%\.config\windowsarchy\theme-menu.log
#  perche' la finestra parte da un PowerShell nascosto.
# =====================================================================

$Base     = Join-Path $env:USERPROFILE '.config\windowsarchy'
$LogFile  = Join-Path $Base 'theme-menu.log'

try {
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public class Primopiano {
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr p);
  [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool f);
  [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] static extern bool BringWindowToTop(IntPtr h);
  // Lanciata da un processo in background, Windows non darebbe il focus
  // alla finestra: ci si aggancia per un attimo al thread in primo piano.
  public static void Forza(IntPtr h) {
    uint fg = GetWindowThreadProcessId(GetForegroundWindow(), IntPtr.Zero);
    uint io = GetCurrentThreadId();
    if (fg != io) AttachThreadInput(io, fg, true);
    BringWindowToTop(h); SetForegroundWindow(h);
    if (fg != io) AttachThreadInput(io, fg, false);
  }
}
'@

$TemiDir  = Join-Path $Base 'themes'
$Current  = Join-Path $Base 'current-theme'
$SetTheme = Join-Path $PSScriptRoot 'set-theme.ps1'
$attivo   = if (Test-Path -LiteralPath $Current) { (Get-Content -LiteralPath $Current -Raw).Trim() } else { '' }

$Ripiego = [pscustomobject]@{
    name = ''; subtitle = ''; description = ''
    palette  = [pscustomobject]@{ bg = '#1F1F28'; surface = '#363646'; text = '#DCD7BA'; subtext = '#C8C093'; accent = '#DCD7BA' }
    komorebi = [pscustomobject]@{ single = '#DCD7BA'; stack = '#76946A'; monocle = '#957FB8'; floating = '#C0A36E'; unfocused = '#363646' }
}

$temi = @(foreach ($d in Get-ChildItem -LiteralPath $TemiDir -Directory | Sort-Object Name) {
    $metaPath = Join-Path $d.FullName 'theme.json'
    $meta = if (Test-Path -LiteralPath $metaPath) { Get-Content -LiteralPath $metaPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { $Ripiego }
    [pscustomobject]@{ Id = $d.Name; Meta = $meta; Preview = (Join-Path $d.FullName 'preview.png') }
})
if ($temi.Count -eq 0) { throw "nessun tema in $TemiDir" }

$corrente = $temi | Where-Object { $_.Id -eq $attivo } | Select-Object -First 1
$ui = if ($corrente) { $corrente.Meta.palette } else { $Ripiego.palette }

function Hex($c) { ([string]$c).TrimStart('#') }
$Conv = New-Object System.Windows.Media.BrushConverter
function Br($c, $alpha = '') { $Conv.ConvertFromString('#' + $alpha + (Hex $c)) }

$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Windowsarchy - Temi" Width="960" Height="620"
        WindowStyle="None" AllowsTransparency="True" Background="Transparent"
        ResizeMode="NoResize" Topmost="True" ShowInTaskbar="False"
        WindowStartupLocation="CenterScreen" UseLayoutRounding="True"
        FontFamily="JetBrainsMono NFP, JetBrains Mono, Consolas">
  <Window.Resources>
    <Style TargetType="ListBoxItem">
      <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="ListBoxItem">
            <Border x:Name="Bd" CornerRadius="8" Padding="12,8" Margin="0,0,0,4" Background="Transparent">
              <ContentPresenter/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property="IsMouseOver" Value="True">
                <Setter TargetName="Bd" Property="Background" Value="#1F@@ACCENT@@"/>
              </Trigger>
              <Trigger Property="IsSelected" Value="True">
                <Setter TargetName="Bd" Property="Background" Value="#3D@@ACCENT@@"/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
  </Window.Resources>
  <Border CornerRadius="12" Background="#F2@@BG@@" BorderBrush="#66@@ACCENT@@" BorderThickness="1">
    <Grid>
      <Grid.RowDefinitions>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="*"/>
        <RowDefinition Height="Auto"/>
      </Grid.RowDefinitions>
      <DockPanel Grid.Row="0" Margin="20,14,20,12" LastChildFill="False">
        <TextBlock DockPanel.Dock="Left" Text="Temi" FontSize="18" Foreground="#@@TEXT@@"/>
        <TextBlock DockPanel.Dock="Right" VerticalAlignment="Center" FontSize="12" Opacity="0.6"
                   Foreground="#@@SUBTEXT@@" Text="frecce  scegli     Invio  applica     Esc  chiudi"/>
      </DockPanel>
      <Rectangle Grid.Row="1" Height="1" Fill="#@@SURFACE@@" Margin="14,0,14,0"/>
      <Grid Grid.Row="2" Margin="12,12,16,4">
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="250"/>
          <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>
        <ListBox x:Name="Lista" Grid.Column="0" Background="Transparent" BorderThickness="0"
                 ScrollViewer.HorizontalScrollBarVisibility="Disabled"/>
        <StackPanel Grid.Column="1" Margin="18,2,0,0">
          <TextBlock x:Name="Titolo" FontSize="22" Foreground="#@@TEXT@@"/>
          <TextBlock x:Name="Descrizione" FontSize="12" Foreground="#@@SUBTEXT@@" TextWrapping="Wrap" Margin="0,4,0,12" Opacity="0.85"/>
          <TextBlock Text="BARRA" FontSize="10" Foreground="#@@SUBTEXT@@" Opacity="0.55" Margin="0,0,0,4"/>
          <Border CornerRadius="6" BorderBrush="#@@SURFACE@@" BorderThickness="1" Width="642" Height="84"
                  HorizontalAlignment="Left" ClipToBounds="True" Background="#111111">
            <Grid>
              <Image x:Name="Barra" Stretch="None" HorizontalAlignment="Left" VerticalAlignment="Center"/>
              <TextBlock x:Name="SenzaAnteprima" FontSize="11" Opacity="0.6" Foreground="#@@SUBTEXT@@"
                         HorizontalAlignment="Center" VerticalAlignment="Center"
                         Text="anteprima non ancora generata: make-theme-previews.ps1"/>
            </Grid>
          </Border>
          <TextBlock Text="FINESTRE E LAUNCHER" FontSize="10" Foreground="#@@SUBTEXT@@" Opacity="0.55" Margin="0,14,0,4"/>
          <Canvas x:Name="Mock" Width="642" Height="190" HorizontalAlignment="Left" ClipToBounds="True"/>
          <WrapPanel x:Name="Colori" Margin="0,12,0,0" Width="642" HorizontalAlignment="Left"/>
        </StackPanel>
      </Grid>
      <TextBlock x:Name="Stato" Grid.Row="3" Margin="20,0,20,12" FontSize="12" Foreground="#@@ACCENT@@"/>
    </Grid>
  </Border>
</Window>
'@
$xaml = $xaml.Replace('@@BG@@', (Hex $ui.bg)).Replace('@@SURFACE@@', (Hex $ui.surface)).Replace('@@TEXT@@', (Hex $ui.text)).Replace('@@SUBTEXT@@', (Hex $ui.subtext)).Replace('@@ACCENT@@', (Hex $ui.accent))
$win = [Windows.Markup.XamlReader]::Parse($xaml)
$Lista          = $win.FindName('Lista')
$Titolo         = $win.FindName('Titolo')
$Descrizione    = $win.FindName('Descrizione')
$Barra          = $win.FindName('Barra')
$SenzaAnteprima = $win.FindName('SenzaAnteprima')
$Mock           = $win.FindName('Mock')
$Colori         = $win.FindName('Colori')
$Stato          = $win.FindName('Stato')

function Nuovo-Testo($testo, $colore, $size, $opacita = 1.0) {
    $t = New-Object System.Windows.Controls.TextBlock
    $t.Text = $testo; $t.Foreground = Br $colore; $t.FontSize = $size; $t.Opacity = $opacita
    return $t
}
function Rett($x, $y, $w, $h, $fill, $stroke = $null, $spessore = 0, $raggio = 0) {
    $r = New-Object System.Windows.Shapes.Rectangle
    $r.Width = $w; $r.Height = $h; $r.RadiusX = $raggio; $r.RadiusY = $raggio
    if ($fill)   { $r.Fill = $fill }
    if ($stroke) { $r.Stroke = $stroke; $r.StrokeThickness = $spessore }
    [System.Windows.Controls.Canvas]::SetLeft($r, $x); [System.Windows.Controls.Canvas]::SetTop($r, $y)
    [void]$Mock.Children.Add($r)
}
function Scritta($x, $y, $testo, $colore, $size, $opacita = 1.0) {
    $t = Nuovo-Testo $testo $colore $size $opacita
    [System.Windows.Controls.Canvas]::SetLeft($t, $x); [System.Windows.Controls.Canvas]::SetTop($t, $y)
    [void]$Mock.Children.Add($t)
}

# --- elenco ---------------------------------------------------------------
foreach ($t in $temi) {
    $m = $t.Meta
    $sp = New-Object System.Windows.Controls.StackPanel

    $riga = New-Object System.Windows.Controls.DockPanel
    if ($t.Id -eq $attivo) {
        $a = Nuovo-Testo 'attivo' $ui.accent 11
        $a.VerticalAlignment = 'Center'
        [System.Windows.Controls.DockPanel]::SetDock($a, 'Right')
        [void]$riga.Children.Add($a)
    }
    $nome = if ($m.name) { $m.name } else { $t.Id }
    [void]$riga.Children.Add((Nuovo-Testo $nome $ui.text 15))
    [void]$sp.Children.Add($riga)
    if ($m.subtitle) { [void]$sp.Children.Add((Nuovo-Testo $m.subtitle $ui.subtext 11 0.8)) }

    $pallini = New-Object System.Windows.Controls.StackPanel
    $pallini.Orientation = 'Horizontal'; $pallini.Margin = '0,6,0,0'
    foreach ($c in @($m.palette.bg, $m.palette.accent, $m.komorebi.single, $m.komorebi.stack, $m.komorebi.monocle, $m.komorebi.floating)) {
        $b = New-Object System.Windows.Controls.Border
        $b.Width = 12; $b.Height = 12; $b.CornerRadius = 6; $b.Margin = '0,0,5,0'
        $b.Background = Br $c; $b.BorderBrush = Br $ui.surface; $b.BorderThickness = 1
        [void]$pallini.Children.Add($b)
    }
    [void]$sp.Children.Add($pallini)

    $item = New-Object System.Windows.Controls.ListBoxItem
    $item.Content = $sp; $item.Tag = $t
    [void]$Lista.Items.Add($item)
}

# --- anteprima ------------------------------------------------------------
function Mostra($t) {
    $m = $t.Meta; $p = $m.palette; $k = $m.komorebi
    $Titolo.Text = if ($m.subtitle) { "$($m.name)  -  $($m.subtitle)" } else { $m.name }
    $Descrizione.Text = $m.description

    if (Test-Path -LiteralPath $t.Preview) {
        $bi = New-Object System.Windows.Media.Imaging.BitmapImage
        $bi.BeginInit(); $bi.CacheOption = 'OnLoad'; $bi.UriSource = New-Object System.Uri $t.Preview; $bi.EndInit()
        $Barra.Source = $bi; $Barra.Visibility = 'Visible'; $SenzaAnteprima.Visibility = 'Collapsed'
    } else {
        $Barra.Source = $null; $Barra.Visibility = 'Collapsed'; $SenzaAnteprima.Visibility = 'Visible'
    }

    $Mock.Children.Clear()
    Rett 0 0 642 190 (Br $p.bg) (Br $p.surface) 1 8
    # finestra con il focus
    Rett 14 14 200 162 (Br $p.surface '80') (Br $k.single) 3 6
    Rett 26 28 110 8 (Br $p.text 'CC') $null 0 3
    Rett 26 46 170 5 (Br $p.subtext '66') $null 0 2
    Rett 26 58 150 5 (Br $p.subtext '66') $null 0 2
    Rett 26 70 160 5 (Br $p.subtext '66') $null 0 2
    Scritta 26 150 'attiva' $k.single 10
    # finestra senza focus
    Rett 226 14 160 74 (Br $p.surface '55') (Br $k.unfocused) 2 6
    Rett 238 28 80 6 (Br $p.text '88') $null 0 3
    Scritta 238 64 'inattiva' $p.subtext 10
    # stack
    Rett 226 100 160 76 (Br $p.surface '55') (Br $k.stack) 2 6
    Rett 238 112 50 8 (Br $k.stack '99') $null 0 3
    Rett 292 112 50 8 (Br $p.subtext '44') $null 0 3
    Scritta 238 152 'stack' $k.stack 10
    # launcher
    Rett 402 20 226 150 (Br $p.bg 'F2') (Br $p.accent '66') 1 10
    Scritta 416 30 'Win+Space' $p.subtext 12 0.7
    Rett 414 52 202 1 (Br $p.surface) $null 0 0
    Rett 410 60 210 28 (Br $p.accent '3D') $null 0 6
    Scritta 422 65 'Firefox' $p.text 12
    Scritta 422 97 'Impostazioni' $p.text 12
    Scritta 422 125 'Terminale' $p.text 12

    $Colori.Children.Clear()
    foreach ($c in @(@('fondo', $p.bg), @('superficie', $p.surface), @('testo', $p.text), @('accento', $p.accent),
                     @('attiva', $k.single), @('stack', $k.stack), @('monocle', $k.monocle), @('floating', $k.floating), @('inattiva', $k.unfocused))) {
        $sp = New-Object System.Windows.Controls.StackPanel
        $sp.Orientation = 'Horizontal'; $sp.Margin = '0,0,14,6'
        $b = New-Object System.Windows.Controls.Border
        $b.Width = 12; $b.Height = 12; $b.CornerRadius = 3
        $b.Background = Br $c[1]; $b.BorderBrush = Br $ui.surface; $b.BorderThickness = 1
        [void]$sp.Children.Add($b)
        $l = Nuovo-Testo "$($c[0]) $($c[1])" $ui.subtext 10 0.8
        $l.Margin = '5,0,0,0'
        [void]$sp.Children.Add($l)
        [void]$Colori.Children.Add($sp)
    }
}

$script:applicando = $false
$script:attivato   = $false

function Applica {
    $item = $Lista.SelectedItem
    if (-not $item -or $script:applicando) { return }
    $t = $item.Tag
    $script:applicando = $true
    $Stato.Text = "Applico $($t.Meta.name)..."
    $win.Dispatcher.Invoke([action]{}, [System.Windows.Threading.DispatcherPriority]::Render)
    try {
        & $SetTheme -Tema $t.Id -Quiet
        $win.Close()
    } catch {
        $Stato.Text = "Errore: $($_.Exception.Message)"
        $script:applicando = $false
    }
}

$Lista.Add_SelectionChanged({ if ($Lista.SelectedItem) { Mostra $Lista.SelectedItem.Tag } })
$Lista.Add_MouseDoubleClick({ Applica })
$win.Add_PreviewKeyDown({
    param($s, $e)
    $k = [string]$e.Key
    if ($k -eq 'Escape') { $e.Handled = $true; $win.Close() }
    elseif ($k -eq 'Return' -or $k -eq 'Enter') { $e.Handled = $true; Applica }
    elseif ($k -eq 'J' -or $k -eq 'K') {
        $e.Handled = $true
        $n = if ($k -eq 'J') { $Lista.SelectedIndex + 1 } else { $Lista.SelectedIndex - 1 }
        $Lista.SelectedIndex = [Math]::Max(0, [Math]::Min($Lista.Items.Count - 1, $n))
        $Lista.ScrollIntoView($Lista.SelectedItem)
        [void]$Lista.SelectedItem.Focus()
    }
})
$win.Add_Activated({ $script:attivato = $true })
$win.Add_Deactivated({ if ($script:attivato -and -not $script:applicando) { $win.Close() } })
$win.Add_Loaded({
    [Primopiano]::Forza((New-Object System.Windows.Interop.WindowInteropHelper $win).Handle)
    $win.Activate() | Out-Null
    if ($Lista.SelectedItem) { [void]$Lista.SelectedItem.Focus() }
})

$indice = [Array]::IndexOf(@($temi | ForEach-Object { $_.Id }), $attivo)
$Lista.SelectedIndex = [Math]::Max(0, $indice)

[void]$win.ShowDialog()
}
catch {
    if (-not (Test-Path -LiteralPath $Base)) { New-Item -ItemType Directory -Path $Base -Force | Out-Null }
    "[$(Get-Date -Format s)] $($_.Exception.Message)`n$($_.ScriptStackTrace)`n" | Out-File -LiteralPath $LogFile -Append -Encoding utf8
    throw
}
