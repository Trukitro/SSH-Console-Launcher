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
- Windows installer wizard (Inno Setup, per-user install)
- Dark-themed dialogs throughout, resizable sidebar, application icon

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

## v1.5.0 - Profile & Credential Improvements

### Goal

Make managing many profiles faster and safer to navigate.

### Planned Features

- **Import from `~/.ssh/config`**: parse `Host`/`HostName`/`User`/`Port`/`IdentityFile` blocks and offer them as importable profiles (preview + select which to import, skip duplicates by name).
- **Recent connections history**: a short "Recently opened" list (last N profiles opened, most-recent-first) above or alongside the saved profile list for one-click reopen.
- **Environment color-coding**: a per-profile color tag (e.g. prod=red, staging=yellow, dev=green) shown on the profile button and the terminal pane header/border, so it's visually obvious which environment a pane is connected to before running a command.

---

## v1.5.1 - Core SSH: Bastion & Session Restore

### Goal

Support real-world multi-hop infrastructure and reduce "reopen everything by hand" friction.

### Planned Features

- **Jump host / bastion support**: a "Jump host" field on the profile (or a separate jump-host profile reference) that runs the connection through `plink -J`-style double hop (plink itself doesn't support `-J`; implement via `-proxycmd "plink -batch -pw ... jumpuser@jumphost -nc %host:%port"` or an equivalent proxy-command chain).
- **Session restore on launch**: remember the last open tabs/panes/profiles (and layout) and offer to reopen them on next start (prompt, don't auto-reconnect silently - passwords may need re-entry).

---

## v1.5.2 - Core SSH: File Transfer & Multi-Pane Input

### Goal

Cover the two most common "I have to drop to a separate tool for this" gaps.

### Planned Features

- **SFTP panel**: a simple file browser backed by `pscp`/`psftp` for drag-and-drop upload/download against the focused profile's connection - not a full dual-pane file manager, just enough to move a file without leaving the app.
- **Broadcast typing**: a toggle that sends keystrokes typed in the focused pane to all panes in the current tab (or a selected subset) simultaneously - useful for running the same interactive command across several identical servers.

---

## v1.5.3 - Monitoring: History & Multi-Server View

### Goal

Turn the Monitoring Dashboard from a point-in-time snapshot into something you'd actually keep open.

### Planned Features

- **Local metrics history**: persist each health-check run's key numbers (load, RAM%, disk%, connections) to a small local store and render sparklines on the relevant cards instead of just the latest value.
- **Multi-server grid**: a mode that runs the health check against several saved profiles at once and shows one compact card per server, instead of only the currently-focused profile.

---

## v1.5.4 - Monitoring: Alerts & Generalization

### Goal

Make the dashboard proactive instead of something you have to remember to check, and usable beyond the Web2py/uWSGI/Nginx stack it was built for.

### Planned Features

- **Desktop/sound notification on critical**: fire a Windows toast notification (and/or a sound) when the Overall Web Host Risk (or any card) crosses into critical, even if the dashboard window isn't focused.
- **Generalized health-check**: let a profile specify its own health-check script/command instead of the hardcoded Web2py/uWSGI/Nginx `MONITORING_HEALTH_COMMAND`, so the dashboard is useful for Docker, Kubernetes, or any other stack. Keep the current script as the default for backward compatibility.

---

## v1.5.5 - Security Hardening

### Goal

Reduce the blast radius of a shared or unattended PC.

### Planned Features

- **Clipboard auto-clear**: after a password is copied/pasted through the app's own dialogs, clear the clipboard after a short delay (only if it still contains that same value, to avoid clobbering something else the user copied since).
- **Connection audit log**: a local, append-only log of `(timestamp, profile name, host, user)` for every connection opened - useful on a shared machine to answer "who connected to what, and when."

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

Recommended next development order:

1. v1.5.0 - Profile & Credential Improvements
2. v1.5.1 - Core SSH: Bastion & Session Restore
3. v1.5.2 - Core SSH: File Transfer & Multi-Pane Input
4. v1.5.3 - Monitoring: History & Multi-Server View
5. v1.5.4 - Monitoring: Alerts & Generalization
6. v1.5.5 - Security Hardening
7. v1.6.1 - Distribution & Release Automation
8. v2.0.0 - Full Terminal Engine Upgrade

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