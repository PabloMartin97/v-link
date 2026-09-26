#!/usr/bin/env python3
"""Apply the kiosk cursor/input policy outside V-Link and Chromium."""

import os
import pwd
import subprocess
import sys
import tempfile
from pathlib import Path

from v_link_lite_support import load_settings


# Labwc consumes these bindings before Chromium sees them. "None" is not a
# blocker in labwc: it removes the binding and forwards the key to the client.
BLOCKED_BROWSER_KEYS = (
    *(f"F{number}" for number in range(1, 13)),
    "Menu", "S-F10", "S-Escape",
    "A-Tab", "A-S-Tab", "A-F4", "A-Space", "A-Home", "A-Left", "A-Right",
    "A-f", "A-e", "A-d", "A-S-t", "A-S-i", "A-S-a", "A-S-n",
    "C-Tab", "C-S-Tab", "C-Prior", "C-Next", "C-S-Prior", "C-S-Next",
    "C-F4", "C-F5", "C-F6",
    *(f"C-{number}" for number in range(10)),
    "C-n", "C-S-n", "C-t", "C-S-t", "C-w", "C-S-w",
    "C-r", "C-S-r", "C-l", "C-k", "C-e", "C-f", "C-g", "C-S-g",
    "C-h", "C-j", "C-p", "C-s", "C-o", "C-u", "C-d", "C-S-d",
    "C-S-b", "C-S-o", "C-S-j", "C-S-i", "C-S-c", "C-S-m",
    "C-S-Delete", "C-plus", "C-minus", "C-equal",
)
BLOCKED_BROWSER_BINDINGS = "".join(
    f'    <keybind key="{key}"><action name="Execute" command="/usr/bin/true" /></keybind>\n'
    for key in BLOCKED_BROWSER_KEYS
)
KEYBIND = '''<?xml version="1.0"?>
<labwc_config>
  <keyboard>
    <keybind key="A-W-h">
      <action name="HideCursor" />
      <action name="WarpCursor" x="-1" y="-1" />
    </keybind>
{browser_bindings}  </keyboard>
  <mouse>
    <!-- No <default />: labwc's desktop and window menus are unnecessary
         in the kiosk. Ordinary clicks inside clients still pass through. -->
    <context name="Frame">
      <mousebind button="Right" action="Press">
        <action name="Execute" command="/usr/bin/true" />
      </mousebind>
    </context>
    <context name="Root">
      <mousebind button="Left" action="Press">
        <action name="Execute" command="/usr/bin/true" />
      </mousebind>
      <mousebind button="Middle" action="Press">
        <action name="Execute" command="/usr/bin/true" />
      </mousebind>
      <mousebind button="Right" action="Press">
        <action name="Execute" command="/usr/bin/true" />
      </mousebind>
    </context>
  </mouse>
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
    content = KEYBIND.format(browser_bindings=BLOCKED_BROWSER_BINDINGS,
                             input_policy=DISABLE_MOUSE if settings["MOUSE_ENABLED"] == "no" else "")
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
