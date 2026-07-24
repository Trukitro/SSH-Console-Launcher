# Architecture

Single-file Windows desktop app (`SSH_Console_Launcher.py`, ~5,300 lines) built with `customtkinter` (falls back to plain `tkinter`/`ttk` if `customtkinter` is missing). No web server, no external services — everything runs in one process plus one `plink.exe` child process per SSH session.

This document was informed by a generated knowledge graph of the codebase (see [CODE_GRAPH.md](CODE_GRAPH.md)) — 1,754 nodes / 4,144 edges across ~74 clustered communities, mostly one cluster per class per historical file version.

## Module map

All classes and top-level helpers live in `SSH_Console_Launcher.py`:

| Component | Lines (approx.) | Responsibility |
|---|---|---|
| `app_base_dir()`, `pyinstaller_resource_dir()`, `find_document_path()`, `load_document_text()` | 289-370 | Locate the script/exe folder and resolve bundled or external Markdown docs (with embedded-string fallback) |
| `SSHProfile`, `QuickCommand` | 371-383 | Plain dataclasses for a saved connection and a saved quick command |
| `ProfileStore` | 384-406 | Load/save `profiles.json` |
| `CommandStore` | 407-449 | Load/save `commands.json`, seeded with default admin commands |
| `PasswordStore` | 450-482 | Wraps the `keyring` package (Windows Credential Manager) — passwords never touch the JSON files |
| `ask_text()` | 483-563 | Modal dialog helper used for password prompts and other single-value inputs |
| `MarkdownDocumentWindow` | 564-832 | In-app Markdown viewer/search for README / VERSION_HISTORY / FEATURES_PLAN |
| `MonitoringDashboardWindow` | 833-1305 | Web2py/uWSGI/Nginx health dashboard — runs non-interactive SSH commands and renders parsed results as cards |
| `EmbeddedTerminal` | 1306-2056 | One embedded SSH console: spawns `plink.exe` via `pywinpty`, reads/parses output with `pyte`, renders ANSI into a `tk.Text` widget |
| `ConsoleTab` | 2057-2393 | One notebook tab; owns 1-4 `EmbeddedTerminal` panes and their grid/split layout |
| `EmbeddedSSHLauncher` | 2394-end | The main window: sidebar, toolbar, profile form, quick commands, tab/notebook management, top-level wiring |

## Data flow

```
EmbeddedSSHLauncher (main window)
  |-- ProfileStore  <-->  %APPDATA%\EmbeddedSSHLauncher\profiles.json
  |-- CommandStore  <-->  %APPDATA%\EmbeddedSSHLauncher\commands.json
  |-- PasswordStore <-->  Windows Credential Manager (via keyring)
  |
  |-- ConsoleTab (one per notebook tab)
  |     |-- EmbeddedTerminal (1-4 panes, grid/split layout)
  |           |-- plink.exe child process (pywinpty)
  |           |-- pyte screen buffer -> ANSI-tagged tk.Text rendering
  |
  |-- MonitoringDashboardWindow
  |     |-- non-interactive `plink.exe ... command` runs (subprocess, not pywinpty)
  |     |-- parses stdout into risk/health cards
  |
  |-- MarkdownDocumentWindow
        |-- find_document_path() -> README.md / VERSION_HISTORY.md / FEATURES_PLAN.md
```

## Threading model

Tkinter is single-threaded, so every background operation hands results back to the main thread via `self.after(...)`:

- **Interactive terminals** (`EmbeddedTerminal`): a daemon `threading.Thread` (`read_loop`) continuously reads from the `pywinpty` pseudo-console and pushes chunks onto a `queue.Queue`. A `self.after(35, self.flush_output)` poll loop drains the queue and feeds it through `pyte` into the `tk.Text` widget roughly every 35ms.
- **Connection status**: polled independently via `self.after(2000, self.check_connection_status)`.
- **Monitoring dashboard health checks** (`run_remote_monitoring_command`): a one-shot daemon thread runs `subprocess.run([plink.exe, ...])` with a 35s timeout, then calls back into the UI thread with `self.after(0, lambda: callback(...))`. This is a *non-interactive* SSH invocation (single command, captured stdout/stderr), separate from the interactive `pywinpty` sessions used for terminals.
- **Auto-refresh**: the dashboard reschedules itself with `self.after(self.refresh_seconds.get() * 1000, self.auto_refresh_tick)` when auto-refresh is enabled.

## External dependencies

- `plink.exe` (PuTTY) — does the actual SSH connection/auth (`-pw` for password auto-login); must sit beside the script/exe or be on `PATH`.
- `pywinpty` — Windows ConPTY wrapper used to run `plink.exe` as an interactive pseudo-terminal for `EmbeddedTerminal`.
- `pyte` — headless terminal emulator; turns the raw ANSI byte stream from `plink.exe` into a structured screen buffer (colors, cursor, alternate screen) that gets rendered into `tk.Text`.
- `keyring` — OS credential storage backend for saved passwords.
- `customtkinter` — modern theming on top of `tkinter`; the app degrades to plain `tkinter`/`ttk` if it isn't installed.

## Known architectural limitation

Terminal rendering is `tk.Text` + `pyte`, not a true terminal emulator (no native mouse reporting, imperfect alternate-screen apps). See [../README.md](../README.md#known-limitations) and `FEATURES_PLAN.md` (`v2.0.0`) for the planned xterm.js/WebView migration path.
