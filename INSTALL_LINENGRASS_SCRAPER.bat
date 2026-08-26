@echo off
cd /d %~dp0

echo ==========================================
echo LinenGrass Scraper first-time setup
echo ==========================================
echo.
echo This will install the app environment and AI model.
echo The AI model download may take a while.
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_all_windows.ps1"

echo.
echo Setup finished.
echo You can now open LinenGrass Scraper using LINENGRASS_SCRAPER.bat or the desktop shortcut.
echo.
pause
