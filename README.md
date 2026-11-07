# Windowsarchy

A Windows tiling-desktop setup inspired by [Omarchy](https://omarchy.org) (not affiliated with or endorsed by it):
[Komorebi](https://github.com/LGUG2Z/komorebi) + [whkd](https://github.com/LGUG2Z/whkd) + [YASB](https://github.com/amnweb/yasb) + [Flow Launcher](https://github.com/Flow-Launcher/Flow.Launcher),
with theme switching, a Wi-Fi panel and a system equalizer.

This repository holds the files that the **Windowsarchy** YASB theme (submitted to
[yasb-themes](https://github.com/amnweb/yasb-themes)) relies on. The theme itself works as a plain
`config.yaml` + `styles.css`; the extra files here are the optional parts it calls.

## What is inside

| Path | What it is |
|---|---|
| `.config/whkdrc` | All keyboard shortcuts, every one on the Win key. `Win + K` shows the cheatsheet. |
| `.config/komorebi/` | `komorebi.json` (workspaces I..VII, borders, gaps) and `applications.json`. |
| `.config/komorebi-scripts/wifi-panel.pyw` | Floating Wi-Fi panel opened by the YASB Wi-Fi widget (left click). |
| `.config/komorebi-scripts/yasb-resubscribe.ps1` | Re-attaches YASB to Komorebi when the bar is stuck on "Komorebi Offline". |
| `.config/komorebi-scripts/set-theme.ps1`, `theme-menu.ps1`, `make-theme-previews.ps1` | Switch a whole theme (bar, window borders, launcher) from a menu with previews (`Win + Ctrl + Shift + Space`). |
| `.config/komorebi-scripts/fix-opacity.ps1` | Fixes windows left semi-transparent after fullscreen (`Win + Shift + T`, `Win + Ctrl + T` for all). |
| `.config/komorebi-scripts/eq.ps1`, `.local/bin/eq.cmd`, `eqapo-presets/` | System equalizer through [Equalizer APO](https://sourceforge.net/projects/equalizerapo/) (`Win + Ctrl/Alt/Shift + E`). |
| `.config/winfetch/config.ps1` | [winfetch](https://github.com/lptstr/winfetch) settings: the system-info panel shown in the terminal, Omarchy style. Run `winfetch`. |
| `.config/windowsarchy/` | Themes (`windowsarchy`, `catppuccin`, `kde-breeze-dark-stable`, `ubuntu-yaru`) and the Flow Launcher template. |

Script comments are partly in Italian. The code and the shortcuts file are documented in English.

## Requirements

- Windows 11
- [YASB](https://github.com/amnweb/yasb), [Komorebi](https://github.com/LGUG2Z/komorebi) and [whkd](https://github.com/LGUG2Z/whkd)
- Fonts: [JetBrainsMono Nerd Font Propo](https://www.nerdfonts.com/font-downloads) and Segoe Fluent Icons (included in Windows 11)
- Optional: [winfetch](https://github.com/lptstr/winfetch) (`Install-Script winfetch`) for the terminal system-info panel, and [Oh My Posh](https://ohmyposh.dev) with its default theme for the prompt (add `oh-my-posh init pwsh | Invoke-Expression` to your PowerShell profile)
- Optional: [Windows Terminal](https://github.com/microsoft/terminal)
- Optional: [Flow Launcher](https://github.com/Flow-Launcher/Flow.Launcher) (`Win + Space`)
- Optional: [Equalizer APO](https://sourceforge.net/projects/equalizerapo/) for the `eq` shortcuts
- Wi-Fi panel: Python 3.10+ with `pythonw` in PATH, then

```powershell
pip install --user PyQt6 psutil qrcode winrt-runtime winrt-Windows.Devices.Radios winrt-Windows.Foundation winrt-Windows.Foundation.Collections
```

## Install

Copy the folders into your user profile, keeping the structure:

```powershell
Copy-Item .config\*  $env:USERPROFILE\.config\ -Recurse -Force
Copy-Item .local\*   $env:USERPROFILE\.local\  -Recurse -Force   # eq.cmd; add .local\bin to PATH
Copy-Item .config\whkdrc $env:USERPROFILE\.config\whkdrc -Force
```

Set `KOMOREBI_CONFIG_HOME` to `%USERPROFILE%\.config\komorebi` if you want Komorebi to read its config from there,
copy `eqapo-presets\*.txt` into `<Equalizer APO>\config\windowsarchy\`, then apply a theme:

```powershell
& $env:USERPROFILE\.config\komorebi-scripts\set-theme.ps1 windowsarchy
```

Back up your own `config.yaml`, `styles.css` and `whkdrc` first: these files overwrite them.

## Main shortcuts

| Keys | Action |
|---|---|
| `Win + K` | Shortcut cheatsheet |
| `Win + arrows` / `Win + Shift + arrows` | Focus / move window |
| `Win + 1..7` / `Win + Shift + 1..7` | Go to workspace / move window to workspace |
| `Win + Alt + arrows` | Stack windows |
| `Win + P` | Pause Komorebi (and re-attach YASB when resuming) |
| `Win + Space` | Flow Launcher |
| `Win + Ctrl + Shift + Space` | Theme menu |

## License

MIT
