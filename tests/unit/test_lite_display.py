"""Host-only Wayland mode tests; no live display or Raspberry Pi required."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from tests.unit.test_lite_setup_tui import SETUP, make_ui
from v_link_lite_support import DEFAULT_SETTINGS, load_settings, parse_settings, save_settings
import v_link_lite_display as display


SINGLE = '''HDMI-A-1 "Car display"
  Enabled: yes
  Modes:
    800x600 px, 60.317001 Hz (current)
    1024x768 px, 60.004002 Hz
    1920x1080 px, 59.939999 Hz
    1920x1080 px, 60.000000 Hz (preferred)
  Position: 0,0
'''
MULTIPLE = SINGLE + '''DP-2 "Bench display"
  Enabled: yes
  Modes:
    1280x720 px, 50.000000 Hz (preferred, current)
  Position: 1920,0
'''
OTHER = '''DP-2 "Bench display"
  Enabled: yes
  Modes:
    1280x720 px, 50.000000 Hz (preferred, current)
'''


def test_parse_single_output_exact_modes_and_flags():
    outputs = display.parse_outputs(SINGLE)
    assert len(outputs) == 1 and outputs[0]["name"] == "HDMI-A-1"
    modes = outputs[0]["modes"]
    assert modes[0]["token"] == "800x600@60.317001" and modes[0]["current"]
    assert modes[-1]["preferred"] and not modes[-1]["current"]
    assert [mode["token"] for mode in modes if mode["width"] == 1920] == [
        "1920x1080@59.939999", "1920x1080@60.000000"]
    assert display.matching_mode(outputs[0], "800x600@60.317001") == modes[0]


def test_parse_multiple_outputs_and_current_preferred():
    outputs = display.parse_outputs(MULTIPLE)
    assert [item["name"] for item in display.active_outputs(outputs)] == ["HDMI-A-1", "DP-2"]
    assert display.find_output(outputs, "DP-2")["modes"][0]["current"]
    assert display.find_output(outputs, "DP-2")["modes"][0]["preferred"]


def test_old_settings_default_to_auto_and_valid_fixed_mode_survives():
    old = parse_settings("CURSOR_MODE=visible\nMOUSE_ENABLED=no\n")
    assert old["DISPLAY_MODE"] == "auto" and old["DISPLAY_OUTPUT"] == ""
    fixed = parse_settings("DISPLAY_MODE=800x600@60.317001\nDISPLAY_OUTPUT=HDMI-A-1\n")
    assert fixed["DISPLAY_MODE"] == "800x600@60.317001"


def test_bad_mode_and_output_are_rejected_without_code_execution():
    for raw in ("DISPLAY_MODE=800x600@0\nDISPLAY_OUTPUT=HDMI-A-1\n",
                "DISPLAY_MODE=800x600@60;touch /tmp/x\nDISPLAY_OUTPUT=HDMI-A-1\n",
                "DISPLAY_MODE=800x600@60\n",
                "DISPLAY_MODE=800x600@60\nDISPLAY_OUTPUT=HDMI-A-1;rm\n"):
        try:
            parse_settings(raw)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid settings accepted: {raw!r}")


def test_apply_uses_argv_and_exact_advertised_mode():
    query = subprocess.CompletedProcess(["wlr-randr"], 0, SINGLE, "")
    applied = subprocess.CompletedProcess([], 0, "", "")
    with patch.object(display.subprocess, "run", side_effect=(query, applied)) as run:
        display.apply_mode("HDMI-A-1", "800x600@60.317001", {})
    assert run.call_args_list[1].args[0] == [
        "wlr-randr", "--output", "HDMI-A-1", "--mode", "800x600@60.317001"]


def test_failed_wlr_randr_does_not_overwrite_saved_preference():
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
        save_settings(directory, DEFAULT_SETTINGS)
        ui, _ = make_ui([])
        ui.home = Path(directory)
        ui.display_available = lambda: True
        ui.choose = lambda *_args, **_kwargs: "800x600@60.317001"
        ui.message = lambda *_args: None
        with patch.object(SETUP.lite_display, "query_outputs", return_value=display.parse_outputs(SINGLE)), \
             patch.object(SETUP.lite_display, "apply_mode", side_effect=display.DisplayError("failed")):
            ui.resolution_menu()
        assert load_settings(directory)["DISPLAY_MODE"] == "auto"


def test_multiple_outputs_require_explicit_selection_and_save_its_name():
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
        save_settings(directory, DEFAULT_SETTINGS)
        ui, _ = make_ui([])
        ui.home = Path(directory)
        ui.display_available = lambda: True
        choices = iter(("DP-2", "1280x720@50.000000"))
        headings = []
        ui.choose = lambda heading, *_args, **_kwargs: (headings.append(heading), next(choices))[1]
        ui.message = lambda *_args: None
        with patch.object(SETUP.lite_display, "query_outputs", return_value=display.parse_outputs(MULTIPLE)), \
             patch.object(SETUP.lite_display, "apply_mode") as apply:
            ui.resolution_menu()
        assert headings[0] == "Select display output"
        apply.assert_called_once_with("DP-2", "1280x720@50.000000", ui.env)
        assert load_settings(directory)["DISPLAY_OUTPUT"] == "DP-2"


def test_auto_clears_override_without_forcing_a_mode():
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
        save_settings(directory, {**DEFAULT_SETTINGS,
                                  "DISPLAY_MODE": "800x600@60.317001", "DISPLAY_OUTPUT": "HDMI-A-1"})
        ui, _ = make_ui([])
        ui.home = Path(directory)
        ui.display_available = lambda: False
        ui.choose = lambda *_args, **_kwargs: "auto"
        ui.message = lambda *_args: None
        ui.resolution_menu()
        assert load_settings(directory)["DISPLAY_MODE"] == "auto"
        assert load_settings(directory)["DISPLAY_OUTPUT"] == ""


def test_boot_stale_mode_falls_back_without_applying():
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
        save_settings(directory, {**DEFAULT_SETTINGS,
                                  "DISPLAY_MODE": "800x600@60.317001", "DISPLAY_OUTPUT": "HDMI-A-1"})
        warnings = []
        with patch.object(display, "wayland_available", return_value=True), \
             patch.object(display, "query_outputs", return_value=display.parse_outputs(
                 SINGLE.replace("800x600 px, 60.317001 Hz (current)\n", ""))), \
             patch.object(display, "apply_mode") as apply:
            assert not display.apply_saved(directory, {}, warnings.append)
        apply.assert_not_called()
        assert "unavailable" in warnings[0]


def test_boot_applies_valid_saved_mode_and_ignores_changed_monitor():
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
        save_settings(directory, {**DEFAULT_SETTINGS,
                                  "DISPLAY_MODE": "800x600@60.317001", "DISPLAY_OUTPUT": "HDMI-A-1"})
        with patch.object(display, "wayland_available", return_value=True), \
             patch.object(display, "query_outputs", return_value=display.parse_outputs(SINGLE)), \
             patch.object(display, "apply_mode") as apply:
            assert display.apply_saved(directory, {})
        apply.assert_called_once_with("HDMI-A-1", "800x600@60.317001", {})
        warnings = []
        with patch.object(display, "wayland_available", return_value=True), \
             patch.object(display, "query_outputs", return_value=display.parse_outputs(OTHER)), \
             patch.object(display, "apply_mode") as apply:
            assert not display.apply_saved(directory, {}, warnings.append)
        apply.assert_not_called()
        assert "unavailable" in warnings[0]


def test_boot_without_wayland_does_not_query_or_block():
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
        save_settings(directory, {**DEFAULT_SETTINGS,
                                  "DISPLAY_MODE": "800x600@60.317001", "DISPLAY_OUTPUT": "HDMI-A-1"})
        with patch.object(display, "wayland_available", return_value=False), \
             patch.object(display, "query_outputs") as query:
            assert not display.apply_saved(directory, {})
        query.assert_not_called()


def test_wayland_socket_detection_requires_owned_socket():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "wayland-0"
        path.touch()
        with patch.object(Path, "is_socket", lambda candidate: candidate == path):
            assert display.wayland_available({"XDG_RUNTIME_DIR": directory,
                                              "WAYLAND_DISPLAY": "wayland-0"})
            assert not display.wayland_available({"XDG_RUNTIME_DIR": directory,
                                                  "WAYLAND_DISPLAY": "wayland-1"})


def test_install_and_check_reference_helper_and_ordered_autostart():
    root = Path(__file__).resolve().parents[2]
    install = (root / "lite/Install-Lite.sh").read_text()
    check = (root / "lite/Check-Lite.sh").read_text()
    assert 'install -o root -g root -m 0755 "$SOURCE_DIR/lite/v_link_lite_display.py"' in install
    assert install.index("v_link_lite_display.py apply") < install.index("v-link-lite-boot; then")
    assert "Lite display helper is installed root:root 0755" in check
    assert "labwc applies the Lite display policy before the boot gate" in check
