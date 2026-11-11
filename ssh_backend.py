"""Direct SSH connections via paramiko - no local terminal emulation layer.

This is the entire reason v2 exists: v1 rendered the terminal itself (pyte
drawing into a Tk widget) fed by plink.exe piped through a Windows console
pty layer (ConPTY, then legacy WinPTY). That pty layer crashed once (ConPTY)
and silently corrupted escape sequences once WinPTY replaced it. Here, Python
never renders a terminal at all - it just relays raw bytes between a real SSH
channel and xterm.js (a mature terminal emulator running in the UI), so there
is no Windows console layer left to crash or corrupt anything.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import paramiko

DEFAULT_TERM = "xterm-256color"


@dataclass
class ConnectParams:
    host: str
    port: int
    username: str
    password: str | None = None
    key_path: str | None = None
    key_passphrase: str | None = None
    jump: "ConnectParams | None" = None


class SSHSession:
    """One interactive shell channel, optionally chained through a jump host."""

    def __init__(self) -> None:
        self.client: paramiko.SSHClient | None = None
        self.jump_client: paramiko.SSHClient | None = None
        self.channel: paramiko.Channel | None = None
        self._reader: threading.Thread | None = None
        self._alive = False

    def connect(
        self,
        params: ConnectParams,
        on_data: Callable[[str], None],
        on_close: Callable[[str], None],
        known_hosts_file: Path | None = None,
        cols: int = 120,
        rows: int = 32,
        timeout: float = 15.0,
    ) -> None:
        sock = None

        if params.jump is not None:
            self.jump_client = _open_client(params.jump, known_hosts_file, timeout)
            sock = self.jump_client.get_transport().open_channel(
                "direct-tcpip", (params.host, params.port), ("127.0.0.1", 0), timeout=timeout,
            )

        try:
            self.client = _open_client(params, known_hosts_file, timeout, sock=sock)
        except Exception:
            if self.jump_client is not None:
                try:
                    self.jump_client.close()
                except Exception:
                    pass
            raise

        channel = self.client.get_transport().open_session(timeout=timeout)
        channel.get_pty(term=DEFAULT_TERM, width=max(1, cols), height=max(1, rows))
        channel.invoke_shell()

        self.channel = channel
        self._alive = True

        def reader() -> None:
            while self._alive:
                try:
                    data = channel.recv(4096)
                except Exception as exc:
                    if self._alive:
                        self._alive = False
                        on_close(str(exc))
                    return
                if data == b"":
                    self._alive = False
                    on_close("closed")
                    return
                on_data(data.decode("utf-8", errors="replace"))

        self._reader = threading.Thread(target=reader, daemon=True)
        self._reader.start()

    def write(self, data: str) -> None:
        if self.channel is None:
            return
        payload = data.encode("utf-8", errors="replace")
        while payload:
            sent = self.channel.send(payload)
            if sent <= 0:
                raise IOError("SSH channel send failed")
            payload = payload[sent:]

    def resize(self, cols: int, rows: int) -> None:
        if self.channel is None:
            return
        try:
            self.channel.resize_pty(width=max(1, cols), height=max(1, rows))
        except Exception:
            pass

    def exec_command(self, command: str, timeout: float = 35.0) -> tuple[bool, str, str]:
        """Run a one-shot non-interactive command (health checks, etc.) -
        no pty, no shell, just the SSH "exec" channel type."""
        if self.client is None:
            return False, "", "not connected"
        try:
            _stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            success = stdout.channel.recv_exit_status() == 0
            return success, out, err
        except Exception as exc:
            return False, "", str(exc)

    def open_sftp(self) -> "paramiko.SFTPClient | None":
        if self.client is None:
            return None
        return self.client.open_sftp()

    def isalive(self) -> bool:
        if self.channel is None or self.channel.closed:
            return False
        transport = self.channel.get_transport()
        return transport is not None and transport.is_active()

    def close(self) -> None:
        self._alive = False
        for obj in (self.channel, self.client, self.jump_client):
            if obj is None:
                continue
            try:
                obj.close()
            except Exception:
                pass


def run_one_shot_command(
    params: ConnectParams, command: str, known_hosts_file: Path | None = None, timeout: float = 35.0,
) -> tuple[bool, str, str]:
    """Non-interactive command execution - no pty, no shell, just the SSH
    "exec" channel type. Used for health checks and similar one-shot calls
    that don't need (or want) an interactive session."""
    client = _open_client(params, known_hosts_file, timeout)
    try:
        _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        success = stdout.channel.recv_exit_status() == 0
        return success, out, err
    finally:
        client.close()


def upload_file(
    params: ConnectParams, local_path: str, remote_path: str,
    known_hosts_file: Path | None = None, timeout: float = 20.0,
) -> None:
    client = _open_client(params, known_hosts_file, timeout)
    try:
        sftp = client.open_sftp()
        try:
            sftp.put(local_path, remote_path)
        finally:
            sftp.close()
    finally:
        client.close()


def download_file(
    params: ConnectParams, remote_path: str, local_path: str,
    known_hosts_file: Path | None = None, timeout: float = 20.0,
) -> None:
    client = _open_client(params, known_hosts_file, timeout)
    try:
        sftp = client.open_sftp()
        try:
            sftp.get(remote_path, local_path)
        finally:
            sftp.close()
    finally:
        client.close()


def _open_client(
    params: ConnectParams, known_hosts_file: Path | None, timeout: float, sock=None,
) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    if known_hosts_file is not None and known_hosts_file.exists():
        try:
            client.load_host_keys(str(known_hosts_file))
        except Exception:
            pass

    connect_kwargs: dict = dict(
        hostname=params.host,
        port=params.port,
        username=params.username,
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
        sock=sock,
        look_for_keys=False,
        allow_agent=False,
    )

    if params.key_path:
        pkey = _load_private_key(params.key_path, params.key_passphrase)
        connect_kwargs["pkey"] = pkey
    else:
        connect_kwargs["password"] = params.password or ""

    client.connect(**connect_kwargs)

    if known_hosts_file is not None:
        try:
            known_hosts_file.parent.mkdir(parents=True, exist_ok=True)
            client.save_host_keys(str(known_hosts_file))
        except Exception:
            pass

    return client


def _load_private_key(key_path: str, passphrase: str | None) -> paramiko.PKey:
    last_exc: Exception | None = None
    for key_cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey):
        try:
            return key_cls.from_private_key_file(key_path, password=passphrase or None)
        except Exception as exc:
            last_exc = exc
    raise ValueError(f"Could not load private key {key_path}: {last_exc}")


def generate_ed25519_keypair(private_key_path: Path) -> str:
    """Generate a new ed25519 keypair and write it to private_key_path /
    private_key_path.pub. Returns the public key line (OpenSSH format).

    paramiko.Ed25519Key can only load/verify existing keys, not generate new
    ones (unlike RSAKey, it has no .generate()) - use the `cryptography`
    library (already a paramiko dependency) to generate the key and write it
    in OpenSSH format, which paramiko can then load normally.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key_path.parent.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )
    private_key_path.write_bytes(private_pem)
    try:
        os.chmod(private_key_path, 0o600)
    except Exception:
        pass

    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )
    public_line = public_bytes.decode("ascii") + " ssh-console-launcher-v2"
    private_key_path.with_suffix(private_key_path.suffix + ".pub").write_text(public_line + "\n", encoding="utf-8")
    return public_line


def install_public_key(params: ConnectParams, public_key_line: str, timeout: float = 15.0) -> None:
    """ssh-copy-id equivalent: authenticate with a password once, append the
    public key line to ~/.ssh/authorized_keys on the remote."""
    client = _open_client(params, None, timeout)
    try:
        command = (
            "umask 077; mkdir -p ~/.ssh && "
            f"grep -qxF {_shell_quote(public_key_line)} ~/.ssh/authorized_keys 2>/dev/null || "
            f"echo {_shell_quote(public_key_line)} >> ~/.ssh/authorized_keys"
        )
        _stdin, stdout, _stderr = client.exec_command(command, timeout=timeout)
        status = stdout.channel.recv_exit_status()
        if status != 0:
            raise RuntimeError(f"Remote command exited with status {status}")
    finally:
        client.close()


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"
