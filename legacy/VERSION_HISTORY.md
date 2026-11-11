# Embedded SSH Console Launcher - Version History

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

## v1.5.6 - Window Title Fix and ConPTY Stability Attempt

### Fixed

- **Window title stuck on v1.5.2**: `APP_NAME` (used for the window title and every dialog title) was a hardcoded string that never got updated across the v1.5.3-v1.5.5 releases, so the app kept reporting itself as "v1.5.2" no matter which version was actually installed and running. It's now derived from a single `APP_VERSION` constant.
- **Reported `conhost.exe` crash during active SSH sessions**: a user reported the app crashing mid-session with a `plink.exe - Application Error (0xc0000142)` dialog. Investigation via the Windows Application event log showed the actual faulting process was `conhost.exe` (Windows's own console host, which ConPTY uses to host the interactive `plink.exe` session) crashing with a stack buffer overrun in `ucrtbase.dll` - not a corrupted `plink.exe` (hash and version were verified intact) and not something reproducible with a simple non-interactive spawn test. `pywinpty` (the ConPTY wrapper used for interactive terminals) was two patch versions behind (3.0.3 vs. the current 3.0.5) and has been upgraded as the most likely, lowest-risk mitigation. This could not be confirmed fixed without a live SSH session to reproduce against, so treat it as an attempted fix pending real-world confirmation.

### Purpose

Fix a visible, confusing bug (wrong version in the title) and attempt a fix for a reported crash affecting active terminal sessions.

---

## v1.5.7 - Debug Log Viewer & Connection Lifecycle Logging

### Added

- **Debug Log Viewer** (Tools sidebar section): a new live, filterable window over the app's internal logging - `stdout`/`stderr` (now redirected instead of going nowhere in the `--windowed` build), the SSH connection lifecycle, and otherwise-invisible Tkinter callback exceptions (Tkinter's default `report_callback_exception` just prints to a stderr that doesn't exist in the frozen `.exe`; it's now overridden to log the full traceback). Filter by severity (DEBUG/INFO/WARNING/ERROR), **Copy Logs**, **Clear Logs**, keeps the last 2,000 entries so history from before the window was opened isn't lost.
- **Connection lifecycle logging**: SSH session spawn (command logged with the password redacted), spawn failures, reader-thread disconnects, session teardown (including if the reader thread doesn't exit within its 0.3s join timeout - previously silent), jump-host resolution failures, and monitoring/health-check command failures/timeouts are now all logged - additive visibility only, no changes to the existing connection-handling logic itself.

### Fixed

- `APP_VERSION` itself was still stuck at "1.5.5" in the v1.5.6 release despite the window-title *mechanism* being fixed - the constant just never got bumped in that release. Corrected, and the title now genuinely reflects the running version.

### Purpose

Give the app real diagnostic visibility for the first time - previously there was no `logging` usage anywhere and no way to see an exception that happened outside a visible dialog. Directly useful for confirming (or further diagnosing) the v1.5.6 `conhost.exe` crash investigation if it recurs.

### Notes

This is the first iteration of a larger UI modernization effort (IDE-style layout, collapsible/tabbed sidebar) - deliberately scoped to just the logging/debug-visibility piece for now, kept separate from the higher-risk sidebar/visual overhaul so it could ship without touching the rest of a live, daily-used app.

---

## v1.5.8 - Crash Diagnostics & a ConPTY Crash Trigger Fix

### Fixed

- **Debug Log Viewer duplicated every entry on open**: the viewer seeded its history from `LOG_BUFFER` but never drained the still-backlogged `LOG_QUEUE`, so the first live-poll tick re-rendered everything already shown. `LOG_QUEUE` is now drained (discarded, since `LOG_BUFFER` already has that data) before history is loaded.
- **Possible ConPTY crash trigger removed**: `initialize_remote_terminal()` sent an explicit `stty rows/columns` resize command immediately before `clear` on every connect and reconnect. Research into the reported `conhost.exe`/`ucrtbase.dll` stack-buffer-overrun crash (v1.5.6) turned up a documented Windows/ConPTY bug with the same shape - a resize immediately adjacent to a scrollback-clearing `clear` (microsoft/terminal#14759). The `stty rows/columns` call was redundant anyway (`PtyProcess.spawn(dimensions=...)` already sets the size at pty creation, which plink's `-t` relays to the remote via SSH's pty-req), so it's removed rather than reordered.

### Added

- **Automatic crash-detail lookup**: when the app detects a session died unexpectedly (either the reader thread's read() failing, or the 2-second connection watchdog finding the underlying process no longer alive), it now automatically queries the Windows Application event log (`Get-WinEvent`, matching Event ID 1000 "Application Error" for `conhost.exe`/`plink.exe` in the last 20 seconds) from a background thread and logs the full crash record - faulting module, exception code, timestamp - directly into the Debug Log Viewer. No more manually digging through Event Viewer to see what actually crashed.

### Notes

**Honesty note**: the `conhost.exe` crash itself could not be reproduced locally despite real effort - a live `htop` session and five repeated attempts at the exact old resize-then-clear sequence, both run directly against a real saved profile/server, all completed cleanly with no crash. The `stty` removal is a well-reasoned mitigation backed by a documented, matching Windows bug report, not a confirmed fix - if the crash recurs on v1.5.8, the new automatic crash-detail lookup should make the next diagnosis pass much faster.

---

## v1.5.9 - Full IDE-Style Redesign & Crash Resilience

### Added

- **Activity Bar + dock panels**: the single long scrolling sidebar (10 stacked sections) is replaced with a VS Code-style icon rail (Connections, Layouts, Quick Commands, Monitoring, Debug Logs, Settings) - clicking an icon swaps in a focused dock panel instead of scrolling past everything else. The active dock and its width both persist across restarts.
- **Header bar**: shows the focused connection's name/host and a color-coded environment badge (Production/Staging/Development), plus a Broadcast Typing toggle promoted out of the sidebar (still mirrors the per-tab switch - both are bound to the same variable).
- **Footer status bar**: a live connection count (updates every second) and a one-click Debug Console toggle.
- **Redesigned tab strip**: a custom-built tab bar (`TabStrip`) replaces the native `ttk.Notebook`, which Windows' theme engine can't restyle beyond native chrome. Real close buttons per tab replace the old coordinate-heuristic "was this click on the × text" detection entirely - simpler and more reliable than what it replaced, not just a reskin. Every existing tab operation (create, close, rename, session restore) keeps working via a drop-in-compatible API, verified with a dedicated functional test exercising the full tab lifecycle before shipping.
- **Terminal pane headers**: each pane shows session elapsed time and a new Duplicate action (opens the same profile in a new pane in the same tab) alongside Focus/Clear/Reconnect/Close.
- **Crashed session state**: a pane that dies from a detected native crash (see v1.5.8's Windows event log lookup) now shows a distinct "⚠ Crashed" indicator instead of the same "Disconnected" state a normal drop uses, making it obvious a reconnect (not just a dropped connection) is needed.
- **Searchable profile cards**: a search box above the Profiles list filters by name or host as you type.
- **Categorized Quick Command chips**: commands are grouped by category (a new optional field) and rendered as a wrapping chip grid instead of a vertical button stack.
- **Layout selector diagrams**: each Layout/Session button now shows a small canvas diagram of its pane arrangement alongside the label.
- **Monitoring progress bars**: the Load/RAM/Disk/Connections cards gained a color-coded progress bar under their sparkline.
- **Dockable Debug Console**: the Debug Log Viewer is now a bottom panel toggled open/closed (Activity Bar icon or footer button) instead of a separate window - keeps polling continuously, so nothing logged while it's closed is lost.
- **Startup/mainloop crash catch-all**: any exception escaping construction or the Tk mainloop itself (beyond what `report_callback_exception` already covers) is now logged and shown as one dark-themed dialog instead of a bare Windows crash dialog with no log trail.

### Design tokens

New base palette (`BG #1E1E2E`, `PANEL`/`CARD #25263A`, `ACCENT #4E87F6`) and dedicated environment colors (Production `#FF5252`, Staging `#FFB300`, Dev `#4CAF50`), replacing the previous slate-blue theme throughout every window in the app.

### Notes

This is a single, all-in-one redesign release (not phased) - the full scope was reviewed and approved as one unit rather than split across versions. The tab strip replacement was the highest-risk single change (touches tab creation/close/rename/session-restore); it was verified with an actual functional test script driving the real tab lifecycle end-to-end, in addition to the usual syntax-check + smoke-test + code-review pattern used elsewhere in this app, since there's no visual GUI testing tool available for this native Tkinter app.

---

## v1.5.10 - Profile Editing Clarity, Password Visibility, and a Real-World Crash Data Point

### Fixed

- **Wrong profile highlighted while a search filter was active**: `refresh_profiles()`'s button tracking was a plain list built in filtered display order, but `select_profile()`'s highlight loop compared that position against the real profile index - correct with no filter, wrong as soon as `profile_search_var` hid any profile. Button tracking is now a dict keyed by the real profile index; verified with a dedicated functional test (10 checks, including the filtered-selection case) rather than just code review.

### Added

- **Editing/new-profile indicator**: the Connection form now shows "Editing: <name>" or "New Profile" so it's obvious which mode you're in.
- **Password-saved indicator**: "No password saved" / "🔒 Password saved" shows whether a profile has a stored password, without ever displaying the value.
- **Show/Hide password toggle**: reveals the password on-screen when needed. The value only ever lives in the form's local `StringVar` for that session - it's never written to `profiles.json`, a log, or any file this app writes to disk.
- **Per-card delete button**: each profile card now has its own 🗑 button - no need to select a profile first to find Delete at the bottom of the form.

### Crash investigation update

A user hit the `conhost.exe`/`ucrtbase.dll` crash (0xc0000409) again on v1.5.9, 100% of the time across several real connection attempts through the actual installed app - despite v1.5.8's mitigation. Follow-up investigation using the real installed profile/password (never committed anywhere) found:

- One direct reproduction: spawning the real installed `plink.exe` (path: `...\AppData\Local\Programs\SSH Console Launcher\plink.exe` - note the space in "SSH Console Launcher") via `pywinpty` crashed `conhost.exe` on the first attempt, confirmed against a fresh Windows Application event log entry at the exact same timestamp.
- Two follow-up tests designed to isolate the cause did **not** reproduce it: (a) the same `plink.exe` copied to a different, unrelated folder that also has a space in its name ran cleanly for 6+ seconds, ruling out "any space in the path" as a sufficient trigger on its own; (b) a Tk mainloop simulating the app's actual timer cadence (250ms Debug Console poll, 1s connection-count/profile-display poll, 2s connection watchdog, 35ms terminal flush) spawning the same real `plink.exe` also ran cleanly for 24+ seconds, ruling out this session's added polling load as a sufficient trigger on its own.
- Net result: the crash is real and was reproduced once, but the root cause is still not isolated - it reproduces 100% of the time when driven through the actual frozen `.exe` with a real rendered GUI, but not reliably through any headless Python reproduction attempted so far (9 attempts total across v1.5.8 and v1.5.9 investigation, 1 hit). The one untested variable is the frozen PyInstaller `.exe` itself (all reproduction attempts used `python.exe` directly) - no way to drive that interactively without a GUI automation tool.

### Notes

No further crash-detection or spawn-path changes in this release - see the investigation update above for what was tried. If the crash recurs, the Debug Console (v1.5.8) will show the same crash-detail lookup as before.

---

## v1.5.11 - conhost.exe Crash Fix: Switch to the Legacy WinPTY Backend

### Fixed

- **The `conhost.exe`/`ucrtbase.dll` crash (0xc0000409, stack buffer overrun) is now avoided by construction.** The decisive lead came from the user: a plain `ssh user@host` in `cmd.exe` (Windows' built-in OpenSSH client) never crashed, while this app's PTY session crashed reliably. The difference is `pywinpty`'s default backend - **ConPTY**, Windows' native pseudo-console, hosted by a spawned `conhost.exe` process (`CreatePseudoConsole`). `pywinpty` also ships a **legacy WinPTY** backend (`winpty-agent.exe` / `winpty.dll`, both already bundled inside the installed `winpty` package) that never touches `conhost.exe` at all. `EmbeddedTerminal.start_process()`'s `PtyProcess.spawn(...)` call now passes `backend=Backend.WinPTY` (falling back to the previous default automatically if the import fails on some other Python/pywinpty install), which routes every SSH session around the exact code path that was crashing.
- Verified against the real, previously-100%-reproducing profile and server (not a synthetic reproduction): three consecutive real connections through the actual `EmbeddedTerminal.start_process()` code path (not a standalone script) ran with **zero matching Windows Application-log crash events**, versus a 100% crash rate on the same profile/server under the default ConPTY backend across every prior test in v1.5.8-v1.5.10. One of the three runs ended in a plain disconnect partway through (`crashed=False`, no matching event) - a normal session end, not the crash signature this fix targets.

### Why this is the fix, not another mitigation

Every previous attempt (v1.5.8's `stty rows/columns` removal, various isolation tests in v1.5.10) tried to avoid *triggering* undefined behavior inside Microsoft's ConPTY implementation without being able to fully explain it. Switching backends removes `conhost.exe` from the process tree entirely for this app's SSH sessions, so the specific fault (`Faulting application: conhost.exe`, `Faulting module: ucrtbase.dll`) has no `conhost.exe` process left to occur in.

### Notes

The legacy WinPTY backend is older and less actively maintained upstream than ConPTY, but is a well-established fallback (it's what `pywinpty` used exclusively before ConPTY existed). No behavioral regressions found in testing (ANSI colors, resizing, real command execution, and the full SSH login banner all worked identically to before). If anything backend-specific turns up later (e.g. resize edge cases), it can be revisited.

---

# Current Stable Version

```text
v1.5.11
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