# build_exe.ps1
# Build SSH Console Launcher as a single Windows EXE.

$ErrorActionPreference = "Stop"

$AppFile = "SSH_Console_Launcher.py"

if (-not (Test-Path $AppFile)) {
    throw "Could not find SSH_Console_Launcher.py"
}

if (-not (Test-Path "plink.exe")) {
    Write-Host "WARNING: plink.exe was not found in this folder. The app can still build, but SSH password mode may not work portably." -ForegroundColor Yellow
}

pyinstaller --onefile --windowed `
  --add-binary "plink.exe;." `
  --add-data "README.md;." `
  --add-data "VERSION_HISTORY.md;." `
  --add-data "FEATURES_PLAN.md;." `
  $AppFile

Write-Host "Build complete. Check the dist folder." -ForegroundColor Green
