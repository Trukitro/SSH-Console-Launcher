# Changelog

## 2.1.0

- New: Event Log panel (replaces the old raw Debug Console) - a structured, readable history of what the app has done: connections created/opened/closed/reconnected, the app starting up and finishing loading, the window closing, and any real errors. Entries are shown as bubbles, filterable by level (all/error/warning/info), one log file per day so past days stay available (defaults to today).
- New: "What's changed" panel in the sidebar, showing this changelog from inside the app.
- Fix (root cause of the slow/stuck startup): pywebview scans every public attribute of the `Api` object looking for methods to expose, and the live window was stored as `Api.window` - so it recursed into the whole native WebView2/.NET object graph, throwing hundreds of COM errors (and a self-referential accessibility tree that hit Python's recursion limit) before the app could finish loading. Renamed to `Api._window` so pywebview skips it. Startup now completes in about 4-5 seconds with a clean log.
- Fix: a regression from the previous round - the app could get stuck on "Loading..." if the startup-ready fallback timer fired before the pywebview bridge genuinely existed. Replaced the blind timer with a real readiness poll.
- Fix: the window-closing hook returned a dict, which pywebview rejects (`unhashable type`); it now returns nothing.
- Fix: the orphaned-WebView2-process cleanup on startup could kill an already-open instance's window, since it matched on storage path alone - a live second launch shares that path. It now skips cleanup entirely whenever another instance is already running.
- Fix: the Event Log (previously Debug Console) no longer picks up pywebview's own internal WebView2/.NET error chatter - it's scoped to this app's own events only, so it can't be flooded by unrelated background noise.
- Fix: text can now be selected and copied anywhere in the app (`text_select=True`) - previously blocked window-wide by a pywebview default.
- New: the Event Log panel can be resized by dragging its top edge.
- New: the app version is now shown in the sidebar and bumped with every release.

## 2.0.4

- New: Debug Console panel (now superseded by the Event Log above) and a bounded in-memory log buffer.
- New: startup loading feedback ("Loading..." / "Restoring session N of M...") instead of a blank window.
- Fix: orphaned `msedgewebview2.exe` helper processes from previous launches are now cleaned up on startup, scoped strictly to this app's own storage path.

## 2.0.3

- Fix: a race condition in split-pane creation that could exceed the 4-pane cap and break the layout on fast double-clicks.
- Fix: unthemed scrollbars in multi-pane view.
- Improved: Copy/Paste buttons redesigned as a single grouped control per pane.

## 2.0.2

- Fix: copy/paste between the terminal and other apps, via the OS clipboard instead of the browser clipboard API (which hung indefinitely in this app's WebView2 context).

## 2.0.1

- Fix: SSH key generation, which used a paramiko API that doesn't exist for Ed25519 keys.
- New: existing saved connections can now be edited, not just deleted and recreated.

## 2.0.0

- Initial release: full rewrite from the WinPTY/plink.exe-based v1 to paramiko + pywebview + xterm.js. Profiles, connection wizard, tabs with split panes, quick commands, SFTP transfer, jump hosts, session restore, broadcast typing.
