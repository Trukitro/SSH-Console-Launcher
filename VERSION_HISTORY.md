# SSH Console Launcher - Version History

This file tracks the project evolution from the first working concept through the current stable version.

---

## v1.0 - Initial Working GUI

### Goal

Create a small Windows GUI that can save SSH connection information and open SSH consoles quickly.

### Main Features

- Tkinter-based GUI.
- Save SSH profiles.
- Store host, user, port, and password.
- Open SSH sessions using `plink.exe`.
- Support opening multiple consoles.
- Basic tab and split-pane workflow.
- Automatic password login.
- Basic terminal output display.

### Notes

This version proved that the core workflow was possible:

```text
Save profile -> Select profile -> Open console quickly
```

---

## v1.1 - Tabs, Rename, Close, and Reconnect

### Added

- Rename current tab.
- Double-click tab to rename.
- `×` symbol in tab title.
- Click `×` to close a tab.
- Reconnect button per console.
- Reconnect selected console from the sidebar.
- Better session lifecycle handling.

### Fixed / Improved

- Added better control over individual SSH panes.
- Added reconnect behavior without needing to close and reopen the whole app.

---

## v1.2 - Quick Commands

### Added

- Quick Commands section.
- Add custom command buttons.
- Edit saved commands.
- Delete saved commands.
- Run command in focused terminal.
- General Clear Console command.
- Default commands:
  - `htop`
  - `cd /home/www-data/web2py/`
  - `tail -f web2py.log`
  - `sudo uwsgitop /tmp/stats.socket`
  - `clear`

### Files Added

```text
%APPDATA%\EmbeddedSSHLauncher\commands.json
```

### Purpose

Reduce repetitive typing for common admin commands.

---

## v1.3 - Modern UI Refresh

### Added

- CustomTkinter UI.
- Modern dark theme.
- Rounded buttons.
- Better sidebar layout.
- Top toolbar.
- Modern connection/profile form.
- Quick command buttons instead of only listbox style.
- Improved spacing.
- Status bar.
- Active terminal visual highlight.

### Dependencies Added

```powershell
pip install customtkinter
```

### Notes

This version modernized the appearance while keeping the working SSH and terminal backend.

---

## v1.3.1 - CustomTkinter Startup Fix

### Fixed

- `CTkScrollableFrame.grid_propagate(False)` startup crash.

### Cause

`CTkScrollableFrame.grid_propagate()` does not accept `False` like a normal Tkinter frame.

### Fix

Use:

```python
self.sidebar.configure(width=320)
```

instead of:

```python
self.sidebar.grid_propagate(False)
```

for CustomTkinter scrollable frames.

---

## v1.3.2 - Safer Tab Close Handling

### Fixed

- Accidental tab closing when clicking or selecting terminal text.
- Fake `×` tab close area was too aggressive.

### Added

- Press/release tracking for tab close.
- Smaller close zone.
- Close only if press and release both happen on the `×` area.
- Ignore drag/focus/select actions.

### Methods Added / Updated

- `get_tab_close_candidate`
- `on_notebook_button_press`
- `on_notebook_button_release`

---

## v1.3.3 - Tab Destruction and Terminal Color Support

### Fixed

- Closed tabs could remain visible or not disappear.
- Notebook tab was being forgotten but not fully destroyed.
- Old tab references could remain in memory.
- SSH processes could remain alive after closing a tab.

### Improved

- Fully destroy tab frame after closing.
- Close all SSH panes inside a tab before removing the tab.
- Clear active/focused terminal references when closing tabs.
- Delay close using `after(1, ...)` so notebook finishes processing click events first.

### Added

- ANSI terminal color support using `pyte` character attributes.
- Text tags for terminal foreground/background colors.
- Support for bold, underline, reverse video, and cursor highlighting.

---

## v1.3.4 - Connection Status Indicator

### Added

- Connection status indicator per terminal:
  - `● Connected`
  - `● Connecting`
  - `● Disconnected`
- Status color:
  - Green for connected
  - Orange for connecting
  - Red for disconnected

### Improved

- SSH sessions are checked periodically.
- Dropped connections are shown visually.
- Reconnect changes status back through connecting to connected.

### Purpose

Make it obvious when a terminal session needs reconnecting.

---

## v1.3.5 - High Contrast Terminal Colors

### Fixed

- Some `htop` and `uwsgitop` colors were too dark.
- Processor numbers, users, and dim values were hard to read.

### Improved

- Dark gray / black foreground values are remapped to readable light gray/white.
- Contrast protection checks foreground/background contrast.
- If contrast is too low, text is forced brighter.

### Purpose

Improve readability of colored terminal applications on black background.

---

## v1.3.6 - Focus, Close, and Quick Command Behavior Fixes

### Fixed

- Quick Commands were sometimes sent to the wrong terminal.
- Focus button did not correctly make a terminal active.
- Top toolbar buttons did not always act on the correct terminal.
- Close button inside a terminal closed the pane but did not destroy the tab when it was the last terminal.
- App could keep references to closed terminals.
- Active terminal highlighting could become stale.

### Improved

- Focus now updates:
  - Current terminal
  - Current tab
  - App-level focused terminal reference
  - Active visual state
- Quick commands now send to the actual focused terminal.
- Top toolbar actions now use the focused terminal or current tab correctly.
- Closing the last terminal in a tab closes and destroys the entire tab.
- Console cleanup is more complete.

### Current Status

This is the current stable version.

---

## v1.3.7 - Built-in Documentation Viewer

### Added

- Built-in documentation viewer inside the app.
- Documentation section in the sidebar.
- In-app Markdown rendering for README and VERSION_HISTORY files.
- Search box inside the documentation viewer.
- Reload documentation button.
- Open documentation folder button.
- PyInstaller-compatible document discovery.
- Embedded fallback Markdown content when external files are not found.

### Improved

- The app can now ship with its own documentation as part of the Windows `.exe` build.

---

## v1.3.8 - Smart Grid Split Layouts

### Fixed

- Open 3 Split no longer creates a long single-line layout.
- Open 4 Split no longer creates four narrow vertical panes.

### Added / Improved

- Open 3 Split now creates two panes on the top row and one full-width pane on the bottom row.
- Open 4 Split now creates a 2 x 2 square grid.
- Manual Vertical Split and Horizontal Split actions still work and can override the auto-grid layout.
- Pane cleanup was adjusted to work with the new grid layout system.

---

## v1.3.9 - Layout Manager

### Added

- Explicit Layout Manager buttons in the sidebar.
- 2-pane side-by-side layout.
- 2-pane stacked layout.
- 3-pane layout with two panes on top and one full-width pane on the bottom.
- 3-pane layout with one full-width pane on top and two panes on the bottom.
- 4-pane 2 x 2 grid layout.
- Auto Layout mode to choose the best layout based on pane count.

### Improved

- Existing panes can now be rearranged without reopening SSH sessions.
- Open 3 Split and Open 4 Split still default to the smart layouts introduced in v1.3.8.
- Manual layout controls are now clearer and more specific than the old Vertical/Horizontal split buttons.

---

## v1.4.0 - Web2py Monitoring Dashboard

### Added

- Monitoring Dashboard window.
- Server health check using non-interactive SSH command execution.
- CPU/load card.
- RAM card.
- Disk `/` card.
- Web2py process card.
- uWSGI process card.
- Recent error count card.
- Top CPU process card.
- Top memory process card.
- Auto-refresh controls.
- Monitoring sidebar section.
- Health check quick action.
- Recent errors quick action.
- Web2py/uWSGI process quick action.

### Notes

- The dashboard does not scrape data from `htop`; it runs direct non-interactive shell commands and parses the results.
- This makes the dashboard more useful for quick alerts and summaries.
- `htop` and `uwsgitop` remain available as Quick Commands for live terminal monitoring.

---


---

## v1.4.1 - Web Host Monitoring Dashboard Upgrade

### Added

- Overall Web Host Risk card.
- 502 / Gateway Risk card.
- Swap Usage card.
- Disk Web2py card.
- Web Connections card.
- Active Users / IPs card.
- Login/User Events card.
- uWSGI Workers card using `/tmp/stats.socket` when available.
- uWSGI Health card with exceptions, harakiri, respawns, RSS, and average response time when available.
- Nginx Status card.
- Web2py/uWSGI CPU card.
- Monitoring quick actions for 502/gateway checks, connection checks, and active user/client IP checks.

### Improved

- Dashboard now evaluates conditions that can lead to web host instability or 502 Bad Gateway responses.
- Monitoring health command now checks Linux load, memory, swap, disk, connections, Nginx logs, Web2py logs, and uWSGI worker saturation.
- Web2py logs are scanned for recent errors, tracebacks, exceptions, tickets, failed events, login/auth/user events, and client IP load.
- Nginx logs are scanned for 502/504, bad gateway, upstream timeout, upstream prematurely closed connection, refused connections, and no live upstreams.
- Worker saturation warnings are based on busy/total uWSGI worker ratio when stats socket data is available.

### Purpose

Help detect early warning signs before the web server reaches a state where users begin seeing `502 Bad Gateway`, Nginx upstream errors, overloaded workers, or resource saturation on Linux.

---

## v1.4.2 - Bug-Fix and Visual-Polish Pass

### Fixed

- Escape and Ctrl-chord keystrokes (readline shortcuts, vim insert-mode exit) were silently dropped in embedded terminals.
- A reconnect race condition could leave a stale reader thread writing garbled output or a false "disconnected" status right after a successful reconnect.
- The Monitoring Dashboard could be opened multiple times at once, and its auto-refresh timer kept firing after the window was closed.
- Two profiles with the same name silently shared (and could overwrite) one keyring password entry.
- Editing a profile's name/host/port didn't update already-open terminal panes for that profile.
- A persistently failing keyring backend could re-prompt for a password on every monitoring auto-refresh tick instead of warning once.
- Double-clicking a tab's close (`×`) zone could open the rename dialog on the wrong tab.
- ANSI background colors reused the brightened foreground palette, rendering "black" backgrounds as near-white.
- Low-contrast terminal text collapsed to flat white/gray instead of keeping its color-coded meaning.
- Most sidebar/toolbar buttons had no visible hover feedback due to a copy-pasted hover-color bug.

### Added

- Dark-themed replacement for all native `messagebox` popups (info/warning/error/confirm), matching the rest of the UI.
- Resizable sidebar with a draggable sash; the width is now remembered between sessions.
- Monitoring Dashboard's card grid now adapts its column count to the window width.
- Application icon and taskbar icon.
- Developer documentation set under `doc/` (architecture, configuration, build, and a generated codebase knowledge graph).
- Windows installer wizard (`installer.iss`, Inno Setup): per-user install, no admin/UAC, Start Menu shortcut, optional desktop shortcut, uninstaller. Fixed `build_exe.ps1` to stop bundling `plink.exe` via `--add-binary`, which was silently non-functional (see `doc/BUILD.md`); it now ships as a loose sibling file instead.

### Purpose

Stability and polish pass with no new user-facing features: fix the bugs and visual inconsistencies found during a full review of the codebase, without changing the app's workflow.

---

## v1.5.0 - Profile & Credential Improvements

### Added

- **Recent Connections**: a "Recent" sidebar section lists the last opened profiles, most-recent-first, for one-click reopen. Persisted to `%APPDATA%\EmbeddedSSHLauncher\recent.json`.
- **Environment Tags**: profiles can be tagged Production/Staging/Development from the Connection form. The tag renders as a colored border (red/amber/green) on the profile button and on any open terminal pane for that profile, and updates live if the tag is edited while the pane is open.
- **Import from SSH Config**: bulk-import `Host` entries from `~/.ssh/config` (host/user/port only - no SSH key auth yet, so `IdentityFile` is not imported). Wildcard `Host *` blocks are excluded; entries missing a `User` line are skipped since it can't be safely guessed. Duplicate names (case-insensitive) are skipped and counted.

### Purpose

Make managing many saved SSH profiles faster and safer to navigate day-to-day.

---

## v1.5.1 - Core SSH: Bastion & Session Restore

### Added

- **Jump Host / Bastion Support**: a profile can be routed through another saved profile as a jump host, via `plink -proxycmd` (real, documented plink functionality - not a hack). The jump host's own saved password is resolved/prompted the same way as any profile's. Single-hop only; a profile can't be set to jump through itself (blocked at save time), and a missing/deleted jump-host profile blocks the connection with a clear error instead of silently connecting direct.
- **Session Restore**: on launch, if tabs were open when the app was last closed, you're asked whether to reopen them (profiles, panes, and layout). Declining clears the offer so it won't ask again until there's a new session to restore. Persisted to `%APPDATA%\EmbeddedSSHLauncher\session.json`.

### Purpose

Support real-world multi-hop infrastructure and reduce "reopen everything by hand" friction after restarting the app.

---

## v1.5.2 - Core SSH: File Transfer & Multi-Pane Input

### Added

- **File Transfer**: an Upload/Download panel for the focused connection, backed by `pscp.exe` (bundled alongside `plink.exe`). File-picker dialogs (native Windows open/save dialogs), not drag-and-drop - Tkinter has no built-in drag-and-drop support, and this avoids adding a new third-party dependency. Does not route through a profile's Jump Host in this release.
- **Broadcast Typing**: a per-tab "Broadcast Typing (this tab)" switch relays everything typed in the focused pane to every other pane in the same tab - useful for running one command across several identical servers at once. Each tab has its own independent on/off state.

### Purpose

Cover the two most common "I have to drop to a separate tool for this" gaps: moving a file, and typing the same thing into several servers at once.

---

## v1.5.3 - Monitoring: History & Multi-Server View

### Added

- **Local Metrics History & Sparklines**: each health-check run's load/RAM%/disk%/connections are saved locally per profile (last 30 samples, `%APPDATA%\EmbeddedSSHLauncher\monitoring_history.json`) and rendered as small trend sparklines on the corresponding dashboard cards, instead of showing only the latest value.
- **Multi-Server View**: a new "Monitor All Profiles" window runs the health check against every saved profile at once (concurrently, not queued) and shows one compact status card per server (OK/Warning/Critical, worst-of load/RAM/disk/connections). Clicking a card opens the full detail dashboard for that profile. The grid reflows its column count on resize, same as the main dashboard.

### Purpose

Turn the Monitoring Dashboard from a point-in-time snapshot into something worth keeping open: see trends over time on one server, or the health of the whole fleet at a glance.

---

## v1.5.4 - Monitoring: Alerts & Generalization

### Added

- **Critical Alerts**: when the dashboard's Overall Web Host Risk crosses into critical, a short-lived popup and a system beep fire even if the dashboard window isn't focused. A "Notify on Critical" switch on the dashboard toggles this per session (on by default); alerts only re-fire on a fresh transition into critical, not on every refresh while it stays critical.
- **Generalized Health Check**: a profile can now specify its own custom health-check command in the Connection form, replacing the hardcoded Web2py/uWSGI/Nginx script for that profile. A custom command only needs to echo the same `__KEY__=value` lines to populate the dashboard cards - anything else still appears in the raw output panel. Leaving it blank keeps the built-in check (default, unchanged for every existing profile).

### Purpose

Make the dashboard something you don't have to remember to check, and useful for stacks (Docker, Kubernetes, or anything else) beyond the Web2py/uWSGI/Nginx setup it was originally built for.

---

## v1.5.5 - Security Hardening

### Added

- **Clipboard Auto-Clear**: a "Copy Saved Password" button in the Connection form copies the selected profile's password to the clipboard, then clears it again after 20 seconds - but only if the clipboard still holds that exact value, so it won't clobber something else you copied in the meantime.
- **Connection Audit Log**: every connection opened is appended to a local, append-only log (timestamp, profile name, host, user) at `%APPDATA%\EmbeddedSSHLauncher\audit_log.jsonl`. A new "Connection Audit Log" viewer in the sidebar's Security section shows the most recent entries, newest first.

### Purpose

Reduce the blast radius of a shared or unattended PC: passwords don't linger on the clipboard indefinitely, and there's a local record to answer "who connected to what, and when."

---

# Current Stable Version

```text
v1.5.5
```

---

# Full Version Summary

| Version | Summary |
|---|---|
| v1.0 | Initial embedded SSH GUI with saved profiles and basic console opening |
| v1.1 | Tab rename, tab close, reconnect |
| v1.2 | Quick Commands |
| v1.3 | Modern CustomTkinter UI refresh |
| v1.3.1 | Fixed CustomTkinter scrollable sidebar crash |
| v1.3.2 | Safer tab close handling |
| v1.3.3 | Full tab destruction fix and ANSI color support |
| v1.3.4 | Connection status indicator |
| v1.3.5 | High-contrast terminal color fix |
| v1.3.6 | Focus, close, toolbar, and quick command behavior fixes |
| v1.3.7 | Built-in README and version history viewer |
| v1.3.8 | Smart grid split layouts for 3 and 4 panes |
| v1.3.9 | Layout Manager controls for 2, 3, and 4 pane layouts |
| v1.4.0 | Web2py Monitoring Dashboard |
| v1.4.1 | Web Host Monitoring Dashboard upgrade |
| v1.4.2 | Bug-fix and visual-polish pass (dialogs, terminal colors, reconnect race, app icon, installer) |
| v1.5.0 | Recent Connections, Environment Tags, Import from SSH Config |
| v1.5.1 | Jump Host / Bastion Support, Session Restore |
| v1.5.2 | File Transfer (pscp), Broadcast Typing |