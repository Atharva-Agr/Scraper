@echo off
cd /d %~dp0

if not exist ".venv\Scripts\python.exe" (
    echo LinenGrass Scraper is not set up yet.
    echo Please run INSTALL_LINENGRASS_SCRAPER.bat first.
    pause
    exit /b 1
)

start "LinenGrass Scraper" ".venv\Scripts\python.exe" app.py
