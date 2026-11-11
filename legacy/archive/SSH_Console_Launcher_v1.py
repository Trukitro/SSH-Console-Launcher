"""
Embedded SSH Console Launcher for Windows

Features:
- Save SSH profiles.
- Store passwords with keyring / Windows Credential Manager.
- Auto-login with plink.exe.
- Open SSH consoles inside this GUI.
- Tabs and split panes.
- Vertical/horizontal split layout.
- Close each console with a mouse click.
- Better terminal rendering using pyte.
- Extra cleanup for htop/top/nano/vim style terminal output.

Requirements:
    pip install pywinpty keyring pyte

Runtime requirement:
- Put plink.exe beside this script/exe, or install PuTTY and add it to PATH.

Build portable EXE:
    pip install pyinstaller pywinpty keyring pyte
    pyinstaller --onefile --windowed --add-binary "plink.exe;." SSH_Console_Launcher_v2.py
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


APP_NAME = "Embedded SSH Launcher"
SERVICE_NAME = "EmbeddedSSHLauncher"
CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "EmbeddedSSHLauncher"
CONFIG_FILE = CONFIG_DIR / "profiles.json"
MAX_PANES_PER_TAB = 4


@dataclass
class SSHProfile:
    name: str
    host: str
    user: str
    port: int = 22


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


class EmbeddedTerminal(ttk.Frame):
    def __init__(
        self,
        master: tk.Widget,
        profile: SSHProfile,
        plink_path: str,
        password: str | None,
    ):
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

        self.term_columns = 140
        self.term_rows = 42

        self.screen = None
        self.stream = None

        if pyte is not None:
            self.screen = pyte.Screen(self.term_columns, self.term_rows)
            self.stream = pyte.ByteStream(self.screen)

        self._build_ui()
        self.start_process()
        self.after(35, self.flush_output)

    def _build_ui(self) -> None:
        self.configure(style="Terminal.TFrame")

        header = ttk.Frame(self)
        header.pack(fill="x")

        self.title_label = ttk.Label(
            header,
            text=f"{self.profile.name}  {self.profile.user}@{self.profile.host}:{self.profile.port}",
            font=("Segoe UI", 9, "bold"),
        )
        self.title_label.pack(side="left", padx=4)

        ttk.Button(
            header,
            text="Close",
            command=self.request_close,
            width=7,
        ).pack(side="right", padx=2)

        ttk.Button(
            header,
            text="Focus",
            command=self.focus_terminal,
            width=7,
        ).pack(side="right", padx=2)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        self.text = tk.Text(
            body,
            wrap="none",
            undo=False,
            bg="#0c0c0c",
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            selectbackground="#444444",
            font=("Consolas", 9),
            state="disabled",
            padx=4,
            pady=4,
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
        self.reader_thread = threading.Thread(target=self.read_loop, daemon=True)
        self.reader_thread.start()

        # Tell the remote shell what kind of terminal and size we are emulating.
        # This improves htop/top/nano/vim behavior.
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
                self.output_queue.put("\n[session closed]\n")
                self.alive = False
                break

    def flush_output(self) -> None:
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
            self.after(35, self.flush_output)

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
        """
        htop/top/nano/vim use ANSI and alternate character set sequences.
        pyte handles many ANSI sequences but not all charset-selection pieces.
        These replacements prevent raw '(B', ')0', etc. from appearing.
        """

        # Remove terminal title updates.
        data = re.sub(r"\x1b\][^\x07]*(\x07|\x1b\\)", "", data)

        # Remove charset selection sequences that often leak as garbage in Tk/pyte.
        data = data.replace("\x1b(B", "")
        data = data.replace("\x1b)B", "")
        data = data.replace("\x1b(0", "")
        data = data.replace("\x1b)0", "")

        # Remove single-shift and locking-shift controls.
        data = data.replace("\x0e", "")
        data = data.replace("\x0f", "")

        # Remove bracketed paste enable/disable. It is harmless but can leak.
        data = data.replace("\x1b[?2004h", "")
        data = data.replace("\x1b[?2004l", "")

        # Remove cursor style changes.
        data = re.sub(r"\x1b\[[0-9 ]+q", "", data)

        return data

    def render_screen(self) -> None:
        if self.screen is None:
            return

        lines = list(self.screen.display)

        cursor_y = max(0, min(self.screen.cursor.y, len(lines) - 1))
        cursor_x = max(0, min(self.screen.cursor.x, self.term_columns - 1))

        if lines:
            line = lines[cursor_y]

            if cursor_x >= len(line):
                line = line + (" " * (cursor_x - len(line) + 1))

            lines[cursor_y] = line[:cursor_x] + "█" + line[cursor_x + 1:]

        rendered = "\n".join(line.rstrip() for line in lines).rstrip() + "\n"

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", rendered)
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
        self.alive = False

        try:
            if self.proc is not None:
                self.proc.close(force=True)
        except Exception:
            pass


class ConsoleTab(ttk.Frame):
    def __init__(self, master: tk.Widget, app: "EmbeddedSSHLauncher"):
        super().__init__(master)

        self.app = app
        self.orientation = tk.HORIZONTAL
        self.panes: list[EmbeddedTerminal] = []
        self.active_terminal: EmbeddedTerminal | None = None

        self.panewindow = ttk.PanedWindow(self, orient=self.orientation)
        self.panewindow.pack(fill="both", expand=True)

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
            password = simpledialog.askstring(
                APP_NAME,
                f"Password for {profile.user}@{profile.host}",
                show="*",
                parent=self,
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
        self.active_terminal = terminal
        self.app.active_tab = self

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
        self.panewindow.pack(fill="both", expand=True)

        for pane in existing:
            self.panewindow.add(pane, weight=1)

    def close_console(self, terminal: EmbeddedTerminal) -> None:
        terminal.close()

        try:
            self.panewindow.forget(terminal)
        except Exception:
            pass

        terminal.destroy()

        self.panes = [pane for pane in self.panes if pane is not terminal]
        self.active_terminal = self.panes[-1] if self.panes else None

    def close_active_console(self) -> None:
        terminal = self.active_terminal

        if terminal is None and self.panes:
            terminal = self.panes[-1]

        if terminal is None:
            return

        self.close_console(terminal)

    def close_all(self) -> None:
        for pane in list(self.panes):
            pane.close()

        self.panes.clear()


class EmbeddedSSHLauncher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title(APP_NAME)
        self.geometry("1150x720")
        self.minsize(900, 560)

        self.profiles: list[SSHProfile] = ProfileStore.load()
        self.selected_profile_index: int | None = None
        self.tab_counter = 0
        self.active_tab: ConsoleTab | None = None

        self._setup_styles()
        self._build_ui()
        self.refresh_profiles()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _setup_styles(self) -> None:
        style = ttk.Style(self)

        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Terminal.TFrame", background="#1e1e1e")

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(self, padding=10)
        sidebar.grid(row=0, column=0, sticky="ns")

        main = ttk.Frame(self, padding=(0, 10, 10, 10))
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        ttk.Label(
            sidebar,
            text="Profiles",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")

        self.profile_list = tk.Listbox(sidebar, height=10, width=30)
        self.profile_list.pack(fill="x", pady=(6, 10))
        self.profile_list.bind("<<ListboxSelect>>", self.on_select_profile)
        self.profile_list.bind("<Double-Button-1>", lambda _event: self.open_new_tab())

        form = ttk.LabelFrame(sidebar, text="Save Profile", padding=8)
        form.pack(fill="x", pady=(0, 10))

        self.name_var = tk.StringVar()
        self.host_var = tk.StringVar()
        self.user_var = tk.StringVar()
        self.port_var = tk.StringVar(value="22")
        self.password_var = tk.StringVar()

        self._form_row(form, "Name", self.name_var)
        self._form_row(form, "Host/IP", self.host_var)
        self._form_row(form, "User", self.user_var)
        self._form_row(form, "Port", self.port_var)
        self._form_row(form, "Password", self.password_var, show="*")

        ttk.Button(
            form,
            text="Save / Update",
            command=self.save_profile,
        ).pack(fill="x", pady=(8, 2))

        ttk.Button(
            form,
            text="New",
            command=self.clear_form,
        ).pack(fill="x", pady=2)

        ttk.Button(
            form,
            text="Delete",
            command=self.delete_profile,
        ).pack(fill="x", pady=2)

        actions = ttk.LabelFrame(sidebar, text="Open Console", padding=8)
        actions.pack(fill="x", pady=(0, 10))

        ttk.Button(actions, text="New Tab", command=self.open_new_tab).pack(fill="x", pady=2)
        ttk.Button(actions, text="Split Current Tab", command=self.split_current_tab).pack(fill="x", pady=2)
        ttk.Button(actions, text="Open 2 Split", command=lambda: self.open_n_split(2)).pack(fill="x", pady=2)
        ttk.Button(actions, text="Open 3 Split", command=lambda: self.open_n_split(3)).pack(fill="x", pady=2)
        ttk.Button(actions, text="Open 4 Split", command=lambda: self.open_n_split(4)).pack(fill="x", pady=2)

        layout = ttk.LabelFrame(sidebar, text="Layout", padding=8)
        layout.pack(fill="x", pady=(0, 10))

        ttk.Button(
            layout,
            text="Vertical Split",
            command=lambda: self.set_active_orientation(tk.HORIZONTAL),
        ).pack(fill="x", pady=2)

        ttk.Button(
            layout,
            text="Horizontal Split",
            command=lambda: self.set_active_orientation(tk.VERTICAL),
        ).pack(fill="x", pady=2)

        ttk.Button(
            layout,
            text="Close Selected Console",
            command=self.close_active_console,
        ).pack(fill="x", pady=(8, 2))

        ttk.Button(
            layout,
            text="Close Current Tab",
            command=self.close_current_tab,
        ).pack(fill="x", pady=2)

        tools = ttk.LabelFrame(sidebar, text="Tools", padding=8)
        tools.pack(fill="x")

        ttk.Button(
            tools,
            text="Check Requirements",
            command=self.check_requirements,
        ).pack(fill="x", pady=2)

        ttk.Button(
            tools,
            text="Open Config Folder",
            command=self.open_config_folder,
        ).pack(fill="x", pady=2)

        topbar = ttk.Frame(main)
        topbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        ttk.Label(
            topbar,
            text="Double-click a profile to open a new SSH tab. Use Split Current Tab to add another console inside the selected tab.",
        ).pack(side="left")

        self.notebook = ttk.Notebook(main)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        self.status_var = tk.StringVar(value="Ready")

        ttk.Label(
            main,
            textvariable=self.status_var,
            anchor="w",
        ).grid(row=2, column=0, sticky="ew", pady=(6, 0))

    def _form_row(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        show: str | None = None,
    ) -> None:
        ttk.Label(parent, text=label).pack(anchor="w")
        ttk.Entry(parent, textvariable=variable, show=show).pack(fill="x", pady=(0, 5))

    def refresh_profiles(self) -> None:
        self.profile_list.delete(0, "end")

        for profile in self.profiles:
            self.profile_list.insert(
                "end",
                f"{profile.name}  ({profile.user}@{profile.host}:{profile.port})",
            )

    def on_select_profile(self, _event: object | None = None) -> None:
        selection = self.profile_list.curselection()

        if not selection:
            return

        self.selected_profile_index = selection[0]
        profile = self.profiles[self.selected_profile_index]

        self.name_var.set(profile.name)
        self.host_var.set(profile.host)
        self.user_var.set(profile.user)
        self.port_var.set(str(profile.port))
        self.password_var.set("")

    def selected_profile(self) -> SSHProfile | None:
        if self.selected_profile_index is None:
            selection = self.profile_list.curselection()

            if selection:
                self.selected_profile_index = selection[0]

        if self.selected_profile_index is None:
            messagebox.showerror(APP_NAME, "Select a saved profile first.")
            return None

        return self.profiles[self.selected_profile_index]

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
        self.clear_form()
        self.status_var.set(f"Saved profile: {name}")

    def clear_form(self) -> None:
        self.selected_profile_index = None
        self.profile_list.selection_clear(0, "end")

        self.name_var.set("")
        self.host_var.set("")
        self.user_var.set("")
        self.port_var.set("22")
        self.password_var.set("")

    def delete_profile(self) -> None:
        if self.selected_profile_index is None:
            messagebox.showerror(APP_NAME, "Select a profile first.")
            return

        profile = self.profiles[self.selected_profile_index]

        if not messagebox.askyesno(APP_NAME, f"Delete profile '{profile.name}'?"):
            return

        PasswordStore.delete(profile.name)
        del self.profiles[self.selected_profile_index]

        ProfileStore.save(self.profiles)
        self.refresh_profiles()
        self.clear_form()
        self.status_var.set(f"Deleted profile: {profile.name}")

    def create_console_tab(self, title: str | None = None) -> ConsoleTab:
        self.tab_counter += 1

        tab = ConsoleTab(self.notebook, self)
        tab_title = title or f"Tab {self.tab_counter}"

        self.notebook.add(tab, text=tab_title)
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

        tab = self.nametowidget(selected)

        if isinstance(tab, ConsoleTab):
            tab.close_all()

        self.notebook.forget(selected)
        self.status_var.set("Closed tab")

    def on_tab_changed(self, _event: object | None = None) -> None:
        self.current_tab()

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
        pywinpty_status = "Found" if PtyProcess is not None else "Missing"
        keyring_status = "Found" if keyring is not None else "Missing"
        pyte_status = "Found" if pyte is not None else "Missing"
        plink_status = "Found" if self.find_plink() else "Missing"

        messagebox.showinfo(
            APP_NAME,
            "Requirements:\n\n"
            f"pywinpty: {pywinpty_status}\n"
            f"keyring: {keyring_status}\n"
            f"pyte: {pyte_status}\n"
            f"plink.exe: {plink_status}\n\n"
            "Install Python packages:\n"
            "pip install pywinpty keyring pyte\n\n"
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
    app = EmbeddedSSHLauncher()
    app.mainloop()