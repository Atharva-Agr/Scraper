$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$model = "qwen2.5:7b"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (!(Test-Path $python)) {
    Write-Host "Missing .venv. Run setup_windows.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Checking Python files..." -ForegroundColor Cyan
& $python -m py_compile app.py app_state.py config.py pipeline.py discovery.py url_utils.py cache_utils.py contacts.py hotel_scraper.py schema.py validation.py purge_utils.py main.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "Python compile check passed." -ForegroundColor Green
}
else {
    Write-Host "Python compile check failed." -ForegroundColor Red
}

Write-Host ""
Write-Host "Checking required folders..." -ForegroundColor Cyan
$folders = @("data", "data\search_lists", "data\run_history", "exports")
foreach ($folder in $folders) {
    if (Test-Path $folder) {
        Write-Host "OK: $folder" -ForegroundColor Green
    }
    else {
        Write-Host "Missing: $folder" -ForegroundColor Yellow
        New-Item -ItemType Directory -Force -Path $folder | Out-Null
    }
}

Write-Host ""
Write-Host "Checking Ollama..." -ForegroundColor Cyan
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    $ollamaOutput = ollama list
    $ollamaOutput

    if ($ollamaOutput -match [regex]::Escape($model)) {
        Write-Host "AI model found: $model" -ForegroundColor Green
    }
    else {
        Write-Host "AI model not found: $model" -ForegroundColor Yellow
        Write-Host "Run: ollama pull $model"
    }
}
else {
    Write-Host "Ollama not found. Run install_ai_ollama.ps1." -ForegroundColor Yellow
}
