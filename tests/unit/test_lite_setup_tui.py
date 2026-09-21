"""Host-side checks for the persistent Lite maintenance UI."""

import curses
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "lite/V-Link-Lite-Setup.py"
SPEC = importlib.util.spec_from_file_location("v_link_lite_setup", SCRIPT)
SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETUP)


class FakeScreen:
    def __init__(self, keys, height=24, width=80):
        self.keys = iter(keys)
        self.draws = 0
        self.height = height
        self.width = width
        self.writes = []

    def bkgd(self, *_args):
        pass

    def keypad(self, *_args):
        pass

    def getmaxyx(self):
        return self.height, self.width

    def erase(self):
        self.draws += 1

    def addnstr(self, *args):
        self.writes.append(args)

    def noutrefresh(self):
        pass

    def touchwin(self):
        pass

    def timeout(self, *_args):
        pass

    def getch(self):
        return next(self.keys)


def make_ui(keys, startup=False, height=24, width=80):
    screen = FakeScreen(keys, height, width)
    with patch.object(curses, "has_colors", return_value=False), \
         patch.object(curses, "curs_set"), \
         patch.object(curses, "doupdate"):
        ui = SETUP.SetupUI(screen, startup, 1000, "tester", {})
    return ui, screen


def test_audio_node_names_and_types():
    payload = json.dumps([
        {"id": 42, "info": {"props": {"media.class": "Audio/Sink",
                                       "node.description": "USB Audio Device",
                                       "node.name": "alsa_output.usb-123"}}},
        {"id": 43, "info": {"props": {"media.class": "Audio/Source",
                                       "node.nick": "Microphone"}}},
    ])
    assert SETUP.parse_audio_nodes(payload, "Audio/Sink") == [(42, "USB Audio Device")]
    assert SETUP.parse_audio_nodes(payload, "Audio/Source") == [(43, "Microphone")]


def test_menu_redraws_in_one_curses_session():
    ui, screen = make_ui([curses.KEY_DOWN, 10])
    with patch.object(curses, "doupdate"), patch.object(curses, "endwin") as endwin:
        choice = ui.choose("Menu", [("one", "One"), ("two", "Two")])
    assert choice == "two"
    assert screen.draws == 2
    endwin.assert_not_called()


def test_setup_panel_is_centered_on_large_terminal():
    ui, screen = make_ui([27], height=40, width=120)
    with patch.object(curses, "doupdate"):
        assert ui.choose("Menu", [("one", "One")]) is None
    assert ui.size() == (28, 84)
    assert (ui.panel_top, ui.panel_left) == (6, 18)
    assert any(row == 7 and col > 18 and value == SETUP.TITLE
               for row, col, value, *_ in screen.writes)


def test_menu_remembers_selection_and_supports_page_navigation():
    ui, _ = make_ui([curses.KEY_NPAGE, 10, 10, curses.KEY_END, 10])
    items = [(str(index), f"Choice {index}") for index in range(30)]
    with patch.object(curses, "doupdate"):
        assert ui.choose("Menu", items) == "12"
        assert ui.choose("Menu", items) == "12"
        assert ui.choose("Menu", items) == "29"


def test_graphical_setup_launchers_use_larger_font_without_changing_boot_gate():
    root = SCRIPT.parents[1]
    gate = (root / "lite/V-Link-Lite-Boot.sh").read_text(encoding="utf-8")
    overlay = (root / "lite/V-Link-Lite-Overlay.py").read_text(encoding="utf-8")
    assert gate.count("--font=monospace:size=16") == 1
    assert '"--font=monospace:size=16"' in overlay
    assert "foot --fullscreen --title='V-Link Lite Boot'" in gate


def test_volume_typing_replaces_initial_value():
    ui, _ = make_ui([ord("5"), ord("0"), 10])
    with patch.object(curses, "doupdate"):
        assert ui.input_number("Volume", "75") == 50


def test_startup_service_menu_does_not_offer_start_or_restart():
    ui, _ = make_ui([], startup=True)
    seen = []

    def choose(_heading, items, **_kwargs):
        seen.extend(tag for tag, _label in items)
        return "back"

    ui.choose = choose
    ui.service_state = lambda *_args, **_kwargs: "inactive"
    ui.vlink_menu()
    assert seen == ["console", "logs", "status", "back"]


def test_power_command_uses_only_existing_limited_sudoers():
    ui, _ = make_ui([])
    ui.choose = lambda *_args: "yes"
    ui.busy = lambda *_args: None
    commands = []

    def command(args, _timeout):
        commands.append(args)
        return 0, ""

    ui.command = command
    assert ui.power_action("reboot") == 20
    assert ui.power_action("shutdown") == 21
    assert commands == [
        ["sudo", "-n", "/usr/sbin/reboot"],
        ["sudo", "-n", "/usr/sbin/shutdown", "-h", "now"],
    ]


def test_nmtui_failure_restores_persistent_screen():
    ui, _ = make_ui([])
    ui.busy = lambda *_args: None
    messages = []
    ui.message = messages.append
    with patch.object(curses, "def_prog_mode"), \
         patch.object(curses, "endwin"), \
         patch.object(curses, "reset_prog_mode") as restore, \
         patch.object(SETUP.subprocess, "run", side_effect=FileNotFoundError):
        ui.open_nmtui()
    restore.assert_called_once()
    assert messages == ["nmtui is unavailable."]


def test_console_only_reads_running_service_and_never_controls_it():
    ui, _ = make_ui([ord("q")])
    ui.service_state = lambda *_args, **_kwargs: "active"
    commands = []

    def command(args, _timeout):
        commands.append(args)
        return 0, "123"

    ui.command = command
    with patch.object(curses, "doupdate"), patch.object(SETUP, "read_snapshot", return_value={
        "version": "3.0", "device": "Pi 4", "rti": False, "ign": True,
        "threads": [["server", True]], "warnings": [],
    }):
        ui.console()
    assert commands == [["systemctl", "--user", "show", "v-link.service",
                         "-p", "MainPID", "--value"]]


def test_ssh_display_has_recoverable_unavailable_message():
    ui, _ = make_ui([])
    assert ui.display_status() == "Wayland display unavailable in this session."
