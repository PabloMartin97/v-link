#!/usr/bin/env python3
"""Persistent, unprivileged maintenance screen for V-Link Lite."""

import curses
import fcntl
import os
import pwd
import stat
import subprocess
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE_ROOT))
if not (SOURCE_ROOT / "setup").is_dir():
    sys.path.insert(0, "/usr/local/lib/v-link-lite")

from v_link_lite_support import (load_settings, save_settings, system_details,
                                 format_size, read_snapshot)
import v_link_lite_audio as lite_audio
import v_link_lite_display as lite_display

from setup.audio import AUDIO_SAMPLE, AudioMixin, parse_audio_nodes
from setup.diagnostics import DiagnosticsMixin
from setup.display import DisplayMixin
from setup.navigation import NavigationMixin
from setup.network import NetworkMixin
from setup.storage import StorageMixin
from setup.terminal import TERMINAL_RC, TerminalMixin
from setup.ui import TITLE, BaseUI, is_socket
from setup.vlink import VLinkMixin


def runtime_directory(uid, home):
    """Use the private login runtime, or a private home directory for SSH."""
    candidate = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}")
    if not (candidate.is_dir() and candidate.stat().st_uid == uid
            and stat.S_IMODE(candidate.stat().st_mode) == 0o700):
        candidate = home / ".local/state/v-link-lite-setup"
        if candidate.is_symlink():
            raise RuntimeError("Unsafe Setup state directory.")
        candidate.mkdir(mode=0o700, parents=True, exist_ok=True)
        if candidate.stat().st_uid != uid:
            raise RuntimeError("Setup state directory is not owned by this user.")
        candidate.chmod(0o700)
    if stat.S_IMODE(candidate.stat().st_mode) != 0o700:
        raise RuntimeError("Setup runtime directory must be private to this user.")
    return candidate


def session_environment(uid):
    env = os.environ.copy()
    login_runtime = Path(f"/run/user/{uid}")
    if login_runtime.is_dir() and login_runtime.stat().st_uid == uid:
        env["XDG_RUNTIME_DIR"] = str(login_runtime)
        bus = login_runtime / "bus"
        if is_socket(bus):
            env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={bus}")
        if not lite_display.wayland_available(env):
            env.pop("WAYLAND_DISPLAY", None)
            if is_socket(bus):
                try:
                    manager = subprocess.run(["systemctl", "--user", "show-environment"],
                                             capture_output=True, text=True, timeout=2, env=env)
                    for line in manager.stdout.splitlines():
                        if line.startswith("WAYLAND_DISPLAY="):
                            env["WAYLAND_DISPLAY"] = line.split("=", 1)[1]
                            if lite_display.wayland_available(env):
                                break
                            env.pop("WAYLAND_DISPLAY", None)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if not lite_display.wayland_available(env):
                candidates = [path.name for path in login_runtime.glob("wayland-*")
                              if not path.is_symlink() and path.is_socket() and path.stat().st_uid == uid]
                if len(candidates) == 1:
                    env["WAYLAND_DISPLAY"] = candidates[0]
    return env


class SetupUI(
        NavigationMixin,
        NetworkMixin,
        AudioMixin,
        DisplayMixin,
        StorageMixin,
        VLinkMixin,
        DiagnosticsMixin,
        TerminalMixin,
        BaseUI):
    pass


def main(argv):
    if len(argv) > 1 or (argv and argv[0] != "--startup"):
        print("Usage: v-link-lite-setup [--startup]", file=sys.stderr)
        return 2
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("V-Link Lite Setup requires an interactive terminal.", file=sys.stderr)
        return 2
    if os.geteuid() == 0:
        print("Run V-Link Lite Setup as the kiosk user, not root.", file=sys.stderr)
        return 2
    uid = os.getuid()
    account = pwd.getpwuid(uid)
    home = Path(account.pw_dir)
    if not home.is_dir():
        print("Could not determine the current user home directory.", file=sys.stderr)
        return 2
    try:
        runtime = runtime_directory(uid, home)
        fd = os.open(runtime / "v-link-lite-setup.lock",
                     os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if os.fstat(fd).st_uid != uid or not stat.S_ISREG(os.fstat(fd).st_mode):
                raise RuntimeError("Unsafe Setup lock file.")
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("V-Link Lite Setup is already running.", file=sys.stderr)
                return 22 if argv else 0
            env = session_environment(uid)
            return curses.wrapper(lambda screen: SetupUI(screen, bool(argv), uid,
                                                          account.pw_name, env).main_menu())
        finally:
            os.close(fd)
    except (RuntimeError, OSError, curses.error) as error:
        print(f"V-Link Lite Setup: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
