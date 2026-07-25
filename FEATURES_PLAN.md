# FEATURES_PLAN.md

# SSH Console Launcher - Future Features Plan

**Current stable version:** v1.5.5  
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
- Windows installer wizard (Inno Setup, per-user install)
- Dark-themed dialogs throughout, resizable sidebar, application icon
- Recent connections list, per-profile environment tags (prod/staging/dev), SSH config import
- Jump host / bastion support, session restore on launch
- File transfer (pscp), per-tab broadcast typing
- Monitoring history/sparklines, multi-server monitor view
- Critical alerts (popup + beep), per-profile custom health-check command
- Clipboard auto-clear for copied passwords, connection audit log

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

## v1.6.0 - Packaged Windows App / Installer ✅ Implemented

### Goal

Make deployment easier.

### Implemented

- One-click build script (`build_exe.ps1`).
- `plink.exe` shipped as a sibling file (not `--add-binary` - see note below).
- README/VERSION_HISTORY/FEATURES_PLAN bundled into the `.exe`.
- App icon (window/taskbar).
- Inno Setup wizard (`installer.iss`): per-user install (no admin/UAC), Start Menu shortcut, optional desktop shortcut, uninstaller.

### Note

`find_plink()` only checks beside the running `.exe` or system `PATH` - it does not check PyInstaller's `_MEIPASS` temp dir. So `plink.exe` must ship as a loose file next to `SSH_Console_Launcher.exe` (which `installer.iss` does), not via `--add-binary`.

---

# Roadmap (prioritized 2026-07-24)

The sections below are the user's top picks from a features brainstorm, grouped into shippable releases. Numbering restarts clean at v1.5.0 (the old v1.4.2-v1.4.6 slot had duplicate/collided version numbers from earlier planning - abandoned in favor of this list).

## v1.5.0 - Profile & Credential Improvements ✅ Implemented

### Goal

Make managing many profiles faster and safer to navigate.

### Implemented

- **Import from `~/.ssh/config`**: parses `Host`/`HostName`/`User`/`Port` blocks and offers them as importable profiles via a checklist dialog; skips duplicates by name and wildcard `Host *` pattern blocks. `IdentityFile` is not imported - no SSH key auth support yet (still in Backlog Ideas).
- **Recent connections**: a "Recent" sidebar section above "Profiles" lists the last 8 opened profiles, most-recent-first, for one-click reopen.
- **Environment color-coding**: a per-profile Production/Staging/Development tag (red/amber/green) shown as a border on the profile button and on the terminal pane for that profile, updating live if the tag is edited while the pane is open.

---

## v1.5.1 - Core SSH: Bastion & Session Restore ✅ Implemented

### Goal

Support real-world multi-hop infrastructure and reduce "reopen everything by hand" friction.

### Implemented

- **Jump host / bastion support**: a "Jump Host" dropdown on the profile references another saved profile; the connection routes through it via `plink -proxycmd` (single hop). Blocked at save time if set to itself; blocked at connect time with a clear error if the referenced profile no longer exists.
- **Session restore on launch**: the app offers to reopen the last session's tabs/panes/profiles/layout on startup (prompt, not automatic - declining clears the offer).

---

## v1.5.2 - Core SSH: File Transfer & Multi-Pane Input ✅ Implemented

### Goal

Cover the two most common "I have to drop to a separate tool for this" gaps.

### Implemented

- **File Transfer**: an Upload/Download panel backed by `pscp.exe` for the focused profile's connection - file-picker dialogs (native open/save dialogs), not drag-and-drop (Tkinter has no built-in DnD, and this avoids a new dependency). Not routed through a profile's Jump Host in this release.
- **Broadcast typing**: a per-tab switch that sends keystrokes typed in the focused pane to all other panes in the current tab.

---

## v1.5.3 - Monitoring: History & Multi-Server View ✅ Implemented

### Goal

Turn the Monitoring Dashboard from a point-in-time snapshot into something you'd actually keep open.

### Implemented

- **Local metrics history**: each health-check run's key numbers (load, RAM%, disk%, connections) are persisted per profile to a small local store (last 30 samples) and rendered as sparklines on the load/RAM/disk/connections cards instead of just the latest value.
- **Multi-server grid**: a new "Monitor All Profiles" window runs the health check against every saved profile at once (concurrently) and shows one compact status card per server. Clicking a card opens the detailed dashboard for that profile.

---

## v1.5.4 - Monitoring: Alerts & Generalization ✅ Implemented

### Goal

Make the dashboard proactive instead of something you have to remember to check, and usable beyond the Web2py/uWSGI/Nginx stack it was built for.

### Implemented

- **Desktop/sound notification on critical**: a short-lived popup plus a system beep fire when the dashboard's Overall Web Host Risk crosses into critical, even if the dashboard window isn't focused. A "Notify on Critical" switch toggles this per session; it only re-fires on a fresh transition into critical, not on every refresh while it stays critical. (A real Windows Action Center toast would need a new third-party dependency or shelling out to PowerShell with interpolated text - a plain always-on-top popup avoids both.)
- **Generalized health-check**: a profile can specify its own custom health-check command in the Connection form instead of the hardcoded Web2py/uWSGI/Nginx `MONITORING_HEALTH_COMMAND`. A custom command only needs to echo the same `__KEY__=value` lines to populate the dashboard cards - anything else still appears in the raw output panel, so the dashboard works for Docker, Kubernetes, or any other stack. Leaving it blank keeps the built-in script (default, unchanged for every existing profile).

---

## v1.5.5 - Security Hardening ✅ Implemented

### Goal

Reduce the blast radius of a shared or unattended PC.

### Implemented

- **Clipboard auto-clear**: a "Copy Saved Password" button copies a profile's password to the clipboard and clears it again after 20 seconds, but only if the clipboard still holds that exact value (so it won't clobber something else copied since).
- **Connection audit log**: a local, append-only `(timestamp, profile name, host, user)` log for every connection opened, with a read-only viewer in the sidebar's Security section - useful on a shared machine to answer "who connected to what, and when."

---

## v1.6.1 - Distribution & Release Automation

### Goal

Make future releases (and getting the app onto other people's machines) less manual.

### Planned Features

- **Auto-update checker**: on startup (or on demand), check the GitHub Releases API for a newer tag than the running version and show a non-blocking notice with a link.
- **GitHub Actions CI**: a workflow that builds `dist\SSH_Console_Launcher.exe` and compiles `installer.iss` automatically on every version tag push, uploading the installer as a release asset - removes the need to build locally for every release.
- **winget/Chocolatey package**: publish a package manifest so `winget install` (or `choco install`) works, once there are a couple of stable tagged releases to point at.

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

Recommended next development order (v1.5.0, v1.5.1, v1.5.2, v1.5.3, v1.5.4, v1.5.5 implemented):

1. v1.6.1 - Distribution & Release Automation
2. v2.0.0 - Full Terminal Engine Upgrade

---

# Backlog Ideas

Lower priority than the roadmap above, or not yet scoped into a specific release:

- App settings page.
- Theme selector.
- Font size selector.
- Terminal font selector.
- Save window size and position.
- Confirm before closing active sessions.
- Add profile search.
- Add environment variables per profile.
- Add per-profile notes.
- Add documentation search improvements.
- Command palette (fuzzy launcher for profiles/commands/actions).
- Highlight ERROR/WARN lines automatically in terminal output.
- "Workspaces": named, reopenable sets of tabs + panes + commands.
- Notification when a long-running command finishes.
- Command groups (organize Quick Commands into categories).
- Run a command on multiple panes/tabs at once.
- Per-profile default layout + auto-run commands on open.
- Per-profile / global auto-reconnect on dropped connections.
- Export/import profiles (with or without passwords) and commands between PCs.
- SSH key authentication (`.ppk` / OpenSSH keys) as an alternative to saved passwords.
- Local session logging (save terminal output to disk).
- Search inside terminal output.
- Configurable Monitoring Dashboard warning/critical thresholds.