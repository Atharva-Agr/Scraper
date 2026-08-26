$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$target = Join-Path $PSScriptRoot "LINENGRASS_SCRAPER.bat"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "LinenGrass Scraper.lnk"

if (!(Test-Path $target)) {
    Write-Host "Could not create shortcut because LINENGRASS_SCRAPER.bat was not found." -ForegroundColor Yellow
    exit 0
}

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = "Open LinenGrass Scraper"
$shortcut.Save()

Write-Host "Desktop shortcut created: $shortcutPath" -ForegroundColor Green
