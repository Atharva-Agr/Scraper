$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$model = "qwen2.5:7b"

Write-Host "=== LinenGrass Scraper AI setup: Ollama + $model ===" -ForegroundColor Cyan

if (!(Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Ollama was not found." -ForegroundColor Yellow

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Trying to install Ollama with winget..."
        winget install Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
    }
    else {
        Write-Host "winget was not found. Install Ollama manually, then rerun this script."
        Write-Host "After installing Ollama, run: ollama pull $model"
        exit 1
    }
}

Write-Host "Checking Ollama service..."
ollama list | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Host "Starting Ollama service in background..."
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 6
}

Write-Host "Pulling AI model: $model"
Write-Host "This can take a while because the model is several GB."
ollama pull $model

Write-Host ""
Write-Host "AI setup complete." -ForegroundColor Green
Write-Host "The app is configured to use: ollama/$model"
Write-Host "Run .\LINENGRASS_SCRAPER.bat to start LinenGrass Scraper."
