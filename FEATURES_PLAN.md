# FEATURES_PLAN.md

# SSH Console Launcher - Future Features Plan

**Current stable version:** v1.4.2  
**Planning document created for:** local Git/project tracking

This document tracks future improvements, proposed versions, and implementation ideas for the SSH Console Launcher app.

---

## Current App Status

The app currently supports:

- Saved SSH profiles
- Automatic login through `plink.exe`
- Embedded SSH terminals
- Tabs
- Split panes
- Smart split layouts for 3 and 4 panes
- Quick command buttons
- Modern CustomTkinter UI
- Terminal ANSI color support
- High-contrast terminal colors
- Connection status indicators
- Built-in documentation viewer
- README and VERSION_HISTORY Markdown files
- PyInstaller packaging support

---

## v1.3.9 - Layout Manager ✅ Implemented

### Goal

Improve split-pane control and make layouts easier to manage.

### Planned Features

- Add explicit layout buttons:
  - 1 pane
  - 2 vertical
  - 2 horizontal
  - 3 layout: 2 top / 1 bottom
  - 3 layout: 1 top / 2 bottom
  - 4 layout: 2 x 2 grid
- Allow changing the current tab layout after consoles are already open.
- Allow moving panes between layout positions.
- Add visual labels or borders for active pane position.

### Notes

This is the most logical next step because split panes are central to the workflow.

---

## v1.4.0 - Web2py Monitoring Dashboard ✅ Implemented

### Goal

Add a monitoring dashboard focused on Web2py/uWSGI server health instead of relying only on visual terminal tools like `htop` and `uwsgitop`.

### Planned Features

- Health Check button.
- CPU, RAM, Disk, and Load cards.
- Web2py process count card.
- uWSGI process/status card.
- Recent errors and tracebacks quick checks.
- Optional auto-refresh interval.
- Warning/critical thresholds.

### Possible Commands

```bash
uptime
free -m
df -h /
pgrep -af web2py | wc -l
pgrep -af uwsgi | wc -l
grep -i error web2py.log | tail -n 50
grep -i traceback web2py.log | tail -n 50
```

### Implemented in v1.4.0

- Monitoring Dashboard window.
- Server health check using non-interactive SSH command execution.
- CPU/load, RAM, Disk, Web2py, uWSGI, Recent Errors, Top CPU, and Top Memory cards.
- Auto-refresh controls.
- Monitoring sidebar section.
- Health check, recent errors, and Web2py/uWSGI process quick actions.

### Notes

The dashboard executes non-interactive commands and parses the results into cards. It does not try to scrape values from the `htop` screen.

---


---

## v1.4.1 - Web Host Monitoring Dashboard Upgrade ✅ Implemented

### Goal

Improve the dashboard so it can identify web host instability, overloaded workers, excessive user/client traffic, connection spikes, and possible 502 Bad Gateway conditions.

### Implemented

- Overall Web Host Risk card.
- 502 / Gateway Risk detection.
- Connection load detection.
- Active users/client IP estimation from Web2py logs.
- Login/user event count from Web2py logs.
- Nginx status and Nginx gateway/upstream log checks.
- uWSGI worker saturation detection from `/tmp/stats.socket` when available.
- uWSGI exceptions, harakiri, respawn, RSS, and average response time checks.
- Web2py/uWSGI top CPU view.
- Monitoring quick buttons for gateway, connections, users/IPs, errors, and processes.

### Next Monitoring Improvements

- Make thresholds configurable per profile.
- Add persistent monitoring history.
- Add popup alerts when risk becomes critical.
- Add per-profile Web2py path and uWSGI socket settings.

---

## v1.4.2 - Monitoring Alerts and Threshold Settings

### Goal

Make the Monitoring Dashboard more actionable by adding configurable thresholds and clearer warnings.

### Planned Features

- Configurable warning and critical thresholds.
- CPU/load thresholds.
- RAM thresholds.
- Disk thresholds.
- Recent error thresholds.
- Visual alert banner.
- Optional popup notification for critical states.

---

## v1.4.2 - Command Groups

### Goal

Organize Quick Commands into categories instead of one long list.

### Planned Groups

- Monitoring
- Web2py
- Logs
- Services
- Database
- Docker
- Custom

### Planned Features

- Add command group selector.
- Save command groups to `commands.json`.
- Let each command belong to a group.
- Filter visible quick commands by selected group.
- Add group management:
  - Add group
  - Rename group
  - Delete group

---

## v1.4.3 - Run Command on Multiple Panes

### Goal

Allow commands to be executed across multiple terminals.

### Planned Features

Run command on:

- Focused terminal only
- All panes in current tab
- All tabs
- Selected panes only

### Safety Options

- Confirm before running on multiple panes.
- Highlight target panes before sending command.
- Add a setting for command execution mode:
  - Run immediately
  - Paste only
  - Ask before run

---

## v1.4.4 - Auto Layout per Profile

### Goal

Allow a saved SSH profile to automatically open with a predefined layout.

### Planned Features

Profile settings:

- Default layout:
  - 1 pane
  - 2 panes
  - 3 panes
  - 4 panes
- Default commands per pane.
- Open profile and automatically run:
  - `htop`
  - `tail -f web2py.log`
  - `sudo uwsgitop /tmp/stats.socket`
  - custom commands

### Example

A profile could open 4 panes automatically:

| Pane | Command |
|---|---|
| Top left | `htop` |
| Top right | `tail -f web2py.log` |
| Bottom left | `sudo uwsgitop /tmp/stats.socket` |
| Bottom right | shell prompt |

---

## v1.4.5 - Auto Reconnect

### Goal

Reconnect dropped SSH sessions automatically or semi-automatically.

### Planned Features

- Per-profile auto reconnect setting.
- Global auto reconnect setting.
- Retry interval setting.
- Max retry count.
- Visual retry counter.
- Status messages:
  - Disconnected
  - Reconnecting
  - Retry failed
  - Reconnected

### Safety

Auto reconnect should be optional because some commands may not resume safely.

---

## v1.4.6 - Export / Import

### Goal

Make it easy to move settings between PCs.

### Planned Features

Export:

- Profiles without passwords
- Profiles with encrypted backup option
- Commands
- Layouts
- App settings

Import:

- Merge with existing config
- Replace existing config
- Preview import before applying

### Files

Possible export format:

```text
ssh_launcher_backup.json
```

---

## v1.5.0 - SSH Key Support

### Goal

Support safer authentication through SSH keys.

### Planned Features

- Add key file field to profile.
- Support `.ppk` for PuTTY/plink.
- Support OpenSSH private key if using Windows OpenSSH later.
- Support passphrase prompt.
- Allow password or key auth per profile.

### Benefits

- Better security.
- Faster login.
- Less reliance on saved passwords.

---

## v1.5.1 - Session Logging

### Goal

Allow terminal output to be saved locally.

### Planned Features

- Enable/disable logging per terminal.
- Save logs by date/profile/tab.
- Add log folder shortcut.
- Add log retention setting.
- Optional command history file.

### Example Path

```text
%APPDATA%\EmbeddedSSHLauncher\logs\
```

---

## v1.5.2 - Terminal Search

### Goal

Search inside terminal output.

### Planned Features

- Search text in focused terminal.
- Highlight matches.
- Next / previous result.
- Case-sensitive toggle.
- Regex toggle.

---

## v1.6.0 - Packaged Windows App / Installer

### Goal

Make deployment easier.

### Planned Features

- One-click build script.
- Include `plink.exe`.
- Include README and VERSION_HISTORY.
- Include app icon.
- Create Start Menu shortcut.
- Optional installer using Inno Setup or NSIS.

### Recommended Build Command

```powershell
pyinstaller --onefile --windowed `
  --add-binary "plink.exe;." `
  --add-data "README_Embedded_SSH_Launcher.md;." `
  --add-data "VERSION_HISTORY_Embedded_SSH_Launcher.md;." `
  SSH_Console_Launcher_v1_3_8.py
```

---

## v2.0.0 - Full Terminal Engine Upgrade

### Goal

Replace `tk.Text + pyte` terminal rendering with a more complete terminal frontend.

### Possible Approaches

- WebView + xterm.js
- Qt + terminal widget
- Embedded Windows Terminal approach if possible
- Dedicated terminal emulator component

### Benefits

- Better `vim`, `nano`, `htop`, mouse support, colors, resizing, alternate screen behavior.
- More accurate terminal emulation.

### Notes

This is a larger architecture change and should be considered after the current Tk/CustomTkinter version is stable.

---

# Priority Recommendation

Recommended next development order:

1. v1.4.1 - Monitoring Alerts and Threshold Settings
2. v1.4.2 - Command Groups
3. v1.4.3 - Run Command on Multiple Panes
4. v1.4.4 - Auto Layout per Profile
5. v1.4.5 - Auto Reconnect
6. v1.4.6 - Export / Import
7. v1.5.0 - SSH Key Support
8. v1.6.0 - Packaged Installer
9. v2.0.0 - Full Terminal Engine Upgrade

---

# Backlog Ideas

- App settings page.
- Theme selector.
- Font size selector.
- Terminal font selector.
- Save window size and position.
- Save last opened tabs.
- Confirm before closing active sessions.
- Add keyboard shortcuts.
- Add command search.
- Add profile search.
- Add profile folders/groups.
- Add environment variables per profile.
- Add per-profile notes.
- Add documentation search improvements.
- Add update checker if published in Git.