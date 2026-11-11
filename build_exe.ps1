# build_exe.ps1 - builds dist\SSH_Console_Launcher_v2.exe
# No plink.exe/pscp.exe to bundle - v2 has zero external binary dependencies
# (paramiko talks SSH directly; pywebview uses the OS's WebView2 runtime).

$ErrorActionPreference = "Stop"

pyinstaller --noconfirm --onefile --windowed `
  --name "SSH_Console_Launcher_v2" `
  --icon "image\app_icon.ico" `
  --add-data "web;web" `
  --add-data "image;image" `
  --add-data "CHANGELOG.md;." `
  --hidden-import "webview.platforms.edgechromium" `
  --hidden-import "win32clipboard" `
  --hidden-import "win32con" `
  --hidden-import "psutil" `
  main.py

Write-Host "Build complete: dist\SSH_Console_Launcher_v2.exe"
