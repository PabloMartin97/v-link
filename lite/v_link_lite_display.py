#!/usr/bin/env python3
"""Discover and apply only advertised Wayland modes for V-Link Lite."""

import os
import re
import subprocess
import sys
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from PIL import Image

from v_link_lite_support import (DISPLAY_MODE_PATTERN, DISPLAY_OUTPUT_PATTERN,
                                 load_settings)


HEADER = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\s+".*"$')
MODE = re.compile(r'^\s+([1-9][0-9]{0,4})x([1-9][0-9]{0,4})\s+px,\s+'
                  r'([0-9]{1,3}(?:\.[0-9]{1,6})?)\s+Hz(?:\s+\(([^)]*)\))?\s*$')
SPLASH_RENDERER = "/usr/local/libexec/v-link-lite-render-splash"
SPLASH_IMAGE = "/usr/local/share/v-link-lite/splash.png"


class DisplayError(Exception):
    """A recoverable display setup error."""


def refresh_millihertz(value):
    return int((Decimal(value) * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_outputs(text):
    """Parse wlr-randr's output, keeping exact advertised mode strings."""
    outputs = []
    current = None
    in_modes = False
    for line in text.splitlines():
        if line and not line[0].isspace():
            match = HEADER.fullmatch(line)
            if not match:
                raise DisplayError(f"Unrecognized output heading: {line[:80]}")
            current = {"name": match.group(1), "enabled": False, "modes": []}
            outputs.append(current)
            in_modes = False
        elif current is not None:
            stripped = line.strip()
            if stripped.startswith("Enabled: "):
                current["enabled"] = stripped == "Enabled: yes"
            elif stripped == "Modes:":
                in_modes = True
            elif in_modes:
                match = MODE.fullmatch(line)
                if match:
                    width, height, refresh, flags = match.groups()
                    if int(width) > 10000 or int(height) > 10000 or not 1 <= Decimal(refresh) <= 500:
                        continue
                    markers = {item.strip() for item in (flags or "").split(",")}
                    current["modes"].append({
                        "width": int(width), "height": int(height),
                        "refresh": refresh, "mhz": refresh_millihertz(refresh),
                        "token": f"{width}x{height}@{refresh}",
                        "current": "current" in markers,
                        "preferred": "preferred" in markers,
                    })
                elif stripped and not line.startswith("    "):
                    in_modes = False
    return outputs


def query_outputs(env):
    try:
        result = subprocess.run(["wlr-randr"], env=env, capture_output=True,
                                text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DisplayError(f"Could not query Wayland outputs: {error}") from error
    if result.returncode:
        raise DisplayError((result.stderr or result.stdout).strip()[:220] or "wlr-randr failed")
    return parse_outputs(result.stdout)


def active_outputs(outputs):
    return [output for output in outputs if output["enabled"] and output["modes"]]


def find_output(outputs, name):
    return next((output for output in active_outputs(outputs) if output["name"] == name), None)


def matching_mode(output, token):
    match = DISPLAY_MODE_PATTERN.fullmatch(token)
    if not match or output is None:
        return None
    width, height = int(match.group(1)), int(match.group(2))
    mhz = refresh_millihertz(match.group(3))
    return next((mode for mode in output["modes"]
                 if mode["width"] == width and mode["height"] == height and mode["mhz"] == mhz), None)


def apply_mode(output_name, token, env):
    if not DISPLAY_OUTPUT_PATTERN.fullmatch(output_name) or not DISPLAY_MODE_PATTERN.fullmatch(token):
        raise DisplayError("Invalid output or mode")
    output = find_output(query_outputs(env), output_name)
    mode = matching_mode(output, token)
    if mode is None:
        raise DisplayError("The selected output or mode is no longer available")
    command = ["wlr-randr", "--output", output_name, "--mode", mode["token"]]
    try:
        result = subprocess.run(command, env=env, capture_output=True,
                                text=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DisplayError(f"Could not apply display mode: {error}") from error
    if result.returncode:
        raise DisplayError((result.stderr or result.stdout).strip()[:220] or "wlr-randr rejected the mode")


def effective_size(home, env):
    outputs = active_outputs(query_outputs(env))
    if not outputs:
        raise DisplayError("No active display mode is available for the Lite splash")
    settings = load_settings(home)
    output = find_output(outputs, settings["DISPLAY_OUTPUT"])
    if output is None:
        if len(outputs) != 1:
            raise DisplayError("Several displays are active and no Lite output is selected")
        output = outputs[0]
    mode = next((item for item in output["modes"] if item["current"]), None)
    if mode is None:
        raise DisplayError("The active display does not report its current mode")
    return mode["width"], mode["height"]


def refresh_splash(width, height, env):
    command = ["sudo", "-n", SPLASH_RENDERER, "--refresh-installed",
               "--width", str(width), "--height", str(height)]
    try:
        result = subprocess.run(command, env=env, capture_output=True,
                                text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DisplayError(f"Could not regenerate the Lite splash: {error}") from error
    if result.returncode:
        raise DisplayError((result.stderr or result.stdout).strip()[:220]
                           or "Lite splash regeneration failed")


def png_size(path=None):
    path = SPLASH_IMAGE if path is None else path
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                return None
            size = image.size
            image.verify()
    except (OSError, SyntaxError, ValueError):
        return None
    return size


def refresh_current_splash(home, env):
    width, height = effective_size(home, env)
    if png_size() != (width, height):
        refresh_splash(width, height, env)
    return width, height


def restart_background(env):
    try:
        subprocess.run(["pkill", "-x", "swaybg"], env=env, capture_output=True,
                       timeout=3, check=False)
        subprocess.Popen(
            ["swaybg", "-i", SPLASH_IMAGE, "-m", "center", "-c", "000000"],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DisplayError(f"Could not restart the Lite background: {error}") from error


def wayland_available(env):
    display = env.get("WAYLAND_DISPLAY", "")
    if not display:
        return False
    path = Path(display) if display.startswith("/") else Path(env.get("XDG_RUNTIME_DIR", "/nonexistent")) / display
    try:
        return not path.is_symlink() and path.is_socket() and path.stat().st_uid == os.getuid()
    except OSError:
        return False


def apply_saved(home, env, warning=print):
    """Best effort at boot. Never block the kiosk for a stale display choice."""
    try:
        settings = load_settings(home)
        if settings["DISPLAY_MODE"] == "auto" or not wayland_available(env):
            return False
        deadline = time.monotonic() + 2
        while True:
            try:
                outputs = query_outputs(env)
            except DisplayError:
                if time.monotonic() >= deadline:
                    raise
            else:
                if active_outputs(outputs) or time.monotonic() >= deadline:
                    break
            time.sleep(0.2)
        output = find_output(outputs, settings["DISPLAY_OUTPUT"])
        if matching_mode(output, settings["DISPLAY_MODE"]) is None:
            warning("V-Link Lite: saved display output/mode is unavailable; keeping compositor default.")
            return False
        apply_mode(settings["DISPLAY_OUTPUT"], settings["DISPLAY_MODE"], env)
        return True
    except (DisplayError, ValueError, OSError) as error:
        warning(f"V-Link Lite: display preference was not applied: {error}")
        return False


def main(argv):
    if argv not in (["apply"], ["current-size"], ["refresh-splash"]):
        print("Usage: v_link_lite_display.py {apply|current-size|refresh-splash}",
              file=sys.stderr)
        return 2
    if argv == ["apply"]:
        apply_saved(Path.home(), os.environ,
                    warning=lambda message: print(message, file=sys.stderr))
    else:
        try:
            if argv == ["current-size"]:
                width, height = effective_size(Path.home(), os.environ)
                print(f"{width}x{height}")
            else:
                refresh_current_splash(Path.home(), os.environ)
        except (DisplayError, ValueError, OSError) as error:
            print(f"V-Link Lite: display query failed: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
