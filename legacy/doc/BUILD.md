# Building a Portable EXE and Installer

## Requirements

```powershell
pip install pyinstaller pywinpty keyring pyte customtkinter
```

`plink.exe` and `pscp.exe` (both from PuTTY) must be present in the project root before building — either already on `PATH` or copied next to the script. Both are `.gitignore`d (redistributable PuTTY binaries, not project source) and stay on disk between builds once downloaded once.

## Build command

Use `build_exe.ps1` (wraps the command below and warns if `plink.exe`/`pscp.exe` are missing):

```powershell
pyinstaller --onefile --windowed `
  --add-data "README.md;." `
  --add-data "VERSION_HISTORY.md;." `
  --add-data "FEATURES_PLAN.md;." `
  --add-data "image;image" `
  --icon "image\app_icon.ico" `
  SSH_Console_Launcher.py
```

`plink.exe`/`pscp.exe` are deliberately **not** passed via `--add-binary` — see the comment in `build_exe.ps1` for why (PyInstaller's onefile bootloader extracts `--add-binary` files into a temp `_MEIPASS` dir at runtime, but `find_plink()`/`find_pscp()` only check beside the real `.exe` or system `PATH`). They ship as loose sibling files instead — `installer.iss` handles this automatically.

The `--add-data` flags for the three Markdown docs matter for a different reason: the app's built-in Documentation Viewer looks for `README.md`, `VERSION_HISTORY.md`, and `FEATURES_PLAN.md` beside the frozen `.exe` (via PyInstaller's `sys._MEIPASS`), falling back to an embedded copy baked into the script if they're missing. See `find_document_path()` in `SSH_Console_Launcher.py`.

Output lands in `dist\`.

## Building the installer

```powershell
"C:\Users\<you>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

Produces `installer_output\SSH-Console-Launcher-Setup-v<version>.exe` — a per-user installer (no admin/UAC) with a Start Menu shortcut, optional desktop shortcut, and uninstaller. Bump `MyAppVersion` in `installer.iss` for each release.

## Recommended distribution layout (portable, no installer)

```text
SSHLauncher\
  SSH_Console_Launcher.exe
  plink.exe
  pscp.exe
```

`plink.exe`/`pscp.exe` can be omitted if PuTTY is installed and on `PATH` system-wide — `pscp.exe` specifically is only needed for the File Transfer feature; the app still runs without it.

## Notes

- Rebuilding after changing any of the three Markdown docs, the icon, or `SSH_Console_Launcher.py` itself requires re-running PyInstaller (and re-compiling the installer) so the bundled copies stay in sync with what ships.
