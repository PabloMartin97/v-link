#!/usr/bin/env python3
"""Apply the kiosk cursor/input policy outside V-Link and Chromium."""

import os
import pwd
import subprocess
import sys
import tempfile
from pathlib import Path

from v_link_lite_support import load_settings


KEYBIND = '''<?xml version="1.0"?>
<labwc_config>
  <keyboard>
    <keybind key="A-W-h">
      <action name="HideCursor" />
      <action name="WarpCursor" x="-1" y="-1" />
    </keybind>
  </keyboard>
{input_policy}</labwc_config>
'''
DISABLE_MOUSE = '''  <libinput>
    <device category="non-touch"><sendEventsMode>no</sendEventsMode></device>
    <device category="touchpad"><sendEventsMode>no</sendEventsMode></device>
  </libinput>
'''


def sync_config(home, settings):
    directory = Path(os.environ.get("XDG_CONFIG_HOME") or Path(home) / ".config") / "labwc"
    if directory.is_symlink():
        raise ValueError("Unsafe labwc configuration directory")
    directory.mkdir(parents=True, exist_ok=True)
    if directory.stat().st_uid != os.getuid():
        raise ValueError("labwc configuration directory must belong to this user")
    content = KEYBIND.format(input_policy=DISABLE_MOUSE if settings["MOUSE_ENABLED"] == "no" else "")
    path = directory / "rc.xml"
    if path.is_symlink():
        raise ValueError("Unsafe labwc configuration file")
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    descriptor, temporary = tempfile.mkstemp(prefix=".rc.", dir=directory)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def apply(home, settings):
    changed = sync_config(home, settings)
    if not os.environ.get("WAYLAND_DISPLAY"):
        return 0  # SSH can save a preference; it takes effect next graphical login.
    if changed:
        subprocess.run(["labwc", "--reconfigure"], check=True, timeout=3)
    subprocess.run(["systemctl", "--user", "stop", "v-link-lite-cursor-idle.service"],
                   check=False, timeout=3)
    if settings["MOUSE_ENABLED"] == "yes" and settings["CURSOR_MODE"] == "auto":
        subprocess.run(["systemctl", "--user", "start", "v-link-lite-cursor-idle.service"],
                       check=True, timeout=3)
    if settings["MOUSE_ENABLED"] == "no" or settings["CURSOR_MODE"] == "auto":
        subprocess.run(["wtype", "-M", "alt", "-M", "logo", "-P", "h"],
                       check=True, timeout=3)
    return 0


def main():
    if os.geteuid() == 0 or len(sys.argv) != 2 or sys.argv[1] not in {"sync-config", "apply", "hide"}:
        print("Usage: v-link-lite-cursor {sync-config|apply|hide} (as kiosk user)", file=sys.stderr)
        return 2
    try:
        if sys.argv[1] == "hide":
            if not os.environ.get("WAYLAND_DISPLAY"):
                return 1
            subprocess.run(["wtype", "-M", "alt", "-M", "logo", "-P", "h"],
                           check=True, timeout=3)
            return 0
        home = pwd.getpwuid(os.getuid()).pw_dir
        settings = load_settings(home)
        if sys.argv[1] == "apply":
            return apply(home, settings)
        sync_config(home, settings)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"V-Link Lite cursor: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
