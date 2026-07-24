# Building a Portable EXE

## Requirements

```powershell
pip install pyinstaller pywinpty keyring pyte customtkinter
```

`plink.exe` (from PuTTY) must be available to bundle — either already on `PATH` or copied next to the script before building.

## Build command

```powershell
pyinstaller --onefile --windowed `
  --add-binary "plink.exe;." `
  --add-data "README.md;." `
  --add-data "VERSION_HISTORY.md;." `
  --add-data "FEATURES_PLAN.md;." `
  SSH_Console_Launcher.py
```

The `--add-data` flags matter: the app's built-in Documentation Viewer looks for `README.md`, `VERSION_HISTORY.md`, and `FEATURES_PLAN.md` beside the frozen `.exe` (via PyInstaller's `sys._MEIPASS`), falling back to an embedded copy baked into the script if they're missing. See `find_document_path()` in `SSH_Console_Launcher.py`.

Output lands in `dist\`.

## Recommended distribution layout

```text
SSHLauncher\
  SSH_Console_Launcher.exe
  plink.exe
```

`plink.exe` can also be omitted from the folder if PuTTY is installed and on `PATH` system-wide.

## Notes

- This is a one-file, one-window build (`--onefile --windowed`) — no console window, no installer. A proper installer (Inno Setup/NSIS) is tracked as a future improvement (`v1.6.0` in `FEATURES_PLAN.md`).
- Rebuilding after changing any of the three Markdown docs requires re-running PyInstaller so the bundled copies stay in sync with what ships inside the `.exe`.
