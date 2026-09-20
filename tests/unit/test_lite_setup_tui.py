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
    def __init__(self, keys):
        self.keys = iter(keys)
        self.draws = 0

    def bkgd(self, *_args):
        pass

    def keypad(self, *_args):
        pass

    def getmaxyx(self):
        return 24, 80

    def erase(self):
        self.draws += 1

    def addnstr(self, *_args):
        pass

    def noutrefresh(self):
        pass

    def touchwin(self):
        pass

    def getch(self):
        return next(self.keys)


def make_ui(keys, startup=False):
    screen = FakeScreen(keys)
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


def test_volume_typing_replaces_initial_value():
    ui, _ = make_ui([ord("5"), ord("0"), 10])
    with patch.object(curses, "doupdate"):
        assert ui.input_number("Volume", "75") == 50


def test_startup_service_menu_does_not_offer_start_or_restart():
    ui, _ = make_ui([], startup=True)
    seen = []

    def choose(_heading, items):
        seen.extend(tag for tag, _label in items)
        return "back"

    ui.choose = choose
    ui.service_state = lambda *_args, **_kwargs: "inactive"
    ui.vlink_menu()
    assert seen == ["status", "logs", "back"]


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
