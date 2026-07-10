# Register the Mac/Win Controller server to start at login (Windows analog of
# macOS Login Items). Creates a shortcut in the current user's Startup folder
# pointing at start_win_controller_server.vbs (which launches the tray app
# hidden). Idempotent: re-running just overwrites the shortcut.
#
# Run:    .\install-autostart.ps1
# Undo:   .\install-autostart.ps1 -Remove   (or delete the shortcut it reports)
#
# Keep this file ASCII-only (Windows PowerShell 5.1 mis-decodes non-ASCII in a
# no-BOM script).

param([switch]$Remove)

$ErrorActionPreference = "Stop"

$here    = $PSScriptRoot
$vbs     = Join-Path $here "start_win_controller_server.vbs"
$startup = [Environment]::GetFolderPath("Startup")
$lnk     = Join-Path $startup "Mac Controller.lnk"

if ($Remove) {
    if (Test-Path $lnk) {
        Remove-Item $lnk -Force
        Write-Host "[OK] Auto-start removed: $lnk" -ForegroundColor Green
    } else {
        Write-Host "  [!] No auto-start shortcut found at $lnk" -ForegroundColor Yellow
    }
    return
}

if (-not (Test-Path $vbs)) {
    Write-Host "  [X] start_win_controller_server.vbs not found next to this script." -ForegroundColor Red
    exit 1
}

$ws = New-Object -ComObject WScript.Shell
$s  = $ws.CreateShortcut($lnk)
# wscript.exe runs the .vbs; the .vbs itself launches pythonw hidden.
$s.TargetPath       = Join-Path $env:WINDIR "System32\wscript.exe"
$s.Arguments        = '"' + $vbs + '"'
$s.WorkingDirectory = $here
$s.Description       = "Start Mac/Win Controller server at login"
$s.Save()

Write-Host "[OK] Auto-start installed: $lnk" -ForegroundColor Green
Write-Host "     The server will start hidden at each login." -ForegroundColor Cyan
Write-Host "     Disable with:  .\install-autostart.ps1 -Remove" -ForegroundColor Cyan
