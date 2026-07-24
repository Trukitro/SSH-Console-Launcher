# Documentation Index

This folder holds developer-facing documentation for the SSH Console Launcher project. It is separate from the user-facing docs that ship inside the app itself.

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | How the app is put together: modules, classes, threading model, data flow |
| [CONFIGURATION.md](CONFIGURATION.md) | Where profiles, commands, and credentials are stored, and how |
| [BUILD.md](BUILD.md) | Building a portable `.exe` with PyInstaller |
| [CODE_GRAPH.md](CODE_GRAPH.md) | The generated knowledge graph of the codebase and how to regenerate it |

## In-app / repo-root documentation

These files live at the project root (not in `doc/`) because the app's built-in Documentation Viewer looks for them beside the script or the packaged `.exe` (see `find_document_path()` in `SSH_Console_Launcher.py`). Moving them out of the root would break that feature.

| Document | Purpose |
|---|---|
| [README.md](../README.md) | User-facing overview, features, requirements, install/run instructions |
| [VERSION_HISTORY.md](../VERSION_HISTORY.md) | Full changelog from v1.0 to the current version |
| [FEATURES_PLAN.md](../FEATURES_PLAN.md) | Roadmap and planned features |
