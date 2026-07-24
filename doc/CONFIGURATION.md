# Configuration & Storage

All user data lives outside the install folder, under:

```text
%APPDATA%\EmbeddedSSHLauncher\
```

| File | Written by | Contents |
|---|---|---|
| `profiles.json` | `ProfileStore` | Saved SSH profiles: name, host, user, port. **No passwords.** |
| `commands.json` | `CommandStore` | Saved Quick Commands (label + shell command string) |

## Passwords

Passwords are **not** stored in either JSON file. `PasswordStore` (wraps the `keyring` package) saves each profile's password in the Windows Credential Manager, keyed by `SERVICE_NAME = "EmbeddedSSHLauncher"` + the profile name. Deleting a profile also deletes its stored credential.

Implication: `profiles.json` is safe to back up, sync, or commit to a private dotfiles repo on its own — it never contains secrets. The credential store is per-Windows-user-account, so profiles copied to another machine or user will prompt for the password again on first connect.

## Default Quick Commands

`CommandStore.default_commands()` seeds these on first run:

```bash
htop
cd /home/www-data/web2py/
tail -f web2py.log
sudo uwsgitop /tmp/stats.socket
clear
```

These assume a Web2py/uWSGI server layout — edit or delete them from the GUI if that doesn't match your target servers.

## Security notes (also see root [README.md](../README.md#security-notes))

- Anyone with access to the logged-in Windows session can open saved profiles and connect without re-entering a password (the credential is fetched from `keyring` transparently).
- `plink.exe -pw` passes the password as a process argument for the duration of the connection — treat this the same as you would any tool doing password auth via CLI flag.
- SSH key-based auth is not implemented yet (tracked as `v1.5.0` in `FEATURES_PLAN.md`).
