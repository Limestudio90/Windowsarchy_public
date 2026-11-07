@echo off
rem =====================================================================
rem  Command-line shortcut for eq.ps1 (Windowsarchy).
rem
rem  Usage: eq              next preset
rem         eq next         same
rem         eq toggle       turn off / back on
rem         eq edit         graphical editor on the active preset
rem         eq status       tells which preset is active
rem         eq list         lists the presets
rem         eq <name>       applies a preset by name
rem         eq toggle quiet no on-screen box
rem
rem  It exists so the komorebi cheatsheet (win + k) shows a short
rem  command ("eq toggle") instead of a long truncated powershell path.
rem =====================================================================

setlocal
set "EQ=%USERPROFILE%\.config\komorebi-scripts\eq.ps1"
set "ARGS="

if "%~1"=="" goto esegui
if /i "%~1"=="next" goto esegui
if /i "%~1"=="toggle" set "ARGS=-Toggle"
if /i "%~1"=="edit"   set "ARGS=-Edit"
if /i "%~1"=="status" set "ARGS=-Status"
if /i "%~1"=="list"   set "ARGS=-List"
if not defined ARGS set "ARGS=-Preset %~1"

:esegui
if /i "%~2"=="quiet" set "ARGS=%ARGS% -Quiet"

powershell -NoProfile -ExecutionPolicy Bypass -File "%EQ%" %ARGS%
exit /b %ERRORLEVEL%
