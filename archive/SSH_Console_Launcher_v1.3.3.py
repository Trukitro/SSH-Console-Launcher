"""
Embedded SSH Console Launcher for Windows - Version 1.3.3 UI Refresh

Features:
- Modern CustomTkinter dark UI.
- Save SSH profiles.
- Store passwords with keyring / Windows Credential Manager.
- Auto-login with plink.exe.
- Open SSH consoles inside this GUI.
- Tabs and split panes.
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

Requirements:
    pip install pywinpty keyring pyte customtkinter

Runtime requirement:
- Put plink.exe beside this script/exe, or install PuTTY and add it to PATH.

Build portable EXE:
    pip install pyinstaller pywinpty keyring pyte customtkinter
    pyinstaller --onefile --windowed --add-binary "plink.exe;." SSH_Console_Launcher_v1_3.py
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import sys
import threading
import time
import tkinter as tk
from dataclasses import asdict, dataclass
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

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


APP_NAME = "Embedded SSH Launcher v1.3.3"
SERVICE_NAME = "EmbeddedSSHLauncher"
CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "EmbeddedSSHLauncher"
CONFIG_FILE = CONFIG_DIR / "profiles.json"
COMMANDS_FILE = CONFIG_DIR / "commands.json"

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
DANGER = "#dc2626"
WARNING = "#d97706"
TEXT = "#e5e7eb"
MUTED = "#9ca3af"
TERMINAL_BG = "#050505"
TERMINAL_FG = "#f8fafc"

ANSI_COLOR_MAP = {
    "default": TERMINAL_FG,
    "black": "#0f172a",
    "red": "#ef4444",
    "green": "#22c55e",
    "yellow": "#eab308",
    "brown": "#eab308",
    "blue": "#3b82f6",
    "magenta": "#d946ef",
    "cyan": "#06b6d4",
    "white": "#e5e7eb",
    "brightblack": "#64748b",
    "brightred": "#f87171",
    "brightgreen": "#4ade80",
    "brightyellow": "#fde047",
    "brightblue": "#60a5fa",
    "brightmagenta": "#e879f9",
    "brightcyan": "#22d3ee",
    "brightwhite": "#ffffff",
    "lightblack": "#64748b",
    "lightred": "#f87171",
    "lightgreen": "#4ade80",
    "lightyellow": "#fde047",
    "lightblue": "#60a5fa",
    "lightmagenta": "#e879f9",
    "lightcyan": "#22d3ee",
    "lightwhite": "#ffffff",
}

ANSI_BACKGROUND_MAP = {
    **ANSI_COLOR_MAP,
    "default": TERMINAL_BG,
}


@dataclass
class SSHProfile:
    name: str
    host: str
    user: str
    port: int = 22


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


def ask_text(
    parent: tk.Widget,
    title: str,
    label: str,
    initial_value: str = "",
    password: bool = False,
) -> str | None:
    dialog = ctk.CTkToplevel(parent) if ctk is not None else tk.Toplevel(parent)
    dialog.title(title)
    dialog.geometry("460x180")
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


class EmbeddedTerminal(ctk.CTkFrame if ctk is not None else ttk.Frame):
    def __init__(
        self,
        master: tk.Widget,
        profile: SSHProfile,
        plink_path: str,
        password: str | None,
    ):
        if ctk is not None:
            super().__init__(master, fg_color=TERMINAL_BG, corner_radius=12)
        else:
            super().__init__(master)

        self.profile = profile
        self.plink_path = plink_path
        self.password = password or ""

        self.proc = None
        self.reader_thread: threading.Thread | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()

        self.alive = False
        self.sent_password = False
        self.active = False
        self.close_callback = None

        self.flush_after_id: str | None = None

        self.term_columns = 140
        self.term_rows = 42

        self.screen = None
        self.stream = None

        self.header = None
        self.title_label = None
        self.style_tag_cache: dict[tuple[str, str, bool, bool], str] = {}

        self._build_ui()
        self.reset_terminal_screen()
        self.start_process()
        self.schedule_flush()

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

            ctk.CTkButton(
                self.header,
                text="Close",
                command=self.request_close,
                width=70,
                height=28,
                fg_color=DANGER,
                hover_color="#991b1b",
            ).pack(side="right", padx=(4, 8), pady=6)

            ctk.CTkButton(
                self.header,
                text="Reconnect",
                command=self.reconnect,
                width=92,
                height=28,
                fg_color=WARNING,
                hover_color="#92400e",
            ).pack(side="right", padx=4, pady=6)

            ctk.CTkButton(
                self.header,
                text="Clear",
                command=self.clear_remote_console,
                width=70,
                height=28,
                fg_color=CARD,
                hover_color=CARD_HOVER,
            ).pack(side="right", padx=4, pady=6)

            ctk.CTkButton(
                self.header,
                text="Focus",
                command=self.focus_terminal,
                width=70,
                height=28,
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
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
        self.active = True
        self.text.configure(state="normal")
        self.text.focus_set()
        self.text.mark_set("insert", "end")
        self.text.configure(state="disabled")
        self.event_generate("<<TerminalFocused>>")

    def start_process(self) -> None:
        if PtyProcess is None:
            self.write_local("ERROR: pywinpty is not installed. Run: pip install pywinpty\n")
            return

        if pyte is None:
            self.write_local("ERROR: pyte is not installed. Run: pip install pyte\n")
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

        if self.password:
            command.extend(["-pw", self.password])

        try:
            self.proc = PtyProcess.spawn(
                command,
                dimensions=(self.term_columns, self.term_rows),
            )
        except Exception as exc:
            self.write_local("ERROR starting terminal:\n" + str(exc) + "\n")
            return

        self.alive = True
        self.sent_password = False
        self.reader_thread = threading.Thread(target=self.read_loop, daemon=True)
        self.reader_thread.start()

        self.after(1200, self.initialize_remote_terminal)

    def initialize_remote_terminal(self) -> None:
        if not self.alive:
            return

        self.send("export TERM=xterm\r")
        self.send(f"stty rows {self.term_rows} columns {self.term_columns}\r")
        self.send("stty erase ^?\r")
        self.send("clear\r")

    def read_loop(self) -> None:
        while self.alive and self.proc is not None:
            try:
                data = self.proc.read(4096)

                if not data:
                    time.sleep(0.02)
                    continue

                self.output_queue.put(data)
            except Exception:
                if self.alive:
                    self.output_queue.put("\n[session closed]\n")
                self.alive = False
                break

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
                data = self.output_queue.get_nowait()
            except queue.Empty:
                break

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
            return

        try:
            self.proc.write(data)
        except Exception:
            self.alive = False
            self.write_local("\n[write failed; session closed]\n")

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
        self.focus_terminal()

    def close_process_only(self) -> None:
        self.alive = False

        if self.flush_after_id is not None:
            try:
                self.after_cancel(self.flush_after_id)
            except Exception:
                pass
            self.flush_after_id = None

        try:
            if self.proc is not None:
                self.proc.close(force=True)
        except Exception:
            pass

        self.proc = None

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

        if event.char and ord(event.char) >= 32:
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
        self.panes: list[EmbeddedTerminal] = []
        self.active_terminal: EmbeddedTerminal | None = None

        self.panewindow = ttk.PanedWindow(self, orient=self.orientation)
        self.panewindow.pack(fill="both", expand=True, padx=4, pady=4)

    def add_console(self, profile: SSHProfile) -> None:
        if len(self.panes) >= MAX_PANES_PER_TAB:
            messagebox.showwarning(APP_NAME, f"Maximum {MAX_PANES_PER_TAB} consoles per tab.")
            return

        plink_path = self.app.find_plink()

        if not plink_path:
            messagebox.showerror(
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
                return

            try:
                PasswordStore.save(profile.name, password)
            except Exception:
                pass

        terminal = EmbeddedTerminal(self.panewindow, profile, plink_path, password)
        terminal.close_callback = self.close_console
        terminal.bind("<<TerminalFocused>>", lambda _event, t=terminal: self.set_active_terminal(t))

        self.panes.append(terminal)
        self.panewindow.add(terminal, weight=1)

        self.set_active_terminal(terminal)
        terminal.focus_terminal()

    def set_active_terminal(self, terminal: EmbeddedTerminal) -> None:
        if self.active_terminal is not None and self.active_terminal is not terminal:
            self.active_terminal.set_active_visual(False)

        self.active_terminal = terminal
        self.app.active_tab = self
        self.app.focused_terminal = terminal
        terminal.set_active_visual(True)

    def set_orientation(self, orientation: str) -> None:
        if orientation == self.orientation:
            return

        self.orientation = orientation
        existing = list(self.panes)

        for pane in existing:
            try:
                self.panewindow.forget(pane)
            except Exception:
                pass

        self.panewindow.destroy()

        self.panewindow = ttk.PanedWindow(self, orient=self.orientation)
        self.panewindow.pack(fill="both", expand=True, padx=4, pady=4)

        for pane in existing:
            self.panewindow.add(pane, weight=1)

    def close_console(self, terminal: EmbeddedTerminal) -> None:
        try:
            terminal.close()
        except Exception:
            pass

        try:
            self.panewindow.forget(terminal)
        except Exception:
            pass

        try:
            terminal.destroy()
        except Exception:
            pass

        self.panes = [pane for pane in self.panes if pane is not terminal]

        if self.active_terminal is terminal:
            self.active_terminal = self.panes[-1] if self.panes else None

        if self.active_terminal is not None:
            self.active_terminal.set_active_visual(True)

        if self.app.focused_terminal is terminal:
            self.app.focused_terminal = self.active_terminal

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

        self._setup_styles()
        self._build_ui()
        self.refresh_profiles()
        self.refresh_commands()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

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
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.topbar = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0) if ctk is not None else ttk.Frame(self)
        self.topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.topbar.grid_columnconfigure(1, weight=1)

        self.sidebar = ctk.CTkScrollableFrame(
            self,
            fg_color=PANEL,
            corner_radius=0,
            width=320,
        ) if ctk is not None else ttk.Frame(self)

        self.sidebar.grid(row=1, column=0, sticky="nsw")

        if ctk is not None:
            self.sidebar.configure(width=320)
        else:
            self.sidebar.grid_propagate(False)

        self.main = ctk.CTkFrame(
            self,
            fg_color=BG,
            corner_radius=0,
        ) if ctk is not None else ttk.Frame(self)
        self.main.grid(row=1, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)

        self.statusbar = ctk.CTkFrame(
            self,
            fg_color=PANEL,
            corner_radius=0,
            height=32,
        ) if ctk is not None else ttk.Frame(self)
        self.statusbar.grid(row=2, column=0, columnspan=2, sticky="ew")

        self._build_topbar()
        self._build_sidebar()
        self._build_main()
        self._build_statusbar()

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
                text="Modern SSH workspace with tabs, split panes, and quick commands",
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
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=92,
            height=34,
            fg_color=color,
            hover_color=CARD_HOVER if color == CARD else color,
            corner_radius=10,
        )

    def _build_sidebar(self) -> None:
        self._sidebar_title("Profiles")

        self.profile_buttons_frame = ctk.CTkFrame(
            self.sidebar,
            fg_color="transparent",
        ) if ctk is not None else ttk.Frame(self.sidebar)
        self.profile_buttons_frame.pack(fill="x", padx=12, pady=(6, 12))

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
            row = ctk.CTkFrame(self.profile_form, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=(8, 12))

            ctk.CTkButton(
                row,
                text="Save",
                command=self.save_profile,
                fg_color=SUCCESS,
                hover_color="#15803d",
                height=34,
                corner_radius=10,
            ).pack(side="left", fill="x", expand=True, padx=(0, 4))

            ctk.CTkButton(
                row,
                text="New",
                command=self.clear_form,
                fg_color=CARD_HOVER,
                hover_color="#475569",
                height=34,
                corner_radius=10,
            ).pack(side="left", fill="x", expand=True, padx=4)

            ctk.CTkButton(
                row,
                text="Delete",
                command=self.delete_profile,
                fg_color=DANGER,
                hover_color="#991b1b",
                height=34,
                corner_radius=10,
            ).pack(side="left", fill="x", expand=True, padx=(4, 0))
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

        self._sidebar_title("Layout / Session")

        self.session_panel = ctk.CTkFrame(
            self.sidebar,
            fg_color=CARD,
            corner_radius=14,
        ) if ctk is not None else ttk.LabelFrame(self.sidebar, text="Layout / Session")
        self.session_panel.pack(fill="x", padx=12, pady=(0, 14))

        self._side_button(self.session_panel, "Vertical Split", lambda: self.set_active_orientation(tk.HORIZONTAL), CARD_HOVER)
        self._side_button(self.session_panel, "Horizontal Split", lambda: self.set_active_orientation(tk.VERTICAL), CARD_HOVER)
        self._side_button(self.session_panel, "Rename Current Tab", self.rename_current_tab, CARD_HOVER)
        self._side_button(self.session_panel, "Reconnect Selected Console", self.reconnect_active_console, WARNING)
        self._side_button(self.session_panel, "Clear Console", self.clear_focused_console, CARD_HOVER)
        self._side_button(self.session_panel, "Close Selected Console", self.close_active_console, DANGER)
        self._side_button(self.session_panel, "Close Current Tab", self.close_current_tab, DANGER)

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

        self._sidebar_title("Tools")

        self.tools_panel = ctk.CTkFrame(
            self.sidebar,
            fg_color=CARD,
            corner_radius=14,
        ) if ctk is not None else ttk.LabelFrame(self.sidebar, text="Tools")
        self.tools_panel.pack(fill="x", padx=12, pady=(0, 20))

        self._side_button(self.tools_panel, "Check Requirements", self.check_requirements, CARD_HOVER)
        self._side_button(self.tools_panel, "Open Config Folder", self.open_config_folder, CARD_HOVER)

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
            ctk.CTkButton(
                parent,
                text=text,
                command=command,
                fg_color=color,
                hover_color=CARD_HOVER if color in {CARD, CARD_HOVER} else color,
                height=34,
                corner_radius=10,
                anchor="w",
            ).pack(fill="x", padx=10, pady=4)
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

        for idx, button in enumerate(self.profile_buttons):
            if ctk is not None:
                button.configure(fg_color=ACCENT if idx == index else CARD)

        self.status_var.set(f"Selected profile: {profile.name}")

    def open_profile_by_index(self, index: int) -> None:
        self.select_profile(index)
        self.open_new_tab()

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
            messagebox.showerror(APP_NAME, "Select a saved profile first.")
            return None

        if self.selected_profile_index < 0 or self.selected_profile_index >= len(self.profiles):
            messagebox.showerror(APP_NAME, "Selected profile is invalid.")
            return None

        return self.profiles[self.selected_profile_index]

    def selected_command(self) -> QuickCommand | None:
        if self.selected_command_index is None:
            messagebox.showerror(APP_NAME, "Right-click or select a command first.")
            return None

        if self.selected_command_index < 0 or self.selected_command_index >= len(self.commands):
            return None

        return self.commands[self.selected_command_index]

    def save_profile(self) -> None:
        name = self.name_var.get().strip()
        host = self.host_var.get().strip()
        user = self.user_var.get().strip()
        password = self.password_var.get()

        if not name or not host or not user:
            messagebox.showerror(APP_NAME, "Name, Host/IP, and User are required.")
            return

        try:
            port = int(self.port_var.get().strip())

            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror(APP_NAME, "Port must be a number from 1 to 65535.")
            return

        old_name = None
        profile = SSHProfile(name=name, host=host, user=user, port=port)

        if self.selected_profile_index is None:
            self.profiles.append(profile)
            self.selected_profile_index = len(self.profiles) - 1
        else:
            old_name = self.profiles[self.selected_profile_index].name
            self.profiles[self.selected_profile_index] = profile

        if old_name and old_name != name:
            PasswordStore.delete(old_name)

        if password:
            try:
                PasswordStore.save(name, password)
            except Exception as exc:
                messagebox.showwarning(
                    APP_NAME,
                    f"Profile saved, but password was not saved securely.\n\n{exc}",
                )

        ProfileStore.save(self.profiles)
        self.refresh_profiles()
        self.select_profile(self.selected_profile_index)
        self.status_var.set(f"Saved profile: {name}")

    def clear_form(self) -> None:
        self.selected_profile_index = None

        self.name_var.set("")
        self.host_var.set("")
        self.user_var.set("")
        self.port_var.set("22")
        self.password_var.set("")

        for button in self.profile_buttons:
            if ctk is not None:
                button.configure(fg_color=CARD)

        self.status_var.set("Ready for new profile")

    def delete_profile(self) -> None:
        if self.selected_profile_index is None:
            messagebox.showerror(APP_NAME, "Select a profile first.")
            return

        profile = self.profiles[self.selected_profile_index]

        if not messagebox.askyesno(APP_NAME, f"Delete profile '{profile.name}'?"):
            return

        PasswordStore.delete(profile.name)
        del self.profiles[self.selected_profile_index]

        self.selected_profile_index = None

        ProfileStore.save(self.profiles)
        self.refresh_profiles()
        self.clear_form()
        self.status_var.set(f"Deleted profile: {profile.name}")

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

        if not messagebox.askyesno(APP_NAME, f"Delete command '{selected.name}'?"):
            return

        del self.commands[self.selected_command_index]
        self.selected_command_index = None
        CommandStore.save(self.commands)
        self.refresh_commands()
        self.status_var.set(f"Deleted command: {selected.name}")

    def run_command_by_index(self, index: int) -> None:
        if index < 0 or index >= len(self.commands):
            return

        self.select_command(index)
        command = self.commands[index]
        self.run_command_on_focused_console(command.command)
        self.status_var.set(f"Ran command: {command.name}")

    def run_command_on_focused_console(self, command: str) -> None:
        terminal = self.focused_terminal

        if terminal is not None and terminal.alive:
            terminal.run_command(command)
            return

        tab = self.current_tab()

        if tab is not None:
            tab.run_command_on_active(command)
            return

        messagebox.showerror(APP_NAME, "No active console found.")

    def clear_focused_console(self) -> None:
        self.run_command_on_focused_console("clear")
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

        self.status_var.set(f"Opened {count} split consoles for {profile.name}")

    def set_active_orientation(self, orientation: str) -> None:
        tab = self.current_tab()

        if tab is None:
            return

        tab.set_orientation(orientation)

        label = "vertical" if orientation == tk.HORIZONTAL else "horizontal"
        self.status_var.set(f"Changed split layout to {label}")

    def rename_current_tab(self) -> None:
        selected = self.notebook.select()

        if not selected:
            messagebox.showerror(APP_NAME, "No tab selected.")
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
        tab = self.current_tab()

        if tab is None:
            return

        tab.reconnect_active_console()
        self.status_var.set("Reconnected selected console")

    def close_active_console(self) -> None:
        tab = self.current_tab()

        if tab is None:
            return

        tab.close_active_console()
        self.status_var.set("Closed selected console")

    def close_current_tab(self) -> None:
        selected = self.notebook.select()

        if not selected:
            return

        self.close_tab_by_id(selected)

    def close_tab_by_id(self, tab_id: str) -> None:
        """
        Fully close a notebook tab.

        notebook.forget() only removes the tab from the notebook.
        It does not always destroy the child widget. We close SSH sessions,
        forget the tab, destroy the frame, and reset references.
        """

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
                self.notebook.select(remaining_tabs[0])
                new_widget = self.nametowidget(remaining_tabs[0])

                if isinstance(new_widget, ConsoleTab):
                    self.active_tab = new_widget

                    if new_widget.active_terminal is not None:
                        self.focused_terminal = new_widget.active_terminal
                    elif new_widget.panes:
                        self.focused_terminal = new_widget.panes[-1]
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
        self.current_tab()

    def on_notebook_double_click(self, event: tk.Event) -> None:
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

    def find_plink(self) -> str | None:
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).resolve().parent
        else:
            base = Path(__file__).resolve().parent

        local = base / "plink.exe"

        if local.exists():
            return str(local)

        return shutil.which("plink.exe") or shutil.which("plink")

    def check_requirements(self) -> None:
        customtkinter_status = "Found" if ctk is not None else "Missing"
        pywinpty_status = "Found" if PtyProcess is not None else "Missing"
        keyring_status = "Found" if keyring is not None else "Missing"
        pyte_status = "Found" if pyte is not None else "Missing"
        plink_status = "Found" if self.find_plink() else "Missing"

        messagebox.showinfo(
            APP_NAME,
            "Requirements:\n\n"
            f"customtkinter: {customtkinter_status}\n"
            f"pywinpty: {pywinpty_status}\n"
            f"keyring: {keyring_status}\n"
            f"pyte: {pyte_status}\n"
            f"plink.exe: {plink_status}\n\n"
            "Install Python packages:\n"
            "pip install pywinpty keyring pyte customtkinter\n\n"
            "Put plink.exe beside the app for portable use.",
        )

    def open_config_folder(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(CONFIG_DIR)  # type: ignore[attr-defined]

    def on_close(self) -> None:
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