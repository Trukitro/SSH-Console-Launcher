# build_exe.ps1
# Build SSH Console Launcher as a single Windows EXE.

$ErrorActionPreference = "Stop"

$AppFile = "SSH_Console_Launcher.py"

if (-not (Test-Path $AppFile)) {
    throw "Could not find SSH_Console_Launcher.py"
}

if (-not (Test-Path "plink.exe")) {
    Write-Host "WARNING: plink.exe was not found in this folder. Copy it beside dist\SSH_Console_Launcher.exe after building (or run installer.iss, which does this for you)." -ForegroundColor Yellow
}

$IconArgs = @()
if (Test-Path "image\app_icon.ico") {
    $IconArgs = @("--icon", "image\app_icon.ico")
}

# Note: plink.exe is intentionally NOT bundled via --add-binary here. PyInstaller's
# --add-binary extracts it into the onefile exe's temp _MEIPASS dir at runtime, but
# find_plink() in SSH_Console_Launcher.py only checks beside sys.executable (the
# real .exe's own folder) or system PATH - it never looks in _MEIPASS. Ship
# plink.exe as a loose sibling file next to the built exe instead (see README.md's
# "Recommended folder structure" and installer.iss).
pyinstaller --onefile --windowed `
  --add-data "README.md;." `
  --add-data "VERSION_HISTORY.md;." `
  --add-data "FEATURES_PLAN.md;." `
  --add-data "image;image" `
  @IconArgs `
  $AppFile

Write-Host "Build complete. Check the dist folder." -ForegroundColor Green
