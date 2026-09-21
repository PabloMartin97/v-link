"""Pure-host checks for Lite preferences, diagnostics and console snapshots."""

import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lite"))
import v_link_lite_support as support

SPEC = importlib.util.spec_from_file_location("lite_cursor", ROOT / "lite/V-Link-Lite-Cursor.py")
cursor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cursor)

CONSOLE_SPEC = importlib.util.spec_from_file_location("lite_console", ROOT / "backend/shared/lite_console.py")
console = importlib.util.module_from_spec(CONSOLE_SPEC)
CONSOLE_SPEC.loader.exec_module(console)


def test_settings_parser_rejects_code_unknown_and_duplicate_keys():
    assert support.parse_settings("CURSOR_MODE=auto\nMOUSE_ENABLED=no\n")["MOUSE_ENABLED"] == "no"
    for content in ("CURSOR_MODE=$(touch /tmp/unsafe)", "OTHER=yes", "CURSOR_MODE=auto\nCURSOR_MODE=visible"):
        try:
            support.parse_settings(content)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid setting was accepted")


def test_default_creation_preserves_existing_preference():
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
        assert support.save_settings(directory, support.DEFAULT_SETTINGS, create_only=True)
        settings = {"CURSOR_MODE": "visible", "MOUSE_ENABLED": "no"}
        support.save_settings(directory, settings)
        assert not support.save_settings(directory, support.DEFAULT_SETTINGS, create_only=True)
        assert support.load_settings(directory) == settings


def test_cpu_percentage_from_two_samples():
    assert support.cpu_percent([100, 0, 0, 100, 0], [130, 0, 0, 170, 0]) == 30
    assert support.cpu_percent([0, 0, 0, 0, 0], [0, 0, 0, 0, 0]) is None


def test_throttling_flags_and_unknown_values():
    bits = support.decode_throttling("throttled=0x50005")
    assert bits["undervoltage_now"] and bits["throttled_now"]
    assert bits["undervoltage_seen"] and bits["throttled_seen"]
    assert bits["unknown_bits"] == 0
    assert support.decode_throttling("permission denied") is None
    assert support.decode_throttling("throttled=0x100000")["unknown_bits"]


def test_cursor_config_disables_only_pointer_categories():
    with tempfile.TemporaryDirectory() as directory:
        cursor.sync_config(directory, {"MOUSE_ENABLED": "no"})
        content = (Path(directory) / ".config/labwc/rc.xml").read_text()
        assert 'category="non-touch"' in content
        assert 'category="touchpad"' in content
        assert 'category="touch"' not in content
        cursor.sync_config(directory, {"MOUSE_ENABLED": "yes"})
        assert "sendEventsMode" not in (Path(directory) / ".config/labwc/rc.xml").read_text()


def test_auto_cursor_policy_starts_idle_service_then_hides_pointer():
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
        "XDG_CONFIG_HOME": str(Path(directory) / ".config"), "WAYLAND_DISPLAY": "wayland-0",
    }), patch.object(cursor.subprocess, "run") as run:
        cursor.apply(directory, {"CURSOR_MODE": "auto", "MOUSE_ENABLED": "yes"})
    commands = [call.args[0] for call in run.call_args_list]
    assert commands == [
        ["labwc", "--reconfigure"],
        ["systemctl", "--user", "stop", "v-link-lite-cursor-idle.service"],
        ["systemctl", "--user", "start", "v-link-lite-cursor-idle.service"],
        ["wtype", "-M", "alt", "-M", "logo", "-P", "h"],
    ]


def test_mouse_off_never_starts_idle_service():
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
        "XDG_CONFIG_HOME": str(Path(directory) / ".config"), "WAYLAND_DISPLAY": "wayland-0",
    }), patch.object(cursor.subprocess, "run") as run:
        cursor.apply(directory, {"CURSOR_MODE": "visible", "MOUSE_ENABLED": "no"})
    commands = [call.args[0] for call in run.call_args_list]
    assert ["systemctl", "--user", "start", "v-link-lite-cursor-idle.service"] not in commands
    assert commands[-1] == ["wtype", "-M", "alt", "-M", "logo", "-P", "h"]


def test_snapshot_rejects_stale_or_wrong_pid():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "console.json"
        with patch.object(support, "snapshot_path", return_value=path):
            path.write_text(json.dumps({"pid": 123, "updated": time.time(), "threads": []}))
            path.chmod(0o600)
            assert support.read_snapshot(os.getuid(), 123)["pid"] == 123
            assert support.read_snapshot(os.getuid(), 124) is None
            path.write_text(json.dumps({"pid": 123, "updated": time.time() - 30}))
            assert support.read_snapshot(os.getuid(), 123) is None


def test_console_payload_reuses_terminal_state_and_removes_ansi():
    payload = console.build_payload(((("server", True),), True, False, ("\x1b[33mWARNING x\x1b[0m",)),
                            "3.0", "Pi 4", "Wayland")
    assert payload["threads"] == (("server", True),)
    assert payload["rti"] and not payload["ign"]
    assert payload["warnings"] == ["WARNING x"]
