"""Structured, day-partitioned event log for the in-app Event Log panel.

Separate from Python's own `logging` module (which still writes the raw
technical launcher_debug.log file for developer troubleshooting). This is
the user-facing history: one JSON object per line, one file per calendar
day, so "what happened today" and "what happened yesterday" are both cheap
to answer and nothing is lost when the app restarts. New event kinds are
just a new `log_event(kind=...)` call at the point they happen - nothing
here needs to change to support them.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import config_store

LOG_DIR = config_store.CONFIG_DIR / "events"
_lock = threading.Lock()


def _day_file(date_str: str) -> Path:
    return LOG_DIR / f"{date_str}.jsonl"


def log_event(kind: str, message: str, detail: dict | None = None, level: str = "info") -> dict:
    now = time.localtime()
    date_str = time.strftime("%Y-%m-%d", now)
    event = {
        "date": date_str,
        "time": time.strftime("%H:%M:%S", now),
        "kind": kind,
        "level": level,
        "message": message,
        "detail": detail or {},
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        with _day_file(date_str).open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def list_events(date_str: str | None = None) -> list[dict]:
    date_str = date_str or time.strftime("%Y-%m-%d")
    path = _day_file(date_str)
    if not path.exists():
        return []
    events: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def list_event_dates() -> list[str]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    dates = {p.stem for p in LOG_DIR.glob("*.jsonl")}
    dates.add(today)
    return sorted(dates, reverse=True)
