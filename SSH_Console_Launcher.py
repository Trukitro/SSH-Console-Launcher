"""
Embedded SSH Console Launcher for Windows - Version 1.4.1 Web Host Monitoring Dashboard

Features:
- Modern CustomTkinter dark UI.
- Save SSH profiles.
- Store passwords with keyring / Windows Credential Manager.
- Auto-login with plink.exe.
- Open SSH consoles inside this GUI.
- Tabs and split panes.
- Smart grid layouts for 3 and 4 split views.
- Layout Manager controls for Auto, 2-pane, 3-pane, and 4-pane layouts.
- Web Host Monitoring Dashboard with CPU/RAM/Disk/Load/uWSGI/Web2py/connection/user-load cards.
- Health check and risk analysis over SSH using non-interactive plink commands.
- Vertical/horizontal split layout.
- Close each console with a mouse click.
- Reconnect each console with a mouse click.
- Rename tabs.
- Double-click a tab to rename it.
- Close tabs using the X in the tab title.
- Quick command buttons.
- Add/edit/delete saved commands.
- Run saved commands in the currently focused terminal.
- Clear focused console.
- Better terminal rendering using pyte.
- Extra cleanup for htop/top/nano/vim style terminal output.
- Safer tab close handling.
- Full tab cleanup so closed tabs disappear correctly.
- ANSI foreground/background colors in the terminal renderer.
- Green/red connection status indicator per terminal pane.
- Fixed focused terminal routing for toolbar and quick commands.
- Closing the last console in a tab now closes and destroys the tab.
- Built-in documentation viewer for README and version history Markdown files.

Requirements:
    pip install pywinpty keyring pyte customtkinter

Runtime requirement:
- Put plink.exe beside this script/exe, or install PuTTY and add it to PATH.

Build portable EXE:
    pip install pyinstaller pywinpty keyring pyte customtkinter
    pyinstaller --onefile --windowed --add-binary "plink.exe;." --add-data "README.md;." --add-data "VERSION_HISTORY.md;." --add-data "FEATURES_PLAN.md;." SSH_Console_Launcher.py
"""

from __future__ import annotations

import io
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import traceback
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    import customtkinter as ctk
except Exception:
    ctk = None

try:
    import keyring
except Exception:
    keyring = None

try:
    from winpty import PtyProcess
except Exception:
    PtyProcess = None

try:
    import pyte
except Exception:
    pyte = None

try:
    import winsound
except Exception:
    winsound = None


# --- In-app debug logging -------------------------------------------------
# No console exists in the --windowed PyInstaller build, so anything a bare
# print() or an uncaught Tkinter callback exception would normally send to
# stderr previously went nowhere. LOG_QUEUE/LOG_BUFFER feed the DebugLogViewer
# window; LOG_BUFFER keeps history so opening the viewer late still shows
# everything logged since startup.
MAX_LOG_ENTRIES = 2000
LOG_QUEUE: "queue.Queue[tuple[str, str, str]]" = queue.Queue()
LOG_BUFFER: "deque[tuple[str, str, str]]" = deque(maxlen=MAX_LOG_ENTRIES)


class InMemoryLogHandler(logging.Handler):
    """Pushes formatted log records onto LOG_QUEUE/LOG_BUFFER instead of a stream."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = (record.levelname, time.strftime("%H:%M:%S"), self.format(record))
        except Exception:
            entry = (record.levelname, time.strftime("%H:%M:%S"), record.getMessage())
        LOG_BUFFER.append(entry)
        LOG_QUEUE.put(entry)


def _setup_app_logger() -> logging.Logger:
    logger = logging.getLogger("ssh_launcher")
    logger.setLevel(logging.DEBUG)
    handler = InMemoryLogHandler()
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


APP_LOGGER = _setup_app_logger()


class _TeeStream(io.TextIOBase):
    """Mirrors writes to the real stream (if any) and into the log queue."""

    def __init__(self, real_stream, level: str) -> None:
        self._real_stream = real_stream
        self._level = level

    def write(self, text: str) -> int:
        if self._real_stream is not None:
            try:
                self._real_stream.write(text)
            except Exception:
                pass
        stripped = text.strip("\n")
        if stripped:
            entry = (self._level, time.strftime("%H:%M:%S"), stripped)
            LOG_BUFFER.append(entry)
            LOG_QUEUE.put(entry)
        return len(text)

    def flush(self) -> None:
        if self._real_stream is not None:
            try:
                self._real_stream.flush()
            except Exception:
                pass


def _install_stdio_tee() -> None:
    sys.stdout = _TeeStream(sys.__stdout__, "INFO")
    sys.stderr = _TeeStream(sys.__stderr__, "ERROR")


_install_stdio_tee()


APP_VERSION = "1.5.7"
APP_NAME = f"Embedded SSH Launcher v{APP_VERSION}"
SERVICE_NAME = "EmbeddedSSHLauncher"
CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "EmbeddedSSHLauncher"
CONFIG_FILE = CONFIG_DIR / "profiles.json"
COMMANDS_FILE = CONFIG_DIR / "commands.json"
UI_STATE_FILE = CONFIG_DIR / "ui_state.json"
RECENT_FILE = CONFIG_DIR / "recent.json"
MAX_RECENT = 8
SESSION_FILE = CONFIG_DIR / "session.json"
MONITORING_HISTORY_FILE = CONFIG_DIR / "monitoring_history.json"
MAX_HISTORY_SAMPLES = 30
AUDIT_LOG_FILE = CONFIG_DIR / "audit_log.jsonl"
MAX_AUDIT_ENTRIES_SHOWN = 300
CLIPBOARD_CLEAR_SECONDS = 20
DEFAULT_SIDEBAR_WIDTH = 320
MIN_SIDEBAR_WIDTH = 240
MAX_SIDEBAR_WIDTH = 560
DOC_README_FILE = "README.md"
DOC_VERSION_FILE = "VERSION_HISTORY.md"
DOC_FEATURES_FILE = "FEATURES_PLAN.md"
DOC_ALIASES = {
    DOC_README_FILE: ["README.md", "README_Embedded_SSH_Launcher.md"],
    DOC_VERSION_FILE: ["VERSION_HISTORY.md", "VERSION_HISTORY_Embedded_SSH_Launcher.md"],
    DOC_FEATURES_FILE: ["FEATURES_PLAN.md"],
}
DOC_FILE_NAMES = [DOC_README_FILE, DOC_VERSION_FILE, DOC_FEATURES_FILE]

ICON_ICO_FILE = "app_icon.ico"
ICON_PNG_FILE = "app_icon_128.png"

MAX_PANES_PER_TAB = 4
TAB_CLOSE_SUFFIX = "   ×"

BG = "#0f172a"
PANEL = "#111827"
PANEL_2 = "#1f2937"
CARD = "#1e293b"
CARD_HOVER = "#334155"
ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
SUCCESS = "#16a34a"
SUCCESS_HOVER = "#15803d"
DANGER = "#dc2626"
DANGER_HOVER = "#991b1b"
WARNING = "#d97706"
WARNING_HOVER = "#92400e"
TEXT = "#e5e7eb"
MUTED = "#9ca3af"
TERMINAL_BG = "#050505"
TERMINAL_FG = "#f8fafc"

# Secondary near-black panel tones (markdown viewer body / blockquote backgrounds)
PANEL_DARK = "#0b1220"
PANEL_QUOTE = "#172033"

# Shared highlight/accent tones used outside the core semantic palette above
HIGHLIGHT_CODE = "#fef08a"
HIGHLIGHT_SEARCH = "#facc15"

# Per-profile environment tags: value -> (display label, border color)
ENV_TAGS = {
    "": ("None", CARD),
    "prod": ("Production", DANGER),
    "staging": ("Staging", WARNING),
    "dev": ("Development", SUCCESS),
}
ENV_TAG_ORDER = ["", "prod", "staging", "dev"]


def _clamp_channel(value: int) -> int:
    return max(0, min(255, value))


def tint(hex_color: str, factor: float) -> str:
    """Blend a hex color toward white (factor > 0) or black (factor < 0).

    factor is clamped to [-1, 1]; 0 returns the color unchanged.
    """
    factor = max(-1.0, min(1.0, factor))
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    target = 255 if factor >= 0 else 0
    blend = abs(factor)
    r = _clamp_channel(round(r + (target - r) * blend))
    g = _clamp_channel(round(g + (target - g) * blend))
    b = _clamp_channel(round(b + (target - b) * blend))
    return f"#{r:02x}{g:02x}{b:02x}"


# Secondary hover shade for buttons whose fg_color is already CARD_HOVER
# (e.g. "New", "Split Current Tab") - must differ from CARD_HOVER itself.
CARD_HOVER_2 = "#475569"

_HOVER_COLOR_MAP = {
    ACCENT: ACCENT_HOVER,
    SUCCESS: SUCCESS_HOVER,
    DANGER: DANGER_HOVER,
    WARNING: WARNING_HOVER,
    CARD: CARD_HOVER,
    CARD_HOVER: CARD_HOVER_2,
}
# Any fg_color not covered above (including the *_HOVER constants themselves,
# if ever used directly as a button color) falls through to tint() in
# resolve_hover_color(), which always yields a visibly different shade.


def resolve_hover_color(color: str) -> str:
    """Return a visibly different hover shade for a given button fg_color."""
    if color in _HOVER_COLOR_MAP:
        return _HOVER_COLOR_MAP[color]
    return tint(color, 0.18)


def build_button(
    parent: tk.Widget,
    text: str,
    command,
    color: str,
    *,
    width: int | None = None,
    height: int = 34,
    corner_radius: int = 10,
    anchor: str | None = None,
    border_width: int | None = None,
    border_color: str | None = None,
):
    """Single shared CTkButton factory used by every button in the app.

    Root-cause fix for the previously copy-pasted hover-color bug: hover_color
    is always resolved to a shade that's actually different from fg_color.
    """
    kwargs = dict(
        text=text,
        command=command,
        fg_color=color,
        hover_color=resolve_hover_color(color),
        height=height,
        corner_radius=corner_radius,
    )
    if width is not None:
        kwargs["width"] = width
    if anchor is not None:
        kwargs["anchor"] = anchor
    if border_width is not None:
        kwargs["border_width"] = border_width
    if border_color is not None:
        kwargs["border_color"] = border_color
    return ctk.CTkButton(parent, **kwargs)


MONITORING_HEALTH_COMMAND = r"""
WEB2PY_DIR="/home/www-data/web2py"
UWSGI_SOCKET="/tmp/stats.socket"
NOW_TS="$(date '+%Y-%m-%d %H:%M:%S %z' 2>/dev/null)"

echo "__CHECK_TIME__=${NOW_TS}"
echo "__HOSTNAME__=$(hostname 2>/dev/null)"
echo "__UPTIME__=$(uptime 2>/dev/null)"
echo "__LOADAVG__=$(cat /proc/loadavg 2>/dev/null)"
echo "__CPUCORES__=$(nproc 2>/dev/null || echo 1)"
free -m 2>/dev/null | awk '/Mem:/ {print "__MEM__="$2","$3","$4","$7}'
free -m 2>/dev/null | awk '/Swap:/ {print "__SWAP__="$2","$3","$4}'
df -P / 2>/dev/null | awk 'NR==2 {print "__DISK_ROOT__="$2","$3","$4","$5}'
if [ -d "$WEB2PY_DIR" ]; then
  echo "__WEB2PY_PATH__=$WEB2PY_DIR"
  df -P "$WEB2PY_DIR" 2>/dev/null | awk 'NR==2 {print "__DISK_WEB2PY__="$2","$3","$4","$5}'
else
  echo "__WEB2PY_PATH__=not found"
  echo "__DISK_WEB2PY__=not found"
fi

echo "__WEB2PY_PROCS__=$(pgrep -af 'web2py' 2>/dev/null | grep -v grep | wc -l)"
echo "__UWSGI_PROCS__=$(pgrep -af 'uwsgi' 2>/dev/null | grep -v grep | wc -l)"
echo "__NGINX_PROCS__=$(pgrep -af 'nginx' 2>/dev/null | grep -v grep | wc -l)"
echo "__PYTHON_PROCS__=$(pgrep -af 'python' 2>/dev/null | grep -v grep | wc -l)"
echo "__NGINX_STATUS__=$(systemctl is-active nginx 2>/dev/null || service nginx status 2>/dev/null | head -n 1 || echo unknown)"
echo "__UWSGI_SERVICE_STATUS__=$(systemctl is-active uwsgi 2>/dev/null || systemctl is-active uwsgi-emperor 2>/dev/null || service uwsgi status 2>/dev/null | head -n 1 || echo unknown)"

echo "__TOP_CPU__=$(ps -eo pid,user,pcpu,pmem,etime,comm --sort=-pcpu 2>/dev/null | head -n 8 | tr '\n' ';')"
echo "__TOP_MEM__=$(ps -eo pid,user,pcpu,pmem,etime,comm --sort=-pmem 2>/dev/null | head -n 8 | tr '\n' ';')"
echo "__UWSGI_TOP_CPU__=$(ps -eo pid,user,pcpu,pmem,etime,cmd --sort=-pcpu 2>/dev/null | grep -Ei 'uwsgi|web2py' | grep -v grep | head -n 8 | tr '\n' ';')"

SS_OUT="$(ss -Htan 2>/dev/null || netstat -tan 2>/dev/null)"
echo "__TCP_ESTABLISHED__=$(printf '%s\n' "$SS_OUT" | awk '$1=="ESTAB" || $1=="ESTABLISHED" {c++} END{print c+0}')"
echo "__TCP_TIME_WAIT__=$(printf '%s\n' "$SS_OUT" | awk '$1=="TIME-WAIT" || $1=="TIME_WAIT" {c++} END{print c+0}')"
echo "__WEB_ESTABLISHED__=$(printf '%s\n' "$SS_OUT" | awk '($1=="ESTAB" || $1=="ESTABLISHED") && ($4 ~ /:(80|443|8000|8001|8080|8443)$/) {c++} END{print c+0}')"
echo "__TOP_REMOTE_IPS__=$(printf '%s\n' "$SS_OUT" | awk '($1=="ESTAB" || $1=="ESTABLISHED") {print $5}' | sed -E 's/.*ffff://' | sed -E 's/:[0-9]+$//' | sort | uniq -c | sort -nr | head -n 8 | tr '\n' ';')"

if [ -d "$WEB2PY_DIR" ]; then
  LOG_FILES="$(find "$WEB2PY_DIR" -type f \( -name '*.log' -o -name 'web2py.log' \) -mmin -1440 2>/dev/null | head -n 60)"
  if [ -n "$LOG_FILES" ]; then
    LOG_SAMPLE="$(printf '%s\n' "$LOG_FILES" | xargs -r tail -n 500 2>/dev/null)"
    echo "__LOG_FILES_COUNT__=$(printf '%s\n' "$LOG_FILES" | wc -l)"
    echo "__LOG_LINES__=$(printf '%s\n' "$LOG_SAMPLE" | wc -l)"
    echo "__RECENT_ERRORS__=$(printf '%s\n' "$LOG_SAMPLE" | grep -iE 'error|traceback|exception|ticket|failed|critical' | wc -l)"
    echo "__LOGIN_EVENTS__=$(printf '%s\n' "$LOG_SAMPLE" | grep -iE 'login|logged in|logged-in|authenticated|auth_user|user_id|email' | wc -l)"
    echo "__UNIQUE_CLIENTS__=$(printf '%s\n' "$LOG_SAMPLE" | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}' | sort -u | wc -l)"
    echo "__TOP_CLIENTS__=$(printf '%s\n' "$LOG_SAMPLE" | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}' | sort | uniq -c | sort -nr | head -n 8 | tr '\n' ';')"
    echo "__LOG_502__=$(printf '%s\n' "$LOG_SAMPLE" | grep -iE '502|bad gateway|gateway timeout|upstream|connection refused|connection reset' | wc -l)"
  else
    echo "__LOG_FILES_COUNT__=0"
    echo "__LOG_LINES__=0"
    echo "__RECENT_ERRORS__=0"
    echo "__LOGIN_EVENTS__=0"
    echo "__UNIQUE_CLIENTS__=0"
    echo "__TOP_CLIENTS__=none"
    echo "__LOG_502__=0"
  fi
else
  echo "__LOG_FILES_COUNT__=0"
  echo "__LOG_LINES__=0"
  echo "__RECENT_ERRORS__=0"
  echo "__LOGIN_EVENTS__=0"
  echo "__UNIQUE_CLIENTS__=0"
  echo "__TOP_CLIENTS__=web2py folder not found"
  echo "__LOG_502__=0"
fi

if [ -d /var/log/nginx ]; then
  NGINX_LOG_SAMPLE="$(find /var/log/nginx -type f \( -name '*.log' -o -name '*error*' -o -name '*access*' \) -mmin -1440 2>/dev/null | head -n 20 | xargs -r tail -n 1000 2>/dev/null)"
  echo "__NGINX_502__=$(printf '%s\n' "$NGINX_LOG_SAMPLE" | grep -iE ' 502 | 504 |bad gateway|gateway timeout|upstream timed out|upstream prematurely|connect\(\) failed|no live upstreams|recv\(\) failed|connection refused' | wc -l)"
  echo "__NGINX_ERRORS__=$(printf '%s\n' "$NGINX_LOG_SAMPLE" | grep -iE 'error|crit|alert|emerg|upstream|failed|refused|timed out' | wc -l)"
  echo "__NGINX_TOP_CLIENTS__=$(printf '%s\n' "$NGINX_LOG_SAMPLE" | awk '{print $1}' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | sort | uniq -c | sort -nr | head -n 8 | tr '\n' ';')"
else
  echo "__NGINX_502__=0"
  echo "__NGINX_ERRORS__=0"
  echo "__NGINX_TOP_CLIENTS__=nginx log folder not found"
fi

python3 - <<'PY_UWSGI_STATS' 2>/dev/null
import json, socket, os
path = "/tmp/stats.socket"
print(f"__UWSGI_STATS_PATH__={path}")
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect(path)
    chunks = []
    while True:
        try:
            data = s.recv(65536)
        except socket.timeout:
            break
        if not data:
            break
        chunks.append(data)
    raw = b"".join(chunks).decode("utf-8", "replace")
    data = json.loads(raw)
    workers = data.get("workers", []) or []
    total = len(workers)
    busy = sum(1 for w in workers if str(w.get("status", "")).lower() == "busy")
    idle = sum(1 for w in workers if str(w.get("status", "")).lower() == "idle")
    requests = sum(int(w.get("requests", 0) or 0) for w in workers)
    exceptions = sum(int(w.get("exceptions", 0) or 0) for w in workers)
    harakiri = sum(int(w.get("harakiri_count", 0) or 0) for w in workers)
    respawns = sum(int(w.get("respawn_count", 0) or 0) for w in workers)
    rss_total = sum(int(w.get("rss", 0) or 0) for w in workers)
    avg_rt_values = []
    for w in workers:
        try:
            avg_rt_values.append(float(w.get("avg_rt", 0) or 0))
        except Exception:
            pass
    avg_rt = sum(avg_rt_values) / len(avg_rt_values) if avg_rt_values else 0
    print("__UWSGI_STATS_OK__=1")
    print(f"__UWSGI_WORKERS_TOTAL__={total}")
    print(f"__UWSGI_WORKERS_BUSY__={busy}")
    print(f"__UWSGI_WORKERS_IDLE__={idle}")
    print(f"__UWSGI_REQUESTS__={requests}")
    print(f"__UWSGI_EXCEPTIONS__={exceptions}")
    print(f"__UWSGI_HARAKIRI__={harakiri}")
    print(f"__UWSGI_RESPAWNS__={respawns}")
    print(f"__UWSGI_RSS_MB__={rss_total / 1024 / 1024:.1f}")
    print(f"__UWSGI_AVG_RT__={avg_rt:.1f}")
except Exception as exc:
    print("__UWSGI_STATS_OK__=0")
    print("__UWSGI_STATS_ERROR__=" + str(exc).replace("\n", " ")[:240])
PY_UWSGI_STATS
"""


def resolve_health_command(profile: "SSHProfile | None") -> str:
    """A profile's custom health-check command, or the built-in Web2py/uWSGI/Nginx one.

    A custom command only needs to emit the same `__KEY__=value` lines the
    dashboard already parses (see parse_health_output/update_cards) to
    populate the cards - anything else still shows up in the raw output
    panel, so the dashboard stays useful for stacks (Docker, Kubernetes,
    etc.) that don't emit any of those keys at all.
    """
    if profile is not None and profile.health_check_command.strip():
        return profile.health_check_command
    return MONITORING_HEALTH_COMMAND


CONNECTED = "#22c55e"
DISCONNECTED = "#ef4444"
CONNECTING = "#f59e0b"

ANSI_COLOR_MAP = {
    "default": TERMINAL_FG,
    # Normal terminal black/dim colors are too hard to read on the app black background.
    # These are intentionally brightened for htop/uwsgitop readability.
    "black": "#cbd5e1",
    "red": "#ff6b6b",
    "green": "#4ade80",
    "yellow": "#fde047",
    "brown": "#fde047",
    "blue": "#60a5fa",
    "magenta": "#e879f9",
    "cyan": "#22d3ee",
    "white": "#f8fafc",
    "brightblack": "#e5e7eb",
    "brightred": "#fca5a5",
    "brightgreen": "#86efac",
    "brightyellow": "#fef08a",
    "brightblue": "#93c5fd",
    "brightmagenta": "#f0abfc",
    "brightcyan": "#67e8f9",
    "brightwhite": "#ffffff",
    "lightblack": "#e5e7eb",
    "lightred": "#fca5a5",
    "lightgreen": "#86efac",
    "lightyellow": "#fef08a",
    "lightblue": "#93c5fd",
    "lightmagenta": "#f0abfc",
    "lightcyan": "#67e8f9",
    "lightwhite": "#ffffff",
}

# Independent from ANSI_COLOR_MAP: that map deliberately brightens dim foreground
# colors (e.g. "black") for text readability, which is wrong for a *background*
# cell - a remote app setting a literal black/dim background must render dark,
# not near-white. These are real dark tones per hue instead.
_ANSI_BG_BASE = "#111827"
_ANSI_BG_RED = "#7f1d1d"
_ANSI_BG_GREEN = "#14532d"
_ANSI_BG_YELLOW = "#78350f"
_ANSI_BG_BLUE = "#1e3a8a"
_ANSI_BG_MAGENTA = "#701a75"
_ANSI_BG_CYAN = "#164e63"
_ANSI_BG_WHITE = "#cbd5e1"

ANSI_BACKGROUND_MAP = {
    "default": TERMINAL_BG,
    "black": _ANSI_BG_BASE,
    "red": _ANSI_BG_RED,
    "green": _ANSI_BG_GREEN,
    "yellow": _ANSI_BG_YELLOW,
    "brown": _ANSI_BG_YELLOW,
    "blue": _ANSI_BG_BLUE,
    "magenta": _ANSI_BG_MAGENTA,
    "cyan": _ANSI_BG_CYAN,
    "white": _ANSI_BG_WHITE,
    "brightblack": tint(_ANSI_BG_BASE, 0.25),
    "brightred": tint(_ANSI_BG_RED, 0.25),
    "brightgreen": tint(_ANSI_BG_GREEN, 0.25),
    "brightyellow": tint(_ANSI_BG_YELLOW, 0.25),
    "brightblue": tint(_ANSI_BG_BLUE, 0.25),
    "brightmagenta": tint(_ANSI_BG_MAGENTA, 0.25),
    "brightcyan": tint(_ANSI_BG_CYAN, 0.25),
    "brightwhite": "#ffffff",
    "lightblack": tint(_ANSI_BG_BASE, 0.25),
    "lightred": tint(_ANSI_BG_RED, 0.25),
    "lightgreen": tint(_ANSI_BG_GREEN, 0.25),
    "lightyellow": tint(_ANSI_BG_YELLOW, 0.25),
    "lightblue": tint(_ANSI_BG_BLUE, 0.25),
    "lightmagenta": tint(_ANSI_BG_MAGENTA, 0.25),
    "lightcyan": tint(_ANSI_BG_CYAN, 0.25),
    "lightwhite": "#ffffff",
}

EMBEDDED_DOCUMENTS = {'README.md': '# Embedded SSH Console Launcher\n\n**Current version:** 1.4.1  \n**Platform:** Windows 10 / Windows 11  \n**Purpose:** A lightweight Windows GUI for managing multiple SSH console sessions with saved profiles, split panes, tabs, quick commands, auto-login, reconnect controls, and terminal monitoring.\n\n---\n\n## Overview\n\nEmbedded SSH Console Launcher is a Windows desktop app built in Python. It was created to make repeated SSH work faster and easier, especially when connecting to the same Linux servers many times per day.\n\nInstead of opening separate command prompt windows or manually typing usernames, passwords, and commands every time, the app lets you:\n\n- Save SSH profiles.\n- Open one or more SSH consoles quickly.\n- Use tabs and split panes.\n- Auto-login with saved credentials.\n- Run frequently used commands with one click.\n- Monitor session connection status.\n- Reconnect, clear, focus, and close sessions from the GUI.\n\nThe app is designed for a maximum practical workflow of around 1 to 4 terminals per tab, but it can support multiple tabs.\n\n---\n\n## Main Features\n\n### SSH Profile Management\n\nYou can save SSH profiles with:\n\n- Profile name\n- Host / IP\n- Username\n- Port\n- Password\n\nPasswords are stored using the Windows credential/keyring system through the Python `keyring` package. Passwords are not stored directly in the JSON profile file.\n\nProfiles are saved in:\n\n```text\n%APPDATA%\\EmbeddedSSHLauncher\\profiles.json\n```\n\n---\n\n### Embedded SSH Consoles\n\nThe app opens SSH sessions inside the GUI instead of launching separate Windows Terminal windows.\n\nEach console supports:\n\n- Auto-login\n- Terminal output rendering\n- ANSI color handling\n- `htop`\n- `uwsgitop`\n- `tail -f`\n- Standard shell commands\n- Copy/paste\n- Reconnect\n- Clear\n- Close\n- Focus selection\n\nSSH sessions are launched through `plink.exe` from PuTTY.\n\n---\n\n### Tabs and Split Panes\n\nThe app supports:\n\n- New tab\n- Split current tab\n- Open 2 split consoles\n- Open 3 split consoles\n- Open 4 split consoles\n- Vertical split\n- Horizontal split\n- Rename current tab\n- Close current tab\n- Close tab using the `×` symbol\n\nIf the last console in a tab is closed, the tab is also destroyed.\n\n---\n\n### Quick Commands\n\nQuick Commands let you create buttons for commands you run often.\n\nDefault quick commands include:\n\n```bash\nhtop\ncd /home/www-data/web2py/\ntail -f web2py.log\nsudo uwsgitop /tmp/stats.socket\nclear\n```\n\nYou can add, edit, and delete commands from the GUI.\n\nQuick commands are saved in:\n\n```text\n%APPDATA%\\EmbeddedSSHLauncher\\commands.json\n```\n\nQuick commands are sent to the currently focused terminal.\n\n---\n\n### Connection Status Indicator\n\nEach terminal shows a connection status indicator:\n\n```text\n● Connected\n● Connecting\n● Disconnected\n```\n\nThe indicator helps identify when a session has dropped and needs reconnecting.\n\n---\n\n### Modern UI\n\nStarting with version 1.3, the UI uses `customtkinter` for a modern dark interface.\n\nUI improvements include:\n\n- Dark theme\n- Modern left sidebar\n- Rounded buttons\n- Toolbar actions\n- Quick command buttons\n- Highlighted active terminal\n- Status bar\n- Improved layout and spacing\n\n---\n\n## Requirements\n\nInstall Python packages:\n\n```powershell\npip install pywinpty keyring pyte customtkinter\n```\n\nRequired executable:\n\n```text\nplink.exe\n```\n\nPlace `plink.exe` in the same folder as the Python script or compiled `.exe`, or install PuTTY and add it to your PATH.\n\n---\n\n## Running the App\n\nExample:\n\n```powershell\n& c:\\python312\\python.exe c:\\Users\\Ricrado\\Documents\\Python_Scripts\\SSH_CONSOLE_LAUNCHER\\SSH_Console_Launcher.py\n```\n\n---\n\n## Building a Portable EXE\n\nInstall build tools:\n\n```powershell\npip install pyinstaller pywinpty keyring pyte customtkinter\n```\n\nBuild:\n\n```powershell\npyinstaller --onefile --windowed `\n  --add-binary "plink.exe;." `\n  --add-data "README.md;." `\n  --add-data "VERSION_HISTORY.md;." `\n  --add-data "FEATURES_PLAN.md;." `\n  SSH_Console_Launcher.py\n```\n\nThe final executable will be created in:\n\n```text\ndist\\\n```\n\nRecommended folder structure:\n\n```text\nSSHLauncher\\\n  SSH_Console_Launcher.exe\n  plink.exe\n```\n\n---\n\n## Configuration Files\n\nThe app stores user data in:\n\n```text\n%APPDATA%\\EmbeddedSSHLauncher\\\n```\n\nFiles:\n\n```text\nprofiles.json\ncommands.json\n```\n\nPasswords are stored through Windows/keyring, not directly in these files.\n\n---\n\n## Security Notes\n\nThis app is designed for internal/personal administrative use.\n\nImportant notes:\n\n- Passwords are saved through `keyring`, not plain JSON.\n- `plink.exe -pw` is used for automatic login.\n- SSH key support is a recommended future improvement.\n- Anyone with access to your Windows user session may be able to use the saved profiles.\n- Use Windows account protection and disk encryption where appropriate.\n\n---\n\n## Known Limitations\n\nThe app uses `tk.Text` plus `pyte` for terminal rendering. This works well enough for the current workflow, including `htop` and `uwsgitop`, but it is not a full native terminal emulator like Windows Terminal, xterm, or xterm.js.\n\nSome highly interactive terminal applications may still have minor rendering differences.\n\nExamples that may not be perfect:\n\n- Complex `vim` usage\n- Some `nano` layouts\n- Advanced ncurses interfaces\n- Mouse interactions inside terminal apps\n\n---\n\n## Layout Manager\n\nStarting with version 1.3.9, the app includes explicit Layout Manager controls so you can rearrange consoles after they are already open.\n\nAvailable layouts:\n\n- **Auto Layout**: chooses the best layout based on pane count.\n- **2 Panes: Side by Side**: two terminals left/right.\n- **2 Panes: Stacked**: two terminals top/bottom.\n- **3 Panes: 2 Top / 1 Bottom**: two terminals on top, one full-width terminal below.\n- **3 Panes: 1 Top / 2 Bottom**: one full-width terminal on top, two terminals below.\n- **4 Panes: 2 x 2 Grid**: four terminals in a square grid.\n\nThis means you no longer need to close and reopen SSH sessions just to change how the panes are arranged.\n\n---\n\n## Smart Split Layouts\n\nStarting with version 1.3.8, multi-console split views are arranged more naturally:\n\n- **Open 3 Split** creates two consoles on the top row and one full-width console on the bottom row.\n- **Open 4 Split** creates a 2 x 2 square layout.\n\nThe manual **Vertical Split** and **Horizontal Split** buttons still force a simple stacked or side-by-side layout when needed.\n\n---\n\n## Built-in Documentation Viewer\n\nThe app can display project documentation inside the GUI. It looks for these files beside the `.py` script or packaged `.exe`:\n\n```text\nREADME.md\nVERSION_HISTORY.md\nFEATURES_PLAN.md\n```\n\nWhen the app is packaged as a Windows `.exe`, include these files with PyInstaller using `--add-data`. If the external files are missing, the app also includes embedded fallback documentation.\n\n---\n\n\n---\n\n## Web Host Monitoring Dashboard Upgrade\n\nStarting with **v1.4.1**, the Monitoring Dashboard is focused on detecting conditions that can lead to web host degradation or outages, including possible **502 Bad Gateway** symptoms.\n\nThe dashboard now checks more than basic CPU/RAM/Disk. It also looks for:\n\n- Load average compared to CPU cores.\n- RAM and swap pressure.\n- Disk usage for `/` and the Web2py folder.\n- Number of established TCP/web connections.\n- Top remote client IPs.\n- Estimated active users/client IPs from Web2py logs.\n- Login/auth/user-related events from Web2py logs.\n- Recent Web2py errors, tracebacks, exceptions, tickets, and failures.\n- Nginx process/status and recent Nginx upstream/gateway errors.\n- uWSGI worker status from `/tmp/stats.socket` when available.\n- Busy/idle uWSGI worker ratio.\n- uWSGI exceptions, harakiri counts, respawns, RSS memory, and average response time when available.\n- Web2py/uWSGI top CPU consumers.\n\n### New Monitoring Cards\n\nThe dashboard includes these additional cards:\n\n- Overall Web Host Risk\n- 502 / Gateway Risk\n- Swap Usage\n- Disk Web2py\n- Web Connections\n- Active Users / IPs\n- uWSGI Workers\n- uWSGI Health\n- Nginx Status\n- Login/User Events\n- Web2py/uWSGI CPU\n\n### New Monitoring Quick Actions\n\nThe sidebar Monitoring section now includes:\n\n- Open Dashboard\n- Run Health Check\n- 502 / Gateway Check\n- Connections\n- Active Users / IPs\n- Recent Errors\n- Web2py Processes\n\nThe goal is to make it easier to detect early warning signs before users begin seeing `502 Bad Gateway`, Nginx upstream failures, overloaded workers, excessive connections, or Linux resource saturation.\n\n---\n\n## Web2py Monitoring Dashboard\n\nStarting with version 1.4.0, the app includes a Monitoring Dashboard focused on Web2py/uWSGI server health.\n\nOpen it from the sidebar under:\n\n```text\nMonitoring -> Open Dashboard\n```\n\nThe dashboard runs a non-interactive health check over SSH using `plink.exe` and shows the result as cards. It does not scrape values from the `htop` screen; it runs direct shell commands and parses the output.\n\nDashboard cards include:\n\n- Server\n- Load Average\n- RAM Usage\n- Disk `/`\n- Web2py Processes\n- uWSGI Processes\n- Recent Errors\n- Top CPU\n- Top Memory\n\nMonitoring quick actions include:\n\n- Open Dashboard\n- Run Health Check\n- Recent Errors\n- Web2py Processes\n\nThe dashboard also supports optional auto-refresh intervals.\n\n---\n\n## Recommended Next Steps\n\nPotential future improvements:\n\n1. Hotkeys for Quick Commands, such as `Ctrl+1`, `Ctrl+2`, etc.\n2. Command groups, such as Web2py, Logs, Monitoring, Docker, Database.\n3. Auto-reconnect option when a connection drops.\n4. Save layouts per profile.\n5. Open a profile with a predefined set of panes and commands.\n6. Run a command on all panes.\n7. Local session logging.\n8. Search inside terminal output.\n9. Import/export profiles and commands.\n10. SSH key support.\n11. Full installer with `plink.exe` included.\n12. Possible migration to xterm.js/WebView for more complete terminal rendering.\n\n---\n\n## Current Stable Version\n\nThe current working version is:\n\n```text\nv1.4.1\n```\n\nThis version includes the modern UI, quick commands, tab close fixes, terminal colors, connection status indicators, corrected focus behavior, Layout Manager, the Web2py Monitoring Dashboard, and the advanced Web Host Monitoring Dashboard upgrade.', 'README_Embedded_SSH_Launcher.md': '# Embedded SSH Console Launcher\n\n**Current version:** 1.4.1  \n**Platform:** Windows 10 / Windows 11  \n**Purpose:** A lightweight Windows GUI for managing multiple SSH console sessions with saved profiles, split panes, tabs, quick commands, auto-login, reconnect controls, and terminal monitoring.\n\n---\n\n## Overview\n\nEmbedded SSH Console Launcher is a Windows desktop app built in Python. It was created to make repeated SSH work faster and easier, especially when connecting to the same Linux servers many times per day.\n\nInstead of opening separate command prompt windows or manually typing usernames, passwords, and commands every time, the app lets you:\n\n- Save SSH profiles.\n- Open one or more SSH consoles quickly.\n- Use tabs and split panes.\n- Auto-login with saved credentials.\n- Run frequently used commands with one click.\n- Monitor session connection status.\n- Reconnect, clear, focus, and close sessions from the GUI.\n\nThe app is designed for a maximum practical workflow of around 1 to 4 terminals per tab, but it can support multiple tabs.\n\n---\n\n## Main Features\n\n### SSH Profile Management\n\nYou can save SSH profiles with:\n\n- Profile name\n- Host / IP\n- Username\n- Port\n- Password\n\nPasswords are stored using the Windows credential/keyring system through the Python `keyring` package. Passwords are not stored directly in the JSON profile file.\n\nProfiles are saved in:\n\n```text\n%APPDATA%\\EmbeddedSSHLauncher\\profiles.json\n```\n\n---\n\n### Embedded SSH Consoles\n\nThe app opens SSH sessions inside the GUI instead of launching separate Windows Terminal windows.\n\nEach console supports:\n\n- Auto-login\n- Terminal output rendering\n- ANSI color handling\n- `htop`\n- `uwsgitop`\n- `tail -f`\n- Standard shell commands\n- Copy/paste\n- Reconnect\n- Clear\n- Close\n- Focus selection\n\nSSH sessions are launched through `plink.exe` from PuTTY.\n\n---\n\n### Tabs and Split Panes\n\nThe app supports:\n\n- New tab\n- Split current tab\n- Open 2 split consoles\n- Open 3 split consoles\n- Open 4 split consoles\n- Vertical split\n- Horizontal split\n- Rename current tab\n- Close current tab\n- Close tab using the `×` symbol\n\nIf the last console in a tab is closed, the tab is also destroyed.\n\n---\n\n### Quick Commands\n\nQuick Commands let you create buttons for commands you run often.\n\nDefault quick commands include:\n\n```bash\nhtop\ncd /home/www-data/web2py/\ntail -f web2py.log\nsudo uwsgitop /tmp/stats.socket\nclear\n```\n\nYou can add, edit, and delete commands from the GUI.\n\nQuick commands are saved in:\n\n```text\n%APPDATA%\\EmbeddedSSHLauncher\\commands.json\n```\n\nQuick commands are sent to the currently focused terminal.\n\n---\n\n### Connection Status Indicator\n\nEach terminal shows a connection status indicator:\n\n```text\n● Connected\n● Connecting\n● Disconnected\n```\n\nThe indicator helps identify when a session has dropped and needs reconnecting.\n\n---\n\n### Modern UI\n\nStarting with version 1.3, the UI uses `customtkinter` for a modern dark interface.\n\nUI improvements include:\n\n- Dark theme\n- Modern left sidebar\n- Rounded buttons\n- Toolbar actions\n- Quick command buttons\n- Highlighted active terminal\n- Status bar\n- Improved layout and spacing\n\n---\n\n## Requirements\n\nInstall Python packages:\n\n```powershell\npip install pywinpty keyring pyte customtkinter\n```\n\nRequired executable:\n\n```text\nplink.exe\n```\n\nPlace `plink.exe` in the same folder as the Python script or compiled `.exe`, or install PuTTY and add it to your PATH.\n\n---\n\n## Running the App\n\nExample:\n\n```powershell\n& c:\\python312\\python.exe c:\\Users\\Ricrado\\Documents\\Python_Scripts\\SSH_CONSOLE_LAUNCHER\\SSH_Console_Launcher.py\n```\n\n---\n\n## Building a Portable EXE\n\nInstall build tools:\n\n```powershell\npip install pyinstaller pywinpty keyring pyte customtkinter\n```\n\nBuild:\n\n```powershell\npyinstaller --onefile --windowed `\n  --add-binary "plink.exe;." `\n  --add-data "README.md;." `\n  --add-data "VERSION_HISTORY.md;." `\n  --add-data "FEATURES_PLAN.md;." `\n  SSH_Console_Launcher.py\n```\n\nThe final executable will be created in:\n\n```text\ndist\\\n```\n\nRecommended folder structure:\n\n```text\nSSHLauncher\\\n  SSH_Console_Launcher.exe\n  plink.exe\n```\n\n---\n\n## Configuration Files\n\nThe app stores user data in:\n\n```text\n%APPDATA%\\EmbeddedSSHLauncher\\\n```\n\nFiles:\n\n```text\nprofiles.json\ncommands.json\n```\n\nPasswords are stored through Windows/keyring, not directly in these files.\n\n---\n\n## Security Notes\n\nThis app is designed for internal/personal administrative use.\n\nImportant notes:\n\n- Passwords are saved through `keyring`, not plain JSON.\n- `plink.exe -pw` is used for automatic login.\n- SSH key support is a recommended future improvement.\n- Anyone with access to your Windows user session may be able to use the saved profiles.\n- Use Windows account protection and disk encryption where appropriate.\n\n---\n\n## Known Limitations\n\nThe app uses `tk.Text` plus `pyte` for terminal rendering. This works well enough for the current workflow, including `htop` and `uwsgitop`, but it is not a full native terminal emulator like Windows Terminal, xterm, or xterm.js.\n\nSome highly interactive terminal applications may still have minor rendering differences.\n\nExamples that may not be perfect:\n\n- Complex `vim` usage\n- Some `nano` layouts\n- Advanced ncurses interfaces\n- Mouse interactions inside terminal apps\n\n---\n\n## Layout Manager\n\nStarting with version 1.3.9, the app includes explicit Layout Manager controls so you can rearrange consoles after they are already open.\n\nAvailable layouts:\n\n- **Auto Layout**: chooses the best layout based on pane count.\n- **2 Panes: Side by Side**: two terminals left/right.\n- **2 Panes: Stacked**: two terminals top/bottom.\n- **3 Panes: 2 Top / 1 Bottom**: two terminals on top, one full-width terminal below.\n- **3 Panes: 1 Top / 2 Bottom**: one full-width terminal on top, two terminals below.\n- **4 Panes: 2 x 2 Grid**: four terminals in a square grid.\n\nThis means you no longer need to close and reopen SSH sessions just to change how the panes are arranged.\n\n---\n\n## Smart Split Layouts\n\nStarting with version 1.3.8, multi-console split views are arranged more naturally:\n\n- **Open 3 Split** creates two consoles on the top row and one full-width console on the bottom row.\n- **Open 4 Split** creates a 2 x 2 square layout.\n\nThe manual **Vertical Split** and **Horizontal Split** buttons still force a simple stacked or side-by-side layout when needed.\n\n---\n\n## Built-in Documentation Viewer\n\nThe app can display project documentation inside the GUI. It looks for these files beside the `.py` script or packaged `.exe`:\n\n```text\nREADME.md\nVERSION_HISTORY.md\nFEATURES_PLAN.md\n```\n\nWhen the app is packaged as a Windows `.exe`, include these files with PyInstaller using `--add-data`. If the external files are missing, the app also includes embedded fallback documentation.\n\n---\n\n\n---\n\n## Web Host Monitoring Dashboard Upgrade\n\nStarting with **v1.4.1**, the Monitoring Dashboard is focused on detecting conditions that can lead to web host degradation or outages, including possible **502 Bad Gateway** symptoms.\n\nThe dashboard now checks more than basic CPU/RAM/Disk. It also looks for:\n\n- Load average compared to CPU cores.\n- RAM and swap pressure.\n- Disk usage for `/` and the Web2py folder.\n- Number of established TCP/web connections.\n- Top remote client IPs.\n- Estimated active users/client IPs from Web2py logs.\n- Login/auth/user-related events from Web2py logs.\n- Recent Web2py errors, tracebacks, exceptions, tickets, and failures.\n- Nginx process/status and recent Nginx upstream/gateway errors.\n- uWSGI worker status from `/tmp/stats.socket` when available.\n- Busy/idle uWSGI worker ratio.\n- uWSGI exceptions, harakiri counts, respawns, RSS memory, and average response time when available.\n- Web2py/uWSGI top CPU consumers.\n\n### New Monitoring Cards\n\nThe dashboard includes these additional cards:\n\n- Overall Web Host Risk\n- 502 / Gateway Risk\n- Swap Usage\n- Disk Web2py\n- Web Connections\n- Active Users / IPs\n- uWSGI Workers\n- uWSGI Health\n- Nginx Status\n- Login/User Events\n- Web2py/uWSGI CPU\n\n### New Monitoring Quick Actions\n\nThe sidebar Monitoring section now includes:\n\n- Open Dashboard\n- Run Health Check\n- 502 / Gateway Check\n- Connections\n- Active Users / IPs\n- Recent Errors\n- Web2py Processes\n\nThe goal is to make it easier to detect early warning signs before users begin seeing `502 Bad Gateway`, Nginx upstream failures, overloaded workers, excessive connections, or Linux resource saturation.\n\n---\n\n## Web2py Monitoring Dashboard\n\nStarting with version 1.4.0, the app includes a Monitoring Dashboard focused on Web2py/uWSGI server health.\n\nOpen it from the sidebar under:\n\n```text\nMonitoring -> Open Dashboard\n```\n\nThe dashboard runs a non-interactive health check over SSH using `plink.exe` and shows the result as cards. It does not scrape values from the `htop` screen; it runs direct shell commands and parses the output.\n\nDashboard cards include:\n\n- Server\n- Load Average\n- RAM Usage\n- Disk `/`\n- Web2py Processes\n- uWSGI Processes\n- Recent Errors\n- Top CPU\n- Top Memory\n\nMonitoring quick actions include:\n\n- Open Dashboard\n- Run Health Check\n- Recent Errors\n- Web2py Processes\n\nThe dashboard also supports optional auto-refresh intervals.\n\n---\n\n## Recommended Next Steps\n\nPotential future improvements:\n\n1. Hotkeys for Quick Commands, such as `Ctrl+1`, `Ctrl+2`, etc.\n2. Command groups, such as Web2py, Logs, Monitoring, Docker, Database.\n3. Auto-reconnect option when a connection drops.\n4. Save layouts per profile.\n5. Open a profile with a predefined set of panes and commands.\n6. Run a command on all panes.\n7. Local session logging.\n8. Search inside terminal output.\n9. Import/export profiles and commands.\n10. SSH key support.\n11. Full installer with `plink.exe` included.\n12. Possible migration to xterm.js/WebView for more complete terminal rendering.\n\n---\n\n## Current Stable Version\n\nThe current working version is:\n\n```text\nv1.4.1\n```\n\nThis version includes the modern UI, quick commands, tab close fixes, terminal colors, connection status indicators, corrected focus behavior, Layout Manager, the Web2py Monitoring Dashboard, and the advanced Web Host Monitoring Dashboard upgrade.', 'VERSION_HISTORY.md': '# Embedded SSH Console Launcher - Version History\n\nThis file tracks the project evolution from the first working concept through the current stable version.\n\n---\n\n## v1.0 - Initial Working GUI\n\n### Goal\n\nCreate a small Windows GUI that can save SSH connection information and open SSH consoles quickly.\n\n### Main Features\n\n- Tkinter-based GUI.\n- Save SSH profiles.\n- Store host, user, port, and password.\n- Open SSH sessions using `plink.exe`.\n- Support opening multiple consoles.\n- Basic tab and split-pane workflow.\n- Automatic password login.\n- Basic terminal output display.\n\n### Notes\n\nThis version proved that the core workflow was possible:\n\n```text\nSave profile -> Select profile -> Open console quickly\n```\n\n---\n\n## v1.1 - Tabs, Rename, Close, and Reconnect\n\n### Added\n\n- Rename current tab.\n- Double-click tab to rename.\n- `×` symbol in tab title.\n- Click `×` to close a tab.\n- Reconnect button per console.\n- Reconnect selected console from the sidebar.\n- Better session lifecycle handling.\n\n### Fixed / Improved\n\n- Added better control over individual SSH panes.\n- Added reconnect behavior without needing to close and reopen the whole app.\n\n---\n\n## v1.2 - Quick Commands\n\n### Added\n\n- Quick Commands section.\n- Add custom command buttons.\n- Edit saved commands.\n- Delete saved commands.\n- Run command in focused terminal.\n- General Clear Console command.\n- Default commands:\n  - `htop`\n  - `cd /home/www-data/web2py/`\n  - `tail -f web2py.log`\n  - `sudo uwsgitop /tmp/stats.socket`\n  - `clear`\n\n### Files Added\n\n```text\n%APPDATA%\\EmbeddedSSHLauncher\\commands.json\n```\n\n### Purpose\n\nReduce repetitive typing for common admin commands.\n\n---\n\n## v1.3 - Modern UI Refresh\n\n### Added\n\n- CustomTkinter UI.\n- Modern dark theme.\n- Rounded buttons.\n- Better sidebar layout.\n- Top toolbar.\n- Modern connection/profile form.\n- Quick command buttons instead of only listbox style.\n- Improved spacing.\n- Status bar.\n- Active terminal visual highlight.\n\n### Dependencies Added\n\n```powershell\npip install customtkinter\n```\n\n### Notes\n\nThis version modernized the appearance while keeping the working SSH and terminal backend.\n\n---\n\n## v1.3.1 - CustomTkinter Startup Fix\n\n### Fixed\n\n- `CTkScrollableFrame.grid_propagate(False)` startup crash.\n\n### Cause\n\n`CTkScrollableFrame.grid_propagate()` does not accept `False` like a normal Tkinter frame.\n\n### Fix\n\nUse:\n\n```python\nself.sidebar.configure(width=320)\n```\n\ninstead of:\n\n```python\nself.sidebar.grid_propagate(False)\n```\n\nfor CustomTkinter scrollable frames.\n\n---\n\n## v1.3.2 - Safer Tab Close Handling\n\n### Fixed\n\n- Accidental tab closing when clicking or selecting terminal text.\n- Fake `×` tab close area was too aggressive.\n\n### Added\n\n- Press/release tracking for tab close.\n- Smaller close zone.\n- Close only if press and release both happen on the `×` area.\n- Ignore drag/focus/select actions.\n\n### Methods Added / Updated\n\n- `get_tab_close_candidate`\n- `on_notebook_button_press`\n- `on_notebook_button_release`\n\n---\n\n## v1.3.3 - Tab Destruction and Terminal Color Support\n\n### Fixed\n\n- Closed tabs could remain visible or not disappear.\n- Notebook tab was being forgotten but not fully destroyed.\n- Old tab references could remain in memory.\n- SSH processes could remain alive after closing a tab.\n\n### Improved\n\n- Fully destroy tab frame after closing.\n- Close all SSH panes inside a tab before removing the tab.\n- Clear active/focused terminal references when closing tabs.\n- Delay close using `after(1, ...)` so notebook finishes processing click events first.\n\n### Added\n\n- ANSI terminal color support using `pyte` character attributes.\n- Text tags for terminal foreground/background colors.\n- Support for bold, underline, reverse video, and cursor highlighting.\n\n---\n\n## v1.3.4 - Connection Status Indicator\n\n### Added\n\n- Connection status indicator per terminal:\n  - `● Connected`\n  - `● Connecting`\n  - `● Disconnected`\n- Status color:\n  - Green for connected\n  - Orange for connecting\n  - Red for disconnected\n\n### Improved\n\n- SSH sessions are checked periodically.\n- Dropped connections are shown visually.\n- Reconnect changes status back through connecting to connected.\n\n### Purpose\n\nMake it obvious when a terminal session needs reconnecting.\n\n---\n\n## v1.3.5 - High Contrast Terminal Colors\n\n### Fixed\n\n- Some `htop` and `uwsgitop` colors were too dark.\n- Processor numbers, users, and dim values were hard to read.\n\n### Improved\n\n- Dark gray / black foreground values are remapped to readable light gray/white.\n- Contrast protection checks foreground/background contrast.\n- If contrast is too low, text is forced brighter.\n\n### Purpose\n\nImprove readability of colored terminal applications on black background.\n\n---\n\n## v1.3.6 - Focus, Close, and Quick Command Behavior Fixes\n\n### Fixed\n\n- Quick Commands were sometimes sent to the wrong terminal.\n- Focus button did not correctly make a terminal active.\n- Top toolbar buttons did not always act on the correct terminal.\n- Close button inside a terminal closed the pane but did not destroy the tab when it was the last terminal.\n- App could keep references to closed terminals.\n- Active terminal highlighting could become stale.\n\n### Improved\n\n- Focus now updates:\n  - Current terminal\n  - Current tab\n  - App-level focused terminal reference\n  - Active visual state\n- Quick commands now send to the actual focused terminal.\n- Top toolbar actions now use the focused terminal or current tab correctly.\n- Closing the last terminal in a tab closes and destroys the entire tab.\n- Console cleanup is more complete.\n\n### Current Status\n\nThis is the current stable version.\n\n---\n\n## v1.3.7 - Built-in Documentation Viewer\n\n### Added\n\n- Built-in documentation viewer inside the app.\n- Documentation section in the sidebar.\n- In-app Markdown rendering for README and VERSION_HISTORY files.\n- Search box inside the documentation viewer.\n- Reload documentation button.\n- Open documentation folder button.\n- PyInstaller-compatible document discovery.\n- Embedded fallback Markdown content when external files are not found.\n\n### Improved\n\n- The app can now ship with its own documentation as part of the Windows `.exe` build.\n\n---\n\n## v1.3.8 - Smart Grid Split Layouts\n\n### Fixed\n\n- Open 3 Split no longer creates a long single-line layout.\n- Open 4 Split no longer creates four narrow vertical panes.\n\n### Added / Improved\n\n- Open 3 Split now creates two panes on the top row and one full-width pane on the bottom row.\n- Open 4 Split now creates a 2 x 2 square grid.\n- Manual Vertical Split and Horizontal Split actions still work and can override the auto-grid layout.\n- Pane cleanup was adjusted to work with the new grid layout system.\n\n---\n\n## v1.3.9 - Layout Manager\n\n### Added\n\n- Explicit Layout Manager buttons in the sidebar.\n- 2-pane side-by-side layout.\n- 2-pane stacked layout.\n- 3-pane layout with two panes on top and one full-width pane on the bottom.\n- 3-pane layout with one full-width pane on top and two panes on the bottom.\n- 4-pane 2 x 2 grid layout.\n- Auto Layout mode to choose the best layout based on pane count.\n\n### Improved\n\n- Existing panes can now be rearranged without reopening SSH sessions.\n- Open 3 Split and Open 4 Split still default to the smart layouts introduced in v1.3.8.\n- Manual layout controls are now clearer and more specific than the old Vertical/Horizontal split buttons.\n\n---\n\n## v1.4.0 - Web2py Monitoring Dashboard\n\n### Added\n\n- Monitoring Dashboard window.\n- Server health check using non-interactive SSH command execution.\n- CPU/load card.\n- RAM card.\n- Disk `/` card.\n- Web2py process card.\n- uWSGI process card.\n- Recent error count card.\n- Top CPU process card.\n- Top memory process card.\n- Auto-refresh controls.\n- Monitoring sidebar section.\n- Health check quick action.\n- Recent errors quick action.\n- Web2py/uWSGI process quick action.\n\n### Notes\n\n- The dashboard does not scrape data from `htop`; it runs direct non-interactive shell commands and parses the results.\n- This makes the dashboard more useful for quick alerts and summaries.\n- `htop` and `uwsgitop` remain available as Quick Commands for live terminal monitoring.\n\n---\n\n\n---\n\n## v1.4.1 - Web Host Monitoring Dashboard Upgrade\n\n### Added\n\n- Overall Web Host Risk card.\n- 502 / Gateway Risk card.\n- Swap Usage card.\n- Disk Web2py card.\n- Web Connections card.\n- Active Users / IPs card.\n- Login/User Events card.\n- uWSGI Workers card using `/tmp/stats.socket` when available.\n- uWSGI Health card with exceptions, harakiri, respawns, RSS, and average response time when available.\n- Nginx Status card.\n- Web2py/uWSGI CPU card.\n- Monitoring quick actions for 502/gateway checks, connection checks, and active user/client IP checks.\n\n### Improved\n\n- Dashboard now evaluates conditions that can lead to web host instability or 502 Bad Gateway responses.\n- Monitoring health command now checks Linux load, memory, swap, disk, connections, Nginx logs, Web2py logs, and uWSGI worker saturation.\n- Web2py logs are scanned for recent errors, tracebacks, exceptions, tickets, failed events, login/auth/user events, and client IP load.\n- Nginx logs are scanned for 502/504, bad gateway, upstream timeout, upstream prematurely closed connection, refused connections, and no live upstreams.\n- Worker saturation warnings are based on busy/total uWSGI worker ratio when stats socket data is available.\n\n### Purpose\n\nHelp detect early warning signs before the web server reaches a state where users begin seeing `502 Bad Gateway`, Nginx upstream errors, overloaded workers, or resource saturation on Linux.\n\n---\n\n# Current Stable Version\n\n```text\nv1.4.1\n```\n\n---\n\n# Full Version Summary\n\n| Version | Summary |\n|---|---|\n| v1.0 | Initial embedded SSH GUI with saved profiles and basic console opening |\n| v1.1 | Tab rename, tab close, reconnect |\n| v1.2 | Quick Commands |\n| v1.3 | Modern CustomTkinter UI refresh |\n| v1.3.1 | Fixed CustomTkinter scrollable sidebar crash |\n| v1.3.2 | Safer tab close handling |\n| v1.3.3 | Full tab destruction fix and ANSI color support |\n| v1.3.4 | Connection status indicator |\n| v1.3.5 | High-contrast terminal color fix |\n| v1.3.6 | Focus, close, toolbar, and quick command behavior fixes |\n| v1.3.7 | Built-in README and version history viewer |\n| v1.3.8 | Smart grid split layouts for 3 and 4 panes |\n| v1.3.9 | Layout Manager controls for 2, 3, and 4 pane layouts |\n| v1.4.0 | Web2py Monitoring Dashboard |\n| v1.4.1 | Web Host Monitoring Dashboard upgrade |', 'VERSION_HISTORY_Embedded_SSH_Launcher.md': '# Embedded SSH Console Launcher - Version History\n\nThis file tracks the project evolution from the first working concept through the current stable version.\n\n---\n\n## v1.0 - Initial Working GUI\n\n### Goal\n\nCreate a small Windows GUI that can save SSH connection information and open SSH consoles quickly.\n\n### Main Features\n\n- Tkinter-based GUI.\n- Save SSH profiles.\n- Store host, user, port, and password.\n- Open SSH sessions using `plink.exe`.\n- Support opening multiple consoles.\n- Basic tab and split-pane workflow.\n- Automatic password login.\n- Basic terminal output display.\n\n### Notes\n\nThis version proved that the core workflow was possible:\n\n```text\nSave profile -> Select profile -> Open console quickly\n```\n\n---\n\n## v1.1 - Tabs, Rename, Close, and Reconnect\n\n### Added\n\n- Rename current tab.\n- Double-click tab to rename.\n- `×` symbol in tab title.\n- Click `×` to close a tab.\n- Reconnect button per console.\n- Reconnect selected console from the sidebar.\n- Better session lifecycle handling.\n\n### Fixed / Improved\n\n- Added better control over individual SSH panes.\n- Added reconnect behavior without needing to close and reopen the whole app.\n\n---\n\n## v1.2 - Quick Commands\n\n### Added\n\n- Quick Commands section.\n- Add custom command buttons.\n- Edit saved commands.\n- Delete saved commands.\n- Run command in focused terminal.\n- General Clear Console command.\n- Default commands:\n  - `htop`\n  - `cd /home/www-data/web2py/`\n  - `tail -f web2py.log`\n  - `sudo uwsgitop /tmp/stats.socket`\n  - `clear`\n\n### Files Added\n\n```text\n%APPDATA%\\EmbeddedSSHLauncher\\commands.json\n```\n\n### Purpose\n\nReduce repetitive typing for common admin commands.\n\n---\n\n## v1.3 - Modern UI Refresh\n\n### Added\n\n- CustomTkinter UI.\n- Modern dark theme.\n- Rounded buttons.\n- Better sidebar layout.\n- Top toolbar.\n- Modern connection/profile form.\n- Quick command buttons instead of only listbox style.\n- Improved spacing.\n- Status bar.\n- Active terminal visual highlight.\n\n### Dependencies Added\n\n```powershell\npip install customtkinter\n```\n\n### Notes\n\nThis version modernized the appearance while keeping the working SSH and terminal backend.\n\n---\n\n## v1.3.1 - CustomTkinter Startup Fix\n\n### Fixed\n\n- `CTkScrollableFrame.grid_propagate(False)` startup crash.\n\n### Cause\n\n`CTkScrollableFrame.grid_propagate()` does not accept `False` like a normal Tkinter frame.\n\n### Fix\n\nUse:\n\n```python\nself.sidebar.configure(width=320)\n```\n\ninstead of:\n\n```python\nself.sidebar.grid_propagate(False)\n```\n\nfor CustomTkinter scrollable frames.\n\n---\n\n## v1.3.2 - Safer Tab Close Handling\n\n### Fixed\n\n- Accidental tab closing when clicking or selecting terminal text.\n- Fake `×` tab close area was too aggressive.\n\n### Added\n\n- Press/release tracking for tab close.\n- Smaller close zone.\n- Close only if press and release both happen on the `×` area.\n- Ignore drag/focus/select actions.\n\n### Methods Added / Updated\n\n- `get_tab_close_candidate`\n- `on_notebook_button_press`\n- `on_notebook_button_release`\n\n---\n\n## v1.3.3 - Tab Destruction and Terminal Color Support\n\n### Fixed\n\n- Closed tabs could remain visible or not disappear.\n- Notebook tab was being forgotten but not fully destroyed.\n- Old tab references could remain in memory.\n- SSH processes could remain alive after closing a tab.\n\n### Improved\n\n- Fully destroy tab frame after closing.\n- Close all SSH panes inside a tab before removing the tab.\n- Clear active/focused terminal references when closing tabs.\n- Delay close using `after(1, ...)` so notebook finishes processing click events first.\n\n### Added\n\n- ANSI terminal color support using `pyte` character attributes.\n- Text tags for terminal foreground/background colors.\n- Support for bold, underline, reverse video, and cursor highlighting.\n\n---\n\n## v1.3.4 - Connection Status Indicator\n\n### Added\n\n- Connection status indicator per terminal:\n  - `● Connected`\n  - `● Connecting`\n  - `● Disconnected`\n- Status color:\n  - Green for connected\n  - Orange for connecting\n  - Red for disconnected\n\n### Improved\n\n- SSH sessions are checked periodically.\n- Dropped connections are shown visually.\n- Reconnect changes status back through connecting to connected.\n\n### Purpose\n\nMake it obvious when a terminal session needs reconnecting.\n\n---\n\n## v1.3.5 - High Contrast Terminal Colors\n\n### Fixed\n\n- Some `htop` and `uwsgitop` colors were too dark.\n- Processor numbers, users, and dim values were hard to read.\n\n### Improved\n\n- Dark gray / black foreground values are remapped to readable light gray/white.\n- Contrast protection checks foreground/background contrast.\n- If contrast is too low, text is forced brighter.\n\n### Purpose\n\nImprove readability of colored terminal applications on black background.\n\n---\n\n## v1.3.6 - Focus, Close, and Quick Command Behavior Fixes\n\n### Fixed\n\n- Quick Commands were sometimes sent to the wrong terminal.\n- Focus button did not correctly make a terminal active.\n- Top toolbar buttons did not always act on the correct terminal.\n- Close button inside a terminal closed the pane but did not destroy the tab when it was the last terminal.\n- App could keep references to closed terminals.\n- Active terminal highlighting could become stale.\n\n### Improved\n\n- Focus now updates:\n  - Current terminal\n  - Current tab\n  - App-level focused terminal reference\n  - Active visual state\n- Quick commands now send to the actual focused terminal.\n- Top toolbar actions now use the focused terminal or current tab correctly.\n- Closing the last terminal in a tab closes and destroys the entire tab.\n- Console cleanup is more complete.\n\n### Current Status\n\nThis is the current stable version.\n\n---\n\n## v1.3.7 - Built-in Documentation Viewer\n\n### Added\n\n- Built-in documentation viewer inside the app.\n- Documentation section in the sidebar.\n- In-app Markdown rendering for README and VERSION_HISTORY files.\n- Search box inside the documentation viewer.\n- Reload documentation button.\n- Open documentation folder button.\n- PyInstaller-compatible document discovery.\n- Embedded fallback Markdown content when external files are not found.\n\n### Improved\n\n- The app can now ship with its own documentation as part of the Windows `.exe` build.\n\n---\n\n## v1.3.8 - Smart Grid Split Layouts\n\n### Fixed\n\n- Open 3 Split no longer creates a long single-line layout.\n- Open 4 Split no longer creates four narrow vertical panes.\n\n### Added / Improved\n\n- Open 3 Split now creates two panes on the top row and one full-width pane on the bottom row.\n- Open 4 Split now creates a 2 x 2 square grid.\n- Manual Vertical Split and Horizontal Split actions still work and can override the auto-grid layout.\n- Pane cleanup was adjusted to work with the new grid layout system.\n\n---\n\n## v1.3.9 - Layout Manager\n\n### Added\n\n- Explicit Layout Manager buttons in the sidebar.\n- 2-pane side-by-side layout.\n- 2-pane stacked layout.\n- 3-pane layout with two panes on top and one full-width pane on the bottom.\n- 3-pane layout with one full-width pane on top and two panes on the bottom.\n- 4-pane 2 x 2 grid layout.\n- Auto Layout mode to choose the best layout based on pane count.\n\n### Improved\n\n- Existing panes can now be rearranged without reopening SSH sessions.\n- Open 3 Split and Open 4 Split still default to the smart layouts introduced in v1.3.8.\n- Manual layout controls are now clearer and more specific than the old Vertical/Horizontal split buttons.\n\n---\n\n## v1.4.0 - Web2py Monitoring Dashboard\n\n### Added\n\n- Monitoring Dashboard window.\n- Server health check using non-interactive SSH command execution.\n- CPU/load card.\n- RAM card.\n- Disk `/` card.\n- Web2py process card.\n- uWSGI process card.\n- Recent error count card.\n- Top CPU process card.\n- Top memory process card.\n- Auto-refresh controls.\n- Monitoring sidebar section.\n- Health check quick action.\n- Recent errors quick action.\n- Web2py/uWSGI process quick action.\n\n### Notes\n\n- The dashboard does not scrape data from `htop`; it runs direct non-interactive shell commands and parses the results.\n- This makes the dashboard more useful for quick alerts and summaries.\n- `htop` and `uwsgitop` remain available as Quick Commands for live terminal monitoring.\n\n---\n\n\n---\n\n## v1.4.1 - Web Host Monitoring Dashboard Upgrade\n\n### Added\n\n- Overall Web Host Risk card.\n- 502 / Gateway Risk card.\n- Swap Usage card.\n- Disk Web2py card.\n- Web Connections card.\n- Active Users / IPs card.\n- Login/User Events card.\n- uWSGI Workers card using `/tmp/stats.socket` when available.\n- uWSGI Health card with exceptions, harakiri, respawns, RSS, and average response time when available.\n- Nginx Status card.\n- Web2py/uWSGI CPU card.\n- Monitoring quick actions for 502/gateway checks, connection checks, and active user/client IP checks.\n\n### Improved\n\n- Dashboard now evaluates conditions that can lead to web host instability or 502 Bad Gateway responses.\n- Monitoring health command now checks Linux load, memory, swap, disk, connections, Nginx logs, Web2py logs, and uWSGI worker saturation.\n- Web2py logs are scanned for recent errors, tracebacks, exceptions, tickets, failed events, login/auth/user events, and client IP load.\n- Nginx logs are scanned for 502/504, bad gateway, upstream timeout, upstream prematurely closed connection, refused connections, and no live upstreams.\n- Worker saturation warnings are based on busy/total uWSGI worker ratio when stats socket data is available.\n\n### Purpose\n\nHelp detect early warning signs before the web server reaches a state where users begin seeing `502 Bad Gateway`, Nginx upstream errors, overloaded workers, or resource saturation on Linux.\n\n---\n\n# Current Stable Version\n\n```text\nv1.4.1\n```\n\n---\n\n# Full Version Summary\n\n| Version | Summary |\n|---|---|\n| v1.0 | Initial embedded SSH GUI with saved profiles and basic console opening |\n| v1.1 | Tab rename, tab close, reconnect |\n| v1.2 | Quick Commands |\n| v1.3 | Modern CustomTkinter UI refresh |\n| v1.3.1 | Fixed CustomTkinter scrollable sidebar crash |\n| v1.3.2 | Safer tab close handling |\n| v1.3.3 | Full tab destruction fix and ANSI color support |\n| v1.3.4 | Connection status indicator |\n| v1.3.5 | High-contrast terminal color fix |\n| v1.3.6 | Focus, close, toolbar, and quick command behavior fixes |\n| v1.3.7 | Built-in README and version history viewer |\n| v1.3.8 | Smart grid split layouts for 3 and 4 panes |\n| v1.3.9 | Layout Manager controls for 2, 3, and 4 pane layouts |\n| v1.4.0 | Web2py Monitoring Dashboard |\n| v1.4.1 | Web Host Monitoring Dashboard upgrade |', 'FEATURES_PLAN.md': '# FEATURES_PLAN.md\n\n# Embedded SSH Console Launcher - Future Features Plan\n\n**Current stable version:** v1.4.1  \n**Planning document created for:** local Git/project tracking\n\nThis document tracks future improvements, proposed versions, and implementation ideas for the Embedded SSH Console Launcher app.\n\n---\n\n## Current App Status\n\nThe app currently supports:\n\n- Saved SSH profiles\n- Automatic login through `plink.exe`\n- Embedded SSH terminals\n- Tabs\n- Split panes\n- Smart split layouts for 3 and 4 panes\n- Quick command buttons\n- Modern CustomTkinter UI\n- Terminal ANSI color support\n- High-contrast terminal colors\n- Connection status indicators\n- Built-in documentation viewer\n- README and VERSION_HISTORY Markdown files\n- PyInstaller packaging support\n\n---\n\n## v1.3.9 - Layout Manager ✅ Implemented\n\n### Goal\n\nImprove split-pane control and make layouts easier to manage.\n\n### Planned Features\n\n- Add explicit layout buttons:\n  - 1 pane\n  - 2 vertical\n  - 2 horizontal\n  - 3 layout: 2 top / 1 bottom\n  - 3 layout: 1 top / 2 bottom\n  - 4 layout: 2 x 2 grid\n- Allow changing the current tab layout after consoles are already open.\n- Allow moving panes between layout positions.\n- Add visual labels or borders for active pane position.\n\n### Notes\n\nThis is the most logical next step because split panes are central to the workflow.\n\n---\n\n## v1.4.0 - Web2py Monitoring Dashboard ✅ Implemented\n\n### Goal\n\nAdd a monitoring dashboard focused on Web2py/uWSGI server health instead of relying only on visual terminal tools like `htop` and `uwsgitop`.\n\n### Planned Features\n\n- Health Check button.\n- CPU, RAM, Disk, and Load cards.\n- Web2py process count card.\n- uWSGI process/status card.\n- Recent errors and tracebacks quick checks.\n- Optional auto-refresh interval.\n- Warning/critical thresholds.\n\n### Possible Commands\n\n```bash\nuptime\nfree -m\ndf -h /\npgrep -af web2py | wc -l\npgrep -af uwsgi | wc -l\ngrep -i error web2py.log | tail -n 50\ngrep -i traceback web2py.log | tail -n 50\n```\n\n### Implemented in v1.4.0\n\n- Monitoring Dashboard window.\n- Server health check using non-interactive SSH command execution.\n- CPU/load, RAM, Disk, Web2py, uWSGI, Recent Errors, Top CPU, and Top Memory cards.\n- Auto-refresh controls.\n- Monitoring sidebar section.\n- Health check, recent errors, and Web2py/uWSGI process quick actions.\n\n### Notes\n\nThe dashboard executes non-interactive commands and parses the results into cards. It does not try to scrape values from the `htop` screen.\n\n---\n\n\n---\n\n## v1.4.1 - Web Host Monitoring Dashboard Upgrade ✅ Implemented\n\n### Goal\n\nImprove the dashboard so it can identify web host instability, overloaded workers, excessive user/client traffic, connection spikes, and possible 502 Bad Gateway conditions.\n\n### Implemented\n\n- Overall Web Host Risk card.\n- 502 / Gateway Risk detection.\n- Connection load detection.\n- Active users/client IP estimation from Web2py logs.\n- Login/user event count from Web2py logs.\n- Nginx status and Nginx gateway/upstream log checks.\n- uWSGI worker saturation detection from `/tmp/stats.socket` when available.\n- uWSGI exceptions, harakiri, respawn, RSS, and average response time checks.\n- Web2py/uWSGI top CPU view.\n- Monitoring quick buttons for gateway, connections, users/IPs, errors, and processes.\n\n### Next Monitoring Improvements\n\n- Make thresholds configurable per profile.\n- Add persistent monitoring history.\n- Add popup alerts when risk becomes critical.\n- Add per-profile Web2py path and uWSGI socket settings.\n\n---\n\n## v1.4.2 - Monitoring Alerts and Threshold Settings\n\n### Goal\n\nMake the Monitoring Dashboard more actionable by adding configurable thresholds and clearer warnings.\n\n### Planned Features\n\n- Configurable warning and critical thresholds.\n- CPU/load thresholds.\n- RAM thresholds.\n- Disk thresholds.\n- Recent error thresholds.\n- Visual alert banner.\n- Optional popup notification for critical states.\n\n---\n\n## v1.4.2 - Command Groups\n\n### Goal\n\nOrganize Quick Commands into categories instead of one long list.\n\n### Planned Groups\n\n- Monitoring\n- Web2py\n- Logs\n- Services\n- Database\n- Docker\n- Custom\n\n### Planned Features\n\n- Add command group selector.\n- Save command groups to `commands.json`.\n- Let each command belong to a group.\n- Filter visible quick commands by selected group.\n- Add group management:\n  - Add group\n  - Rename group\n  - Delete group\n\n---\n\n## v1.4.3 - Run Command on Multiple Panes\n\n### Goal\n\nAllow commands to be executed across multiple terminals.\n\n### Planned Features\n\nRun command on:\n\n- Focused terminal only\n- All panes in current tab\n- All tabs\n- Selected panes only\n\n### Safety Options\n\n- Confirm before running on multiple panes.\n- Highlight target panes before sending command.\n- Add a setting for command execution mode:\n  - Run immediately\n  - Paste only\n  - Ask before run\n\n---\n\n## v1.4.4 - Auto Layout per Profile\n\n### Goal\n\nAllow a saved SSH profile to automatically open with a predefined layout.\n\n### Planned Features\n\nProfile settings:\n\n- Default layout:\n  - 1 pane\n  - 2 panes\n  - 3 panes\n  - 4 panes\n- Default commands per pane.\n- Open profile and automatically run:\n  - `htop`\n  - `tail -f web2py.log`\n  - `sudo uwsgitop /tmp/stats.socket`\n  - custom commands\n\n### Example\n\nA profile could open 4 panes automatically:\n\n| Pane | Command |\n|---|---|\n| Top left | `htop` |\n| Top right | `tail -f web2py.log` |\n| Bottom left | `sudo uwsgitop /tmp/stats.socket` |\n| Bottom right | shell prompt |\n\n---\n\n## v1.4.5 - Auto Reconnect\n\n### Goal\n\nReconnect dropped SSH sessions automatically or semi-automatically.\n\n### Planned Features\n\n- Per-profile auto reconnect setting.\n- Global auto reconnect setting.\n- Retry interval setting.\n- Max retry count.\n- Visual retry counter.\n- Status messages:\n  - Disconnected\n  - Reconnecting\n  - Retry failed\n  - Reconnected\n\n### Safety\n\nAuto reconnect should be optional because some commands may not resume safely.\n\n---\n\n## v1.4.6 - Export / Import\n\n### Goal\n\nMake it easy to move settings between PCs.\n\n### Planned Features\n\nExport:\n\n- Profiles without passwords\n- Profiles with encrypted backup option\n- Commands\n- Layouts\n- App settings\n\nImport:\n\n- Merge with existing config\n- Replace existing config\n- Preview import before applying\n\n### Files\n\nPossible export format:\n\n```text\nssh_launcher_backup.json\n```\n\n---\n\n## v1.5.0 - SSH Key Support\n\n### Goal\n\nSupport safer authentication through SSH keys.\n\n### Planned Features\n\n- Add key file field to profile.\n- Support `.ppk` for PuTTY/plink.\n- Support OpenSSH private key if using Windows OpenSSH later.\n- Support passphrase prompt.\n- Allow password or key auth per profile.\n\n### Benefits\n\n- Better security.\n- Faster login.\n- Less reliance on saved passwords.\n\n---\n\n## v1.5.1 - Session Logging\n\n### Goal\n\nAllow terminal output to be saved locally.\n\n### Planned Features\n\n- Enable/disable logging per terminal.\n- Save logs by date/profile/tab.\n- Add log folder shortcut.\n- Add log retention setting.\n- Optional command history file.\n\n### Example Path\n\n```text\n%APPDATA%\\EmbeddedSSHLauncher\\logs\\\n```\n\n---\n\n## v1.5.2 - Terminal Search\n\n### Goal\n\nSearch inside terminal output.\n\n### Planned Features\n\n- Search text in focused terminal.\n- Highlight matches.\n- Next / previous result.\n- Case-sensitive toggle.\n- Regex toggle.\n\n---\n\n## v1.6.0 - Packaged Windows App / Installer\n\n### Goal\n\nMake deployment easier.\n\n### Planned Features\n\n- One-click build script.\n- Include `plink.exe`.\n- Include README and VERSION_HISTORY.\n- Include app icon.\n- Create Start Menu shortcut.\n- Optional installer using Inno Setup or NSIS.\n\n### Recommended Build Command\n\n```powershell\npyinstaller --onefile --windowed `\n  --add-binary "plink.exe;." `\n  --add-data "README_Embedded_SSH_Launcher.md;." `\n  --add-data "VERSION_HISTORY_Embedded_SSH_Launcher.md;." `\n  SSH_Console_Launcher_v1_3_8.py\n```\n\n---\n\n## v2.0.0 - Full Terminal Engine Upgrade\n\n### Goal\n\nReplace `tk.Text + pyte` terminal rendering with a more complete terminal frontend.\n\n### Possible Approaches\n\n- WebView + xterm.js\n- Qt + terminal widget\n- Embedded Windows Terminal approach if possible\n- Dedicated terminal emulator component\n\n### Benefits\n\n- Better `vim`, `nano`, `htop`, mouse support, colors, resizing, alternate screen behavior.\n- More accurate terminal emulation.\n\n### Notes\n\nThis is a larger architecture change and should be considered after the current Tk/CustomTkinter version is stable.\n\n---\n\n# Priority Recommendation\n\nRecommended next development order:\n\n1. v1.4.1 - Monitoring Alerts and Threshold Settings\n2. v1.4.2 - Command Groups\n3. v1.4.3 - Run Command on Multiple Panes\n4. v1.4.4 - Auto Layout per Profile\n5. v1.4.5 - Auto Reconnect\n6. v1.4.6 - Export / Import\n7. v1.5.0 - SSH Key Support\n8. v1.6.0 - Packaged Installer\n9. v2.0.0 - Full Terminal Engine Upgrade\n\n---\n\n# Backlog Ideas\n\n- App settings page.\n- Theme selector.\n- Font size selector.\n- Terminal font selector.\n- Save window size and position.\n- Save last opened tabs.\n- Confirm before closing active sessions.\n- Add keyboard shortcuts.\n- Add command search.\n- Add profile search.\n- Add profile folders/groups.\n- Add environment variables per profile.\n- Add per-profile notes.\n- Add documentation search improvements.\n- Add update checker if published in Git.'}


def app_base_dir() -> Path:
    """Return the folder beside the script or beside the frozen .exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def pyinstaller_resource_dir() -> Path | None:
    """Return PyInstaller's temporary resource dir when running as a one-file .exe."""
    resource_dir = getattr(sys, "_MEIPASS", None)
    if resource_dir:
        return Path(resource_dir)
    return None


def find_document_path(filename: str) -> Path | None:
    """Find a bundled or external documentation file.

    v1.4.0 standardizes repo docs as README.md, VERSION_HISTORY.md,
    and FEATURES_PLAN.md, but keeps compatibility with the older
    README_Embedded_SSH_Launcher.md and VERSION_HISTORY_Embedded_SSH_Launcher.md
    filenames.
    """
    possible_names = DOC_ALIASES.get(filename, [filename])

    resource_dir = pyinstaller_resource_dir()

    for name in possible_names:
        candidates = [
            app_base_dir() / name,
            CONFIG_DIR / name,
        ]

        if resource_dir is not None:
            candidates.insert(1, resource_dir / name)

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

    return None


def find_image_path(filename: str) -> Path | None:
    """Find a bundled or external image asset (icon/logo) under image/."""
    resource_dir = pyinstaller_resource_dir()

    candidates = [app_base_dir() / "image" / filename]

    if resource_dir is not None:
        candidates.append(resource_dir / "image" / filename)

    candidates.append(app_base_dir() / filename)

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def find_ssh_config_path() -> Path | None:
    """Locate the user's OpenSSH client config file, if any."""
    candidate = Path.home() / ".ssh" / "config"
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def parse_ssh_config(path: Path) -> list[dict]:
    """Parse Host/HostName/User/Port blocks from an OpenSSH config file.

    Only fields the app can actually use today (host/user/port) are
    extracted - IdentityFile and everything else is ignored, since there's
    no SSH key auth support yet. A `Host` line naming multiple aliases
    produces one candidate per alias; any alias containing a glob character
    (`*` or `?`) is a pattern block, not a real host, and is skipped.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []

    blocks: list[dict] = []
    current: list[dict] | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" in line.split()[0]:
            key, _, value = line.partition("=")
        else:
            parts = line.split(None, 1)
            key = parts[0]
            value = parts[1] if len(parts) > 1 else ""
        key = key.strip().lower()
        value = value.strip().strip('"')

        if key == "host":
            aliases = [a for a in value.split() if "*" not in a and "?" not in a]
            current = [{"name": alias, "host": alias, "user": "", "port": 22} for alias in aliases]
            blocks.extend(current)
        elif current is None:
            continue
        elif key == "hostname":
            for entry in current:
                entry["host"] = value
        elif key == "user":
            for entry in current:
                entry["user"] = value
        elif key == "port":
            try:
                port = int(value)
            except ValueError:
                continue
            for entry in current:
                entry["port"] = port

    # Require at least a resolvable user; SSHProfile needs one, and an
    # imported entry with no `User` line isn't safely guessable.
    return [entry for entry in blocks if entry["user"]]


def load_document_text(filename: str) -> tuple[str, str]:
    """Load Markdown text and return (text, source_description)."""
    path = find_document_path(filename)
    if path is not None:
        try:
            return path.read_text(encoding="utf-8"), str(path)
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1"), str(path)
        except Exception as exc:
            fallback = EMBEDDED_DOCUMENTS.get(filename, "")
            return fallback or f"# Documentation Error\n\nCould not read {filename}.\n\n{exc}", f"embedded fallback after read error: {exc}"

    fallback = EMBEDDED_DOCUMENTS.get(filename, "")
    if fallback:
        return fallback, "embedded fallback"

    return (
        f"# Missing Documentation\n\nThe file `{filename}` was not found.\n\n"
        "Expected locations:\n\n"
        f"- `{app_base_dir() / filename}`\n"
        f"- `{CONFIG_DIR / filename}`\n"
        "- PyInstaller bundled resource folder when packaged as an `.exe`\n",
        "missing",
    )


def write_embedded_docs_to_config() -> None:
    """Ensure users can inspect documentation files in the config folder."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for filename, content in EMBEDDED_DOCUMENTS.items():
        path = CONFIG_DIR / filename
        if not path.exists():
            try:
                path.write_text(content, encoding="utf-8")
            except Exception:
                pass


@dataclass
class SSHProfile:
    name: str
    host: str
    user: str
    port: int = 22
    env_color: str = ""  # "" / "prod" / "staging" / "dev" - see ENV_TAGS
    jump_profile_name: str = ""  # "" = direct connection; otherwise another profile's .name
    health_check_command: str = ""  # "" = use the built-in MONITORING_HEALTH_COMMAND


@dataclass
class QuickCommand:
    name: str
    command: str


class ProfileStore:
    @staticmethod
    def load() -> list[SSHProfile]:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        if not CONFIG_FILE.exists():
            return []

        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return [SSHProfile(**item) for item in raw]
        except Exception:
            return []

    @staticmethod
    def save(profiles: list[SSHProfile]) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps([asdict(profile) for profile in profiles], indent=2),
            encoding="utf-8",
        )


class CommandStore:
    @staticmethod
    def default_commands() -> list[QuickCommand]:
        return [
            QuickCommand("htop", "htop"),
            QuickCommand("web2py folder", "cd /home/www-data/web2py/"),
            QuickCommand("tail web2py.log", "tail -f web2py.log"),
            QuickCommand("uwsgitop", "sudo uwsgitop /tmp/stats.socket"),
            QuickCommand("clear", "clear"),
        ]

    @staticmethod
    def load() -> list[QuickCommand]:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        if not COMMANDS_FILE.exists():
            commands = CommandStore.default_commands()
            CommandStore.save(commands)
            return commands

        try:
            raw = json.loads(COMMANDS_FILE.read_text(encoding="utf-8"))
            commands = [QuickCommand(**item) for item in raw]

            if not commands:
                commands = CommandStore.default_commands()
                CommandStore.save(commands)

            return commands
        except Exception:
            commands = CommandStore.default_commands()
            CommandStore.save(commands)
            return commands

    @staticmethod
    def save(commands: list[QuickCommand]) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        COMMANDS_FILE.write_text(
            json.dumps([asdict(command) for command in commands], indent=2),
            encoding="utf-8",
        )


class UIState:
    """Small persisted UI preferences (currently just the sidebar width)."""

    @staticmethod
    def load_sidebar_width() -> int:
        if not UI_STATE_FILE.exists():
            return DEFAULT_SIDEBAR_WIDTH
        try:
            raw = json.loads(UI_STATE_FILE.read_text(encoding="utf-8"))
            width = int(raw.get("sidebar_width", DEFAULT_SIDEBAR_WIDTH))
            return max(MIN_SIDEBAR_WIDTH, min(MAX_SIDEBAR_WIDTH, width))
        except Exception:
            return DEFAULT_SIDEBAR_WIDTH

    @staticmethod
    def save_sidebar_width(width: int) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            UI_STATE_FILE.write_text(json.dumps({"sidebar_width": width}, indent=2), encoding="utf-8")
        except Exception:
            pass


class RecentStore:
    """Persisted list of recently-opened profile names, most-recent-first."""

    @staticmethod
    def load() -> list[str]:
        if not RECENT_FILE.exists():
            return []
        try:
            raw = json.loads(RECENT_FILE.read_text(encoding="utf-8"))
            return [str(name) for name in raw][:MAX_RECENT]
        except Exception:
            return []

    @staticmethod
    def _write(names: list[str]) -> list[str]:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            RECENT_FILE.write_text(json.dumps(names, indent=2), encoding="utf-8")
        except Exception:
            pass
        return names

    @staticmethod
    def record(name: str) -> list[str]:
        names = [n for n in RecentStore.load() if n != name]
        names.insert(0, name)
        return RecentStore._write(names[:MAX_RECENT])

    @staticmethod
    def rename(old_name: str, new_name: str) -> list[str]:
        names = [new_name if n == old_name else n for n in RecentStore.load()]
        return RecentStore._write(names)

    @staticmethod
    def remove(name: str) -> list[str]:
        names = [n for n in RecentStore.load() if n != name]
        return RecentStore._write(names)


class SessionStore:
    """Persisted snapshot of open tabs/panes/layout, offered back on next launch."""

    @staticmethod
    def load() -> list[dict]:
        if not SESSION_FILE.exists():
            return []
        try:
            raw = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            return raw if isinstance(raw, list) else []
        except Exception:
            return []

    @staticmethod
    def save(tabs: list[dict]) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            SESSION_FILE.write_text(json.dumps(tabs, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def clear() -> None:
        try:
            SESSION_FILE.unlink(missing_ok=True)
        except Exception:
            pass


class MetricsHistoryStore:
    """Small local history of monitoring samples per profile, for sparklines."""

    @staticmethod
    def _load_all() -> dict[str, list[dict]]:
        if not MONITORING_HISTORY_FILE.exists():
            return {}
        try:
            raw = json.loads(MONITORING_HISTORY_FILE.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def load(profile_name: str) -> list[dict]:
        return MetricsHistoryStore._load_all().get(profile_name, [])

    @staticmethod
    def record(profile_name: str, load: float, ram_pct: float, disk_pct: float, connections: int) -> list[dict]:
        data = MetricsHistoryStore._load_all()
        samples = data.get(profile_name, [])
        samples.append({
            "ts": time.time(),
            "load": load,
            "ram_pct": ram_pct,
            "disk_pct": disk_pct,
            "connections": connections,
        })
        samples = samples[-MAX_HISTORY_SAMPLES:]
        data[profile_name] = samples

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            MONITORING_HISTORY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass
        return samples


class AuditLogStore:
    """Local, append-only log of every connection opened - who connected to what, and when.

    JSON-lines instead of a single JSON array so appending never needs to
    read/rewrite the whole (unbounded, ever-growing) file.
    """

    @staticmethod
    def record(profile: "SSHProfile") -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": time.time(),
            "profile": profile.name,
            "host": profile.host,
            "user": profile.user,
        }
        try:
            with AUDIT_LOG_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    @staticmethod
    def load(limit: int = MAX_AUDIT_ENTRIES_SHOWN) -> list[dict]:
        if not AUDIT_LOG_FILE.exists():
            return []
        entries: list[dict] = []
        try:
            for line in AUDIT_LOG_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
        except Exception:
            return []
        entries.reverse()
        return entries[:limit]


class PasswordStore:
    @staticmethod
    def key(profile_name: str) -> str:
        return profile_name

    @staticmethod
    def save(profile_name: str, password: str) -> None:
        if keyring is None:
            raise RuntimeError("keyring package is not installed")

        keyring.set_password(SERVICE_NAME, PasswordStore.key(profile_name), password)

    @staticmethod
    def get(profile_name: str) -> str | None:
        if keyring is None:
            return None

        try:
            return keyring.get_password(SERVICE_NAME, PasswordStore.key(profile_name))
        except Exception:
            return None

    @staticmethod
    def delete(profile_name: str) -> None:
        if keyring is None:
            return

        try:
            keyring.delete_password(SERVICE_NAME, PasswordStore.key(profile_name))
        except Exception:
            pass


def center_toplevel(dialog: tk.Widget, parent: tk.Widget, width: int, height: int) -> None:
    """Position a Toplevel centered over its parent, clamped to the screen bounds."""
    try:
        parent.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + max(0, (pw - width) // 2)
        y = py + max(0, (ph - height) // 2)
        screen_w, screen_h = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        x = min(max(0, x), max(0, screen_w - width))
        y = min(max(0, y), max(0, screen_h - height))
        dialog.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        dialog.geometry(f"{width}x{height}")


def show_toast(root: tk.Widget, title: str, message: str, duration_ms: int = 7000) -> None:
    """Small self-dismissing, always-on-top popup in the bottom-right corner.

    A real Windows Action Center toast needs a new third-party dependency
    (win10toast/winrt) or shelling out to PowerShell with the message text
    interpolated into a command line - a plain Tk popup avoids both and is
    good enough for "the dashboard isn't focused" style alerts.
    """
    try:
        toast = ctk.CTkToplevel(root) if ctk is not None else tk.Toplevel(root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        if ctk is not None:
            toast.configure(fg_color=PANEL)

        width, height = 320, 96
        screen_w = toast.winfo_screenwidth()
        screen_h = toast.winfo_screenheight()
        x = screen_w - width - 24
        y = screen_h - height - 64
        toast.geometry(f"{width}x{height}+{x}+{y}")

        if ctk is not None:
            frame = ctk.CTkFrame(toast, fg_color=PANEL, corner_radius=10, border_width=1, border_color=DANGER)
            frame.pack(fill="both", expand=True)
            ctk.CTkLabel(frame, text=title, text_color=DANGER, font=ctk.CTkFont(size=13, weight="bold"), wraplength=290, justify="left").pack(anchor="w", padx=14, pady=(12, 2))
            ctk.CTkLabel(frame, text=message, text_color=TEXT, font=ctk.CTkFont(size=11), wraplength=290, justify="left").pack(anchor="w", padx=14, pady=(0, 12))
        else:
            tk.Label(toast, text=f"{title}\n{message}", justify="left").pack(fill="both", expand=True)

        toast.after(duration_ms, lambda: toast.destroy() if toast.winfo_exists() else None)
    except Exception:
        pass


def ask_text(
    parent: tk.Widget,
    title: str,
    label: str,
    initial_value: str = "",
    password: bool = False,
) -> str | None:
    dialog = ctk.CTkToplevel(parent) if ctk is not None else tk.Toplevel(parent)
    dialog.title(title)
    center_toplevel(dialog, parent, 460, 180)
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    if ctk is not None:
        dialog.configure(fg_color=BG)

        frame = ctk.CTkFrame(dialog, fg_color=PANEL, corner_radius=16)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            frame,
            text=label,
            text_color=TEXT,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(16, 8))

        value_var = tk.StringVar(value=initial_value)
        entry = ctk.CTkEntry(
            frame,
            textvariable=value_var,
            show="*" if password else "",
            fg_color=CARD,
            border_color=ACCENT,
            text_color=TEXT,
            height=36,
        )
        entry.pack(fill="x", padx=16, pady=(0, 14))

        result: dict[str, str | None] = {"value": None}

        button_row = ctk.CTkFrame(frame, fg_color="transparent")
        button_row.pack(fill="x", padx=16, pady=(0, 16))

        def submit() -> None:
            result["value"] = value_var.get()
            dialog.destroy()

        def cancel() -> None:
            result["value"] = None
            dialog.destroy()

        ctk.CTkButton(
            button_row,
            text="Cancel",
            command=cancel,
            fg_color=CARD,
            hover_color=CARD_HOVER,
            text_color=TEXT,
            width=100,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            button_row,
            text="OK",
            command=submit,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            width=100,
        ).pack(side="right")

        entry.bind("<Return>", lambda _event: submit())
        entry.focus_set()
        dialog.wait_window()
        return result["value"]

    value = simpledialog.askstring(title, label, initialvalue=initial_value, show="*" if password else None)
    dialog.destroy()
    return value


_MESSAGE_KIND_STYLE = {
    "info": (ACCENT, ACCENT_HOVER, "ℹ"),
    "warning": (WARNING, WARNING_HOVER, "⚠"),
    "error": (DANGER, DANGER_HOVER, "✕"),
    "confirm": (WARNING, WARNING_HOVER, "?"),
}


def show_message(parent: tk.Widget, kind: str, title: str, text: str) -> bool | None:
    """Dark-themed replacement for tkinter.messagebox.

    kind is one of "info"/"warning"/"error"/"confirm". Returns True/False for
    "confirm" (Cancel or closing the window both mean False, mirroring
    messagebox.askyesno's falsy-on-cancel behavior); returns None otherwise.
    """
    accent, accent_hover, icon = _MESSAGE_KIND_STYLE.get(kind, _MESSAGE_KIND_STYLE["info"])
    is_confirm = kind == "confirm"

    if ctk is None:
        if is_confirm:
            return messagebox.askyesno(title, text, parent=parent)
        {"info": messagebox.showinfo, "warning": messagebox.showwarning, "error": messagebox.showerror}.get(
            kind, messagebox.showinfo
        )(title, text, parent=parent)
        return None

    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    width, height = 440, 200
    center_toplevel(dialog, parent, width, height)
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.configure(fg_color=BG)
    dialog.grab_set()

    result: dict[str, bool | None] = {"value": False if is_confirm else None}

    frame = ctk.CTkFrame(dialog, fg_color=PANEL, corner_radius=16)
    frame.pack(fill="both", expand=True, padx=16, pady=16)

    header = ctk.CTkFrame(frame, fg_color="transparent")
    header.pack(fill="x", padx=16, pady=(16, 8))
    ctk.CTkLabel(
        header,
        text=icon,
        text_color=accent,
        font=ctk.CTkFont(size=20, weight="bold"),
        width=28,
    ).pack(side="left")
    ctk.CTkLabel(
        header,
        text=title,
        text_color=TEXT,
        font=ctk.CTkFont(size=14, weight="bold"),
    ).pack(side="left", padx=(6, 0))

    ctk.CTkLabel(
        frame,
        text=text,
        text_color=TEXT,
        font=ctk.CTkFont(size=13),
        wraplength=width - 64,
        justify="left",
    ).pack(fill="both", expand=True, padx=16, pady=(0, 14))

    button_row = ctk.CTkFrame(frame, fg_color="transparent")
    button_row.pack(fill="x", padx=16, pady=(0, 16))

    def close(value: bool | None) -> None:
        result["value"] = value
        dialog.destroy()

    if is_confirm:
        ctk.CTkButton(
            button_row,
            text="No",
            command=lambda: close(False),
            fg_color=CARD,
            hover_color=CARD_HOVER,
            text_color=TEXT,
            width=90,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            button_row,
            text="Yes",
            command=lambda: close(True),
            fg_color=accent,
            hover_color=accent_hover,
            width=90,
        ).pack(side="right")
    else:
        ctk.CTkButton(
            button_row,
            text="OK",
            command=lambda: close(None),
            fg_color=accent,
            hover_color=accent_hover,
            width=90,
        ).pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", lambda: close(False if is_confirm else None))
    dialog.bind("<Return>", lambda _event: close(True if is_confirm else None))
    dialog.bind("<Escape>", lambda _event: close(False if is_confirm else None))
    dialog.focus_set()
    dialog.wait_window()
    return result["value"]


def ask_ssh_config_import(parent: tk.Widget, entries: list[dict]) -> list[dict]:
    """Show a checklist of parsed ~/.ssh/config entries; return the ones selected.

    Same CTkToplevel/grab_set()/wait_window() dialog pattern as ask_text()
    and show_message(). Returns [] if the dialog is cancelled or closed.
    """
    if ctk is None:
        return []

    dialog = ctk.CTkToplevel(parent)
    dialog.title("Import from SSH Config")
    width, height = 480, 480
    center_toplevel(dialog, parent, width, height)
    dialog.minsize(360, 300)
    dialog.transient(parent)
    dialog.configure(fg_color=BG)
    dialog.grab_set()

    result: list[dict] = []
    check_vars: list[tuple[tk.BooleanVar, dict]] = []

    frame = ctk.CTkFrame(dialog, fg_color=PANEL, corner_radius=16)
    frame.pack(fill="both", expand=True, padx=16, pady=16)

    ctk.CTkLabel(
        frame,
        text=f"Found {len(entries)} host(s) in ~/.ssh/config",
        text_color=TEXT,
        font=ctk.CTkFont(size=14, weight="bold"),
    ).pack(anchor="w", padx=16, pady=(16, 8))

    select_all_var = tk.BooleanVar(value=True)

    def toggle_all() -> None:
        for var, _entry in check_vars:
            var.set(select_all_var.get())

    ctk.CTkCheckBox(
        frame, text="Select all", variable=select_all_var, command=toggle_all, text_color=TEXT,
    ).pack(anchor="w", padx=16, pady=(0, 6))

    list_frame = ctk.CTkScrollableFrame(frame, fg_color=PANEL_DARK)
    list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    for entry in entries:
        var = tk.BooleanVar(value=True)
        label = f"{entry['name']}  ({entry['user']}@{entry['host']}:{entry['port']})"
        ctk.CTkCheckBox(list_frame, text=label, variable=var, text_color=TEXT).pack(anchor="w", pady=3)
        check_vars.append((var, entry))

    button_row = ctk.CTkFrame(frame, fg_color="transparent")
    button_row.pack(fill="x", padx=16, pady=(0, 16))

    def cancel() -> None:
        dialog.destroy()

    def do_import() -> None:
        result.extend(entry for var, entry in check_vars if var.get())
        dialog.destroy()

    ctk.CTkButton(
        button_row, text="Cancel", command=cancel, fg_color=CARD, hover_color=CARD_HOVER, text_color=TEXT, width=100,
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        button_row, text="Import Selected", command=do_import, fg_color=ACCENT, hover_color=ACCENT_HOVER, width=140,
    ).pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", cancel)
    dialog.focus_set()
    dialog.wait_window()
    return result


class MarkdownDocumentWindow(ctk.CTkToplevel if ctk is not None else tk.Toplevel):
    def __init__(self, parent: tk.Widget, initial_file: str = DOC_README_FILE):
        super().__init__(parent)
        self.parent = parent
        self.current_file = initial_file
        self.current_text = ""
        self.current_source = ""
        self.search_var = tk.StringVar()

        self.title("Documentation")
        center_toplevel(self, parent, 1050, 760)
        self.minsize(820, 560)
        self.transient(parent)

        if ctk is not None:
            self.configure(fg_color=BG)

        self._build_ui()
        self.load_document(initial_file)
        self.focus()

    def _build_ui(self) -> None:
        if ctk is not None:
            root = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        else:
            root = ttk.Frame(self)
        root.pack(fill="both", expand=True)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        if ctk is not None:
            header = ctk.CTkFrame(root, fg_color=PANEL, corner_radius=0)
            title = ctk.CTkLabel(
                header,
                text="Documentation",
                text_color=TEXT,
                font=ctk.CTkFont(size=20, weight="bold"),
            )
            subtitle = ctk.CTkLabel(
                header,
                text="README, version history, and features plan rendered inside the app",
                text_color=MUTED,
                font=ctk.CTkFont(size=12),
            )
        else:
            header = ttk.Frame(root)
            title = ttk.Label(header, text="Documentation", font=("Segoe UI", 16, "bold"))
            subtitle = ttk.Label(header, text="README, version history, and features plan rendered inside the app")

        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        title.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 0))
        subtitle.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

        if ctk is not None:
            toolbar = ctk.CTkFrame(root, fg_color=PANEL_2, corner_radius=12)
        else:
            toolbar = ttk.Frame(root)
        toolbar.grid(row=1, column=0, sticky="ew", padx=12, pady=10)
        toolbar.grid_columnconfigure(5, weight=1)

        self._doc_button(toolbar, "README", lambda: self.load_document(DOC_README_FILE), ACCENT).grid(row=0, column=0, padx=(10, 4), pady=10)
        self._doc_button(toolbar, "Version History", lambda: self.load_document(DOC_VERSION_FILE), ACCENT).grid(row=0, column=1, padx=4, pady=10)
        self._doc_button(toolbar, "Reload", self.reload_document, CARD_HOVER).grid(row=0, column=2, padx=4, pady=10)
        self._doc_button(toolbar, "Open Docs Folder", self.open_docs_folder, CARD_HOVER).grid(row=0, column=3, padx=4, pady=10)
        self._doc_button(toolbar, "Export Docs", self.export_docs_to_config, SUCCESS).grid(row=0, column=4, padx=4, pady=10)

        if ctk is not None:
            search = ctk.CTkEntry(
                toolbar,
                textvariable=self.search_var,
                placeholder_text="Search in document...",
                fg_color=PANEL,
                border_color="#334155",
                text_color=TEXT,
                height=34,
                corner_radius=10,
            )
        else:
            search = ttk.Entry(toolbar, textvariable=self.search_var)
        search.grid(row=0, column=5, sticky="ew", padx=(12, 4), pady=10)
        search.bind("<Return>", lambda _event: self.highlight_search())
        self._doc_button(toolbar, "Search", self.highlight_search, WARNING).grid(row=0, column=6, padx=(4, 10), pady=10)

        body = ttk.Frame(root)
        body.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 8))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        self.text = tk.Text(
            body,
            wrap="word",
            bg=PANEL_DARK,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground=CARD_HOVER,
            font=("Segoe UI", 11),
            padx=24,
            pady=18,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=y_scroll.set)

        self.status_var = tk.StringVar(value="Ready")
        if ctk is not None:
            status = ctk.CTkLabel(root, textvariable=self.status_var, text_color=MUTED, font=ctk.CTkFont(size=11))
        else:
            status = ttk.Label(root, textvariable=self.status_var)
        status.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))

        self.configure_markdown_tags()

    def _doc_button(self, parent: tk.Widget, text: str, command, color: str):
        if ctk is not None:
            return build_button(parent, text, command, color)
        return ttk.Button(parent, text=text, command=command)

    def configure_markdown_tags(self) -> None:
        self.text.tag_configure("h1", font=("Segoe UI", 22, "bold"), foreground="#ffffff", spacing1=14, spacing3=10)
        self.text.tag_configure("h2", font=("Segoe UI", 18, "bold"), foreground="#dbeafe", spacing1=14, spacing3=8)
        self.text.tag_configure("h3", font=("Segoe UI", 15, "bold"), foreground="#bfdbfe", spacing1=10, spacing3=6)
        self.text.tag_configure("normal", font=("Segoe UI", 11), foreground=TEXT, spacing1=2, spacing3=5)
        self.text.tag_configure("muted", foreground=MUTED)
        self.text.tag_configure("bullet", lmargin1=32, lmargin2=48, foreground=TEXT, spacing3=3)
        self.text.tag_configure("code", font=("Cascadia Mono", 10), foreground="#e2e8f0", background=PANEL, lmargin1=18, lmargin2=18, spacing1=3, spacing3=3)
        self.text.tag_configure("inline_code", font=("Cascadia Mono", 10), foreground=HIGHLIGHT_CODE)
        self.text.tag_configure("rule", foreground=CARD_HOVER_2, spacing1=8, spacing3=8)
        self.text.tag_configure("table", font=("Cascadia Mono", 10), foreground="#d1d5db", background=PANEL, spacing1=2, spacing3=2)
        self.text.tag_configure("quote", foreground="#cbd5e1", background=PANEL_QUOTE, lmargin1=20, lmargin2=30, spacing1=4, spacing3=4)
        self.text.tag_configure("search", background=HIGHLIGHT_SEARCH, foreground=PANEL)

    def load_document(self, filename: str) -> None:
        self.current_file = filename
        text, source = load_document_text(filename)
        self.current_text = text
        self.current_source = source
        self.render_markdown(text)
        self.status_var.set(f"Showing {filename} | Source: {source}")

    def reload_document(self) -> None:
        self.load_document(self.current_file)

    def render_markdown(self, markdown_text: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")

        in_code = False
        code_buffer: list[str] = []

        def flush_code() -> None:
            if code_buffer:
                self.text.insert("end", "\n".join(code_buffer).rstrip() + "\n", "code")
                code_buffer.clear()

        for raw_line in markdown_text.splitlines():
            line = raw_line.rstrip("\n")

            if line.strip().startswith("```"):
                if in_code:
                    flush_code()
                    in_code = False
                else:
                    in_code = True
                continue

            if in_code:
                code_buffer.append(line)
                continue

            stripped = line.strip()
            if not stripped:
                self.text.insert("end", "\n", "normal")
                continue

            if stripped == "---" or stripped.startswith("***"):
                self.text.insert("end", "─" * 90 + "\n", "rule")
                continue

            if stripped.startswith("### "):
                self.text.insert("end", stripped[4:] + "\n", "h3")
            elif stripped.startswith("## "):
                self.text.insert("end", stripped[3:] + "\n", "h2")
            elif stripped.startswith("# "):
                self.text.insert("end", stripped[2:] + "\n", "h1")
            elif stripped.startswith(">"):
                self.text.insert("end", stripped.lstrip("> ") + "\n", "quote")
            elif stripped.startswith("- ") or stripped.startswith("* "):
                self.text.insert("end", "• " + stripped[2:] + "\n", "bullet")
            elif re.match(r"^\d+\.\s+", stripped):
                self.text.insert("end", stripped + "\n", "bullet")
            elif stripped.startswith("|") and stripped.endswith("|"):
                self.text.insert("end", stripped + "\n", "table")
            else:
                self.insert_inline_markdown(stripped + "\n")

        if in_code:
            flush_code()

        self.text.configure(state="disabled")
        self.text.see("1.0")

    def insert_inline_markdown(self, text: str) -> None:
        # Minimal inline rendering for backtick code and bold markers.
        pos = 0
        pattern = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*)")
        for match in pattern.finditer(text):
            if match.start() > pos:
                self.text.insert("end", text[pos:match.start()], "normal")
            token = match.group(0)
            if token.startswith("`"):
                self.text.insert("end", token.strip("`"), "inline_code")
            elif token.startswith("**"):
                self.text.insert("end", token.strip("*"), "h3")
            pos = match.end()
        if pos < len(text):
            self.text.insert("end", text[pos:], "normal")

    def highlight_search(self) -> None:
        self.text.configure(state="normal")
        self.text.tag_remove("search", "1.0", "end")
        query = self.search_var.get().strip()
        if not query:
            self.text.configure(state="disabled")
            return

        start = "1.0"
        count = 0
        while True:
            index = self.text.search(query, start, stopindex="end", nocase=True)
            if not index:
                break
            end = f"{index}+{len(query)}c"
            self.text.tag_add("search", index, end)
            if count == 0:
                self.text.see(index)
            count += 1
            start = end
        self.text.configure(state="disabled")
        self.status_var.set(f"Found {count} match(es) for: {query}")

    def open_docs_folder(self) -> None:
        path = find_document_path(self.current_file)
        folder = path.parent if path is not None else app_base_dir()
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except Exception as exc:
            show_message(self, "error", APP_NAME, f"Could not open documentation folder.\n\n{exc}")

    def export_docs_to_config(self) -> None:
        write_embedded_docs_to_config()
        show_message(self, "info", APP_NAME, f"Documentation exported to:\n\n{CONFIG_DIR}")
        self.status_var.set(f"Documentation exported to {CONFIG_DIR}")



class MonitoringDashboardWindow(ctk.CTkToplevel if ctk is not None else tk.Toplevel):
    def __init__(self, app: "EmbeddedSSHLauncher"):
        super().__init__(app)
        self.app = app
        self.title("Web Host Monitoring Dashboard")
        self.geometry("1180x820")
        self.minsize(960, 660)
        self.transient(app)

        if ctk is not None:
            self.configure(fg_color=BG)

        self.profile: SSHProfile | None = self.app.get_monitoring_profile()
        self.auto_refresh_enabled = tk.BooleanVar(value=False)
        self.refresh_seconds = tk.IntVar(value=15)
        self.auto_refresh_after_id: str | None = None
        self.last_metrics: dict[str, str] = {}
        self.notify_enabled = tk.BooleanVar(value=True)
        self.last_overall_status = "ok"

        self.card_labels: dict[str, dict[str, object]] = {}

        self._current_columns = 4
        self._regrid_after_id: str | None = None

        self._build_ui()
        self.refresh_dashboard()

    def _build_ui(self) -> None:
        if ctk is None:
            self.text = tk.Text(self)
            self.text.pack(fill="both", expand=True)
            self.text.insert("1.0", "Monitoring Dashboard requires customtkinter for the full UI.\n")
            return

        root = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        root.pack(fill="both", expand=True)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(root, fg_color=PANEL, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Web Host Monitoring Dashboard",
            text_color=TEXT,
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=(14, 4), sticky="w")

        self.profile_label = ctk.CTkLabel(
            header,
            text=self.profile_title(),
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
        )
        self.profile_label.grid(row=1, column=0, padx=18, pady=(0, 14), sticky="w")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=2, padx=18, pady=12, sticky="e")

        build_button(actions, "Refresh", self.refresh_dashboard, ACCENT, width=90).pack(side="left", padx=4)
        build_button(actions, "Run in Terminal", self.run_health_command_in_terminal, CARD_HOVER, width=120).pack(side="left", padx=4)
        build_button(actions, "502 Check", self.run_gateway_check_in_terminal, WARNING, width=95).pack(side="left", padx=4)
        self.close_button = build_button(actions, "Close", self.on_close, DANGER, width=80)
        self.close_button.pack(side="left", padx=4)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        auto = ctk.CTkFrame(root, fg_color=PANEL, corner_radius=14)
        auto.grid(row=1, column=0, sticky="ew", padx=14, pady=(12, 8))
        auto.grid_columnconfigure(6, weight=1)

        ctk.CTkSwitch(auto, text="Auto refresh", variable=self.auto_refresh_enabled, command=self.toggle_auto_refresh, text_color=TEXT).grid(row=0, column=0, padx=12, pady=10, sticky="w")
        ctk.CTkLabel(auto, text="Interval", text_color=MUTED).grid(row=0, column=1, padx=(12, 4), pady=10)
        self.interval_menu = ctk.CTkOptionMenu(auto, values=["5", "10", "15", "30", "60"], command=self.set_refresh_interval, width=80)
        self.interval_menu.set(str(self.refresh_seconds.get()))
        self.interval_menu.grid(row=0, column=2, padx=4, pady=10)
        ctk.CTkLabel(auto, text="seconds", text_color=MUTED).grid(row=0, column=3, padx=(4, 12), pady=10)

        ctk.CTkSwitch(auto, text="Notify on Critical", variable=self.notify_enabled, text_color=TEXT).grid(row=0, column=4, padx=12, pady=10, sticky="w")

        self.status_label = ctk.CTkLabel(auto, text="Ready", text_color=MUTED)
        self.status_label.grid(row=0, column=5, padx=12, pady=10, sticky="w")

        body = ctk.CTkScrollableFrame(root, fg_color=BG)
        body.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
        body.grid_columnconfigure(tuple(range(self._current_columns)), weight=1)

        self.cards_frame = body
        body.bind("<Configure>", self.on_body_configure)

        card_specs = [
            ("overall", "Overall Web Host Risk", "Waiting...", MUTED),
            ("gateway", "502 / Gateway Risk", "Waiting...", MUTED),
            ("load", "Load Average", "Waiting...", MUTED),
            ("ram", "RAM Usage", "Waiting...", MUTED),
            ("swap", "Swap Usage", "Waiting...", MUTED),
            ("disk", "Disk /", "Waiting...", MUTED),
            ("webdisk", "Disk Web2py", "Waiting...", MUTED),
            ("connections", "Web Connections", "Waiting...", MUTED),
            ("clients", "Active Users / IPs", "Waiting...", MUTED),
            ("uwsgi_workers", "uWSGI Workers", "Waiting...", MUTED),
            ("uwsgi_health", "uWSGI Health", "Waiting...", MUTED),
            ("web2py", "Web2py Processes", "Waiting...", MUTED),
            ("nginx", "Nginx Status", "Waiting...", MUTED),
            ("errors", "Recent Errors", "Waiting...", MUTED),
            ("logins", "Login/User Events", "Waiting...", MUTED),
            ("top_cpu", "Top CPU", "Waiting...", MUTED),
            ("top_mem", "Top Memory", "Waiting...", MUTED),
            ("uwsgi_top", "Web2py/uWSGI CPU", "Waiting...", MUTED),
        ]

        sparkline_keys = ("load", "ram", "disk", "connections")

        for idx, (key, title, value, color) in enumerate(card_specs):
            card = ctk.CTkFrame(self.cards_frame, fg_color=CARD, corner_radius=16)
            card.grid(row=idx // self._current_columns, column=idx % self._current_columns, sticky="nsew", padx=8, pady=8)
            card.grid_columnconfigure(0, weight=1)

            title_label = ctk.CTkLabel(card, text=title, text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold"))
            title_label.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 2))

            value_label = ctk.CTkLabel(card, text=value, text_color=TEXT, font=ctk.CTkFont(size=19, weight="bold"), wraplength=235, justify="left")
            value_label.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 8))

            detail_label = ctk.CTkLabel(card, text="", text_color=MUTED, font=ctk.CTkFont(size=11), wraplength=235, justify="left")

            self.card_labels[key] = {"frame": card, "value": value_label, "detail": detail_label}

            if key in sparkline_keys:
                detail_label.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 4))
                sparkline = tk.Canvas(card, width=90, height=24, bg=CARD, highlightthickness=0, bd=0)
                sparkline.grid(row=3, column=0, sticky="w", padx=14, pady=(0, 12))
                self.card_labels[key]["sparkline"] = sparkline
            else:
                detail_label.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 14))

        self.raw_output = tk.Text(
            body,
            height=10,
            bg=TERMINAL_BG,
            fg=TERMINAL_FG,
            insertbackground=TERMINAL_FG,
            font=("Cascadia Mono", 9),
            wrap="none",
            borderwidth=0,
            highlightthickness=0,
        )
        self.raw_output.grid(row=len(card_specs) // self._current_columns + 1, column=0, columnspan=self._current_columns, sticky="ew", padx=8, pady=(12, 8))
        self.raw_output.insert("1.0", "Raw health-check output will appear here.\n")
        self.raw_output.configure(state="disabled")

    def on_body_configure(self, event: tk.Event) -> None:
        """Recompute the card grid's column count from available width.

        Debounced: only re-grids once the width has settled (no re-grid on
        every pixel of a drag) and only when the column count actually
        changes, so a resize doesn't thrash the layout.
        """
        columns = max(1, min(6, event.width // 260))
        if columns == self._current_columns:
            return
        if self._regrid_after_id is not None:
            try:
                self.after_cancel(self._regrid_after_id)
            except Exception:
                pass
        self._regrid_after_id = self.after(120, lambda: self.regrid_cards(columns))

    def regrid_cards(self, columns: int) -> None:
        self._regrid_after_id = None
        if not self.winfo_exists():
            return

        old_columns = self._current_columns
        self._current_columns = columns

        if old_columns > columns:
            self.cards_frame.grid_columnconfigure(tuple(range(old_columns)), weight=0)
        self.cards_frame.grid_columnconfigure(tuple(range(columns)), weight=1)

        for idx, labels in enumerate(self.card_labels.values()):
            labels["frame"].grid_configure(row=idx // columns, column=idx % columns)

        card_count = len(self.card_labels)
        if hasattr(self, "raw_output"):
            self.raw_output.grid_configure(row=card_count // columns + 1, columnspan=columns)

    def profile_title(self) -> str:
        if self.profile is None:
            return "No profile selected. Select a profile or focus an active SSH console."
        return f"{self.profile.name} - {self.profile.user}@{self.profile.host}:{self.profile.port}"

    def set_refresh_interval(self, value: str) -> None:
        try:
            self.refresh_seconds.set(int(value))
        except ValueError:
            self.refresh_seconds.set(15)
        if self.auto_refresh_enabled.get():
            self.schedule_auto_refresh()

    def toggle_auto_refresh(self) -> None:
        if self.auto_refresh_enabled.get():
            self.schedule_auto_refresh()
        elif self.auto_refresh_after_id is not None:
            try:
                self.after_cancel(self.auto_refresh_after_id)
            except Exception:
                pass
            self.auto_refresh_after_id = None

    def schedule_auto_refresh(self) -> None:
        if self.auto_refresh_after_id is not None:
            try:
                self.after_cancel(self.auto_refresh_after_id)
            except Exception:
                pass
        if self.auto_refresh_enabled.get():
            self.auto_refresh_after_id = self.after(self.refresh_seconds.get() * 1000, self.auto_refresh_tick)

    def auto_refresh_tick(self) -> None:
        self.auto_refresh_after_id = None
        if self.auto_refresh_enabled.get():
            self.refresh_dashboard()
            self.schedule_auto_refresh()

    def on_close(self) -> None:
        """Cancel the auto-refresh timer before destroying the window.

        Without this, a pending self.after() from schedule_auto_refresh() can
        fire after the window (and its widgets) are already destroyed, raising
        an unhandled TclError from the next refresh_dashboard()/set_status()
        widget .configure() call.
        """
        if self.auto_refresh_after_id is not None:
            try:
                self.after_cancel(self.auto_refresh_after_id)
            except Exception:
                pass
            self.auto_refresh_after_id = None
        if self._regrid_after_id is not None:
            try:
                self.after_cancel(self._regrid_after_id)
            except Exception:
                pass
            self._regrid_after_id = None
        if self.app.monitoring_dashboard is self:
            self.app.monitoring_dashboard = None
        self.destroy()

    def run_health_command_in_terminal(self) -> None:
        self.app.run_command_on_focused_console(resolve_health_command(self.profile))
        self.app.status_var.set("Sent advanced health-check command to focused terminal")

    def run_gateway_check_in_terminal(self) -> None:
        command = "find /var/log/nginx -type f -name '*.log' -mmin -1440 2>/dev/null | head -n 20 | xargs -r tail -n 1000 2>/dev/null | grep -iEn ' 502 | 504 |bad gateway|gateway timeout|upstream timed out|upstream prematurely|connect\\(\\) failed|no live upstreams|connection refused' | tail -n 80"
        self.app.run_command_on_focused_console(command)
        self.app.status_var.set("Sent 502/gateway risk check to focused terminal")

    def refresh_dashboard(self) -> None:
        if not self.winfo_exists():
            return

        self.profile = self.app.get_monitoring_profile()
        if hasattr(self, "profile_label"):
            self.profile_label.configure(text=self.profile_title())

        if self.profile is None:
            self.set_status("Select a profile or focus a connected terminal first.", DANGER)
            return

        self.set_status("Running advanced health check...", WARNING)
        self.set_cards_loading()

        self.app.run_remote_monitoring_command(self.profile, resolve_health_command(self.profile), callback=self.on_monitoring_result)

    def set_status(self, text: str, color: str = MUTED) -> None:
        if not self.winfo_exists():
            return
        if hasattr(self, "status_label"):
            self.status_label.configure(text=text, text_color=color)

    def set_cards_loading(self) -> None:
        if not self.winfo_exists():
            return
        for labels in self.card_labels.values():
            labels["value"].configure(text="Loading...", text_color=MUTED)
            labels["detail"].configure(text="")
            labels["frame"].configure(fg_color=CARD)

    def on_monitoring_result(self, success: bool, output: str, error: str) -> None:
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        if not success:
            self.set_status("Health check failed", DANGER)
            self.update_raw_output((output or "") + "\n" + (error or ""))
            for labels in self.card_labels.values():
                labels["value"].configure(text="Failed", text_color=DANGER)
                labels["detail"].configure(text=error[:260] if error else "Could not run remote command.")
                labels["frame"].configure(fg_color=CARD)
            return

        metrics = self.parse_health_output(output)
        self.last_metrics = metrics
        self.update_cards(metrics)
        self.record_metrics_history(metrics)
        self.update_raw_output(output)
        self.set_status("Last refresh completed", SUCCESS)

    def record_metrics_history(self, metrics: dict[str, str]) -> None:
        if not self.profile:
            return

        cores = max(1, self.as_int(metrics, "CPUCORES", 1))
        loadavg = metrics.get("LOADAVG", "")
        try:
            load1 = float(loadavg.split()[0])
        except Exception:
            load1 = 0.0

        mem = metrics.get("MEM", "")
        try:
            total, used = [float(x) for x in mem.split(",")[:2]]
            ram_pct = (used / total) * 100 if total else 0.0
        except Exception:
            ram_pct = 0.0

        disk = metrics.get("DISK_ROOT", "")
        try:
            disk_pct = float(disk.split(",")[3].replace("%", ""))
        except Exception:
            disk_pct = 0.0

        connections = self.as_int(metrics, "WEB_ESTABLISHED")

        samples = MetricsHistoryStore.record(self.profile.name, load1 / cores * 100, ram_pct, disk_pct, connections)

        series = {
            "load": [s.get("load", 0.0) for s in samples],
            "ram": [s.get("ram_pct", 0.0) for s in samples],
            "disk": [s.get("disk_pct", 0.0) for s in samples],
            "connections": [s.get("connections", 0) for s in samples],
        }
        for key, values in series.items():
            self.draw_sparkline(key, values)

    def draw_sparkline(self, key: str, values: list[float]) -> None:
        labels = self.card_labels.get(key)
        if not labels or "sparkline" not in labels:
            return
        canvas: tk.Canvas = labels["sparkline"]
        try:
            if not canvas.winfo_exists():
                return
        except Exception:
            return

        canvas.delete("all")
        if len(values) < 2:
            return

        width = int(canvas["width"])
        height = int(canvas["height"])
        pad = 2
        lo, hi = min(values), max(values)
        span = (hi - lo) or 1.0

        points: list[float] = []
        step = (width - 2 * pad) / (len(values) - 1)
        for i, v in enumerate(values):
            x = pad + i * step
            y = height - pad - ((v - lo) / span) * (height - 2 * pad)
            points.extend([x, y])

        canvas.create_line(*points, fill=ACCENT, width=2, smooth=True)

    def update_raw_output(self, output: str) -> None:
        if not self.winfo_exists():
            return
        if hasattr(self, "raw_output"):
            self.raw_output.configure(state="normal")
            self.raw_output.delete("1.0", "end")
            self.raw_output.insert("1.0", output or "No output.")
            self.raw_output.configure(state="disabled")

    def parse_health_output(self, output: str) -> dict[str, str]:
        metrics: dict[str, str] = {}
        for line in output.splitlines():
            if line.startswith("__") and "__=" in line:
                key, value = line.split("=", 1)
                metrics[key.strip("_")] = value.strip()
        return metrics

    def as_int(self, metrics: dict[str, str], key: str, default: int = 0) -> int:
        try:
            return int(float(metrics.get(key, str(default)) or default))
        except Exception:
            return default

    def as_float(self, metrics: dict[str, str], key: str, default: float = 0.0) -> float:
        try:
            return float(metrics.get(key, str(default)) or default)
        except Exception:
            return default

    def pct_color(self, pct: float, warning: float, critical: float) -> str:
        if pct >= critical:
            return DANGER
        if pct >= warning:
            return WARNING
        return SUCCESS

    def card_color(self, status: str) -> str:
        # Derived from the same DANGER/WARNING/SUCCESS constants used for the
        # danger/warning/success buttons and status indicators elsewhere, so
        # severity coloring stays visually connected instead of being its own
        # hand-picked mini-palette.
        if status == "critical":
            return tint(DANGER, -0.72)
        if status == "warning":
            return tint(WARNING, -0.72)
        if status == "ok":
            return tint(SUCCESS, -0.78)
        return CARD

    def set_card(self, key: str, value: str, detail: str = "", color: str = TEXT, bg_status: str = "neutral") -> None:
        labels = self.card_labels.get(key)
        if not labels:
            return
        labels["value"].configure(text=value, text_color=color)
        labels["detail"].configure(text=detail)
        labels["frame"].configure(fg_color=self.card_color(bg_status))

    def add_reason(self, reasons: list[str], severity: list[str], level: str, message: str) -> None:
        order = {"ok": 0, "warning": 1, "critical": 2}
        if order[level] > order[severity[0]]:
            severity[0] = level
        reasons.append(message)

    def update_cards(self, metrics: dict[str, str]) -> None:
        reasons: list[str] = []
        severity = ["ok"]

        hostname = metrics.get("HOSTNAME", "Unknown")
        check_time = metrics.get("CHECK_TIME", "")
        uptime = metrics.get("UPTIME", "")
        self.set_card("server", hostname, f"{check_time}\n{uptime}", TEXT, "neutral")

        cores = max(1, self.as_int(metrics, "CPUCORES", 1))
        loadavg = metrics.get("LOADAVG", "")
        try:
            load1 = float(loadavg.split()[0])
            ratio = load1 / cores
            if ratio >= 2.0:
                status, color = "critical", DANGER
                self.add_reason(reasons, severity, "critical", f"Load {load1:.2f} is very high for {cores} cores")
            elif ratio >= 1.0:
                status, color = "warning", WARNING
                self.add_reason(reasons, severity, "warning", f"Load {load1:.2f} is near/above CPU capacity")
            else:
                status, color = "ok", SUCCESS
            self.set_card("load", f"{load1:.2f} / {cores} cores", f"Raw: {loadavg}", color, status)
        except Exception:
            self.set_card("load", "Unknown", loadavg, MUTED, "neutral")

        mem = metrics.get("MEM", "")
        try:
            total, used, free, available = [float(x) for x in mem.split(",")[:4]]
            pct = (used / total) * 100 if total else 0
            color = self.pct_color(pct, 80, 92)
            status = "critical" if pct >= 92 else "warning" if pct >= 80 else "ok"
            if status != "ok":
                self.add_reason(reasons, severity, status, f"RAM usage {pct:.1f}%")
            self.set_card("ram", f"{pct:.1f}%", f"Used {used:.0f} MB of {total:.0f} MB | Available {available:.0f} MB", color, status)
        except Exception:
            self.set_card("ram", "Unknown", mem, MUTED, "neutral")

        swap = metrics.get("SWAP", "")
        try:
            total, used, free = [float(x) for x in swap.split(",")[:3]]
            pct = (used / total) * 100 if total else 0
            color = self.pct_color(pct, 20, 50)
            status = "critical" if pct >= 50 else "warning" if pct >= 20 else "ok"
            if total > 0 and status != "ok":
                self.add_reason(reasons, severity, status, f"Swap usage {pct:.1f}%")
            self.set_card("swap", f"{pct:.1f}%" if total else "0%", f"Used {used:.0f} MB of {total:.0f} MB", color, status)
        except Exception:
            self.set_card("swap", "Unknown", swap, MUTED, "neutral")

        self.update_disk_card(metrics, "DISK_ROOT", "disk", "Disk /")
        self.update_disk_card(metrics, "DISK_WEB2PY", "webdisk", "Disk Web2py")

        web_est = self.as_int(metrics, "WEB_ESTABLISHED")
        tcp_est = self.as_int(metrics, "TCP_ESTABLISHED")
        time_wait = self.as_int(metrics, "TCP_TIME_WAIT")
        if web_est >= 500 or tcp_est >= 1000:
            conn_status, conn_color = "critical", DANGER
            self.add_reason(reasons, severity, "critical", f"High connections: web={web_est}, tcp={tcp_est}")
        elif web_est >= 200 or tcp_est >= 500 or time_wait >= 1000:
            conn_status, conn_color = "warning", WARNING
            self.add_reason(reasons, severity, "warning", f"Elevated connections: web={web_est}, tcp={tcp_est}")
        else:
            conn_status, conn_color = "ok", SUCCESS
        self.set_card("connections", f"{web_est} web", f"TCP ESTAB {tcp_est} | TIME_WAIT {time_wait}\nTop: {self.format_process_list(metrics.get('TOP_REMOTE_IPS', ''))}", conn_color, conn_status)

        unique_clients = self.as_int(metrics, "UNIQUE_CLIENTS")
        login_events = self.as_int(metrics, "LOGIN_EVENTS")
        if unique_clients >= 150:
            clients_status, clients_color = "critical", DANGER
            self.add_reason(reasons, severity, "critical", f"High active client/IP count: {unique_clients}")
        elif unique_clients >= 75:
            clients_status, clients_color = "warning", WARNING
            self.add_reason(reasons, severity, "warning", f"Elevated active client/IP count: {unique_clients}")
        else:
            clients_status, clients_color = "ok", SUCCESS
        self.set_card("clients", str(unique_clients), f"Login/user events: {login_events}\nTop clients: {self.format_process_list(metrics.get('TOP_CLIENTS', ''))}", clients_color, clients_status)

        workers_total = self.as_int(metrics, "UWSGI_WORKERS_TOTAL")
        workers_busy = self.as_int(metrics, "UWSGI_WORKERS_BUSY")
        workers_idle = self.as_int(metrics, "UWSGI_WORKERS_IDLE")
        stats_ok = metrics.get("UWSGI_STATS_OK", "0") == "1"
        if stats_ok and workers_total > 0:
            busy_pct = (workers_busy / workers_total) * 100
            if busy_pct >= 90:
                worker_status, worker_color = "critical", DANGER
                self.add_reason(reasons, severity, "critical", f"uWSGI workers saturated: {workers_busy}/{workers_total} busy")
            elif busy_pct >= 70:
                worker_status, worker_color = "warning", WARNING
                self.add_reason(reasons, severity, "warning", f"uWSGI workers high usage: {workers_busy}/{workers_total} busy")
            else:
                worker_status, worker_color = "ok", SUCCESS
            self.set_card("uwsgi_workers", f"{workers_busy}/{workers_total} busy", f"Idle {workers_idle} | Busy {busy_pct:.1f}%", worker_color, worker_status)
        else:
            proc_count = self.as_int(metrics, "UWSGI_PROCS")
            status = "ok" if proc_count > 0 else "critical"
            color = SUCCESS if proc_count > 0 else DANGER
            detail = metrics.get("UWSGI_STATS_ERROR", "No stats socket data")
            if proc_count <= 0:
                self.add_reason(reasons, severity, "critical", "No uWSGI process detected")
            self.set_card("uwsgi_workers", f"{proc_count} procs", detail, color, status)

        uwsgi_exceptions = self.as_int(metrics, "UWSGI_EXCEPTIONS")
        uwsgi_harakiri = self.as_int(metrics, "UWSGI_HARAKIRI")
        uwsgi_respawns = self.as_int(metrics, "UWSGI_RESPAWNS")
        uwsgi_avg_rt = metrics.get("UWSGI_AVG_RT", "0")
        uwsgi_rss = metrics.get("UWSGI_RSS_MB", "0")
        if uwsgi_harakiri > 0 or uwsgi_respawns > 0 or uwsgi_exceptions > 10:
            uh_status, uh_color = "warning", WARNING
            self.add_reason(reasons, severity, "warning", f"uWSGI exceptions/respawns detected: exceptions={uwsgi_exceptions}, respawns={uwsgi_respawns}")
        else:
            uh_status, uh_color = "ok", SUCCESS
        self.set_card("uwsgi_health", f"exc {uwsgi_exceptions}", f"Harakiri {uwsgi_harakiri} | Respawns {uwsgi_respawns}\nRSS {uwsgi_rss} MB | avg_rt {uwsgi_avg_rt}", uh_color, uh_status)

        web2py_count = self.as_int(metrics, "WEB2PY_PROCS")
        web2py_status = "ok" if web2py_count > 0 else "warning"
        web2py_color = SUCCESS if web2py_count > 0 else WARNING
        if web2py_count <= 0:
            self.add_reason(reasons, severity, "warning", "No explicit web2py process detected")
        self.set_card("web2py", str(web2py_count), metrics.get("WEB2PY_PATH", ""), web2py_color, web2py_status)

        nginx_procs = self.as_int(metrics, "NGINX_PROCS")
        nginx_status = metrics.get("NGINX_STATUS", "unknown")
        if nginx_procs <= 0 or nginx_status.strip().lower() in {"inactive", "failed"}:
            ng_status, ng_color = "critical", DANGER
            self.add_reason(reasons, severity, "critical", "Nginx appears down or failed")
        elif nginx_status.strip().lower() != "active" and nginx_status.strip().lower() != "unknown":
            ng_status, ng_color = "warning", WARNING
        else:
            ng_status, ng_color = "ok", SUCCESS
        self.set_card("nginx", nginx_status or "unknown", f"Processes: {nginx_procs}", ng_color, ng_status)

        recent_errors = self.as_int(metrics, "RECENT_ERRORS")
        nginx_errors = self.as_int(metrics, "NGINX_ERRORS")
        total_errors = recent_errors + nginx_errors
        if total_errors >= 80:
            err_status, err_color = "critical", DANGER
            self.add_reason(reasons, severity, "critical", f"High recent error volume: {total_errors}")
        elif total_errors >= 20:
            err_status, err_color = "warning", WARNING
            self.add_reason(reasons, severity, "warning", f"Recent errors detected: {total_errors}")
        else:
            err_status, err_color = "ok", SUCCESS
        self.set_card("errors", str(total_errors), f"web2py errors {recent_errors} | nginx errors {nginx_errors}", err_color, err_status)

        log_502 = self.as_int(metrics, "LOG_502")
        nginx_502 = self.as_int(metrics, "NGINX_502")
        total_502 = log_502 + nginx_502
        if total_502 >= 10:
            gw_status, gw_color = "critical", DANGER
            self.add_reason(reasons, severity, "critical", f"502/Bad Gateway evidence found: {total_502}")
        elif total_502 > 0 or severity[0] in {"warning", "critical"} and (workers_total and workers_busy >= max(1, int(workers_total * 0.7))):
            gw_status, gw_color = "warning", WARNING
            if total_502 > 0:
                self.add_reason(reasons, severity, "warning", f"Some gateway errors found: {total_502}")
        else:
            gw_status, gw_color = "ok", SUCCESS
        self.set_card("gateway", f"{total_502} events", f"nginx {nginx_502} | web2py logs {log_502}", gw_color, gw_status)

        self.set_card("logins", str(login_events), f"Log files scanned: {metrics.get('LOG_FILES_COUNT', '0')} | Lines: {metrics.get('LOG_LINES', '0')}", clients_color, clients_status)
        self.set_card("top_cpu", "Top CPU", self.format_process_list(metrics.get("TOP_CPU", "")), TEXT, "neutral")
        self.set_card("top_mem", "Top Memory", self.format_process_list(metrics.get("TOP_MEM", "")), TEXT, "neutral")
        self.set_card("uwsgi_top", "Web2py/uWSGI", self.format_process_list(metrics.get("UWSGI_TOP_CPU", "")), TEXT, "neutral")

        if not reasons:
            reasons.append("No critical web host risk detected.")
        overall = severity[0]
        overall_text = "CRITICAL" if overall == "critical" else "WARNING" if overall == "warning" else "OK"
        overall_color = DANGER if overall == "critical" else WARNING if overall == "warning" else SUCCESS
        self.set_card("overall", overall_text, "\n".join(reasons[:6]), overall_color, overall)

        if overall == "critical" and self.last_overall_status != "critical":
            self.notify_critical(reasons)
        self.last_overall_status = overall

    def notify_critical(self, reasons: list[str]) -> None:
        if not self.notify_enabled.get():
            return
        if winsound is not None:
            try:
                winsound.MessageBeep(winsound.MB_ICONHAND)
            except Exception:
                pass
        name = self.profile.name if self.profile else "Server"
        show_toast(self.app, f"{name}: CRITICAL", "\n".join(reasons[:3]))

    def update_disk_card(self, metrics: dict[str, str], metric_key: str, card_key: str, label: str) -> None:
        disk = metrics.get(metric_key, "")
        try:
            size, used, avail, pct_text = disk.split(",")[:4]
            pct = float(pct_text.replace("%", ""))
            color = self.pct_color(pct, 85, 95)
            status = "critical" if pct >= 95 else "warning" if pct >= 85 else "ok"
            self.set_card(card_key, pct_text, f"Used {used} KB of {size} KB | Available {avail} KB", color, status)
        except Exception:
            self.set_card(card_key, "Unknown", disk, MUTED, "neutral")

    def format_process_list(self, raw: str) -> str:
        if not raw:
            return "No data"
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        return "\n".join(parts[:8])


def summarize_health(metrics: dict[str, str]) -> tuple[str, str]:
    """Lightweight worst-of-4 status (load/RAM/disk/connections) for the multi-server grid.

    Deliberately not a reuse of MonitoringDashboardWindow.update_cards()'s full
    gateway/nginx/uWSGI risk scoring - this is a compact per-server summary line,
    not the detailed dashboard.
    """
    order = {"ok": 0, "warning": 1, "critical": 2}
    overall = "ok"
    parts: list[str] = []

    def bump(level: str) -> None:
        nonlocal overall
        if order[level] > order[overall]:
            overall = level

    try:
        cores = max(1, int(float(metrics.get("CPUCORES", "1") or 1)))
        load1 = float(metrics.get("LOADAVG", "0").split()[0])
        ratio = load1 / cores
        level = "critical" if ratio >= 2.0 else "warning" if ratio >= 1.0 else "ok"
        bump(level)
        parts.append(f"Load {load1:.2f}/{cores}")
    except Exception:
        parts.append("Load ?")

    try:
        total, used = [float(x) for x in metrics.get("MEM", "").split(",")[:2]]
        ram_pct = (used / total) * 100 if total else 0.0
        level = "critical" if ram_pct >= 92 else "warning" if ram_pct >= 80 else "ok"
        bump(level)
        parts.append(f"RAM {ram_pct:.0f}%")
    except Exception:
        parts.append("RAM ?")

    try:
        disk_pct = float(metrics.get("DISK_ROOT", "").split(",")[3].replace("%", ""))
        level = "critical" if disk_pct >= 95 else "warning" if disk_pct >= 85 else "ok"
        bump(level)
        parts.append(f"Disk {disk_pct:.0f}%")
    except Exception:
        parts.append("Disk ?")

    try:
        web_est = int(float(metrics.get("WEB_ESTABLISHED", "0") or 0))
        level = "critical" if web_est >= 500 else "warning" if web_est >= 200 else "ok"
        bump(level)
        parts.append(f"Conns {web_est}")
    except Exception:
        parts.append("Conns ?")

    return overall, " | ".join(parts)


class MultiServerMonitorWindow(ctk.CTkToplevel if ctk is not None else tk.Toplevel):
    """Runs the health check against every saved profile at once, one compact card per server."""

    def __init__(self, app: "EmbeddedSSHLauncher"):
        super().__init__(app)
        self.app = app
        self.title("Monitor All Profiles")
        self.geometry("1180x760")
        self.minsize(720, 480)
        self.transient(app)

        if ctk is not None:
            self.configure(fg_color=BG)

        self.card_labels: dict[str, dict[str, object]] = {}
        self._current_columns = 3
        self._regrid_after_id: str | None = None

        self._build_ui()
        self.refresh_all()

    def _build_ui(self) -> None:
        if ctk is None:
            self.text = tk.Text(self)
            self.text.pack(fill="both", expand=True)
            self.text.insert("1.0", "Multi-server monitor requires customtkinter for the full UI.\n")
            return

        root = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        root.pack(fill="both", expand=True)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(root, fg_color=PANEL, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Monitor All Profiles",
            text_color=TEXT,
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=(14, 4), sticky="w")

        self.status_label = ctk.CTkLabel(header, text="Ready", text_color=MUTED, font=ctk.CTkFont(size=12))
        self.status_label.grid(row=1, column=0, padx=18, pady=(0, 14), sticky="w")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=2, padx=18, pady=12, sticky="e")
        build_button(actions, "Refresh All", self.refresh_all, ACCENT, width=100).pack(side="left", padx=4)
        build_button(actions, "Close", self.destroy, DANGER, width=80).pack(side="left", padx=4)

        body = ctk.CTkScrollableFrame(root, fg_color=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=14, pady=14)
        body.grid_columnconfigure(tuple(range(self._current_columns)), weight=1)
        self.cards_frame = body
        body.bind("<Configure>", self.on_body_configure)

        if not self.app.profiles:
            ctk.CTkLabel(body, text="No saved profiles yet.", text_color=MUTED).grid(row=0, column=0, padx=8, pady=8, sticky="w")
            return

        for idx, profile in enumerate(self.app.profiles):
            card = ctk.CTkFrame(self.cards_frame, fg_color=CARD, corner_radius=16, cursor="hand2")
            card.grid(row=idx // self._current_columns, column=idx % self._current_columns, sticky="nsew", padx=8, pady=8)
            card.grid_columnconfigure(0, weight=1)

            title_label = ctk.CTkLabel(card, text=profile.name, text_color=TEXT, font=ctk.CTkFont(size=14, weight="bold"))
            title_label.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 2))

            host_label = ctk.CTkLabel(card, text=f"{profile.user}@{profile.host}:{profile.port}", text_color=MUTED, font=ctk.CTkFont(size=11))
            host_label.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 6))

            status_value = ctk.CTkLabel(card, text="Waiting...", text_color=MUTED, font=ctk.CTkFont(size=15, weight="bold"))
            status_value.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 4))

            summary_label = ctk.CTkLabel(card, text="", text_color=MUTED, font=ctk.CTkFont(size=11), wraplength=220, justify="left")
            summary_label.grid(row=3, column=0, sticky="w", padx=14, pady=(0, 14))

            for widget in (card, title_label, host_label, status_value, summary_label):
                widget.bind("<Button-1>", lambda _e, i=idx: self.open_detail(i))

            self.card_labels[profile.name] = {"frame": card, "value": status_value, "detail": summary_label}

    def on_body_configure(self, event: tk.Event) -> None:
        columns = max(1, min(6, event.width // 260))
        if columns == self._current_columns:
            return
        if self._regrid_after_id is not None:
            try:
                self.after_cancel(self._regrid_after_id)
            except Exception:
                pass
        self._regrid_after_id = self.after(120, lambda: self.regrid_cards(columns))

    def regrid_cards(self, columns: int) -> None:
        self._regrid_after_id = None
        if not self.winfo_exists():
            return

        old_columns = self._current_columns
        self._current_columns = columns

        if old_columns > columns:
            self.cards_frame.grid_columnconfigure(tuple(range(old_columns)), weight=0)
        self.cards_frame.grid_columnconfigure(tuple(range(columns)), weight=1)

        for idx, labels in enumerate(self.card_labels.values()):
            labels["frame"].grid_configure(row=idx // columns, column=idx % columns)

    def open_detail(self, index: int) -> None:
        self.app.select_profile(index)
        self.app.open_monitoring_dashboard()

    def refresh_all(self) -> None:
        if not self.winfo_exists() or ctk is None:
            return
        if not self.app.profiles:
            return

        self.status_label.configure(text=f"Checking {len(self.app.profiles)} profile(s)...", text_color=WARNING)
        for profile in self.app.profiles:
            labels = self.card_labels.get(profile.name)
            if labels:
                labels["value"].configure(text="Loading...", text_color=MUTED)
                labels["detail"].configure(text="")
                labels["frame"].configure(fg_color=CARD)
            self.app.run_remote_monitoring_command(
                profile,
                resolve_health_command(profile),
                callback=lambda success, output, error, p=profile: self.on_result(p, success, output, error),
            )

    def on_result(self, profile: SSHProfile, success: bool, output: str, error: str) -> None:
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        labels = self.card_labels.get(profile.name)
        if not labels:
            return

        if not success:
            labels["value"].configure(text="Failed", text_color=DANGER)
            labels["detail"].configure(text=(error or "Could not run remote command.")[:200])
            labels["frame"].configure(fg_color=CARD)
            self.status_label.configure(text="Last refresh completed with errors", text_color=WARNING)
            return

        metrics: dict[str, str] = {}
        for line in output.splitlines():
            if line.startswith("__") and "__=" in line:
                key, value = line.split("=", 1)
                metrics[key.strip("_")] = value.strip()

        status, summary = summarize_health(metrics)
        status_text = "CRITICAL" if status == "critical" else "WARNING" if status == "warning" else "OK"
        color = DANGER if status == "critical" else WARNING if status == "warning" else SUCCESS
        bg = tint(DANGER, -0.72) if status == "critical" else tint(WARNING, -0.72) if status == "warning" else tint(SUCCESS, -0.78)

        labels["value"].configure(text=status_text, text_color=color)
        labels["detail"].configure(text=summary)
        labels["frame"].configure(fg_color=bg)

        self.status_label.configure(text="Last refresh completed", text_color=SUCCESS)


class AuditLogWindow(ctk.CTkToplevel if ctk is not None else tk.Toplevel):
    """Read-only viewer for the local connection audit log (who connected to what, and when)."""

    def __init__(self, app: "EmbeddedSSHLauncher"):
        super().__init__(app)
        self.app = app
        self.title("Connection Audit Log")
        self.geometry("760x520")
        self.minsize(560, 360)
        self.transient(app)

        if ctk is not None:
            self.configure(fg_color=BG)

        self._build_ui()
        self.refresh_log()

    def _build_ui(self) -> None:
        if ctk is None:
            self.text = tk.Text(self)
            self.text.pack(fill="both", expand=True)
            return

        root = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        root.pack(fill="both", expand=True)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(root, fg_color=PANEL, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Connection Audit Log",
            text_color=TEXT,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=14, sticky="w")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, padx=18, pady=12, sticky="e")
        build_button(actions, "Refresh", self.refresh_log, ACCENT, width=90).pack(side="left", padx=4)
        build_button(actions, "Close", self.destroy, DANGER, width=80).pack(side="left", padx=4)

        self.log_text = tk.Text(
            root,
            bg=TERMINAL_BG,
            fg=TERMINAL_FG,
            insertbackground=TERMINAL_FG,
            font=("Cascadia Mono", 10),
            wrap="none",
            borderwidth=0,
            highlightthickness=0,
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=14, pady=14)
        self.log_text.configure(state="disabled")

    def refresh_log(self) -> None:
        entries = AuditLogStore.load()

        if ctk is None:
            if hasattr(self, "text"):
                self.text.delete("1.0", "end")
                self.text.insert("1.0", self._format_entries(entries))
            return

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", self._format_entries(entries))
        self.log_text.configure(state="disabled")

    def _format_entries(self, entries: list[dict]) -> str:
        if not entries:
            return "No connections logged yet."
        lines = []
        for entry in entries:
            try:
                when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.get("ts", 0)))
            except Exception:
                when = "?"
            lines.append(f"{when}  |  {entry.get('profile', '?'):<20}  |  {entry.get('user', '?')}@{entry.get('host', '?')}")
        return "\n".join(lines)


class DebugLogViewer(ctk.CTkToplevel if ctk is not None else tk.Toplevel):
    """Live viewer over LOG_BUFFER/LOG_QUEUE - app logging, redirected stdout/stderr,
    and otherwise-invisible Tkinter callback exceptions (see report_callback_exception).
    """

    SEVERITY_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
    SEVERITY_COLOR = {"DEBUG": MUTED, "INFO": TEXT, "WARNING": WARNING, "ERROR": DANGER}

    def __init__(self, app: "EmbeddedSSHLauncher"):
        super().__init__(app)
        self.app = app
        self.title("Debug Log Viewer")
        self.geometry("900x560")
        self.minsize(600, 360)
        self.transient(app)

        if ctk is not None:
            self.configure(fg_color=BG)

        self.min_severity = "DEBUG"
        self._poll_after_id: str | None = None

        self._build_ui()
        self._load_history()
        self._schedule_poll()

    def _build_ui(self) -> None:
        if ctk is None:
            self.text = tk.Text(self)
            self.text.pack(fill="both", expand=True)
            return

        root = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        root.pack(fill="both", expand=True)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(root, fg_color=PANEL, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Debug Log Viewer",
            text_color=TEXT,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=14, sticky="w")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, padx=18, pady=12, sticky="e")

        ctk.CTkLabel(actions, text="Severity", text_color=MUTED).pack(side="left", padx=(0, 6))
        self.severity_menu = ctk.CTkOptionMenu(
            actions, values=["ALL", "DEBUG", "INFO", "WARNING", "ERROR"],
            command=self.set_severity_filter, width=100,
        )
        self.severity_menu.set("ALL")
        self.severity_menu.pack(side="left", padx=4)

        build_button(actions, "Copy Logs", self.copy_logs, CARD_HOVER, width=90).pack(side="left", padx=4)
        build_button(actions, "Clear Logs", self.clear_logs, WARNING, width=90).pack(side="left", padx=4)
        build_button(actions, "Close", self.destroy, DANGER, width=80).pack(side="left", padx=4)

        self.log_text = tk.Text(
            root,
            bg=TERMINAL_BG,
            fg=TERMINAL_FG,
            insertbackground=TERMINAL_FG,
            font=("Cascadia Mono", 10),
            wrap="none",
            borderwidth=0,
            highlightthickness=0,
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=14, pady=14)
        for level, color in self.SEVERITY_COLOR.items():
            self.log_text.tag_configure(level, foreground=color)
        self.log_text.configure(state="disabled")

    def set_severity_filter(self, value: str) -> None:
        self.min_severity = "DEBUG" if value == "ALL" else value
        self._load_history()

    def _passes_filter(self, level: str) -> bool:
        return self.SEVERITY_ORDER.get(level, 0) >= self.SEVERITY_ORDER.get(self.min_severity, 0)

    def _append_entry(self, level: str, when: str, message: str) -> None:
        if not self._passes_filter(level):
            return
        line = f"[{when}] {level:<7} {message}\n"
        if ctk is None:
            if hasattr(self, "text"):
                self.text.insert("end", line)
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line, level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _load_history(self) -> None:
        if ctk is not None:
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.configure(state="disabled")
        elif hasattr(self, "text"):
            self.text.delete("1.0", "end")

        for level, when, message in list(LOG_BUFFER):
            self._append_entry(level, when, message)

    def _schedule_poll(self) -> None:
        self._poll_after_id = self.after(250, self._poll_log_queue)

    def _poll_log_queue(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        drained = 0
        while drained < 200:
            try:
                level, when, message = LOG_QUEUE.get_nowait()
            except queue.Empty:
                break
            self._append_entry(level, when, message)
            drained += 1

        self._schedule_poll()

    def copy_logs(self) -> None:
        if ctk is None:
            content = self.text.get("1.0", "end") if hasattr(self, "text") else ""
        else:
            content = self.log_text.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(content)

    def clear_logs(self) -> None:
        LOG_BUFFER.clear()
        if ctk is not None:
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.configure(state="disabled")
        elif hasattr(self, "text"):
            self.text.delete("1.0", "end")

    def destroy(self) -> None:
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except Exception:
                pass
            self._poll_after_id = None
        super().destroy()


class FileTransferWindow(ctk.CTkToplevel if ctk is not None else tk.Toplevel):
    """Simple upload/download panel over pscp - file-picker dialogs, not drag-and-drop."""

    def __init__(self, app: "EmbeddedSSHLauncher"):
        super().__init__(app)
        self.app = app
        self.title("File Transfer")
        center_toplevel(self, app, 520, 260)
        self.minsize(420, 220)
        self.transient(app)

        if ctk is not None:
            self.configure(fg_color=BG)

        self.profile: SSHProfile | None = self.app.get_monitoring_profile()

        self._build_ui()

    def _build_ui(self) -> None:
        if ctk is None:
            self.text = tk.Text(self)
            self.text.pack(fill="both", expand=True)
            self.text.insert("1.0", "File Transfer requires customtkinter for the full UI.\n")
            return

        frame = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=16)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            frame, text="File Transfer", text_color=TEXT, font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(16, 4))

        self.profile_label = ctk.CTkLabel(
            frame, text=self.profile_title(), text_color=MUTED, font=ctk.CTkFont(size=12),
        )
        self.profile_label.pack(anchor="w", padx=16, pady=(0, 14))

        button_row = ctk.CTkFrame(frame, fg_color="transparent")
        button_row.pack(fill="x", padx=16, pady=(0, 10))

        build_button(button_row, "Upload File...", self.start_upload, ACCENT).pack(
            side="left", fill="x", expand=True, padx=(0, 4)
        )
        build_button(button_row, "Download File...", self.start_download, ACCENT).pack(
            side="left", fill="x", expand=True, padx=(4, 0)
        )

        self.status_var = tk.StringVar(value="Ready.")
        ctk.CTkLabel(
            frame, textvariable=self.status_var, text_color=MUTED, font=ctk.CTkFont(size=12),
            wraplength=460, justify="left",
        ).pack(anchor="w", padx=16, pady=(10, 16), fill="x")

    def profile_title(self) -> str:
        if self.profile is None:
            return "No profile selected. Select a profile or focus an active SSH console."
        return f"{self.profile.name} - {self.profile.user}@{self.profile.host}:{self.profile.port}"

    def start_upload(self) -> None:
        if self.profile is None:
            show_message(self, "error", APP_NAME, "Select a profile or focus a connected terminal first.")
            return
        local_path = filedialog.askopenfilename(parent=self, title="Select file to upload")
        if not local_path:
            return
        default_remote = f"~/{Path(local_path).name}"
        remote_path = ask_text(self, APP_NAME, "Remote destination path:", initial_value=default_remote)
        if not remote_path:
            return
        self.status_var.set(f"Uploading {Path(local_path).name}...")
        self.app.run_file_transfer(self.profile, local_path, remote_path, True, self.on_transfer_result)

    def start_download(self) -> None:
        if self.profile is None:
            show_message(self, "error", APP_NAME, "Select a profile or focus a connected terminal first.")
            return
        remote_path = ask_text(self, APP_NAME, "Remote source path:")
        if not remote_path:
            return
        suggested_name = remote_path.rstrip("/").rsplit("/", 1)[-1] or "download"
        local_path = filedialog.asksaveasfilename(parent=self, title="Save downloaded file as", initialfile=suggested_name)
        if not local_path:
            return
        self.status_var.set(f"Downloading {suggested_name}...")
        self.app.run_file_transfer(self.profile, local_path, remote_path, False, self.on_transfer_result)

    def on_transfer_result(self, success: bool, message: str) -> None:
        if not self.winfo_exists():
            return
        if success:
            self.status_var.set("Transfer completed successfully.")
        else:
            self.status_var.set("Transfer failed.")
            show_message(self, "error", APP_NAME, f"File transfer failed.\n\n{message[:500]}")


class EmbeddedTerminal(ctk.CTkFrame if ctk is not None else ttk.Frame):
    def __init__(
        self,
        master: tk.Widget,
        profile: SSHProfile,
        plink_path: str,
        password: str | None,
        proxy_command: str | None = None,
    ):
        if ctk is not None:
            super().__init__(master, fg_color=TERMINAL_BG, corner_radius=12)
        else:
            super().__init__(master)

        self.profile = profile
        self.plink_path = plink_path
        self.password = password or ""
        self.proxy_command = proxy_command
        self.tab_broadcast_hook = None  # set by ConsoleTab.add_console to ConsoleTab.broadcast_raw

        if ctk is not None:
            self.apply_env_border()

        self.proc = None
        self.reader_thread: threading.Thread | None = None
        self.output_queue: queue.Queue[object] = queue.Queue()
        # Bumped on every start_process()/close_process_only() call. read_loop()
        # captures the epoch it was started with and checks it before every push
        # to output_queue, so a reader thread from a session that reconnect()
        # already tore down can never write stale data/status for the new session.
        self.session_epoch = 0

        self.alive = False
        self.sent_password = False
        self.active = False
        self.close_callback = None
        self.activate_callback = None

        self.flush_after_id: str | None = None
        self.status_after_id: str | None = None

        self.term_columns = 140
        self.term_rows = 42

        self.screen = None
        self.stream = None

        self.header = None
        self.title_label = None
        self.status_label = None
        self.connection_state = "disconnected"
        self.style_tag_cache: dict[tuple[str, str, bool, bool], str] = {}

        self._build_ui()
        self.reset_terminal_screen()
        self.start_process()
        self.schedule_flush()
        self.schedule_connection_check()

    def _build_ui(self) -> None:
        if ctk is not None:
            self.header = ctk.CTkFrame(self, fg_color=PANEL_2, corner_radius=10)
            self.header.pack(fill="x", padx=4, pady=(4, 2))

            self.title_label = ctk.CTkLabel(
                self.header,
                text=f"{self.profile.name}  {self.profile.user}@{self.profile.host}:{self.profile.port}",
                text_color=TEXT,
                font=ctk.CTkFont(size=12, weight="bold"),
            )
            self.title_label.pack(side="left", padx=10, pady=6)

            self.status_label = ctk.CTkLabel(
                self.header,
                text="● Disconnected",
                text_color=DISCONNECTED,
                font=ctk.CTkFont(size=12, weight="bold"),
            )
            self.status_label.pack(side="left", padx=(8, 4), pady=6)

            build_button(
                self.header, "Close", self.request_close, DANGER, width=70, height=28
            ).pack(side="right", padx=(4, 8), pady=6)

            build_button(
                self.header, "Reconnect", self.reconnect, WARNING, width=92, height=28
            ).pack(side="right", padx=4, pady=6)

            build_button(
                self.header, "Clear", self.clear_remote_console, CARD, width=70, height=28
            ).pack(side="right", padx=4, pady=6)

            build_button(
                self.header, "Focus", self.focus_terminal, ACCENT, width=70, height=28
            ).pack(side="right", padx=4, pady=6)

            body = ctk.CTkFrame(self, fg_color=TERMINAL_BG, corner_radius=10)
            body.pack(fill="both", expand=True, padx=4, pady=(2, 4))
        else:
            self.header = ttk.Frame(self)
            self.header.pack(fill="x")

            self.title_label = ttk.Label(
                self.header,
                text=f"{self.profile.name}  {self.profile.user}@{self.profile.host}:{self.profile.port}",
                font=("Segoe UI", 9, "bold"),
            )
            self.title_label.pack(side="left", padx=4)

            self.status_label = ttk.Label(
                self.header,
                text="● Disconnected",
                foreground=DISCONNECTED,
                font=("Segoe UI", 9, "bold"),
            )
            self.status_label.pack(side="left", padx=8)

            ttk.Button(self.header, text="Close", command=self.request_close, width=7).pack(side="right", padx=2)
            ttk.Button(self.header, text="Reconnect", command=self.reconnect, width=10).pack(side="right", padx=2)
            ttk.Button(self.header, text="Clear", command=self.clear_remote_console, width=7).pack(side="right", padx=2)
            ttk.Button(self.header, text="Focus", command=self.focus_terminal, width=7).pack(side="right", padx=2)

            body = ttk.Frame(self)
            body.pack(fill="both", expand=True)

        self.text = tk.Text(
            body,
            wrap="none",
            undo=False,
            bg=TERMINAL_BG,
            fg=TERMINAL_FG,
            insertbackground=TERMINAL_FG,
            selectbackground="#334155",
            font=("Cascadia Mono", 9),
            state="disabled",
            padx=6,
            pady=6,
            borderwidth=0,
            highlightthickness=0,
        )
        self.text.pack(side="left", fill="both", expand=True)

        y_scroll = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        y_scroll.pack(side="right", fill="y")

        x_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        x_scroll.pack(fill="x")

        self.text.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
        )

        self.text.bind("<Button-1>", lambda _event: self.focus_terminal())
        self.text.bind("<KeyPress>", self.on_key_press)
        self.text.bind("<Return>", self.on_return)
        self.text.bind("<BackSpace>", self.on_backspace)
        self.text.bind("<Delete>", self.on_delete)
        self.text.bind("<Tab>", self.on_tab_key)

        self.text.bind("<Control-c>", self.on_ctrl_c)
        self.text.bind("<Control-d>", self.on_ctrl_d)
        self.text.bind("<Control-v>", self.on_paste)
        self.text.bind("<<Paste>>", self.on_paste)

        self.text.bind("<Up>", lambda event: self.send_special("\x1b[A", event))
        self.text.bind("<Down>", lambda event: self.send_special("\x1b[B", event))
        self.text.bind("<Right>", lambda event: self.send_special("\x1b[C", event))
        self.text.bind("<Left>", lambda event: self.send_special("\x1b[D", event))
        self.text.bind("<Home>", lambda event: self.send_special("\x1b[H", event))
        self.text.bind("<End>", lambda event: self.send_special("\x1b[F", event))
        self.text.bind("<Prior>", lambda event: self.send_special("\x1b[5~", event))
        self.text.bind("<Next>", lambda event: self.send_special("\x1b[6~", event))

    def refresh_header_label(self) -> None:
        """Re-render the pane header from self.profile - call after an in-place profile edit."""
        if self.title_label is None:
            return
        text = f"{self.profile.name}  {self.profile.user}@{self.profile.host}:{self.profile.port}"
        self.title_label.configure(text=text)
        if ctk is not None:
            self.apply_env_border()

    def apply_env_border(self) -> None:
        """Show the pane's environment tag (prod/staging/dev) as a colored frame border."""
        _label, color = ENV_TAGS.get(self.profile.env_color, ENV_TAGS[""])
        self.configure(border_width=3 if self.profile.env_color else 0, border_color=color)

    def set_connection_state(self, state: str, message: str | None = None) -> None:
        """Update the visible connection status indicator for this terminal pane."""
        self.connection_state = state

        if state == "connected":
            label_text = "● Connected" if message is None else f"● {message}"
            color = CONNECTED
        elif state == "connecting":
            label_text = "● Connecting" if message is None else f"● {message}"
            color = CONNECTING
        else:
            label_text = "● Disconnected" if message is None else f"● {message}"
            color = DISCONNECTED

        if self.status_label is not None:
            try:
                if ctk is not None and isinstance(self.status_label, ctk.CTkLabel):
                    self.status_label.configure(text=label_text, text_color=color)
                else:
                    self.status_label.configure(text=label_text, foreground=color)
            except Exception:
                pass

    def mark_disconnected(self, reason: str = "Disconnected") -> None:
        self.alive = False
        self.set_connection_state("disconnected", reason)

    def set_active_visual(self, active: bool) -> None:
        if ctk is None or self.header is None:
            return

        if active:
            self.header.configure(fg_color=ACCENT)
        else:
            self.header.configure(fg_color=PANEL_2)

    def reset_terminal_screen(self) -> None:
        self.screen = None
        self.stream = None

        if pyte is not None:
            self.screen = pyte.Screen(self.term_columns, self.term_rows)
            self.stream = pyte.ByteStream(self.screen)

    def clear_terminal_widget(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def clear_remote_console(self) -> None:
        self.run_command("clear")

    def focus_terminal(self) -> None:
        """Mark this pane as the active/focused terminal for quick commands and toolbar actions."""
        self.active = True

        # Direct callback is more reliable than only relying on Tk virtual events.
        # This fixes the Focus button and prevents quick commands from going to
        # the wrong split pane.
        if callable(self.activate_callback):
            try:
                self.activate_callback(self)
            except Exception:
                pass

        self.text.configure(state="normal")
        self.text.focus_set()
        self.text.mark_set("insert", "end")
        self.text.configure(state="disabled")
        self.event_generate("<<TerminalFocused>>", when="tail")

    def start_process(self) -> None:
        self.set_connection_state("connecting", "Connecting")

        if PtyProcess is None:
            self.write_local("ERROR: pywinpty is not installed. Run: pip install pywinpty\n")
            self.set_connection_state("disconnected", "Missing pywinpty")
            return

        if pyte is None:
            self.write_local("ERROR: pyte is not installed. Run: pip install pyte\n")
            self.set_connection_state("disconnected", "Missing pyte")
            return

        command = [
            self.plink_path,
            "-ssh",
            f"{self.profile.user}@{self.profile.host}",
            "-P",
            str(self.profile.port),
            "-t",
            "-no-antispoof",
        ]

        if self.proxy_command:
            command.extend(["-proxycmd", self.proxy_command])

        if self.password:
            command.extend(["-pw", self.password])

        redacted_command: list[str] = []
        redact_next = False
        for part in command:
            redacted_command.append("<password>" if redact_next else part)
            redact_next = part == "-pw"

        APP_LOGGER.info(f"Spawning SSH session for {self.profile.name}: {' '.join(redacted_command)}")

        try:
            self.proc = PtyProcess.spawn(
                command,
                dimensions=(self.term_columns, self.term_rows),
            )
        except Exception as exc:
            APP_LOGGER.error(f"Failed to spawn SSH session for {self.profile.name}: {exc}")
            self.write_local("ERROR starting terminal:\n" + str(exc) + "\n")
            self.set_connection_state("disconnected", "Start failed")
            return

        APP_LOGGER.info(f"SSH session started for {self.profile.name}")
        self.alive = True
        self.set_connection_state("connected", "Connected")
        self.sent_password = False
        self.session_epoch += 1
        self.reader_thread = threading.Thread(target=self.read_loop, args=(self.session_epoch,), daemon=True)
        self.reader_thread.start()

        self.after(1200, self.initialize_remote_terminal)

    def initialize_remote_terminal(self) -> None:
        if not self.alive:
            return

        self.send("export TERM=xterm\r")
        self.send(f"stty rows {self.term_rows} columns {self.term_columns}\r")
        self.send("stty erase ^?\r")
        self.send("clear\r")

    def read_loop(self, epoch: int) -> None:
        while self.alive and self.proc is not None and epoch == self.session_epoch:
            try:
                data = self.proc.read(4096)

                if not data:
                    time.sleep(0.02)
                    continue

                if epoch != self.session_epoch:
                    break
                self.output_queue.put((epoch, data))
            except Exception as exc:
                if self.alive and epoch == self.session_epoch:
                    APP_LOGGER.warning(f"Reader thread for {self.profile.name} ended: {exc}")
                    self.output_queue.put((epoch, ("STATUS", "disconnected", "Disconnected")))
                    self.output_queue.put((epoch, "\n[session closed]\n"))
                    self.alive = False
                break

    def schedule_connection_check(self) -> None:
        if self.status_after_id is not None:
            try:
                self.after_cancel(self.status_after_id)
            except Exception:
                pass

        self.status_after_id = self.after(2000, self.check_connection_status)

    def check_connection_status(self) -> None:
        self.status_after_id = None

        if self.proc is None:
            self.set_connection_state("disconnected", "Disconnected")
            return

        if not self.alive:
            self.set_connection_state("disconnected", "Disconnected")
            return

        try:
            if hasattr(self.proc, "isalive") and not self.proc.isalive():
                self.alive = False
                self.set_connection_state("disconnected", "Disconnected")
                return
        except Exception:
            pass

        self.set_connection_state("connected", "Connected")
        self.schedule_connection_check()

    def schedule_flush(self) -> None:
        if self.flush_after_id is not None:
            try:
                self.after_cancel(self.flush_after_id)
            except Exception:
                pass

        self.flush_after_id = self.after(35, self.flush_output)

    def flush_output(self) -> None:
        self.flush_after_id = None
        changed = False

        while True:
            try:
                item = self.output_queue.get_nowait()
            except queue.Empty:
                break

            # Every item is (epoch, payload) - see read_loop(). Drop anything
            # from a reader thread whose session has since been torn down by
            # reconnect()/close_process_only(), so a straggling stale-epoch
            # write can never corrupt the current session's terminal output
            # or connection status (closes the last TOCTOU gap the epoch
            # check in read_loop can't fully cover on its own).
            if not (isinstance(item, tuple) and len(item) == 2):
                continue
            epoch, data = item
            if epoch != self.session_epoch:
                continue

            if isinstance(data, tuple) and len(data) >= 3 and data[0] == "STATUS":
                _kind, state, message = data
                self.set_connection_state(str(state), str(message))
                continue

            if not isinstance(data, str):
                continue

            self.maybe_answer_prompts(data)
            self.feed_terminal(data)
            changed = True

        if changed:
            self.render_screen()

        if self.alive:
            self.schedule_flush()

    def maybe_answer_prompts(self, data: str) -> None:
        lower = data.lower()

        if (
            "store key in cache" in lower
            or "cache the key" in lower
            or "the server's host key is not cached" in lower
            or "continue connecting" in lower
        ):
            self.send("y\r")
            return

        if self.sent_password or not self.password:
            return

        if "password:" in lower or "password for" in lower:
            self.send(self.password + "\r")
            self.sent_password = True

    def feed_terminal(self, data: str) -> None:
        if self.stream is None or self.screen is None:
            self.write_local(self.clean_basic_output(data))
            return

        cleaned = self.prepare_terminal_input(data)

        try:
            self.stream.feed(cleaned.encode("utf-8", errors="replace"))
        except Exception:
            self.write_local(self.clean_basic_output(cleaned))

    def prepare_terminal_input(self, data: str) -> str:
        data = re.sub(r"\x1b\][^\x07]*(\x07|\x1b\\)", "", data)

        data = data.replace("\x1b(B", "")
        data = data.replace("\x1b)B", "")
        data = data.replace("\x1b(0", "")
        data = data.replace("\x1b)0", "")

        data = data.replace("\x0e", "")
        data = data.replace("\x0f", "")

        data = data.replace("\x1b[?2004h", "")
        data = data.replace("\x1b[?2004l", "")

        data = re.sub(r"\x1b\[[0-9 ]+q", "", data)

        return data

    def normalize_pyte_color(self, value: object, *, background: bool = False) -> str:
        color_name = str(value or "default").replace("-", "").replace("_", "").lower()

        if color_name.startswith("#"):
            return color_name

        if background:
            return ANSI_BACKGROUND_MAP.get(color_name, TERMINAL_BG)

        return ANSI_COLOR_MAP.get(color_name, TERMINAL_FG)

    def color_luminance(self, color: str) -> float:
        """Return perceived luminance for #RRGGBB colors."""
        try:
            color = color.strip().lstrip("#")
            if len(color) != 6:
                return 255.0
            red = int(color[0:2], 16)
            green = int(color[2:4], 16)
            blue = int(color[4:6], 16)
            return (0.299 * red) + (0.587 * green) + (0.114 * blue)
        except Exception:
            return 255.0

    def improve_terminal_contrast(self, fg: str, bg: str, bold: bool = False) -> str:
        """
        htop/uwsgitop often use black or dim gray text for CPU numbers, users,
        and low-contrast table values. On a real terminal this can still be visible
        depending on theme. In Tk Text on a pure black background it becomes almost
        unreadable, so force low-contrast foregrounds to a readable light color.
        """
        fg_lum = self.color_luminance(fg)
        bg_lum = self.color_luminance(bg)

        # If foreground is close to the background or very dark, brighten it -
        # but blend the original hue toward white instead of collapsing to a
        # flat neutral, so red/green/blue status text keeps its color-coded
        # meaning instead of becoming indistinguishable gray/white.
        if abs(fg_lum - bg_lum) < 65 or fg_lum < 75:
            blended = tint(fg, 0.6 if bold else 0.4)
            if abs(self.color_luminance(blended) - bg_lum) >= 65:
                return blended
            # Blend didn't gain enough contrast (e.g. fg was already near-white) -
            # fall back to the previous flat-neutral behavior as a safety net.
            return "#ffffff" if bold else "#e5e7eb"

        return fg

    def get_or_create_text_tag(self, fg: str, bg: str, bold: bool, underline: bool) -> str:
        key = (fg, bg, bold, underline)

        if key in self.style_tag_cache:
            return self.style_tag_cache[key]

        tag_name = f"term_style_{len(self.style_tag_cache)}"
        self.style_tag_cache[key] = tag_name

        font_weight = "bold" if bold else "normal"
        underline_value = 1 if underline else 0

        self.text.tag_configure(
            tag_name,
            foreground=fg,
            background=bg,
            font=("Cascadia Mono", 9, font_weight),
            underline=underline_value,
        )

        return tag_name

    def render_screen(self) -> None:
        if self.screen is None:
            return

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")

        buffer = self.screen.buffer
        cursor_y = max(0, min(self.screen.cursor.y, self.term_rows - 1))
        cursor_x = max(0, min(self.screen.cursor.x, self.term_columns - 1))

        for row in range(self.term_rows):
            line = buffer.get(row, {})
            current_text: list[str] = []
            current_tag: str | None = None

            def flush_segment() -> None:
                nonlocal current_text, current_tag

                if not current_text:
                    return

                segment = "".join(current_text)

                if current_tag:
                    self.text.insert("end", segment, current_tag)
                else:
                    self.text.insert("end", segment)

                current_text = []

            for col in range(self.term_columns):
                char = line.get(col)

                if char is None:
                    data = " "
                    fg = TERMINAL_FG
                    bg = TERMINAL_BG
                    bold = False
                    underline = False
                    reverse = False
                else:
                    data = getattr(char, "data", " ") or " "
                    fg = self.normalize_pyte_color(getattr(char, "fg", "default"), background=False)
                    bg = self.normalize_pyte_color(getattr(char, "bg", "default"), background=True)
                    bold = bool(getattr(char, "bold", False))
                    underline = bool(getattr(char, "underscore", False) or getattr(char, "underline", False))
                    reverse = bool(getattr(char, "reverse", False))

                if reverse:
                    fg, bg = bg, fg

                fg = self.improve_terminal_contrast(fg, bg, bold)

                if row == cursor_y and col == cursor_x:
                    data = "█"
                    fg = "#ffffff"
                    bg = ACCENT
                    bold = True

                if len(data) != 1:
                    data = data[:1] if data else " "

                tag = self.get_or_create_text_tag(fg, bg, bold, underline)

                if tag != current_tag:
                    flush_segment()
                    current_tag = tag

                current_text.append(data)

            flush_segment()

            if row < self.term_rows - 1:
                self.text.insert("end", "\n")

        self.text.configure(state="disabled")

    def write_local(self, data: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", data)
        self.text.configure(state="disabled")
        self.text.see("end")

    def clean_basic_output(self, data: str) -> str:
        data = data.replace("\r\n", "\n").replace("\r", "\n")

        data = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", data)
        data = re.sub(r"\x1b\][^\x07]*(\x07|\x1b\\)", "", data)

        data = data.replace("\x1b(B", "")
        data = data.replace("\x1b)B", "")
        data = data.replace("\x1b(0", "")
        data = data.replace("\x1b)0", "")
        data = data.replace("\x0e", "")
        data = data.replace("\x0f", "")

        data = data.replace("\x08", "")
        data = data.replace("\x7f", "")

        data = "".join(
            ch for ch in data
            if ch == "\n" or ch == "\t" or ord(ch) >= 32
        )

        return data

    def send(self, data: str) -> None:
        if self.proc is None or not self.alive:
            self.set_connection_state("disconnected", "Disconnected")
            return

        try:
            self.proc.write(data)
        except Exception:
            self.alive = False
            self.set_connection_state("disconnected", "Disconnected")
            self.write_local("\n[write failed; session closed]\n")
            return

        if callable(self.tab_broadcast_hook):
            self.tab_broadcast_hook(data, self)

    def run_command(self, command: str) -> None:
        if not command.strip():
            return

        self.focus_terminal()
        self.send(command.rstrip() + "\r")

    def reconnect(self) -> None:
        self.write_local("\n[reconnecting...]\n")

        self.close_process_only()
        self.clear_queue()
        self.reset_terminal_screen()
        self.clear_terminal_widget()

        self.start_process()
        self.schedule_flush()
        self.schedule_connection_check()
        self.focus_terminal()

    def close_process_only(self) -> None:
        APP_LOGGER.info(f"Closing SSH session for {self.profile.name}")
        self.alive = False
        # Invalidate the current reader thread's epoch immediately, before the
        # pty is even closed, so a late read()/exception from it can never be
        # mistaken for the next session (see read_loop's epoch check).
        self.session_epoch += 1

        if self.flush_after_id is not None:
            try:
                self.after_cancel(self.flush_after_id)
            except Exception:
                pass
            self.flush_after_id = None

        if self.status_after_id is not None:
            try:
                self.after_cancel(self.status_after_id)
            except Exception:
                pass
            self.status_after_id = None

        try:
            if self.proc is not None:
                self.proc.close(force=True)
        except Exception:
            pass

        self.proc = None

        # Belt-and-suspenders: bound wait for the old reader thread to actually
        # exit its blocking read(), reducing (though the epoch check above is
        # what makes it safe rather than just probable) the window where two
        # reader threads could be alive at once.
        if self.reader_thread is not None and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=0.3)
            if self.reader_thread.is_alive():
                APP_LOGGER.warning(f"Reader thread for {self.profile.name} did not exit within 0.3s of close()")

        self.set_connection_state("disconnected", "Disconnected")

    def clear_queue(self) -> None:
        while True:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break

    def on_key_press(self, event: tk.Event) -> str | None:
        if event.keysym in {
            "Return",
            "BackSpace",
            "Delete",
            "Tab",
            "Up",
            "Down",
            "Left",
            "Right",
            "Home",
            "End",
            "Prior",
            "Next",
        }:
            return None

        if event.keysym == "Escape":
            self.send("\x1b")
            return "break"

        if event.char and ord(event.char) >= 32:
            self.send(event.char)
            return "break"

        # Any other Ctrl-chord (Ctrl-A/E/U/K/L/R/W/Z, etc.) that doesn't have a
        # dedicated <Control-x> binding above still lands here as a control
        # character (ord 1-31) and was previously dropped silently - e.g.
        # readline shortcuts in bash, or anything a remote app binds to a raw
        # control code. Ctrl-C/D/V are intercepted earlier by their own more
        # specific bindings (which return "break"), so they never reach here.
        if event.char and 0 < ord(event.char) < 32:
            self.send(event.char)
            return "break"

        return None

    def on_return(self, _event: tk.Event) -> str:
        self.send("\r")
        return "break"

    def on_backspace(self, _event: tk.Event) -> str:
        self.send("\x7f")
        return "break"

    def on_delete(self, _event: tk.Event) -> str:
        self.send("\x1b[3~")
        return "break"

    def on_tab_key(self, _event: tk.Event) -> str:
        self.send("\t")
        return "break"

    def on_ctrl_c(self, _event: tk.Event) -> str:
        self.send("\x03")
        return "break"

    def on_ctrl_d(self, _event: tk.Event) -> str:
        self.send("\x04")
        return "break"

    def on_paste(self, _event: tk.Event) -> str:
        try:
            text = self.clipboard_get()
        except Exception:
            return "break"

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\n", "\r")
        self.send(text)
        return "break"

    def send_special(self, sequence: str, _event: tk.Event) -> str:
        self.send(sequence)
        return "break"

    def request_close(self) -> None:
        if callable(self.close_callback):
            self.close_callback(self)
        else:
            self.close()

    def close(self) -> None:
        self.close_process_only()


class ConsoleTab(ctk.CTkFrame if ctk is not None else ttk.Frame):
    def __init__(self, master: tk.Widget, app: "EmbeddedSSHLauncher"):
        if ctk is not None:
            super().__init__(master, fg_color=BG, corner_radius=0)
        else:
            super().__init__(master)

        self.app = app
        self.orientation = tk.HORIZONTAL
        self.layout_mode = "horizontal"
        self.panes: list[EmbeddedTerminal] = []
        self.active_terminal: EmbeddedTerminal | None = None
        self.broadcast_enabled = False

        # v1.3.8 change:
        # The previous version used one linear ttk.PanedWindow. That made 3 and 4
        # split views appear as long vertical/horizontal strips. A grid-capable
        # container lets us arrange:
        #   3 panes = 2 on top, 1 full-width at the bottom
        #   4 panes = 2 x 2 square layout
        #
        # This also keeps all terminal widgets as direct children of one stable
        # parent, which makes closing/rebuilding layouts much safer.
        if ctk is not None:
            self.layout_frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        else:
            self.layout_frame = ttk.Frame(self)

        self.layout_frame.pack(fill="both", expand=True, padx=4, pady=4)

    def add_console(self, profile: SSHProfile) -> None:
        if len(self.panes) >= MAX_PANES_PER_TAB:
            show_message(self, "warning", APP_NAME, f"Maximum {MAX_PANES_PER_TAB} consoles per tab.")
            return

        plink_path = self.app.find_plink()

        if not plink_path:
            APP_LOGGER.error(f"add_console({profile.name}): plink.exe not found")
            show_message(
                self,
                "error",
                APP_NAME,
                "plink.exe was not found. Place plink.exe beside this app or install PuTTY and add it to PATH.",
            )
            return

        password = PasswordStore.get(profile.name)

        if password is None:
            password = ask_text(
                self,
                APP_NAME,
                f"Password for {profile.user}@{profile.host}",
                password=True,
            )

            if password is None:
                APP_LOGGER.info(f"add_console({profile.name}): password prompt cancelled")
                return

            try:
                PasswordStore.save(profile.name, password)
            except Exception as exc:
                APP_LOGGER.warning(f"add_console({profile.name}): could not save password to keyring: {exc}")
                self.app.warn_keyring_failure_once(exc)

        proxy_command, ok = self.resolve_proxy_command(profile, plink_path)
        if not ok:
            return

        terminal = EmbeddedTerminal(self.layout_frame, profile, plink_path, password, proxy_command=proxy_command)
        terminal.close_callback = self.close_console
        # focus_terminal() already invokes this directly (see its own comment on
        # why the direct call was added); binding <<TerminalFocused>> to the same
        # callback here would fire it a second time on every focus event.
        terminal.activate_callback = self.set_active_terminal
        terminal.tab_broadcast_hook = self.broadcast_raw

        self.panes.append(terminal)
        self.apply_layout()

        self.set_active_terminal(terminal)
        terminal.focus_terminal()
        self.app.record_recent_connection(profile.name)
        AuditLogStore.record(profile)

    def broadcast_raw(self, data: str, source: "EmbeddedTerminal") -> None:
        """Relay a keystroke to every other pane in this tab, if broadcast is on.

        Writes straight to each pane's pty (`pane.proc.write`), never through
        `pane.send()` - that's what keeps this from becoming a rebroadcast loop.
        """
        if not self.broadcast_enabled:
            return
        for pane in self.panes:
            if pane is source or not pane.alive or pane.proc is None:
                continue
            try:
                pane.proc.write(data)
            except Exception:
                pass

    def resolve_proxy_command(self, profile: SSHProfile, plink_path: str) -> tuple[str | None, bool]:
        """Resolve `profile.jump_profile_name` into a plink -proxycmd string.

        Returns (proxy_command, ok). (None, True) means "no jump host, connect
        directly". (None, False) means resolution failed or the user cancelled
        a password prompt - the caller should abort the connection attempt
        rather than silently falling back to a direct connection.
        """
        if not profile.jump_profile_name:
            return None, True

        jump_profile = next((p for p in self.app.profiles if p.name == profile.jump_profile_name), None)
        if jump_profile is None:
            APP_LOGGER.error(f"resolve_proxy_command({profile.name}): jump host '{profile.jump_profile_name}' no longer exists")
            show_message(
                self, "error", APP_NAME,
                f"Jump host profile '{profile.jump_profile_name}' no longer exists.",
            )
            return None, False

        jump_password = PasswordStore.get(jump_profile.name)
        if jump_password is None:
            jump_password = ask_text(
                self, APP_NAME, f"Password for jump host {jump_profile.user}@{jump_profile.host}", password=True,
            )
            if jump_password is None:
                return None, False
            try:
                PasswordStore.save(jump_profile.name, jump_password)
            except Exception as exc:
                self.app.warn_keyring_failure_once(exc)

        proxy_command = (
            f'"{plink_path}" -batch -pw "{jump_password}" '
            f"{jump_profile.user}@{jump_profile.host} -P {jump_profile.port} -nc %host:%port"
        )
        return proxy_command, True

    def set_active_terminal(self, terminal: EmbeddedTerminal) -> None:
        if self.active_terminal is not None and self.active_terminal is not terminal:
            self.active_terminal.set_active_visual(False)

        self.active_terminal = terminal
        self.app.active_tab = self
        self.app.focused_terminal = terminal
        terminal.set_active_visual(True)

    def reset_layout_grid(self) -> None:
        for pane in list(self.panes):
            try:
                pane.grid_forget()
            except Exception:
                pass

        for column in range(4):
            try:
                self.layout_frame.grid_columnconfigure(column, weight=0)
            except Exception:
                pass

        for row in range(4):
            try:
                self.layout_frame.grid_rowconfigure(row, weight=0)
            except Exception:
                pass

    def default_layout_for_count(self, pane_count: int) -> str:
        """Return the best layout for the number of panes currently open."""
        if pane_count >= 4:
            return "grid4"
        if pane_count == 3:
            return "grid3_top"
        if pane_count == 2:
            return "horizontal"
        return "horizontal"

    def set_layout_mode(self, layout_mode: str) -> None:
        """Set a named layout mode and rebuild the current tab layout."""
        allowed_modes = {
            "auto",
            "horizontal",
            "vertical",
            "grid3_top",
            "grid3_bottom",
            "grid4",
        }

        if layout_mode not in allowed_modes:
            layout_mode = "auto"

        self.layout_mode = layout_mode
        self.apply_layout()

    def effective_layout_mode(self, pane_count: int) -> str:
        """Resolve the selected layout mode into a layout that fits the current pane count."""
        if self.layout_mode == "auto":
            return self.default_layout_for_count(pane_count)

        if self.layout_mode == "grid4" and pane_count < 4:
            return self.default_layout_for_count(pane_count)

        if self.layout_mode in {"grid3_top", "grid3_bottom"} and pane_count < 3:
            return self.default_layout_for_count(pane_count)

        return self.layout_mode

    def apply_layout(self) -> None:
        self.reset_layout_grid()

        pane_count = len(self.panes)

        if pane_count == 0:
            return

        layout_mode = self.effective_layout_mode(pane_count)

        # Make all grid cells start neutral before applying the selected layout.
        for column in range(4):
            self.layout_frame.grid_columnconfigure(column, weight=0)

        for row in range(4):
            self.layout_frame.grid_rowconfigure(row, weight=0)

        if pane_count == 1:
            self.layout_frame.grid_columnconfigure(0, weight=1)
            self.layout_frame.grid_rowconfigure(0, weight=1)
            self.panes[0].grid(row=0, column=0, sticky="nsew", padx=3, pady=3)
            return

        if layout_mode == "grid4" and pane_count >= 4:
            # 4-pane layout: 2 x 2 square grid.
            for row in range(2):
                self.layout_frame.grid_rowconfigure(row, weight=1)

            for column in range(2):
                self.layout_frame.grid_columnconfigure(column, weight=1)

            positions = [
                (0, 0),
                (0, 1),
                (1, 0),
                (1, 1),
            ]

            for pane, (row, column) in zip(self.panes[:4], positions):
                pane.grid(row=row, column=column, sticky="nsew", padx=3, pady=3)

            return

        if layout_mode == "grid3_top" and pane_count >= 3:
            # 3-pane layout: two panes on top, one full-width pane below.
            self.layout_frame.grid_rowconfigure(0, weight=1)
            self.layout_frame.grid_rowconfigure(1, weight=1)
            self.layout_frame.grid_columnconfigure(0, weight=1)
            self.layout_frame.grid_columnconfigure(1, weight=1)

            self.panes[0].grid(row=0, column=0, sticky="nsew", padx=3, pady=3)
            self.panes[1].grid(row=0, column=1, sticky="nsew", padx=3, pady=3)
            self.panes[2].grid(row=1, column=0, columnspan=2, sticky="nsew", padx=3, pady=3)

            return

        if layout_mode == "grid3_bottom" and pane_count >= 3:
            # 3-pane layout: one full-width pane on top, two panes below.
            self.layout_frame.grid_rowconfigure(0, weight=1)
            self.layout_frame.grid_rowconfigure(1, weight=1)
            self.layout_frame.grid_columnconfigure(0, weight=1)
            self.layout_frame.grid_columnconfigure(1, weight=1)

            self.panes[0].grid(row=0, column=0, columnspan=2, sticky="nsew", padx=3, pady=3)
            self.panes[1].grid(row=1, column=0, sticky="nsew", padx=3, pady=3)
            self.panes[2].grid(row=1, column=1, sticky="nsew", padx=3, pady=3)

            return

        if layout_mode == "vertical":
            # Stack panes top-to-bottom.
            self.layout_frame.grid_columnconfigure(0, weight=1)

            for index, pane in enumerate(self.panes):
                self.layout_frame.grid_rowconfigure(index, weight=1)
                pane.grid(row=index, column=0, sticky="nsew", padx=3, pady=3)

            return

        # Default horizontal layout: panes side-by-side.
        self.layout_frame.grid_rowconfigure(0, weight=1)

        for index, pane in enumerate(self.panes):
            self.layout_frame.grid_columnconfigure(index, weight=1)
            pane.grid(row=0, column=index, sticky="nsew", padx=3, pady=3)

    def set_grid_layout_for_count(self, count: int) -> None:
        if count == 4:
            self.set_layout_mode("grid4")
        elif count == 3:
            self.set_layout_mode("grid3_top")
        elif count == 2:
            self.set_layout_mode("horizontal")
        else:
            self.set_layout_mode("auto")

    def set_orientation(self, orientation: str) -> None:
        self.orientation = orientation
        self.set_layout_mode("horizontal" if orientation == tk.HORIZONTAL else "vertical")

    def close_console(self, terminal: EmbeddedTerminal) -> None:
        """Close one console pane. If it was the last pane, close the tab too."""
        try:
            terminal.close()
        except Exception:
            pass

        try:
            terminal.grid_forget()
        except Exception:
            pass

        try:
            terminal.destroy()
        except Exception:
            pass

        self.panes = [pane for pane in self.panes if pane is not terminal]

        if self.active_terminal is terminal:
            self.active_terminal = self.panes[-1] if self.panes else None

        if self.app.focused_terminal is terminal:
            self.app.focused_terminal = self.active_terminal

        if self.active_terminal is not None:
            # If a special 3/4-grid loses panes, fall back to a sensible layout.
            if len(self.panes) < 3 and self.layout_mode in {"grid3_top", "grid3_bottom", "grid4"}:
                self.layout_mode = "horizontal"

            self.apply_layout()
            self.set_active_terminal(self.active_terminal)
            return

        # If that was the last/only console in the tab, remove the empty tab too.
        # after(1) lets the button callback finish before the notebook destroys widgets.
        try:
            self.after(1, lambda: self.app.close_tab_for_widget(self))
        except Exception:
            pass

    def close_active_console(self) -> None:
        terminal = self.active_terminal

        if terminal is None and self.panes:
            terminal = self.panes[-1]

        if terminal is None:
            return

        self.close_console(terminal)

    def reconnect_active_console(self) -> None:
        terminal = self.active_terminal

        if terminal is None and self.panes:
            terminal = self.panes[-1]

        if terminal is None:
            return

        terminal.reconnect()

    def run_command_on_active(self, command: str) -> None:
        terminal = self.active_terminal

        if terminal is None and self.panes:
            terminal = self.panes[-1]

        if terminal is None:
            return

        terminal.run_command(command)

    def clear_active_console(self) -> None:
        self.run_command_on_active("clear")

    def close_all(self) -> None:
        for pane in list(self.panes):
            try:
                pane.close()
            except Exception:
                pass

            try:
                pane.grid_forget()
            except Exception:
                pass

            try:
                pane.destroy()
            except Exception:
                pass

        self.panes.clear()
        self.active_terminal = None

class EmbeddedSSHLauncher(ctk.CTk if ctk is not None else tk.Tk):
    def __init__(self) -> None:
        if ctk is not None:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
            super().__init__()
            self.configure(fg_color=BG)
        else:
            super().__init__()

        self.title(APP_NAME)
        self.geometry("1440x820")
        self.minsize(1100, 680)
        self.apply_app_icon()

        APP_LOGGER.info(f"{APP_NAME} starting up")

        write_embedded_docs_to_config()

        self.profiles: list[SSHProfile] = ProfileStore.load()
        self.commands: list[QuickCommand] = CommandStore.load()

        self.selected_profile_index: int | None = None
        self.selected_command_index: int | None = None

        self.tab_counter = 0
        self.active_tab: ConsoleTab | None = None
        self.focused_terminal: EmbeddedTerminal | None = None

        # Safe tab close tracking.
        # This prevents tabs from closing when clicking/focusing/selecting terminal text.
        self.pending_tab_close_id: str | None = None
        self.pending_tab_close_press_xy: tuple[int, int] | None = None

        self.profile_buttons: list[ctk.CTkButton] = []
        self.command_buttons: list[ctk.CTkButton] = []
        self.recent_buttons: list[ctk.CTkButton] = []
        self.recent_names: list[str] = RecentStore.load()

        self.monitoring_dashboard: "MonitoringDashboardWindow | None" = None
        self._keyring_warned = False

        self._setup_styles()
        self._build_ui()
        self.refresh_profiles()
        self.refresh_commands()
        self.refresh_recent()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.maybe_restore_session()

    def apply_app_icon(self) -> None:
        """Set the window/taskbar icon. Safe no-op if the asset isn't found."""
        ico_path = find_image_path(ICON_ICO_FILE)
        if ico_path is not None:
            try:
                self.iconbitmap(str(ico_path))
            except Exception:
                pass

        png_path = find_image_path(ICON_PNG_FILE)
        if png_path is not None:
            try:
                # Keep a reference on self - PhotoImage is garbage collected
                # (and the icon silently disappears) if nothing holds onto it.
                self._icon_image = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, self._icon_image)
            except Exception:
                pass

    def _setup_styles(self) -> None:
        style = ttk.Style(self)

        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "TNotebook",
            background=BG,
            borderwidth=0,
            tabmargins=[4, 4, 4, 0],
        )
        style.configure(
            "TNotebook.Tab",
            background=PANEL_2,
            foreground=TEXT,
            padding=[14, 8],
            borderwidth=0,
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", ACCENT), ("active", CARD_HOVER)],
            foreground=[("selected", "#ffffff"), ("active", "#ffffff")],
        )
        style.configure(
            "TPanedwindow",
            background=BG,
            borderwidth=0,
        )
        style.configure(
            "Vertical.TScrollbar",
            background=PANEL_2,
            troughcolor=BG,
            arrowcolor=TEXT,
            borderwidth=0,
        )
        style.configure(
            "Horizontal.TScrollbar",
            background=PANEL_2,
            troughcolor=BG,
            arrowcolor=TEXT,
            borderwidth=0,
        )

    def _build_ui(self) -> None:
        self.sidebar_width = UIState.load_sidebar_width()
        self._sash_drag_start_x: int | None = None
        self._sash_drag_start_width: int | None = None

        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.topbar = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0) if ctk is not None else ttk.Frame(self)
        self.topbar.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.topbar.grid_columnconfigure(1, weight=1)

        self.sidebar = ctk.CTkScrollableFrame(
            self,
            fg_color=PANEL,
            corner_radius=0,
            width=self.sidebar_width,
        ) if ctk is not None else ttk.Frame(self)

        self.sidebar.grid(row=1, column=0, sticky="nsw")

        if ctk is not None:
            self.sidebar.configure(width=self.sidebar_width)
        else:
            self.sidebar.grid_propagate(False)

        if ctk is not None:
            self.sidebar_sash = ctk.CTkFrame(self, fg_color=CARD_HOVER, corner_radius=0, width=6)
            self.sidebar_sash.grid(row=1, column=1, sticky="ns")
            self.sidebar_sash.grid_propagate(False)
            try:
                self.sidebar_sash.configure(cursor="sb_h_double_arrow")
            except Exception:
                pass
            self.sidebar_sash.bind("<ButtonPress-1>", self.on_sash_press)
            self.sidebar_sash.bind("<B1-Motion>", self.on_sash_drag)
            self.sidebar_sash.bind("<ButtonRelease-1>", self.on_sash_release)

        self.main = ctk.CTkFrame(
            self,
            fg_color=BG,
            corner_radius=0,
        ) if ctk is not None else ttk.Frame(self)
        self.main.grid(row=1, column=2, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)

        self.statusbar = ctk.CTkFrame(
            self,
            fg_color=PANEL,
            corner_radius=0,
            height=32,
        ) if ctk is not None else ttk.Frame(self)
        self.statusbar.grid(row=2, column=0, columnspan=3, sticky="ew")

        self._build_topbar()
        self._build_sidebar()
        self._build_main()
        self._build_statusbar()

    def on_sash_press(self, event: tk.Event) -> None:
        self._sash_drag_start_x = event.x_root
        self._sash_drag_start_width = self.sidebar_width

    def on_sash_drag(self, event: tk.Event) -> None:
        if self._sash_drag_start_x is None or self._sash_drag_start_width is None:
            return
        delta = event.x_root - self._sash_drag_start_x
        max_width = max(MIN_SIDEBAR_WIDTH, min(MAX_SIDEBAR_WIDTH, int(self.winfo_width() * 0.5)))
        new_width = max(MIN_SIDEBAR_WIDTH, min(max_width, self._sash_drag_start_width + delta))
        if new_width != self.sidebar_width:
            self.sidebar_width = new_width
            self.sidebar.configure(width=new_width)

    def on_sash_release(self, _event: tk.Event) -> None:
        self._sash_drag_start_x = None
        self._sash_drag_start_width = None
        UIState.save_sidebar_width(self.sidebar_width)

    def _build_topbar(self) -> None:
        if ctk is not None:
            ctk.CTkLabel(
                self.topbar,
                text="Embedded SSH Launcher",
                text_color=TEXT,
                font=ctk.CTkFont(size=18, weight="bold"),
            ).grid(row=0, column=0, padx=18, pady=12, sticky="w")

            ctk.CTkLabel(
                self.topbar,
                text="Modern SSH workspace with tabs, smart layouts, split panes, and quick commands",
                text_color=MUTED,
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=1, padx=8, pady=12, sticky="w")

            button_bar = ctk.CTkFrame(self.topbar, fg_color="transparent")
            button_bar.grid(row=0, column=2, padx=14, pady=8, sticky="e")

            self._toolbar_button(button_bar, "New Tab", self.open_new_tab, ACCENT).pack(side="left", padx=4)
            self._toolbar_button(button_bar, "Split", self.split_current_tab, CARD).pack(side="left", padx=4)
            self._toolbar_button(button_bar, "Reconnect", self.reconnect_active_console, WARNING).pack(side="left", padx=4)
            self._toolbar_button(button_bar, "Clear", self.clear_focused_console, CARD).pack(side="left", padx=4)
            self._toolbar_button(button_bar, "Close", self.close_active_console, DANGER).pack(side="left", padx=4)
        else:
            ttk.Label(self.topbar, text="Embedded SSH Launcher").pack(side="left", padx=10)

    def _toolbar_button(self, parent: tk.Widget, text: str, command, color: str):
        return build_button(parent, text, command, color, width=92)

    def _build_sidebar(self) -> None:
        self._sidebar_title("Recent")

        self.recent_buttons_frame = ctk.CTkFrame(
            self.sidebar,
            fg_color="transparent",
        ) if ctk is not None else ttk.Frame(self.sidebar)
        self.recent_buttons_frame.pack(fill="x", padx=12, pady=(6, 12))

        self._sidebar_title("Profiles")

        self.profile_buttons_frame = ctk.CTkFrame(
            self.sidebar,
            fg_color="transparent",
        ) if ctk is not None else ttk.Frame(self.sidebar)
        self.profile_buttons_frame.pack(fill="x", padx=12, pady=(6, 6))

        # Outside profile_buttons_frame on purpose - that frame's children are
        # destroyed and rebuilt on every refresh_profiles() call.
        self._side_button(self.sidebar, "Import from SSH Config", self.import_from_ssh_config, CARD_HOVER)

        self._sidebar_title("Connection")

        self.profile_form = ctk.CTkFrame(
            self.sidebar,
            fg_color=CARD,
            corner_radius=14,
        ) if ctk is not None else ttk.LabelFrame(self.sidebar, text="Connection")
        self.profile_form.pack(fill="x", padx=12, pady=(0, 14))

        self.name_var = tk.StringVar()
        self.host_var = tk.StringVar()
        self.user_var = tk.StringVar()
        self.port_var = tk.StringVar(value="22")
        self.password_var = tk.StringVar()

        self.name_entry = self._form_row(self.profile_form, "Name", self.name_var)
        self.host_entry = self._form_row(self.profile_form, "Host/IP", self.host_var)
        self.user_entry = self._form_row(self.profile_form, "User", self.user_var)
        self.port_entry = self._form_row(self.profile_form, "Port", self.port_var)
        self.password_entry = self._form_row(self.profile_form, "Password", self.password_var, show="*")

        if ctk is not None:
            build_button(
                self.profile_form, "Copy Saved Password", self.copy_saved_password, CARD_HOVER,
                height=26, corner_radius=8,
            ).pack(fill="x", padx=12, pady=(0, 2))

        self.env_color_var = tk.StringVar(value="")
        self.env_swatch_buttons: dict[str, "ctk.CTkButton"] = {}

        if ctk is not None:
            ctk.CTkLabel(
                self.profile_form,
                text="Environment",
                text_color=MUTED,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", padx=12, pady=(10, 2))

            env_row = ctk.CTkFrame(self.profile_form, fg_color="transparent")
            env_row.pack(fill="x", padx=12, pady=(0, 2))

            for tag in ENV_TAG_ORDER:
                label, color = ENV_TAGS[tag]
                button = build_button(
                    env_row, label, lambda t=tag: self.set_env_color_selection(t), color,
                    height=28, corner_radius=8,
                )
                button.pack(side="left", fill="x", expand=True, padx=2)
                self.env_swatch_buttons[tag] = button

            self.set_env_color_selection("")

        self.jump_host_var = tk.StringVar(value="None")

        if ctk is not None:
            ctk.CTkLabel(
                self.profile_form,
                text="Jump Host (optional)",
                text_color=MUTED,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", padx=12, pady=(10, 2))

            self.jump_host_menu = ctk.CTkOptionMenu(
                self.profile_form,
                variable=self.jump_host_var,
                values=["None"],
                fg_color=PANEL,
                button_color=CARD_HOVER,
                button_hover_color=CARD_HOVER_2,
            )
            self.jump_host_menu.pack(fill="x", padx=12, pady=(0, 2))

        if ctk is not None:
            ctk.CTkLabel(
                self.profile_form,
                text="Custom Health Check Command (optional)",
                text_color=MUTED,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", padx=12, pady=(10, 2))

            ctk.CTkLabel(
                self.profile_form,
                text="Leave blank to use the built-in Web2py/uWSGI/Nginx check. To populate\n"
                     "the dashboard cards, echo the same __KEY__=value lines (see docs);\n"
                     "otherwise the output still shows in the dashboard's raw output panel.",
                text_color=MUTED,
                font=ctk.CTkFont(size=10),
                justify="left",
            ).pack(anchor="w", padx=12, pady=(0, 4))

            self.health_check_textbox = ctk.CTkTextbox(self.profile_form, height=70, fg_color=PANEL, wrap="none")
            self.health_check_textbox.pack(fill="x", padx=12, pady=(0, 2))
        else:
            self.health_check_textbox = tk.Text(self.profile_form, height=4)
            self.health_check_textbox.pack(fill="x")

        if ctk is not None:
            row = ctk.CTkFrame(self.profile_form, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=(8, 12))

            build_button(row, "Save", self.save_profile, SUCCESS).pack(
                side="left", fill="x", expand=True, padx=(0, 4)
            )
            build_button(row, "New", self.clear_form, CARD_HOVER).pack(
                side="left", fill="x", expand=True, padx=4
            )
            build_button(row, "Delete", self.delete_profile, DANGER).pack(
                side="left", fill="x", expand=True, padx=(4, 0)
            )
        else:
            ttk.Button(self.profile_form, text="Save", command=self.save_profile).pack(fill="x")
            ttk.Button(self.profile_form, text="New", command=self.clear_form).pack(fill="x")
            ttk.Button(self.profile_form, text="Delete", command=self.delete_profile).pack(fill="x")

        self._sidebar_title("Open Console")

        self.open_panel = ctk.CTkFrame(
            self.sidebar,
            fg_color=CARD,
            corner_radius=14,
        ) if ctk is not None else ttk.LabelFrame(self.sidebar, text="Open Console")
        self.open_panel.pack(fill="x", padx=12, pady=(0, 14))

        self._side_button(self.open_panel, "New Tab", self.open_new_tab, ACCENT)
        self._side_button(self.open_panel, "Split Current Tab", self.split_current_tab, CARD_HOVER)
        self._side_button(self.open_panel, "Open 2 Split", lambda: self.open_n_split(2), CARD_HOVER)
        self._side_button(self.open_panel, "Open 3 Split", lambda: self.open_n_split(3), CARD_HOVER)
        self._side_button(self.open_panel, "Open 4 Split", lambda: self.open_n_split(4), CARD_HOVER)
        self._side_button(self.open_panel, "File Transfer...", self.open_file_transfer_window, CARD_HOVER)

        self._sidebar_title("Layout / Session")

        self.session_panel = ctk.CTkFrame(
            self.sidebar,
            fg_color=CARD,
            corner_radius=14,
        ) if ctk is not None else ttk.LabelFrame(self.sidebar, text="Layout / Session")
        self.session_panel.pack(fill="x", padx=12, pady=(0, 14))

        self._side_button(self.session_panel, "2 Panes: Side by Side", lambda: self.set_active_layout_mode("horizontal"), CARD_HOVER)
        self._side_button(self.session_panel, "2 Panes: Stacked", lambda: self.set_active_layout_mode("vertical"), CARD_HOVER)
        self._side_button(self.session_panel, "3 Panes: 2 Top / 1 Bottom", lambda: self.set_active_layout_mode("grid3_top"), CARD_HOVER)
        self._side_button(self.session_panel, "3 Panes: 1 Top / 2 Bottom", lambda: self.set_active_layout_mode("grid3_bottom"), CARD_HOVER)
        self._side_button(self.session_panel, "4 Panes: 2 x 2 Grid", lambda: self.set_active_layout_mode("grid4"), CARD_HOVER)
        self._side_button(self.session_panel, "Auto Layout", lambda: self.set_active_layout_mode("auto"), CARD_HOVER)
        self._side_button(self.session_panel, "Rename Current Tab", self.rename_current_tab, CARD_HOVER)
        self._side_button(self.session_panel, "Reconnect Selected Console", self.reconnect_active_console, WARNING)
        self._side_button(self.session_panel, "Clear Console", self.clear_focused_console, CARD_HOVER)
        self._side_button(self.session_panel, "Close Selected Console", self.close_active_console, DANGER)
        self._side_button(self.session_panel, "Close Current Tab", self.close_current_tab, DANGER)

        self.broadcast_var = tk.BooleanVar(value=False)
        if ctk is not None:
            ctk.CTkSwitch(
                self.session_panel, text="Broadcast Typing (this tab)", variable=self.broadcast_var,
                command=self.toggle_broadcast_typing, text_color=TEXT,
            ).pack(anchor="w", padx=10, pady=(8, 10))

        self._sidebar_title("Quick Commands")

        self.commands_panel = ctk.CTkFrame(
            self.sidebar,
            fg_color=CARD,
            corner_radius=14,
        ) if ctk is not None else ttk.LabelFrame(self.sidebar, text="Quick Commands")
        self.commands_panel.pack(fill="x", padx=12, pady=(0, 14))

        self.command_buttons_frame = ctk.CTkFrame(
            self.commands_panel,
            fg_color="transparent",
        ) if ctk is not None else ttk.Frame(self.commands_panel)
        self.command_buttons_frame.pack(fill="x", padx=10, pady=(10, 8))

        if ctk is not None:
            command_tools = ctk.CTkFrame(self.commands_panel, fg_color="transparent")
            command_tools.pack(fill="x", padx=10, pady=(0, 10))

            ctk.CTkButton(
                command_tools,
                text="Add",
                command=self.add_command,
                fg_color=SUCCESS,
                hover_color="#15803d",
                height=32,
                width=70,
                corner_radius=10,
            ).pack(side="left", expand=True, fill="x", padx=(0, 3))

            ctk.CTkButton(
                command_tools,
                text="Edit",
                command=self.edit_command,
                fg_color=WARNING,
                hover_color="#92400e",
                height=32,
                width=70,
                corner_radius=10,
            ).pack(side="left", expand=True, fill="x", padx=3)

            ctk.CTkButton(
                command_tools,
                text="Delete",
                command=self.delete_command,
                fg_color=DANGER,
                hover_color="#991b1b",
                height=32,
                width=70,
                corner_radius=10,
            ).pack(side="left", expand=True, fill="x", padx=(3, 0))
        else:
            ttk.Button(self.commands_panel, text="Add", command=self.add_command).pack(fill="x")
            ttk.Button(self.commands_panel, text="Edit", command=self.edit_command).pack(fill="x")
            ttk.Button(self.commands_panel, text="Delete", command=self.delete_command).pack(fill="x")


        self._sidebar_title("Monitoring")

        self.monitoring_panel = ctk.CTkFrame(
            self.sidebar,
            fg_color=CARD,
            corner_radius=14,
        ) if ctk is not None else ttk.LabelFrame(self.sidebar, text="Monitoring")
        self.monitoring_panel.pack(fill="x", padx=12, pady=(0, 14))

        self._side_button(self.monitoring_panel, "Open Dashboard", self.open_monitoring_dashboard, ACCENT)
        self._side_button(self.monitoring_panel, "Monitor All Profiles", self.open_multi_server_monitor, ACCENT)
        self._side_button(self.monitoring_panel, "Run Health Check", self.run_health_check_in_terminal, CARD_HOVER)
        self._side_button(self.monitoring_panel, "502 / Gateway Check", self.run_gateway_check, WARNING)
        self._side_button(self.monitoring_panel, "Connections", self.run_connections_check, CARD_HOVER)
        self._side_button(self.monitoring_panel, "Active Users / IPs", self.run_active_users_check, CARD_HOVER)
        self._side_button(self.monitoring_panel, "Recent Errors", self.run_recent_errors_check, CARD_HOVER)
        self._side_button(self.monitoring_panel, "Web2py Processes", self.run_web2py_process_check, CARD_HOVER)

        self._sidebar_title("Security")

        self.security_panel = ctk.CTkFrame(
            self.sidebar,
            fg_color=CARD,
            corner_radius=14,
        ) if ctk is not None else ttk.LabelFrame(self.sidebar, text="Security")
        self.security_panel.pack(fill="x", padx=12, pady=(0, 14))

        self._side_button(self.security_panel, "Connection Audit Log", self.open_audit_log, CARD_HOVER)

        self._sidebar_title("Documentation")

        self.docs_panel = ctk.CTkFrame(
            self.sidebar,
            fg_color=CARD,
            corner_radius=14,
        ) if ctk is not None else ttk.LabelFrame(self.sidebar, text="Documentation")
        self.docs_panel.pack(fill="x", padx=12, pady=(0, 14))

        self._side_button(self.docs_panel, "Open Documentation", self.open_documentation, ACCENT)
        self._side_button(self.docs_panel, "README", lambda: self.open_documentation(DOC_README_FILE), CARD_HOVER)
        self._side_button(self.docs_panel, "Version History", lambda: self.open_documentation(DOC_VERSION_FILE), CARD_HOVER)
        self._side_button(self.docs_panel, "Features Plan", lambda: self.open_documentation(DOC_FEATURES_FILE), CARD_HOVER)

        self._sidebar_title("Tools")

        self.tools_panel = ctk.CTkFrame(
            self.sidebar,
            fg_color=CARD,
            corner_radius=14,
        ) if ctk is not None else ttk.LabelFrame(self.sidebar, text="Tools")
        self.tools_panel.pack(fill="x", padx=12, pady=(0, 20))

        self._side_button(self.tools_panel, "Check Requirements", self.check_requirements, CARD_HOVER)
        self._side_button(self.tools_panel, "Open Config Folder", self.open_config_folder, CARD_HOVER)
        self._side_button(self.tools_panel, "Debug Log Viewer", self.open_debug_log_viewer, CARD_HOVER)

    def _sidebar_title(self, text: str) -> None:
        if ctk is not None:
            ctk.CTkLabel(
                self.sidebar,
                text=text,
                text_color=TEXT,
                font=ctk.CTkFont(size=15, weight="bold"),
            ).pack(anchor="w", padx=14, pady=(12, 2))
        else:
            ttk.Label(self.sidebar, text=text).pack(anchor="w")

    def _form_row(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
        show: str | None = None,
    ):
        if ctk is not None:
            ctk.CTkLabel(
                parent,
                text=label,
                text_color=MUTED,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", padx=12, pady=(10, 2))

            entry = ctk.CTkEntry(
                parent,
                textvariable=variable,
                show=show or "",
                fg_color=PANEL,
                border_color="#374151",
                text_color=TEXT,
                height=34,
                corner_radius=10,
            )
            entry.pack(fill="x", padx=12, pady=(0, 2))
            return entry

        ttk.Label(parent, text=label).pack(anchor="w")
        entry = ttk.Entry(parent, textvariable=variable, show=show)
        entry.pack(fill="x")
        return entry

    def _side_button(self, parent: tk.Widget, text: str, command, color: str) -> None:
        if ctk is not None:
            build_button(parent, text, command, color, anchor="w").pack(fill="x", padx=10, pady=4)
        else:
            ttk.Button(parent, text=text, command=command).pack(fill="x")

    def _build_main(self) -> None:
        hint_panel = ctk.CTkFrame(
            self.main,
            fg_color=PANEL,
            corner_radius=14,
        ) if ctk is not None else ttk.Frame(self.main)
        hint_panel.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 8))
        hint_panel.grid_columnconfigure(0, weight=1)

        if ctk is not None:
            ctk.CTkLabel(
                hint_panel,
                text="Double-click a profile to open SSH. Click a quick command to run it in the focused console. Click × on a tab to close it.",
                text_color=MUTED,
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=0, padx=14, pady=10, sticky="w")
        else:
            ttk.Label(
                hint_panel,
                text="Double-click a profile to open SSH. Click a quick command to run it in the focused console. Click × on a tab to close it.",
            ).grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.notebook = ttk.Notebook(self.main)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.notebook.bind("<Double-Button-1>", self.on_notebook_double_click)

        # Safer X-close handling.
        # We track press and release so a random release/focus click cannot close a tab.
        self.notebook.bind("<ButtonPress-1>", self.on_notebook_button_press)
        self.notebook.bind("<ButtonRelease-1>", self.on_notebook_button_release)

    def _build_statusbar(self) -> None:
        self.status_var = tk.StringVar(value="Ready")

        if ctk is not None:
            ctk.CTkLabel(
                self.statusbar,
                textvariable=self.status_var,
                text_color=MUTED,
                font=ctk.CTkFont(size=12),
            ).pack(side="left", padx=14, pady=6)
        else:
            ttk.Label(self.statusbar, textvariable=self.status_var).pack(side="left", padx=10)

    def tab_text(self, title: str) -> str:
        clean = title.replace("×", "").strip()
        return clean + TAB_CLOSE_SUFFIX

    def tab_title_without_close(self, tab_id: str) -> str:
        title = self.notebook.tab(tab_id, "text")
        return title.replace("×", "").strip()

    def refresh_profiles(self) -> None:
        for widget in self.profile_buttons_frame.winfo_children():
            widget.destroy()

        self.profile_buttons = []

        for index, profile in enumerate(self.profiles):
            label = f"{profile.name}\n{profile.user}@{profile.host}:{profile.port}"
            _env_label, env_border = ENV_TAGS.get(profile.env_color, ENV_TAGS[""])

            if ctk is not None:
                button = ctk.CTkButton(
                    self.profile_buttons_frame,
                    text=label,
                    command=lambda i=index: self.select_profile(i),
                    fg_color=CARD,
                    hover_color=CARD_HOVER,
                    text_color=TEXT,
                    anchor="w",
                    height=52,
                    corner_radius=12,
                    border_width=3 if profile.env_color else 0,
                    border_color=env_border,
                )
                button.pack(fill="x", pady=4)
                button.bind("<Double-Button-1>", lambda _event, i=index: self.open_profile_by_index(i))
                self.profile_buttons.append(button)
            else:
                button = ttk.Button(
                    self.profile_buttons_frame,
                    text=label,
                    command=lambda i=index: self.select_profile(i),
                )
                button.pack(fill="x")
                self.profile_buttons.append(button)

        self.refresh_jump_host_options()

    def refresh_jump_host_options(self, exclude_name: str | None = None) -> None:
        if ctk is None or not hasattr(self, "jump_host_menu"):
            return
        names = [p.name for p in self.profiles if p.name != exclude_name]
        values = ["None"] + names
        self.jump_host_menu.configure(values=values)
        if self.jump_host_var.get() not in values:
            self.jump_host_var.set("None")

    def refresh_recent(self) -> None:
        for widget in self.recent_buttons_frame.winfo_children():
            widget.destroy()

        self.recent_buttons = []
        by_name = {profile.name: profile for profile in self.profiles}

        for name in self.recent_names:
            profile = by_name.get(name)
            if profile is None:
                continue  # renamed or deleted since it was last opened - skip silently

            label = f"{profile.name}\n{profile.user}@{profile.host}:{profile.port}"
            _env_label, env_border = ENV_TAGS.get(profile.env_color, ENV_TAGS[""])

            if ctk is not None:
                button = build_button(
                    self.recent_buttons_frame,
                    label,
                    lambda n=name: self.open_profile_by_name(n),
                    CARD,
                    height=44,
                    corner_radius=12,
                    anchor="w",
                    border_width=3 if profile.env_color else 0,
                    border_color=env_border,
                )
                button.pack(fill="x", pady=3)
                self.recent_buttons.append(button)
            else:
                button = ttk.Button(
                    self.recent_buttons_frame,
                    text=label,
                    command=lambda n=name: self.open_profile_by_name(n),
                )
                button.pack(fill="x")
                self.recent_buttons.append(button)

        if not self.recent_buttons and ctk is not None:
            ctk.CTkLabel(
                self.recent_buttons_frame,
                text="Profiles you open will show up here.",
                text_color=MUTED,
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=2, pady=2)

    def record_recent_connection(self, name: str) -> None:
        self.recent_names = RecentStore.record(name)
        self.refresh_recent()

    def select_profile(self, index: int) -> None:
        if index < 0 or index >= len(self.profiles):
            return

        self.selected_profile_index = index
        profile = self.profiles[index]

        self.name_var.set(profile.name)
        self.host_var.set(profile.host)
        self.user_var.set(profile.user)
        self.port_var.set(str(profile.port))
        self.password_var.set("")
        self.set_env_color_selection(profile.env_color)
        self.refresh_jump_host_options(exclude_name=profile.name)
        self.jump_host_var.set(profile.jump_profile_name or "None")
        self.health_check_textbox.delete("1.0", "end")
        self.health_check_textbox.insert("1.0", profile.health_check_command)

        for idx, button in enumerate(self.profile_buttons):
            if ctk is not None:
                selected = idx == index
                button.configure(
                    fg_color=ACCENT if selected else CARD,
                    hover_color=ACCENT_HOVER if selected else CARD_HOVER,
                )

        self.status_var.set(f"Selected profile: {profile.name}")

    def open_profile_by_index(self, index: int) -> None:
        self.select_profile(index)
        self.open_new_tab()

    def open_profile_by_name(self, name: str) -> None:
        for index, profile in enumerate(self.profiles):
            if profile.name == name:
                self.open_profile_by_index(index)
                return

    def set_env_color_selection(self, tag: str) -> None:
        """Update the Environment swatch row in the Connection form to show `tag` selected."""
        if tag not in ENV_TAGS:
            tag = ""
        self.env_color_var.set(tag)
        if ctk is None:
            return
        for swatch_tag, button in self.env_swatch_buttons.items():
            selected = swatch_tag == tag
            button.configure(border_width=3 if selected else 0, border_color=TEXT)

    def refresh_commands(self) -> None:
        for widget in self.command_buttons_frame.winfo_children():
            widget.destroy()

        self.command_buttons = []

        for index, command in enumerate(self.commands):
            if ctk is not None:
                button = ctk.CTkButton(
                    self.command_buttons_frame,
                    text=command.name,
                    command=lambda i=index: self.run_command_by_index(i),
                    fg_color=ACCENT if command.name.lower() == "clear" else CARD_HOVER,
                    hover_color=ACCENT_HOVER,
                    text_color=TEXT,
                    anchor="w",
                    height=34,
                    corner_radius=10,
                )
                button.pack(fill="x", pady=4)
                button.bind("<Button-3>", lambda _event, i=index: self.select_command(i))
                self.command_buttons.append(button)
            else:
                button = ttk.Button(
                    self.command_buttons_frame,
                    text=command.name,
                    command=lambda i=index: self.run_command_by_index(i),
                )
                button.pack(fill="x")
                self.command_buttons.append(button)

    def select_command(self, index: int) -> None:
        if index < 0 or index >= len(self.commands):
            return

        self.selected_command_index = index

        for idx, button in enumerate(self.command_buttons):
            if ctk is not None:
                selected_color = ACCENT if idx == index else CARD_HOVER
                button.configure(fg_color=selected_color)

        self.status_var.set(f"Selected command: {self.commands[index].name}")

    def selected_profile(self) -> SSHProfile | None:
        if self.selected_profile_index is None:
            show_message(self, "error", APP_NAME, "Select a saved profile first.")
            return None

        if self.selected_profile_index < 0 or self.selected_profile_index >= len(self.profiles):
            show_message(self, "error", APP_NAME, "Selected profile is invalid.")
            return None

        return self.profiles[self.selected_profile_index]

    def selected_command(self) -> QuickCommand | None:
        if self.selected_command_index is None:
            show_message(self, "error", APP_NAME, "Right-click or select a command first.")
            return None

        if self.selected_command_index < 0 or self.selected_command_index >= len(self.commands):
            return None

        return self.commands[self.selected_command_index]

    def refresh_open_panes_for_profile(self, profile: SSHProfile) -> None:
        """Update already-open terminal headers after profile is edited in place."""
        for tab_id in self.notebook.tabs():
            tab = self.nametowidget(tab_id)
            for pane in tab.panes:
                if pane.profile is profile:
                    pane.refresh_header_label()

    def warn_keyring_failure_once(self, exc: Exception) -> None:
        """Warn about a keyring/password-save failure at most once per app session.

        Without this, a persistently failing keyring backend would otherwise
        re-prompt via a blocking modal on every monitoring auto-refresh tick.
        """
        if getattr(self, "_keyring_warned", False):
            print(f"[keyring] password save failed (already warned once): {exc}")
            return
        self._keyring_warned = True
        show_message(self, "warning", APP_NAME, f"Could not save password securely.\n\n{exc}")

    def save_profile(self) -> None:
        name = self.name_var.get().strip()
        host = self.host_var.get().strip()
        user = self.user_var.get().strip()
        password = self.password_var.get()

        if not name or not host or not user:
            show_message(self, "error", APP_NAME, "Name, Host/IP, and User are required.")
            return

        try:
            port = int(self.port_var.get().strip())

            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            show_message(self, "error", APP_NAME, "Port must be a number from 1 to 65535.")
            return

        duplicate = any(
            i != self.selected_profile_index and existing.name.strip().lower() == name.lower()
            for i, existing in enumerate(self.profiles)
        )
        if duplicate:
            show_message(
                self,
                "error",
                APP_NAME,
                f"A profile named '{name}' already exists. Choose a unique name.\n\n"
                "(Profile names are used as the credential-store key, so duplicate "
                "names would share the same saved password.)",
            )
            return

        jump_profile_name = self.jump_host_var.get()
        if jump_profile_name == "None":
            jump_profile_name = ""
        if jump_profile_name and jump_profile_name.strip().lower() == name.strip().lower():
            show_message(self, "error", APP_NAME, "A profile can't be its own jump host.")
            return

        old_name = None
        env_color = self.env_color_var.get()
        if env_color not in ENV_TAGS:
            env_color = ""
        health_check_command = self.health_check_textbox.get("1.0", "end").rstrip("\n")

        if self.selected_profile_index is None:
            profile = SSHProfile(
                name=name, host=host, user=user, port=port,
                env_color=env_color, jump_profile_name=jump_profile_name,
                health_check_command=health_check_command,
            )
            self.profiles.append(profile)
            self.selected_profile_index = len(self.profiles) - 1
        else:
            # Mutate the existing SSHProfile object in place (instead of replacing
            # the list entry) so already-open EmbeddedTerminal panes - which hold a
            # reference to this same object - can be refreshed to show the new
            # name/host/port instead of going stale.
            profile = self.profiles[self.selected_profile_index]
            old_name = profile.name
            profile.name, profile.host, profile.user, profile.port = name, host, user, port
            profile.env_color = env_color
            profile.jump_profile_name = jump_profile_name
            profile.health_check_command = health_check_command
            self.refresh_open_panes_for_profile(profile)

        if old_name and old_name != name:
            PasswordStore.delete(old_name)
            self.recent_names = RecentStore.rename(old_name, name)

        if password:
            try:
                PasswordStore.save(name, password)
            except Exception as exc:
                self.warn_keyring_failure_once(exc)

        ProfileStore.save(self.profiles)
        self.refresh_profiles()
        self.refresh_recent()
        self.select_profile(self.selected_profile_index)
        self.status_var.set(f"Saved profile: {name}")

    def copy_saved_password(self) -> None:
        if self.selected_profile_index is None:
            show_message(self, "info", APP_NAME, "Select a saved profile first.")
            return

        profile = self.profiles[self.selected_profile_index]
        password = self.password_var.get()
        if not password:
            try:
                password = PasswordStore.get(profile.name) or ""
            except Exception:
                password = ""

        if not password:
            show_message(self, "info", APP_NAME, "No saved password for this profile.")
            return

        self.clipboard_clear()
        self.clipboard_append(password)
        self.status_var.set(f"Copied password for {profile.name} to clipboard - clears in {CLIPBOARD_CLEAR_SECONDS}s")
        self.after(CLIPBOARD_CLEAR_SECONDS * 1000, lambda: self.clear_clipboard_if_unchanged(password))

    def clear_clipboard_if_unchanged(self, expected: str) -> None:
        try:
            current = self.clipboard_get()
        except Exception:
            return
        if current == expected:
            try:
                self.clipboard_clear()
            except Exception:
                pass

    def clear_form(self) -> None:
        self.selected_profile_index = None

        self.name_var.set("")
        self.host_var.set("")
        self.user_var.set("")
        self.port_var.set("22")
        self.password_var.set("")
        self.set_env_color_selection("")
        self.refresh_jump_host_options()
        self.jump_host_var.set("None")
        self.health_check_textbox.delete("1.0", "end")

        for button in self.profile_buttons:
            if ctk is not None:
                button.configure(fg_color=CARD)

        self.status_var.set("Ready for new profile")

    def delete_profile(self) -> None:
        if self.selected_profile_index is None:
            show_message(self, "error", APP_NAME, "Select a profile first.")
            return

        profile = self.profiles[self.selected_profile_index]

        if not show_message(self, "confirm", APP_NAME, f"Delete profile '{profile.name}'?"):
            return

        PasswordStore.delete(profile.name)
        del self.profiles[self.selected_profile_index]
        self.recent_names = RecentStore.remove(profile.name)

        self.selected_profile_index = None

        ProfileStore.save(self.profiles)
        self.refresh_profiles()
        self.refresh_recent()
        self.clear_form()
        self.status_var.set(f"Deleted profile: {profile.name}")

    def import_from_ssh_config(self) -> None:
        path = find_ssh_config_path()
        if path is None:
            show_message(self, "error", APP_NAME, "No SSH config file found at ~/.ssh/config.")
            return

        entries = parse_ssh_config(path)
        if not entries:
            show_message(self, "info", APP_NAME, "No importable Host entries found in ~/.ssh/config.")
            return

        selected = ask_ssh_config_import(self, entries)
        if not selected:
            return

        existing_names = {p.name.strip().lower() for p in self.profiles}
        imported = 0
        skipped = 0

        for entry in selected:
            if entry["name"].strip().lower() in existing_names:
                skipped += 1
                continue
            profile = SSHProfile(name=entry["name"], host=entry["host"], user=entry["user"], port=entry["port"])
            self.profiles.append(profile)
            existing_names.add(profile.name.strip().lower())
            imported += 1

        if imported:
            ProfileStore.save(self.profiles)
            self.refresh_profiles()

        self.status_var.set(f"Imported {imported} profile(s), skipped {skipped} (name already exists).")

    def add_command(self) -> None:
        name = ask_text(self, APP_NAME, "Command button name:")

        if name is None:
            return

        name = name.strip()

        if not name:
            return

        command = ask_text(self, APP_NAME, "Command to run:")

        if command is None:
            return

        command = command.strip()

        if not command:
            return

        self.commands.append(QuickCommand(name=name, command=command))
        CommandStore.save(self.commands)
        self.refresh_commands()
        self.status_var.set(f"Added command: {name}")

    def edit_command(self) -> None:
        selected = self.selected_command()

        if selected is None:
            return

        old_index = self.selected_command_index

        name = ask_text(
            self,
            APP_NAME,
            "Command button name:",
            initial_value=selected.name,
        )

        if name is None:
            return

        name = name.strip()

        if not name:
            return

        command = ask_text(
            self,
            APP_NAME,
            "Command to run:",
            initial_value=selected.command,
        )

        if command is None:
            return

        command = command.strip()

        if not command:
            return

        self.commands[old_index] = QuickCommand(name=name, command=command)
        CommandStore.save(self.commands)
        self.refresh_commands()
        self.select_command(old_index)
        self.status_var.set(f"Edited command: {name}")

    def delete_command(self) -> None:
        selected = self.selected_command()

        if selected is None:
            return

        if not show_message(self, "confirm", APP_NAME, f"Delete command '{selected.name}'?"):
            return

        del self.commands[self.selected_command_index]
        self.selected_command_index = None
        CommandStore.save(self.commands)
        self.refresh_commands()
        self.status_var.set(f"Deleted command: {selected.name}")

    def tab_for_terminal(self, terminal: EmbeddedTerminal | None) -> ConsoleTab | None:
        if terminal is None:
            return None

        for tab_id in self.notebook.tabs():
            try:
                tab = self.nametowidget(tab_id)
            except Exception:
                continue

            if isinstance(tab, ConsoleTab) and terminal in tab.panes:
                return tab

        return None

    def get_target_terminal(self) -> EmbeddedTerminal | None:
        """Return the console that toolbar and quick-command actions should affect."""
        terminal = self.focused_terminal

        if terminal is not None and self.tab_for_terminal(terminal) is not None:
            return terminal

        tab = self.current_tab()
        if tab is not None:
            if tab.active_terminal is not None:
                self.focused_terminal = tab.active_terminal
                return tab.active_terminal
            if tab.panes:
                self.focused_terminal = tab.panes[-1]
                return tab.panes[-1]

        self.focused_terminal = None
        return None

    def close_tab_for_widget(self, tab_widget: ConsoleTab) -> None:
        for tab_id in list(self.notebook.tabs()):
            try:
                if self.nametowidget(tab_id) is tab_widget:
                    self.close_tab_by_id(tab_id)
                    return
            except Exception:
                continue

    def run_command_by_index(self, index: int) -> None:
        if index < 0 or index >= len(self.commands):
            return

        self.select_command(index)
        command = self.commands[index]
        self.run_command_on_focused_console(command.command)
        self.status_var.set(f"Ran command: {command.name}")

    def run_command_on_focused_console(self, command: str) -> None:
        terminal = self.get_target_terminal()

        if terminal is None:
            show_message(self, "error", APP_NAME, "No active console found.")
            return

        if not terminal.alive:
            show_message(self, "warning", APP_NAME, "The selected console is disconnected. Use Reconnect first.")
            return

        terminal.run_command(command)

    def clear_focused_console(self) -> None:
        terminal = self.get_target_terminal()

        if terminal is None:
            show_message(self, "error", APP_NAME, "No active console found.")
            return

        if terminal.alive:
            terminal.run_command("clear")
        else:
            terminal.clear_terminal_widget()

        self.status_var.set("Cleared focused console")

    def create_console_tab(self, title: str | None = None) -> ConsoleTab:
        self.tab_counter += 1

        tab = ConsoleTab(self.notebook, self)
        raw_title = title or f"Tab {self.tab_counter}"

        self.notebook.add(tab, text=self.tab_text(raw_title))
        self.notebook.select(tab)

        self.active_tab = tab
        return tab

    def current_tab(self) -> ConsoleTab | None:
        selected = self.notebook.select()

        if not selected:
            return None

        widget = self.nametowidget(selected)

        if isinstance(widget, ConsoleTab):
            self.active_tab = widget
            return widget

        return None

    def open_new_tab(self) -> None:
        profile = self.selected_profile()

        if profile is None:
            return

        tab = self.create_console_tab(profile.name)
        tab.add_console(profile)

        self.status_var.set(f"Opened new tab for {profile.name}")

    def split_current_tab(self) -> None:
        profile = self.selected_profile()

        if profile is None:
            return

        tab = self.current_tab()

        if tab is None:
            tab = self.create_console_tab(profile.name)

        tab.add_console(profile)
        self.status_var.set(f"Added split console for {profile.name}")

    def open_n_split(self, count: int) -> None:
        profile = self.selected_profile()

        if profile is None:
            return

        tab = self.create_console_tab(f"{profile.name} x{count}")

        for _ in range(count):
            tab.add_console(profile)

        # v1.3.8:
        # Open 3 split now uses 2 panes on top and 1 full-width pane on bottom.
        # Open 4 split now uses a 2 x 2 square layout instead of a long strip.
        tab.set_grid_layout_for_count(count)

        if count == 4:
            layout_label = "2 x 2 grid"
        elif count == 3:
            layout_label = "2 top + 1 bottom grid"
        else:
            layout_label = "split"

        self.status_var.set(f"Opened {count} consoles for {profile.name} using {layout_label}")

    def layout_mode_label(self, layout_mode: str) -> str:
        labels = {
            "auto": "auto",
            "horizontal": "2 panes side by side / horizontal",
            "vertical": "2 panes stacked / vertical",
            "grid3_top": "3 panes: 2 top / 1 bottom",
            "grid3_bottom": "3 panes: 1 top / 2 bottom",
            "grid4": "4 panes: 2 x 2 grid",
        }
        return labels.get(layout_mode, layout_mode)

    def set_active_layout_mode(self, layout_mode: str) -> None:
        tab = self.current_tab()

        if tab is None:
            show_message(self, "error", APP_NAME, "No tab selected.")
            return

        tab.set_layout_mode(layout_mode)
        self.status_var.set(f"Changed layout to {self.layout_mode_label(layout_mode)}")

    def set_active_orientation(self, orientation: str) -> None:
        tab = self.current_tab()

        if tab is None:
            return

        tab.set_orientation(orientation)

        label = "vertical" if orientation == tk.VERTICAL else "horizontal"
        self.status_var.set(f"Changed split layout to {label}")

    def rename_current_tab(self) -> None:
        selected = self.notebook.select()

        if not selected:
            show_message(self, "error", APP_NAME, "No tab selected.")
            return

        current_name = self.tab_title_without_close(selected)

        new_name = ask_text(
            self,
            APP_NAME,
            "New tab name:",
            initial_value=current_name,
        )

        if new_name is None:
            return

        new_name = new_name.strip()

        if not new_name:
            return

        self.notebook.tab(selected, text=self.tab_text(new_name))
        self.status_var.set(f"Renamed tab to {new_name}")

    def reconnect_active_console(self) -> None:
        terminal = self.get_target_terminal()

        if terminal is None:
            show_message(self, "error", APP_NAME, "No active console found.")
            return

        terminal.reconnect()
        self.status_var.set("Reconnected selected console")

    def close_active_console(self) -> None:
        terminal = self.get_target_terminal()

        if terminal is None:
            show_message(self, "error", APP_NAME, "No active console found.")
            return

        tab = self.tab_for_terminal(terminal)
        if tab is None:
            show_message(self, "error", APP_NAME, "Could not find the selected console tab.")
            return

        tab.close_console(terminal)
        self.status_var.set("Closed selected console")

    def close_current_tab(self) -> None:
        selected = self.notebook.select()

        if not selected:
            return

        self.close_tab_by_id(selected)

    def close_tab_by_id(self, tab_id: str) -> None:
        """Fully close a notebook tab and destroy all SSH panes inside it."""
        tabs_before = list(self.notebook.tabs())

        if tab_id not in tabs_before:
            return

        try:
            tab_name = self.tab_title_without_close(tab_id)
        except Exception:
            tab_name = "tab"

        try:
            tab_widget = self.nametowidget(tab_id)
        except Exception:
            tab_widget = None

        if isinstance(tab_widget, ConsoleTab):
            if self.focused_terminal in tab_widget.panes:
                self.focused_terminal = None

            if self.active_tab is tab_widget:
                self.active_tab = None

            tab_widget.close_all()

        try:
            self.notebook.forget(tab_id)
        except Exception:
            pass

        try:
            if tab_widget is not None:
                tab_widget.destroy()
        except Exception:
            pass

        self.pending_tab_close_id = None
        self.pending_tab_close_press_xy = None

        remaining_tabs = list(self.notebook.tabs())

        if remaining_tabs:
            try:
                old_index = tabs_before.index(tab_id)
                next_index = min(old_index, len(remaining_tabs) - 1)
                next_tab_id = remaining_tabs[next_index]
                self.notebook.select(next_tab_id)
                new_widget = self.nametowidget(next_tab_id)

                if isinstance(new_widget, ConsoleTab):
                    self.active_tab = new_widget

                    if new_widget.active_terminal is not None:
                        self.focused_terminal = new_widget.active_terminal
                        new_widget.set_active_terminal(new_widget.active_terminal)
                    elif new_widget.panes:
                        self.focused_terminal = new_widget.panes[-1]
                        new_widget.set_active_terminal(new_widget.panes[-1])
                    else:
                        self.focused_terminal = None
            except Exception:
                self.active_tab = None
                self.focused_terminal = None
        else:
            self.active_tab = None
            self.focused_terminal = None

        self.status_var.set(f"Closed tab: {tab_name}")

    def on_tab_changed(self, _event: object | None = None) -> None:
        tab = self.current_tab()
        if tab is not None:
            if tab.active_terminal is not None:
                tab.set_active_terminal(tab.active_terminal)
            elif tab.panes:
                tab.set_active_terminal(tab.panes[-1])

        # Keep the Broadcast Typing switch in sync with whichever tab is now
        # active - each tab has its own independent on/off state.
        if hasattr(self, "broadcast_var"):
            self.broadcast_var.set(tab.broadcast_enabled if tab is not None else False)

    def toggle_broadcast_typing(self) -> None:
        tab = self.current_tab()
        if tab is None:
            self.broadcast_var.set(False)
            return
        tab.broadcast_enabled = self.broadcast_var.get()
        state = "enabled" if tab.broadcast_enabled else "disabled"
        self.status_var.set(f"Broadcast typing {state} for this tab")

    def on_notebook_double_click(self, event: tk.Event) -> None:
        # A double-click on/near the x close zone must never trigger a rename.
        # Without this guard, the first click's deferred close (see
        # on_notebook_button_release) can close a tab 1ms later, shifting
        # later tabs left, and the second click of the same double-click then
        # resolves against whatever tab slid into that position - opening the
        # rename dialog on the wrong tab.
        if self.get_tab_close_candidate(event) is not None:
            return

        try:
            clicked_tab = self.notebook.index(f"@{event.x},{event.y}")
        except Exception:
            return

        self.notebook.select(clicked_tab)
        self.rename_current_tab()

    def get_tab_close_candidate(self, event: tk.Event) -> str | None:
        """
        Return a tab id only if the event is clearly on the X area of a tab.

        This is intentionally strict to prevent accidental closes when:
        - focusing a terminal
        - selecting terminal text
        - clicking a tab label
        - dragging the mouse
        """

        # Only accept events that really belong to the notebook widget.
        if event.widget is not self.notebook:
            return None

        try:
            clicked_tab_index = self.notebook.index(f"@{event.x},{event.y}")
        except Exception:
            return None

        tabs = self.notebook.tabs()

        if clicked_tab_index < 0 or clicked_tab_index >= len(tabs):
            return None

        tab_id = tabs[clicked_tab_index]

        try:
            bbox = self.notebook.bbox(clicked_tab_index)
        except Exception:
            return None

        if not bbox:
            return None

        tab_x, tab_y, tab_width, tab_height = bbox

        # Must be vertically inside the real tab area.
        if event.y < tab_y or event.y > tab_y + tab_height:
            return None

        # Smaller close zone than before.
        # Old value was 24 px and was too easy to trigger accidentally.
        close_zone_width = 12
        close_zone_left = tab_x + tab_width - close_zone_width

        if event.x < close_zone_left or event.x > tab_x + tab_width:
            return None

        title = self.notebook.tab(tab_id, "text")

        if "×" not in title:
            return None

        return tab_id

    def on_notebook_button_press(self, event: tk.Event) -> None:
        self.pending_tab_close_id = self.get_tab_close_candidate(event)

        if self.pending_tab_close_id is not None:
            self.pending_tab_close_press_xy = (event.x, event.y)
        else:
            self.pending_tab_close_press_xy = None

    def on_notebook_button_release(self, event: tk.Event) -> None:
        tab_to_close = self.pending_tab_close_id

        if tab_to_close is None:
            return

        try:
            if tab_to_close not in self.notebook.tabs():
                self.pending_tab_close_id = None
                self.pending_tab_close_press_xy = None
                return
        except Exception:
            self.pending_tab_close_id = None
            self.pending_tab_close_press_xy = None
            return

        if self.pending_tab_close_press_xy is None:
            self.pending_tab_close_id = None
            return

        press_x, press_y = self.pending_tab_close_press_xy

        if abs(event.x - press_x) > 4 or abs(event.y - press_y) > 4:
            self.pending_tab_close_id = None
            self.pending_tab_close_press_xy = None
            return

        release_candidate = self.get_tab_close_candidate(event)

        self.pending_tab_close_id = None
        self.pending_tab_close_press_xy = None

        if release_candidate == tab_to_close:
            self.after(1, lambda tab_id=tab_to_close: self.close_tab_by_id(tab_id))


    def open_monitoring_dashboard(self) -> None:
        if self.monitoring_dashboard is not None and self.monitoring_dashboard.winfo_exists():
            self.monitoring_dashboard.lift()
            self.monitoring_dashboard.focus()
            return
        try:
            self.monitoring_dashboard = MonitoringDashboardWindow(self)
            self.status_var.set("Opened web host monitoring dashboard")
        except Exception as exc:
            self.monitoring_dashboard = None
            show_message(self, "error", APP_NAME, f"Could not open monitoring dashboard.\n\n{exc}")

    def open_file_transfer_window(self) -> None:
        try:
            FileTransferWindow(self)
            self.status_var.set("Opened file transfer window")
        except Exception as exc:
            show_message(self, "error", APP_NAME, f"Could not open file transfer window.\n\n{exc}")

    def open_multi_server_monitor(self) -> None:
        if not self.profiles:
            show_message(self, "info", APP_NAME, "No saved profiles yet. Add a profile first.")
            return
        try:
            MultiServerMonitorWindow(self)
            self.status_var.set("Opened multi-server monitor")
        except Exception as exc:
            show_message(self, "error", APP_NAME, f"Could not open multi-server monitor.\n\n{exc}")

    def open_audit_log(self) -> None:
        try:
            AuditLogWindow(self)
            self.status_var.set("Opened connection audit log")
        except Exception as exc:
            show_message(self, "error", APP_NAME, f"Could not open audit log.\n\n{exc}")

    def open_debug_log_viewer(self) -> None:
        try:
            DebugLogViewer(self)
            self.status_var.set("Opened debug log viewer")
        except Exception as exc:
            show_message(self, "error", APP_NAME, f"Could not open debug log viewer.\n\n{exc}")

    def get_monitoring_profile(self) -> SSHProfile | None:
        if self.focused_terminal is not None:
            return self.focused_terminal.profile
        if self.selected_profile_index is not None and 0 <= self.selected_profile_index < len(self.profiles):
            return self.profiles[self.selected_profile_index]
        tab = self.current_tab()
        if tab is not None and tab.active_terminal is not None:
            return tab.active_terminal.profile
        return None

    def run_remote_monitoring_command(self, profile: SSHProfile, command: str, callback) -> None:
        plink_path = self.find_plink()
        if not plink_path:
            self.after(0, lambda: callback(False, "", "plink.exe was not found."))
            return

        password = PasswordStore.get(profile.name)
        if password is None:
            password = ask_text(self, APP_NAME, f"Password for {profile.user}@{profile.host}", password=True)
            if password is None:
                self.after(0, lambda: callback(False, "", "Password was not provided."))
                return
            try:
                PasswordStore.save(profile.name, password)
            except Exception as exc:
                self.warn_keyring_failure_once(exc)

        args = [
            plink_path,
            "-ssh",
            f"{profile.user}@{profile.host}",
            "-P",
            str(profile.port),
            "-batch",
            "-no-antispoof",
            "-pw",
            password,
            command,
        ]

        def worker() -> None:
            try:
                result = subprocess.run(args, capture_output=True, text=True, timeout=35, shell=False)
                output = result.stdout or ""
                error = result.stderr or ""
                success = result.returncode == 0
                if not success:
                    APP_LOGGER.warning(f"run_remote_monitoring_command({profile.name}): exit code {result.returncode}: {error[:200]}")
                self.after(0, lambda: callback(success, output, error))
            except subprocess.TimeoutExpired as exc:
                APP_LOGGER.warning(f"run_remote_monitoring_command({profile.name}): timed out after 35s")
                out = exc.stdout or ""
                err = exc.stderr or "Monitoring command timed out."
                self.after(0, lambda: callback(False, out, err))
            except Exception as exc:
                APP_LOGGER.error(f"run_remote_monitoring_command({profile.name}): {exc}")
                self.after(0, lambda: callback(False, "", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def run_health_check_in_terminal(self) -> None:
        self.run_command_on_focused_console(resolve_health_command(self.get_monitoring_profile()))
        self.status_var.set("Sent advanced health-check command to focused terminal")

    def run_gateway_check(self) -> None:
        command = "find /var/log/nginx -type f -name '*.log' -mmin -1440 2>/dev/null | head -n 20 | xargs -r tail -n 1000 2>/dev/null | grep -iEn ' 502 | 504 |bad gateway|gateway timeout|upstream timed out|upstream prematurely|connect\\(\\) failed|no live upstreams|connection refused' | tail -n 80"
        self.run_command_on_focused_console(command)
        self.status_var.set("Sent 502/gateway risk check to focused terminal")

    def run_connections_check(self) -> None:
        command = "ss -Htan 2>/dev/null | awk '($1==\"ESTAB\" || $1==\"ESTABLISHED\") {print $4, $5}' | sort | uniq -c | sort -nr | head -n 80"
        self.run_command_on_focused_console(command)
        self.status_var.set("Sent connection load check to focused terminal")

    def run_active_users_check(self) -> None:
        command = "find /home/www-data/web2py -type f \\( -name '*.log' -o -name 'web2py.log' \\) -mmin -1440 2>/dev/null | head -n 60 | xargs -r tail -n 500 2>/dev/null | grep -Eo '([0-9]{1,3}\\.){3}[0-9]{1,3}' | sort | uniq -c | sort -nr | head -n 40"
        self.run_command_on_focused_console(command)
        self.status_var.set("Sent active users/client IP check to focused terminal")

    def run_recent_errors_check(self) -> None:
        command = "find /home/www-data/web2py -name '*.log' -type f -mmin -1440 2>/dev/null | head -n 30 | xargs -r grep -iEn 'error|traceback|exception|ticket|failed|critical|502|bad gateway' 2>/dev/null | tail -n 120"
        self.run_command_on_focused_console(command)
        self.status_var.set("Sent recent errors check to focused terminal")

    def run_web2py_process_check(self) -> None:
        command = "echo '--- web2py/uwsgi processes ---'; ps -eo pid,user,pcpu,pmem,etime,cmd --sort=-pcpu | grep -Ei 'web2py|uwsgi' | grep -v grep; echo; echo '--- nginx processes ---'; ps -eo pid,user,pcpu,pmem,etime,cmd --sort=-pcpu | grep -Ei 'nginx' | grep -v grep"
        self.run_command_on_focused_console(command)
        self.status_var.set("Sent Web2py/uWSGI/nginx process check to focused terminal")

    def open_documentation(self, initial_file: str = DOC_README_FILE) -> None:
        try:
            MarkdownDocumentWindow(self, initial_file=initial_file)
            self.status_var.set("Opened documentation viewer")
        except Exception as exc:
            show_message(self, "error", APP_NAME, f"Could not open documentation viewer.\n\n{exc}")

    def open_docs_folder(self) -> None:
        write_embedded_docs_to_config()
        try:
            os.startfile(CONFIG_DIR)  # type: ignore[attr-defined]
        except Exception as exc:
            show_message(self, "error", APP_NAME, f"Could not open documentation folder.\n\n{exc}")

    def find_plink(self) -> str | None:
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).resolve().parent
        else:
            base = Path(__file__).resolve().parent

        local = base / "plink.exe"

        if local.exists():
            return str(local)

        return shutil.which("plink.exe") or shutil.which("plink")

    def run_file_transfer(
        self, profile: SSHProfile, local_path: str, remote_path: str, upload: bool, callback,
    ) -> None:
        pscp_path = self.find_pscp()
        if not pscp_path:
            self.after(0, lambda: callback(False, "pscp.exe was not found. Place it beside this app."))
            return

        password = PasswordStore.get(profile.name)
        if password is None:
            password = ask_text(self, APP_NAME, f"Password for {profile.user}@{profile.host}", password=True)
            if password is None:
                self.after(0, lambda: callback(False, "Password was not provided."))
                return
            try:
                PasswordStore.save(profile.name, password)
            except Exception as exc:
                self.warn_keyring_failure_once(exc)

        remote_spec = f"{profile.user}@{profile.host}:{remote_path}"
        source, target = (local_path, remote_spec) if upload else (remote_spec, local_path)

        def worker() -> None:
            # pscp has no inline -pw flag (unlike plink) - only -pwfile, so the
            # password has to go through a short-lived temp file, deleted in
            # `finally` regardless of how the transfer ends.
            pwfile_fd, pwfile_path = tempfile.mkstemp(prefix="sshcl_pw_")
            try:
                with os.fdopen(pwfile_fd, "w", encoding="utf-8") as f:
                    f.write(password)
                args = [pscp_path, "-pwfile", pwfile_path, "-P", str(profile.port), "-batch", source, target]
                result = subprocess.run(args, capture_output=True, text=True, timeout=300, shell=False)
                success = result.returncode == 0
                message = "" if success else (result.stderr or result.stdout or "Transfer failed.")
                self.after(0, lambda: callback(success, message))
            except subprocess.TimeoutExpired:
                self.after(0, lambda: callback(False, "Transfer timed out."))
            except Exception as exc:
                self.after(0, lambda: callback(False, str(exc)))
            finally:
                try:
                    os.remove(pwfile_path)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def find_pscp(self) -> str | None:
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).resolve().parent
        else:
            base = Path(__file__).resolve().parent

        local = base / "pscp.exe"

        if local.exists():
            return str(local)

        return shutil.which("pscp.exe") or shutil.which("pscp")

    def check_requirements(self) -> None:
        customtkinter_status = "Found" if ctk is not None else "Missing"
        pywinpty_status = "Found" if PtyProcess is not None else "Missing"
        keyring_status = "Found" if keyring is not None else "Missing"
        pyte_status = "Found" if pyte is not None else "Missing"
        plink_status = "Found" if self.find_plink() else "Missing"

        show_message(
            self,
            "info",
            APP_NAME,
            "Requirements:\n\n"
            f"customtkinter: {customtkinter_status}\n"
            f"pywinpty: {pywinpty_status}\n"
            f"keyring: {keyring_status}\n"
            f"pyte: {pyte_status}\n"
            f"plink.exe: {plink_status}\n\n"
            "Install Python packages:\n"
            "pip install pywinpty keyring pyte customtkinter\n\n"
            "Put plink.exe beside the app for portable use.\n\n"
            "For bundled documentation in .exe builds, include:\n"
            "--add-data \"README_Embedded_SSH_Launcher.md;.\"\n"
            "--add-data \"VERSION_HISTORY_Embedded_SSH_Launcher.md;.\"",
        )

    def open_config_folder(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(CONFIG_DIR)  # type: ignore[attr-defined]

    def capture_session_state(self) -> list[dict]:
        tabs_data = []
        for tab_id in self.notebook.tabs():
            widget = self.nametowidget(tab_id)
            if not isinstance(widget, ConsoleTab):
                continue
            profile_names = [pane.profile.name for pane in widget.panes]
            if not profile_names:
                continue
            tabs_data.append({"layout_mode": widget.layout_mode, "profiles": profile_names})
        return tabs_data

    def maybe_restore_session(self) -> None:
        tabs_data = SessionStore.load()
        if not tabs_data:
            return

        if not show_message(
            self, "confirm", APP_NAME, f"Reopen {len(tabs_data)} tab(s) from your last session?",
        ):
            SessionStore.clear()
            return

        by_name = {p.name: p for p in self.profiles}
        for tab_entry in tabs_data:
            names = tab_entry.get("profiles", [])
            profiles = [by_name[n] for n in names if n in by_name]
            if not profiles:
                continue  # every profile in this tab was renamed/deleted since - skip it

            tab = self.create_console_tab(profiles[0].name)
            for profile in profiles:
                tab.add_console(profile)

            layout_mode = tab_entry.get("layout_mode")
            if layout_mode:
                tab.set_layout_mode(layout_mode)

    def report_callback_exception(self, exc, val, tb) -> None:
        """Tkinter calls this for any exception raised inside a bound callback or
        after() job instead of letting it propagate - the default implementation
        just prints to stderr, which is invisible in the --windowed build.
        """
        APP_LOGGER.error("Unhandled UI exception:\n" + "".join(traceback.format_exception(exc, val, tb)))

    def on_close(self) -> None:
        SessionStore.save(self.capture_session_state())

        for tab_id in self.notebook.tabs():
            widget = self.nametowidget(tab_id)

            if isinstance(widget, ConsoleTab):
                widget.close_all()

        self.destroy()


if __name__ == "__main__":
    if ctk is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            APP_NAME,
            "customtkinter is not installed.\n\nRun:\npip install customtkinter",
        )
        root.destroy()
        sys.exit(1)

    app = EmbeddedSSHLauncher()
    app.mainloop()