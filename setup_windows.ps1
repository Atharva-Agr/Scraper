$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== LinenGrass Scraper desktop setup ===" -ForegroundColor Cyan

if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python was not found on PATH." -ForegroundColor Red
    Write-Host "Install Python 3.11+ first, then run this script again."
    exit 1
}

if (!(Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$pip = Join-Path $PSScriptRoot ".venv\Scripts\pip.exe"

Write-Host "Upgrading pip..."
& $python -m pip install --upgrade pip

Write-Host "Installing Python packages..."
& $pip install -r requirements.txt

Write-Host "Installing Playwright Chromium browser..."
& $python -m playwright install chromium

if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

Write-Host ""
Write-Host "Python setup complete." -ForegroundColor Green
Write-Host "Next: run .\install_ai_ollama.ps1 to install/pull the local AI model."
Write-Host "Then run .\LINENGRASS_SCRAPER.bat"
