"""Local profile storage + credential handling.

Profiles (host/user/port/auth method) live in a plain JSON file. Secrets
(passwords, key passphrases) never touch that file - they go through
`keyring` (Windows Credential Manager), keyed by the profile's stable id
rather than its name, so renaming a profile can't orphan its saved secret
the way the original app's name-keyed lookup could.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypeVar

import keyring

LOGGER = logging.getLogger("ssh_launcher_v2")

CONFIG_DIR = Path.home() / "AppData" / "Roaming" / "SSHConsoleLauncherV2"
PROFILES_FILE = CONFIG_DIR / "profiles.json"
COMMANDS_FILE = CONFIG_DIR / "commands.json"
SESSION_FILE = CONFIG_DIR / "session.json"
KEYS_DIR = CONFIG_DIR / "keys"
KNOWN_HOSTS_FILE = CONFIG_DIR / "known_hosts"
AUDIT_LOG_FILE = CONFIG_DIR / "audit_log.jsonl"

SERVICE_NAME = "SSHConsoleLauncherV2"

_T = TypeVar("_T")


def _from_dict(cls: type[_T], item: dict) -> _T:
    """Build a dataclass from a saved JSON dict, tolerant of schema drift:
    unknown keys (from an older/newer version) are dropped, missing keys
    fall back to the dataclass's own defaults. Config files are meant to
    outlive app updates and reinstalls - a field added or removed in a
    later version should never corrupt or wipe a user's existing profiles
    or commands."""
    known = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in item.items() if k in known})


# Default quick commands for daily SSH/web2py work: directory navigation,
# the web2py app lifecycle, service/process management, databases, and
# server monitoring - the paths match the real server layout this app has
# always been used against (see v1's CommandStore.default_commands()).
# load_commands() merges any of these the user doesn't already have (by
# name) into their saved list, so upgrading never removes what they added
# or customized, but does grow the built-in set over time.
DEFAULT_COMMANDS = [
    # Navigation
    {"name": "pwd", "command": "pwd", "category": "Navigation", "description": "Show the current directory."},
    {"name": "ls -la", "command": "ls -la", "category": "Navigation", "description": "List all files in the current directory, including hidden ones, with permissions and size."},
    {"name": "cd ..", "command": "cd ..", "category": "Navigation", "description": "Go up one directory."},
    {"name": "cd ~", "command": "cd ~", "category": "Navigation", "description": "Go to the home directory."},
    # Web2py
    {"name": "web2py folder", "command": "cd /home/www-data/web2py/", "category": "Web2py", "description": "Go to the Web2py root folder."},
    {"name": "web2py apps", "command": "cd /home/www-data/web2py/applications", "category": "Web2py", "description": "Go to the folder holding every Web2py application."},
    {"name": "tail web2py.log", "command": "tail -f /home/www-data/web2py/web2py.log", "category": "Web2py", "description": "Follow the Web2py log live - the first place to look when something breaks.", "interactive": True},
    {"name": "uwsgitop", "command": "sudo uwsgitop /tmp/stats.socket", "category": "Web2py", "description": "Live view of uWSGI worker load (busy/idle workers, requests, memory).", "interactive": True},
    {"name": "restart uwsgi", "command": "sudo systemctl restart uwsgi", "category": "Web2py", "description": "Restart the uWSGI service running Web2py - picks up code/config changes."},
    # Applications / processes
    {"name": "ps aux | grep python", "command": "ps aux | grep python", "category": "Applications", "description": "List running Python processes - useful to confirm Web2py/uWSGI workers are alive."},
    {"name": "nginx status", "command": "sudo systemctl status nginx", "category": "Applications", "description": "Check whether Nginx is running and see its recent log lines."},
    {"name": "restart nginx", "command": "sudo systemctl restart nginx", "category": "Applications", "description": "Restart Nginx - picks up config changes, clears a stuck worker."},
    {"name": "recent service errors", "command": "sudo journalctl -xe", "category": "Applications", "description": "Show the most recent system/service error log entries.", "interactive": True},
    # Database
    {"name": "mysql shell", "command": "mysql -u root -p", "category": "Database", "description": "Open an interactive MySQL shell (prompts for the root password).", "interactive": True},
    {"name": "postgres shell", "command": "psql -U postgres", "category": "Database", "description": "Open an interactive PostgreSQL shell.", "interactive": True},
    {"name": "mysql status", "command": "sudo systemctl status mysql", "category": "Database", "description": "Check whether the MySQL service is running."},
    {"name": "postgres status", "command": "sudo systemctl status postgresql", "category": "Database", "description": "Check whether the PostgreSQL service is running."},
    # Monitoring
    {"name": "htop", "command": "htop", "category": "Monitoring", "description": "Interactive live view of CPU, memory, and running processes.", "interactive": True},
    {"name": "disk usage", "command": "df -h", "category": "Monitoring", "description": "Show disk space used/free per mounted volume, in human-readable sizes."},
    {"name": "memory usage", "command": "free -h", "category": "Monitoring", "description": "Show RAM and swap usage, in human-readable sizes."},
    {"name": "uptime", "command": "uptime", "category": "Monitoring", "description": "Show how long the server has been running and its load average."},
    {"name": "listening ports", "command": "sudo netstat -tulpn", "category": "Monitoring", "description": "List listening network ports and which process owns each one."},
    # General
    {"name": "clear", "command": "clear", "category": "General", "description": "Clear the terminal screen."},
    {"name": "whoami", "command": "whoami", "category": "General", "description": "Show the currently logged-in user."},
    {"name": "recent history", "command": "history | tail -30", "category": "General", "description": "Show your last 30 commands on this server."},
]


@dataclass
class Profile:
    id: str
    name: str
    host: str
    port: int = 22
    user: str = ""
    auth_method: str = "password"  # "password" | "key"
    key_path: str = ""  # set when auth_method == "key"
    env_color: str = ""  # "" | "prod" | "staging" | "dev"
    jump_profile_id: str = ""  # "" = direct connection

    @staticmethod
    def new(name: str, host: str, port: int, user: str) -> "Profile":
        return Profile(id=str(uuid.uuid4()), name=name, host=host, port=port, user=user)


def _ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    KEYS_DIR.mkdir(parents=True, exist_ok=True)


def load_profiles() -> list[Profile]:
    _ensure_dirs()
    if not PROFILES_FILE.exists():
        return []
    try:
        raw = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        return [_from_dict(Profile, item) for item in raw]
    except Exception as exc:
        LOGGER.error("load_profiles: %s", exc)
        return []


def save_profiles(profiles: list[Profile]) -> None:
    _ensure_dirs()
    PROFILES_FILE.write_text(
        json.dumps([asdict(p) for p in profiles], indent=2), encoding="utf-8",
    )


def upsert_profile(profile: Profile) -> None:
    profiles = load_profiles()
    for i, existing in enumerate(profiles):
        if existing.id == profile.id:
            profiles[i] = profile
            save_profiles(profiles)
            return
    profiles.append(profile)
    save_profiles(profiles)


def delete_profile(profile_id: str) -> None:
    profiles = [p for p in load_profiles() if p.id != profile_id]
    save_profiles(profiles)
    try:
        keyring.delete_password(SERVICE_NAME, profile_id)
    except Exception:
        pass


def get_password(profile_id: str) -> str | None:
    try:
        return keyring.get_password(SERVICE_NAME, profile_id)
    except Exception as exc:
        LOGGER.warning("get_password(%s): %s", profile_id, exc)
        return None


def save_password(profile_id: str, password: str) -> None:
    keyring.set_password(SERVICE_NAME, profile_id, password)


def key_path_for(profile_id: str) -> Path:
    return KEYS_DIR / f"{profile_id}_ed25519"


@dataclass
class Command:
    id: str
    name: str
    command: str
    category: str = "General"
    description: str = ""
    # True for full-screen/curses apps (htop, uwsgitop), pagers (journalctl -xe),
    # streaming output (tail -f) and interactive REPLs/sudo prompts (mysql/psql
    # shell) - anything that needs a correctly-sized PTY and doesn't just print
    # output and return. Purely informational today (shown as a badge in the
    # UI) - see the visibility plan in Main Vault for why this exists.
    interactive: bool = False

    @staticmethod
    def new(
        name: str, command: str, category: str = "General", description: str = "", interactive: bool = False,
    ) -> "Command":
        return Command(
            id=str(uuid.uuid4()), name=name, command=command, category=category,
            description=description, interactive=interactive,
        )


def load_commands() -> list[Command]:
    _ensure_dirs()
    if not COMMANDS_FILE.exists():
        commands = [Command.new(**c) for c in DEFAULT_COMMANDS]
        save_commands(commands)
        return commands

    try:
        raw = json.loads(COMMANDS_FILE.read_text(encoding="utf-8"))
        commands = [_from_dict(Command, item) for item in raw]
    except Exception as exc:
        LOGGER.error("load_commands: %s", exc)
        return []

    existing_names = {c.name for c in commands}
    added = False
    for default in DEFAULT_COMMANDS:
        if default["name"] not in existing_names:
            commands.append(Command.new(**default))
            added = True
    if added:
        save_commands(commands)

    return commands


def save_commands(commands: list[Command]) -> None:
    _ensure_dirs()
    COMMANDS_FILE.write_text(json.dumps([asdict(c) for c in commands], indent=2), encoding="utf-8")


def upsert_command(command: Command) -> None:
    commands = load_commands()
    for i, existing in enumerate(commands):
        if existing.id == command.id:
            commands[i] = command
            save_commands(commands)
            return
    commands.append(command)
    save_commands(commands)


def delete_command(command_id: str) -> None:
    save_commands([c for c in load_commands() if c.id != command_id])


def load_session_profile_ids() -> list[str]:
    if not SESSION_FILE.exists():
        return []
    try:
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        LOGGER.error("load_session_profile_ids: %s", exc)
        return []


def save_session_profile_ids(profile_ids: list[str]) -> None:
    _ensure_dirs()
    try:
        SESSION_FILE.write_text(json.dumps(profile_ids), encoding="utf-8")
    except Exception as exc:
        LOGGER.warning("save_session_profile_ids: %s", exc)


def record_audit(profile: Profile) -> None:
    import time

    _ensure_dirs()
    entry = {"ts": time.time(), "profile": profile.name, "host": profile.host, "user": profile.user}
    try:
        with AUDIT_LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except Exception as exc:
        LOGGER.warning("record_audit: %s", exc)
