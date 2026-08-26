$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== LinenGrass Scraper full setup ===" -ForegroundColor Cyan

.\setup_windows.ps1
.\install_ai_ollama.ps1
.\check_install.ps1
.\create_desktop_shortcut.ps1

Write-Host ""
Write-Host "LinenGrass Scraper setup is finished." -ForegroundColor Green
Write-Host "Open the app with LINENGRASS_SCRAPER.bat or the LinenGrass Scraper desktop shortcut."
