# SSH Console Launcher

**Current version:** 1.5.3  
**Platform:** Windows 10 / Windows 11  
**Purpose:** A lightweight Windows GUI for managing multiple SSH console sessions with saved profiles, split panes, tabs, quick commands, auto-login, reconnect controls, and terminal monitoring.

---

## Overview

SSH Console Launcher is a Windows desktop app built in Python. It was created to make repeated SSH work faster and easier, especially when connecting to the same Linux servers many times per day.

Instead of opening separate command prompt windows or manually typing usernames, passwords, and commands every time, the app lets you:

- Save SSH profiles.
- Open one or more SSH consoles quickly.
- Use tabs and split panes.
- Auto-login with saved credentials.
- Run frequently used commands with one click.
- Monitor session connection status.
- Reconnect, clear, focus, and close sessions from the GUI.

The app is designed for a maximum practical workflow of around 1 to 4 terminals per tab, but it can support multiple tabs.

---

## Main Features

### SSH Profile Management

You can save SSH profiles with:

- Profile name
- Host / IP
- Username
- Port
- Password

Passwords are stored using the Windows credential/keyring system through the Python `keyring` package. Passwords are not stored directly in the JSON profile file.

Profiles are saved in:

```text
%APPDATA%\EmbeddedSSHLauncher\profiles.json
```

---

### Recent Connections, Environment Tags, and SSH Config Import

Starting with version 1.5.0:

- **Recent**: the sidebar shows the last profiles you opened, most-recent-first, for one-click reopen.
- **Environment tags**: mark a profile as Production, Staging, or Development from the Connection form. The tag shows as a colored border on the profile button and on any open terminal pane for that profile - red/amber/green, so it's obvious at a glance which environment a pane is talking to.
- **Import from SSH Config**: bulk-import `Host` entries from your existing `~/.ssh/config` as profiles (host/user/port only - password is entered on first connect, same as a manually-created profile).

---

### Jump Host and Session Restore

Starting with version 1.5.1:

- **Jump Host**: set a profile's "Jump Host" (in the Connection form) to another saved profile to connect through it as a bastion - the app opens the target host through a single hop via the jump host, prompting for the jump host's own saved password the same way it does for any profile.
- **Session Restore**: when you relaunch the app, if you had tabs open when you last closed it, you'll be asked whether to reopen them (same profiles, panes, and layout). Declining clears the offer so you won't be asked again until you have another session to restore.

---

### File Transfer and Broadcast Typing

Starting with version 1.5.2:

- **File Transfer**: a "File Transfer..." button opens an Upload/Download panel for the focused connection - pick a local file and a remote destination path to upload, or a remote source path and a local save location to download. Runs over `pscp.exe` (bundled alongside `plink.exe`). This is file-picker dialogs, not drag-and-drop.
- **Broadcast Typing**: a "Broadcast Typing (this tab)" switch sends everything you type in the focused pane to every other pane in the same tab - useful for running the same command across several identical servers at once. Each tab remembers its own on/off state.

---

### Embedded SSH Consoles

The app opens SSH sessions inside the GUI instead of launching separate Windows Terminal windows.

Each console supports:

- Auto-login
- Terminal output rendering
- ANSI color handling
- `htop`
- `uwsgitop`
- `tail -f`
- Standard shell commands
- Copy/paste
- Reconnect
- Clear
- Close
- Focus selection

SSH sessions are launched through `plink.exe` from PuTTY.

---

### Tabs and Split Panes

The app supports:

- New tab
- Split current tab
- Open 2 split consoles
- Open 3 split consoles
- Open 4 split consoles
- Vertical split
- Horizontal split
- Rename current tab
- Close current tab
- Close tab using the `×` symbol

If the last console in a tab is closed, the tab is also destroyed.

---

### Quick Commands

Quick Commands let you create buttons for commands you run often.

Default quick commands include:

```bash
htop
cd /home/www-data/web2py/
tail -f web2py.log
sudo uwsgitop /tmp/stats.socket
clear
```

You can add, edit, and delete commands from the GUI.

Quick commands are saved in:

```text
%APPDATA%\EmbeddedSSHLauncher\commands.json
```

Quick commands are sent to the currently focused terminal.

---

### Connection Status Indicator

Each terminal shows a connection status indicator:

```text
● Connected
● Connecting
● Disconnected
```

The indicator helps identify when a session has dropped and needs reconnecting.

---

### Modern UI

Starting with version 1.3, the UI uses `customtkinter` for a modern dark interface.

UI improvements include:

- Dark theme
- Modern left sidebar
- Rounded buttons
- Toolbar actions
- Quick command buttons
- Highlighted active terminal
- Status bar
- Improved layout and spacing

---

## Requirements

Install Python packages:

```powershell
pip install pywinpty keyring pyte customtkinter
```

Required executables:

```text
plink.exe
pscp.exe
```

Place both beside the Python script or compiled `.exe` (or install PuTTY and add it to your PATH). `pscp.exe` is only needed for File Transfer - the app still runs without it, that feature just won't work.

---

## Running the App

Example:

```powershell
python SSH_Console_Launcher.py
```

---

## Building a Portable EXE or Installer

Install build tools:

```powershell
pip install pyinstaller pywinpty keyring pyte customtkinter
```

With `plink.exe` and `pscp.exe` in the project root, build:

```powershell
.\build_exe.ps1
```

The `.exe` lands in `dist\`. To also build the one-click installer (Inno Setup - see [doc/BUILD.md](doc/BUILD.md) for full setup):

```powershell
"C:\Users\<you>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

Produces `installer_output\SSH-Console-Launcher-Setup-v<version>.exe`.

Recommended portable (no-installer) folder structure:

```text
SSHLauncher\
  SSH_Console_Launcher.exe
  plink.exe
  pscp.exe
```

---

## Configuration Files

The app stores user data in:

```text
%APPDATA%\EmbeddedSSHLauncher\
```

Files:

```text
profiles.json
commands.json
```

Passwords are stored through Windows/keyring, not directly in these files.

---

## Security Notes

This app is designed for internal/personal administrative use.

Important notes:

- Passwords are saved through `keyring`, not plain JSON.
- `plink.exe -pw` is used for automatic login.
- SSH key support is a recommended future improvement.
- Anyone with access to your Windows user session may be able to use the saved profiles.
- Use Windows account protection and disk encryption where appropriate.

---

## Known Limitations

The app uses `tk.Text` plus `pyte` for terminal rendering. This works well enough for the current workflow, including `htop` and `uwsgitop`, but it is not a full native terminal emulator like Windows Terminal, xterm, or xterm.js.

Some highly interactive terminal applications may still have minor rendering differences.

Examples that may not be perfect:

- Complex `vim` usage
- Some `nano` layouts
- Advanced ncurses interfaces
- Mouse interactions inside terminal apps

---

## Layout Manager

Starting with version 1.3.9, the app includes explicit Layout Manager controls so you can rearrange consoles after they are already open.

Available layouts:

- **Auto Layout**: chooses the best layout based on pane count.
- **2 Panes: Side by Side**: two terminals left/right.
- **2 Panes: Stacked**: two terminals top/bottom.
- **3 Panes: 2 Top / 1 Bottom**: two terminals on top, one full-width terminal below.
- **3 Panes: 1 Top / 2 Bottom**: one full-width terminal on top, two terminals below.
- **4 Panes: 2 x 2 Grid**: four terminals in a square grid.

This means you no longer need to close and reopen SSH sessions just to change how the panes are arranged.

---

## Smart Split Layouts

Starting with version 1.3.8, multi-console split views are arranged more naturally:

- **Open 3 Split** creates two consoles on the top row and one full-width console on the bottom row.
- **Open 4 Split** creates a 2 x 2 square layout.

The manual **Vertical Split** and **Horizontal Split** buttons still force a simple stacked or side-by-side layout when needed.

---

## Built-in Documentation Viewer

The app can display project documentation inside the GUI. It looks for these files beside the `.py` script or packaged `.exe`:

```text
README.md
VERSION_HISTORY.md
FEATURES_PLAN.md
```

When the app is packaged as a Windows `.exe`, include these files with PyInstaller using `--add-data`. If the external files are missing, the app also includes embedded fallback documentation.

---


---

## Web Host Monitoring Dashboard Upgrade

Starting with **v1.4.1**, the Monitoring Dashboard is focused on detecting conditions that can lead to web host degradation or outages, including possible **502 Bad Gateway** symptoms.

The dashboard now checks more than basic CPU/RAM/Disk. It also looks for:

- Load average compared to CPU cores.
- RAM and swap pressure.
- Disk usage for `/` and the Web2py folder.
- Number of established TCP/web connections.
- Top remote client IPs.
- Estimated active users/client IPs from Web2py logs.
- Login/auth/user-related events from Web2py logs.
- Recent Web2py errors, tracebacks, exceptions, tickets, and failures.
- Nginx process/status and recent Nginx upstream/gateway errors.
- uWSGI worker status from `/tmp/stats.socket` when available.
- Busy/idle uWSGI worker ratio.
- uWSGI exceptions, harakiri counts, respawns, RSS memory, and average response time when available.
- Web2py/uWSGI top CPU consumers.

### New Monitoring Cards

The dashboard includes these additional cards:

- Overall Web Host Risk
- 502 / Gateway Risk
- Swap Usage
- Disk Web2py
- Web Connections
- Active Users / IPs
- uWSGI Workers
- uWSGI Health
- Nginx Status
- Login/User Events
- Web2py/uWSGI CPU

### New Monitoring Quick Actions

The sidebar Monitoring section now includes:

- Open Dashboard
- Run Health Check
- 502 / Gateway Check
- Connections
- Active Users / IPs
- Recent Errors
- Web2py Processes

The goal is to make it easier to detect early warning signs before users begin seeing `502 Bad Gateway`, Nginx upstream failures, overloaded workers, excessive connections, or Linux resource saturation.

---

## Web2py Monitoring Dashboard

Starting with version 1.4.0, the app includes a Monitoring Dashboard focused on Web2py/uWSGI server health.

Open it from the sidebar under:

```text
Monitoring -> Open Dashboard
```

The dashboard runs a non-interactive health check over SSH using `plink.exe` and shows the result as cards. It does not scrape values from the `htop` screen; it runs direct shell commands and parses the output.

Dashboard cards include:

- Server
- Load Average
- RAM Usage
- Disk `/`
- Web2py Processes
- uWSGI Processes
- Recent Errors
- Top CPU
- Top Memory

Monitoring quick actions include:

- Open Dashboard
- Run Health Check
- Recent Errors
- Web2py Processes

The dashboard also supports optional auto-refresh intervals.

---

## Recommended Next Steps

Potential future improvements:

1. Hotkeys for Quick Commands, such as `Ctrl+1`, `Ctrl+2`, etc.
2. Command groups, such as Web2py, Logs, Monitoring, Docker, Database.
3. Auto-reconnect option when a connection drops.
4. Save layouts per profile.
5. Open a profile with a predefined set of panes and commands.
6. Run a command on all panes.
7. Local session logging.
8. Search inside terminal output.
9. Import/export profiles and commands.
10. SSH key support.
11. Full installer with `plink.exe` included.
12. Possible migration to xterm.js/WebView for more complete terminal rendering.

---

## Current Stable Version

The current working version is:

```text
v1.5.3
```

This version includes the modern UI, quick commands, tab close fixes, terminal colors, connection status indicators, corrected focus behavior, Layout Manager, the Web2py Monitoring Dashboard, the advanced Web Host Monitoring Dashboard upgrade, the v1.4.2 bug-fix and visual-polish pass, v1.5.0's Recent Connections/Environment Tags/SSH Config Import, v1.5.1's Jump Host support and Session Restore, v1.5.2's File Transfer and Broadcast Typing, and v1.5.3's Monitoring History/Sparklines and Multi-Server View. See `VERSION_HISTORY.md` for details.

---

## Documentation

Developer-facing documentation (architecture, configuration, build/packaging, and the generated codebase knowledge graph) lives in [doc/](doc/).

---

## License

MIT License - see [LICENSE](LICENSE).