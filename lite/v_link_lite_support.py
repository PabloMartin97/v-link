"""Small, dependency-free helpers shared by the Lite maintenance tools."""

import json
import os
import re
import shutil
import stat
import tempfile
import time
from pathlib import Path


MODES = {"auto", "visible"}
DISPLAY_OUTPUT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
DISPLAY_MODE_PATTERN = re.compile(r"^([1-9][0-9]{0,4})x([1-9][0-9]{0,4})@([0-9]{1,3}(?:\.[0-9]{1,6})?)$")
DEFAULT_SETTINGS = {"CURSOR_MODE": "auto", "MOUSE_ENABLED": "yes",
                    "DISPLAY_MODE": "auto", "DISPLAY_OUTPUT": ""}
SNAPSHOT_NAME = "v-link-lite-console.json"


def settings_path(home):
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path(home) / ".config") / "v-link-lite/settings.conf"


def parse_settings(content):
    settings = DEFAULT_SETTINGS.copy()
    seen = set()
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("Invalid Lite setting")
        key, value = (part.strip() for part in line.split("=", 1))
        if key not in DEFAULT_SETTINGS or key in seen:
            raise ValueError("Unknown or duplicate Lite setting")
        if key == "CURSOR_MODE" and value not in MODES:
            raise ValueError("CURSOR_MODE must be auto or visible")
        if key == "MOUSE_ENABLED" and value not in {"yes", "no"}:
            raise ValueError("MOUSE_ENABLED must be yes or no")
        if key == "DISPLAY_MODE" and value != "auto":
            match = DISPLAY_MODE_PATTERN.fullmatch(value)
            if not match or int(match.group(1)) > 10000 or int(match.group(2)) > 10000 or not 1 <= float(match.group(3)) <= 500:
                raise ValueError("DISPLAY_MODE must be auto or WIDTHxHEIGHT@REFRESH")
        if key == "DISPLAY_OUTPUT" and value and not DISPLAY_OUTPUT_PATTERN.fullmatch(value):
            raise ValueError("DISPLAY_OUTPUT is invalid")
        seen.add(key)
        settings[key] = value
    if settings["DISPLAY_MODE"] != "auto" and not settings["DISPLAY_OUTPUT"]:
        raise ValueError("DISPLAY_OUTPUT is required for a fixed display mode")
    return settings


def load_settings(home):
    path = settings_path(home)
    if path.is_symlink():
        raise ValueError("Lite settings cannot be a symlink")
    try:
        return parse_settings(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return DEFAULT_SETTINGS.copy()


def save_settings(home, settings, create_only=False):
    if set(settings) - set(DEFAULT_SETTINGS):
        raise ValueError("Unknown Lite setting")
    settings = {**DEFAULT_SETTINGS, **settings}
    path = settings_path(home)
    parent = path.parent
    if parent.is_symlink() or path.is_symlink():
        raise ValueError("Unsafe Lite settings path")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if parent.stat().st_uid != os.getuid():
        raise ValueError("Lite settings directory must belong to this user")
    parent.chmod(0o700)
    content = "".join(f"{key}={settings[key]}\n" for key in DEFAULT_SETTINGS)
    parse_settings(content)
    if create_only and path.exists():
        return False
    if path.exists() and (not path.is_file() or path.stat().st_uid != os.getuid()):
        raise ValueError("Unsafe Lite settings file")
    descriptor, temporary = tempfile.mkstemp(prefix=".settings.", dir=parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def cpu_percent(before, after):
    delta_total = sum(after) - sum(before)
    delta_idle = (after[3] + after[4]) - (before[3] + before[4])
    return None if delta_total <= 0 else round(100 * (delta_total - delta_idle) / delta_total)


def cpu_sample(path="/proc/stat"):
    return [int(value) for value in Path(path).read_text().splitlines()[0].split()[1:]]


def decode_throttling(output):
    match = re.search(r"throttled=0x([0-9a-fA-F]+)\b", output)
    if not match:
        return None
    value = int(match.group(1), 16)
    return {
        "raw": match.group(0),
        "undervoltage_now": bool(value & (1 << 0)),
        "frequency_capped_now": bool(value & (1 << 1)),
        "throttled_now": bool(value & (1 << 2)),
        "soft_temp_now": bool(value & (1 << 3)),
        "undervoltage_seen": bool(value & (1 << 16)),
        "frequency_capped_seen": bool(value & (1 << 17)),
        "throttled_seen": bool(value & (1 << 18)),
        "soft_temp_seen": bool(value & (1 << 19)),
        "unknown_bits": value & ~0xF000F,
    }


def system_details(command):
    """Read local kernel counters; only the CPU sample waits (300 ms)."""
    details = {}
    def read(path):
        try:
            return Path(path).read_text().strip("\x00\n ")
        except (OSError, ValueError):
            return ""

    details["model"] = read("/proc/device-tree/model") or "unavailable"
    details["cores"] = os.cpu_count() or "unavailable"
    try:
        before = cpu_sample()
        time.sleep(0.3)
        details["cpu"] = cpu_percent(before, cpu_sample())
    except (OSError, ValueError, IndexError):
        details["cpu"] = None
    details["load"] = " / ".join(read("/proc/loadavg").split()[:3]) or "unavailable"
    try:
        details["temperature"] = float(read("/sys/class/thermal/thermal_zone0/temp")) / 1000
    except ValueError:
        details["temperature"] = None
    memory = {}
    for line in read("/proc/meminfo").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            try:
                memory[key] = int(value.strip().split()[0]) * 1024
            except (ValueError, IndexError):
                pass
    total = memory.get("MemTotal")
    available = memory.get("MemAvailable")
    details["ram_total"] = total
    details["ram_available"] = available
    details["ram_used"] = total - available if total is not None and available is not None else None
    try:
        disk = shutil.disk_usage("/")
        details["disk_total"], details["disk_used"] = disk.total, disk.used
    except OSError:
        details["disk_total"] = details["disk_used"] = None
    try:
        details["uptime"] = int(float(read("/proc/uptime").split()[0]))
    except (ValueError, IndexError):
        details["uptime"] = None
    _, output = command(["vcgencmd", "get_throttled"], 2)
    details["power"] = decode_throttling(output)
    return details


def format_size(value):
    if value is None:
        return "unavailable"
    unit = "B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            break
        value /= 1024
    return f"{value:.1f} {unit}"


def snapshot_path(uid):
    return Path(f"/run/user/{uid}") / SNAPSHOT_NAME


def read_snapshot(uid, expected_pid=None):
    path = snapshot_path(uid)
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) & 0o077:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("pid") != expected_pid:
            return None
        if abs(time.time() - data.get("updated", 0)) > 3:
            return None
        return data
    except (OSError, ValueError, TypeError):
        return None
