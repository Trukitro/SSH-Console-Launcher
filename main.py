"""SSH Console Launcher v2 - entry point.

The Api class is the entire bridge between the UI (web/app.js, running
inside the pywebview-hosted browser) and the backend (ssh_backend.py,
config_store.py). Every SSH session is keyed by a session_id so multiple
tabs can be open - and connecting at all - at once.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path

import webview
import win32clipboard

import config_store
import event_log
from config_store import Command, Profile
from ssh_backend import (
    ConnectParams,
    SSHSession,
    download_file as ssh_download_file,
    generate_ed25519_keypair,
    install_public_key,
    run_one_shot_command,
    upload_file as ssh_upload_file,
)

config_store.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

APP_VERSION = "2.1.0"

# Raw technical log file, for developer troubleshooting - always on, never
# shown to the user. The user-facing Event Log (see event_log.py and the
# Api.list_events/log_event methods below) is a separate, structured thing:
# it used to be fed by a handler on the ROOT logger, which meant it silently
# picked up pywebview's own internal .NET/WebView2 error chatter too (one
# real message measured at 6001 characters, from a recursive accessibility
# property lookup) - that's not something a user opening a "what did I just
# do" panel needs to see, and rendering it was slow enough to help stall the
# UI thread. LOGGER only feeds the technical file/console now; anything the
# user should see goes through event_log.log_event() explicitly at the
# point it happens, or via the WARNING+ safety-net handler below (which is
# attached to LOGGER, not root, so it only ever sees this app's own calls).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(config_store.CONFIG_DIR / "launcher_debug.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
LOGGER = logging.getLogger("ssh_launcher_v2")


class _EventLogSafetyNetHandler(logging.Handler):
    """Catches any LOGGER.warning/error call that wasn't already reported
    through an explicit event_log.log_event() call, so a real problem can
    never silently miss the user-facing Event Log. Full, untruncated detail
    always - unlike the noisy pywebview chatter this replaced, anything
    that reaches here is one of our own app's warnings/errors."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            return
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        level = "error" if record.levelno >= logging.ERROR else "warning"
        event_log.log_event("log", message, level=level)


_safety_net = _EventLogSafetyNetHandler()
_safety_net.setLevel(logging.WARNING)
LOGGER.addHandler(_safety_net)

_BASE_DIR = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
WEB_DIR = _BASE_DIR / "web"


class _Tab:
    __slots__ = ("session", "profile_id")

    def __init__(self, session: SSHSession, profile_id: str) -> None:
        self.session = session
        self.profile_id = profile_id


class Api:
    def __init__(self) -> None:
        # Leading underscore is load-bearing: pywebview's own inject_pywebview()
        # walks every non-underscore, non-callable attribute of this object
        # via dir()/getattr() looking for more exposable API methods (see
        # webview/util.py get_functions()). A plain `self.window` here made it
        # recurse into the entire native WebView2/.NET COM object graph -
        # hundreds of properties, including an accessibility tree with a
        # self-referential .Empty chain that blew Python's recursion limit -
        # synchronously during pywebview's own startup, before pywebviewready
        # even fires. That's what the huge "Error while processing
        # window.native.AccessibilityObject..." log flood and the slow/stuck
        # "Loading..." were actually from. The underscore makes pywebview's
        # walker skip this attribute entirely (it explicitly does).
        self._window: webview.Window | None = None
        self.tabs: dict[str, _Tab] = {}

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    # --- profiles ---------------------------------------------------------

    def list_profiles(self) -> list[dict]:
        return [asdict(p) for p in config_store.load_profiles()]

    def get_profile(self, profile_id: str) -> dict | None:
        for p in config_store.load_profiles():
            if p.id == profile_id:
                return asdict(p)
        return None

    def save_profile(self, data: dict) -> dict:
        is_new = not data.get("id")
        try:
            profile_id = data.get("id") or str(uuid.uuid4())
            profile = Profile(
                id=profile_id,
                name=data["name"],
                host=data["host"],
                port=int(data.get("port") or 22),
                user=data["user"],
                auth_method=data.get("auth_method", "password"),
                key_path=data.get("key_path", ""),
                env_color=data.get("env_color", ""),
                jump_profile_id=data.get("jump_profile_id", ""),
            )
            config_store.upsert_profile(profile)

            password = data.get("password")
            if profile.auth_method == "password" and password:
                config_store.save_password(profile.id, password)

            event_log.log_event(
                "connection_created" if is_new else "connection_updated",
                f"{'Created' if is_new else 'Updated'} connection “{profile.name}”",
                {"name": profile.name, "host": profile.host, "user": profile.user,
                 "port": profile.port, "auth_method": profile.auth_method},
            )
            return {"ok": True, "id": profile.id}
        except Exception as exc:
            event_log.log_event(
                "connection_created" if is_new else "connection_updated",
                f"Failed to save connection: {exc}",
                {"data": {k: v for k, v in data.items() if k != "password"}},
                level="error",
            )
            return {"ok": False, "error": str(exc)}

    def delete_profile(self, profile_id: str) -> dict:
        LOGGER.info("delete_profile: %s", profile_id)
        config_store.delete_profile(profile_id)
        return {"ok": True}

    # --- quick commands -----------------------------------------------------

    def list_commands(self) -> list[dict]:
        return [asdict(c) for c in config_store.load_commands()]

    def save_command(self, data: dict) -> dict:
        try:
            command = Command(
                id=data.get("id") or str(uuid.uuid4()),
                name=data["name"],
                command=data["command"],
                category=data.get("category") or "General",
                description=data.get("description") or "",
                interactive=bool(data.get("interactive")),
            )
            config_store.upsert_command(command)
            LOGGER.info("save_command: '%s' (%s) [%s]", command.name, command.command, command.category)
            return {"ok": True, "id": command.id}
        except Exception as exc:
            LOGGER.error("save_command: %s", exc)
            return {"ok": False, "error": str(exc)}

    def delete_command(self, command_id: str) -> dict:
        LOGGER.info("delete_command: %s", command_id)
        config_store.delete_command(command_id)
        return {"ok": True}

    # --- SSH key onboarding -------------------------------------------------

    def generate_key(self, profile_id: str) -> dict:
        try:
            key_path = config_store.key_path_for(profile_id)
            public_line = generate_ed25519_keypair(key_path)
            return {"ok": True, "key_path": str(key_path), "public_key": public_line}
        except Exception as exc:
            LOGGER.error("generate_key(%s): %s", profile_id, exc)
            return {"ok": False, "error": str(exc)}

    def install_key(self, host: str, port: int, user: str, password: str, public_key: str) -> dict:
        if not public_key:
            return {"ok": False, "error": "No key was generated yet - go back and try again."}
        try:
            params = ConnectParams(host=host, port=int(port), username=user, password=password)
            install_public_key(params, public_key)
            return {"ok": True}
        except Exception as exc:
            LOGGER.error("install_key(%s@%s): %s", user, host, exc)
            return {"ok": False, "error": str(exc)}

    # --- terminal sessions --------------------------------------------------

    def _params_for_profile(self, profile: Profile) -> ConnectParams:
        if profile.auth_method == "key":
            params = ConnectParams(host=profile.host, port=profile.port, username=profile.user, key_path=profile.key_path)
        else:
            params = ConnectParams(
                host=profile.host, port=profile.port, username=profile.user,
                password=config_store.get_password(profile.id) or "",
            )

        if profile.jump_profile_id:
            jump_dict = self.get_profile(profile.jump_profile_id)
            if jump_dict is not None:
                params.jump = self._params_for_profile(Profile(**jump_dict))

        return params

    def open_session(self, profile_id: str, cols: int = 120, rows: int = 32) -> dict:
        profile_dict = self.get_profile(profile_id)
        if profile_dict is None:
            return {"ok": False, "error": "Profile not found"}
        profile = Profile(**profile_dict)

        session_id = str(uuid.uuid4())
        params = self._params_for_profile(profile)

        self._connect_async(session_id, profile.id, profile.name, params, cols, rows, "connection_open")
        config_store.record_audit(profile)
        return {"ok": True, "session_id": session_id}

    def reconnect_session(self, session_id: str, cols: int = 120, rows: int = 32) -> dict:
        tab = self.tabs.get(session_id)
        if tab is None:
            return {"ok": False, "error": "Unknown session"}
        try:
            tab.session.close()
        except Exception:
            pass

        profile_dict = self.get_profile(tab.profile_id)
        if profile_dict is None:
            return {"ok": False, "error": "Profile no longer exists"}
        profile = Profile(**profile_dict)

        self._connect_async(
            session_id, profile.id, profile.name, self._params_for_profile(profile), cols, rows, "connection_reconnect",
        )
        return {"ok": True}

    def get_last_session(self) -> list[dict]:
        """Profiles that had an open session when the app last closed, for
        restoring on startup. Silently drops ids for profiles since deleted."""
        ids = config_store.load_session_profile_ids()
        profiles = {p.id: p for p in config_store.load_profiles()}
        return [asdict(profiles[i]) for i in ids if i in profiles]

    def _save_open_profiles(self) -> None:
        seen: list[str] = []
        for tab in self.tabs.values():
            if tab.profile_id not in seen:
                seen.append(tab.profile_id)
        config_store.save_session_profile_ids(seen)

    def _connect_async(
        self, session_id: str, profile_id: str, profile_name: str,
        params: ConnectParams, cols: int, rows: int, event_kind: str,
    ) -> None:
        self._push_status(session_id, "connecting", "Connecting")

        def worker() -> None:
            session = SSHSession()
            try:
                session.connect(
                    params,
                    on_data=lambda text, sid=session_id: self._on_data(sid, text),
                    on_close=lambda reason, sid=session_id: self._on_close(sid, reason),
                    known_hosts_file=config_store.KNOWN_HOSTS_FILE,
                    cols=cols,
                    rows=rows,
                )
            except Exception as exc:
                event_log.log_event(
                    event_kind, f"Failed to connect to “{profile_name}”: {exc}",
                    {"profile": profile_name, "host": params.host, "user": params.username}, level="error",
                )
                self._push_status(session_id, "disconnected", str(exc))
                return

            self.tabs[session_id] = _Tab(session, profile_id)
            event_log.log_event(
                event_kind, f"Opened connection to “{profile_name}”",
                {"profile": profile_name, "host": params.host, "user": params.username, "port": params.port},
            )
            self._push_status(session_id, "connected", "Connected")
            self._save_open_profiles()

        threading.Thread(target=worker, daemon=True).start()

    def send_input(self, session_id: str, data: str) -> None:
        tab = self.tabs.get(session_id)
        if tab is None:
            return
        try:
            tab.session.write(data)
        except Exception as exc:
            LOGGER.warning("send_input(%s): %s", session_id, exc)

    def resize(self, session_id: str, cols: int, rows: int) -> None:
        tab = self.tabs.get(session_id)
        if tab is not None:
            tab.session.resize(int(cols), int(rows))

    def close_session(self, session_id: str) -> None:
        tab = self.tabs.pop(session_id, None)
        if tab is not None:
            tab.session.close()
            profile_dict = self.get_profile(tab.profile_id)
            name = profile_dict["name"] if profile_dict else tab.profile_id
            event_log.log_event("connection_close", f"Closed connection to “{name}”", {"profile": name})
            self._save_open_profiles()

    # --- event log ---------------------------------------------------------

    def list_events(self, date: str | None = None) -> list[dict]:
        return event_log.list_events(date)

    def list_event_dates(self) -> list[str]:
        return event_log.list_event_dates()

    def log_event(self, kind: str, message: str, detail: dict | None = None, level: str = "info") -> None:
        event_log.log_event(kind, message, detail, level)

    def get_app_version(self) -> str:
        return APP_VERSION

    def get_changelog(self) -> str:
        try:
            return (_BASE_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
        except Exception as exc:
            LOGGER.warning("get_changelog: %s", exc)
            return "Changelog not available."

    # --- clipboard -----------------------------------------------------------
    # navigator.clipboard.readText() hangs forever in this app: it needs a
    # permission prompt that WebView2 never actually surfaces without a host
    # app hooking CoreWebView2's PermissionRequested event, which pywebview
    # doesn't expose. Going through the OS clipboard directly from Python
    # sidesteps the browser's permission model entirely - win32clipboard has
    # no thread-affinity requirement (see below for why that matters here).

    def get_clipboard(self) -> str:
        # Not tkinter: pywebview dispatches Api calls on a worker thread (not
        # necessarily the same one each time), and Tcl/Tk's clipboard access
        # has real thread-affinity requirements that broke silently under
        # that dispatch - confirmed by testing the actual button code path,
        # not just a direct call. win32clipboard's OpenClipboard/CloseClipboard
        # pattern has no such affinity requirement.
        try:
            win32clipboard.OpenClipboard()
            try:
                return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
        except Exception as exc:
            LOGGER.warning("get_clipboard: %s", exc)
            return ""

    def set_clipboard(self, text: str) -> None:
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()
        except Exception as exc:
            LOGGER.warning("set_clipboard: %s", exc)

    def run_command(self, profile_id: str, command: str) -> dict:
        """One-shot non-interactive command - no tab, no pty (health checks etc.)."""
        profile_dict = self.get_profile(profile_id)
        if profile_dict is None:
            return {"ok": False, "error": "Profile not found"}
        profile = Profile(**profile_dict)

        try:
            success, out, err = run_one_shot_command(
                self._params_for_profile(profile), command, config_store.KNOWN_HOSTS_FILE,
            )
            return {"ok": success, "output": out, "error": err}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # --- SFTP file transfer --------------------------------------------------

    def pick_upload_file(self) -> str | None:
        if self._window is None:
            return None
        result = self._window.create_file_dialog(webview.FileDialog.OPEN)
        return result[0] if result else None

    def pick_download_target(self, suggested_name: str) -> str | None:
        if self._window is None:
            return None
        result = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=suggested_name)
        return result[0] if result else None

    def upload_file(self, profile_id: str, local_path: str, remote_path: str) -> dict:
        profile_dict = self.get_profile(profile_id)
        if profile_dict is None:
            return {"ok": False, "error": "Profile not found"}
        profile = Profile(**profile_dict)

        try:
            ssh_upload_file(self._params_for_profile(profile), local_path, remote_path, config_store.KNOWN_HOSTS_FILE)
            return {"ok": True}
        except Exception as exc:
            LOGGER.error("upload_file(%s -> %s): %s", local_path, remote_path, exc)
            return {"ok": False, "error": str(exc)}

    def download_file(self, profile_id: str, remote_path: str, local_path: str) -> dict:
        profile_dict = self.get_profile(profile_id)
        if profile_dict is None:
            return {"ok": False, "error": "Profile not found"}
        profile = Profile(**profile_dict)

        try:
            ssh_download_file(self._params_for_profile(profile), remote_path, local_path, config_store.KNOWN_HOSTS_FILE)
            return {"ok": True}
        except Exception as exc:
            LOGGER.error("download_file(%s -> %s): %s", remote_path, local_path, exc)
            return {"ok": False, "error": str(exc)}

    # --- push helpers (Python -> JS) ---------------------------------------

    def _on_data(self, session_id: str, text: str) -> None:
        if self._window is None:
            return
        self._window.evaluate_js(f"window.termWrite({json.dumps(session_id)}, {json.dumps(text)})")

    def _on_close(self, session_id: str, reason: str) -> None:
        LOGGER.info("session %s closed: %s", session_id, reason)
        self._push_status(session_id, "disconnected", reason)

    def _push_status(self, session_id: str, state: str, message: str) -> None:
        if self._window is None:
            return
        self._window.evaluate_js(
            f"window.onSessionStatus({json.dumps(session_id)}, {json.dumps(state)}, {json.dumps(message)})"
        )


WEBVIEW_STORAGE_PATH = config_store.CONFIG_DIR / "webview_cache"


def _cleanup_orphaned_webview_processes() -> None:
    """pywebview's edgechromium backend never disposes the WebView2
    controller/environment on window close (confirmed: only clear_user_data()
    calls .Dispose(), and that's not on the close path) - even a clean
    window.destroy() leaves msedgewebview2.exe helper processes running with
    no parent. Across repeated launches these accumulate and start fighting
    each other for the same user-data-folder lock, which is what a "blank,
    then Not Responding, then eventually loads" startup looks like from the
    outside. Point WebView2 at our own storage_path (instead of the pywebview
    default, which every pywebview app on the machine shares) so we can
    identify - via each process's own command line - exactly which stray
    msedgewebview2.exe processes are ours.

    Real bug this fixes: the storage path alone can't tell a truly orphaned
    process from a live one - a second launch while an earlier window is
    still open shares that same path, so a naive "kill anything matching"
    pass was closing the user's already-open window out from under them.
    Skip cleanup entirely whenever another instance of this app is still
    running (own pid excluded) - orphans just wait one more launch to be
    cleared, which is a much smaller cost than killing a live session.
    """
    import psutil

    own_pid = os.getpid()
    own_exe = Path(sys.argv[0]).name.lower()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        if proc.info["pid"] == own_pid:
            continue
        try:
            name = (proc.info["name"] or "").lower()
            if name == own_exe or name == "ssh_console_launcher_v2.exe":
                LOGGER.info("Another instance is already running (pid %d) - skipping webview cleanup", proc.info["pid"])
                return
            if name.startswith("python") and any(
                "main.py" in arg and "SSH_Console_Launcher_v2" in arg for arg in (proc.info["cmdline"] or [])
            ):
                LOGGER.info("Another dev instance is already running (pid %d) - skipping webview cleanup", proc.info["pid"])
                return
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    target = str(WEBVIEW_STORAGE_PATH)
    killed = 0
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            if proc.info["name"] != "msedgewebview2.exe":
                continue
            cmdline = proc.info["cmdline"] or []
            if any(target in arg for arg in cmdline):
                proc.kill()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        LOGGER.info("Cleaned up %d orphaned msedgewebview2.exe process(es) from a previous session", killed)


def main() -> None:
    LOGGER.info("SSH Console Launcher v2 starting up (v%s)", APP_VERSION)
    event_log.log_event("system", "App starting", {"version": APP_VERSION})
    _cleanup_orphaned_webview_processes()

    api = Api()
    window = webview.create_window(
        "SSH Console Launcher v2",
        str(WEB_DIR / "index.html"),
        js_api=api,
        width=1400,
        height=860,
        min_size=(900, 560),
        background_color="#0d1117",
        text_select=True,
    )
    def on_closing() -> None:
        # Must return None: pywebview collects each handler's return value in a
        # set (and treats a literal False as "cancel the close"), so returning
        # the event dict raises "unhashable type: 'dict'".
        event_log.log_event("system", "Closing window")

    window.events.closing += on_closing
    api.set_window(window)
    webview.start(debug=False, storage_path=str(WEBVIEW_STORAGE_PATH))


if __name__ == "__main__":
    main()
