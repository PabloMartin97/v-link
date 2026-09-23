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
    def __init__(self, keys, height=24, width=80, sizes=None):
        self.keys = iter(keys)
        self.draws = 0
        self.height = height
        self.width = width
        self.sizes = sizes or []
        self.writes = []
        self.frames = []

    def bkgd(self, *_args):
        pass

    def keypad(self, *_args):
        pass

    def getmaxyx(self):
        if self.sizes:
            index = min(max(0, self.draws - 1), len(self.sizes) - 1)
            self.height, self.width = self.sizes[index]
        return self.height, self.width

    def erase(self):
        self.draws += 1
        self.frames.append([])

    def addnstr(self, *args):
        self.writes.append(args)
        if self.frames:
            self.frames[-1].append(args)

    def noutrefresh(self):
        pass

    def touchwin(self):
        pass

    def timeout(self, *_args):
        pass

    def getch(self):
        return next(self.keys)


def make_ui(keys, startup=False, height=24, width=80, sizes=None):
    screen = FakeScreen(keys, height, width, sizes)
    with patch.object(curses, "has_colors", return_value=False), \
         patch.object(curses, "curs_set"), \
         patch.object(curses, "doupdate"):
        ui = SETUP.SetupUI(screen, startup, 1000, "tester", {})
    return ui, screen


def drawn_values(frame):
    return [str(write[2]).rstrip() for write in frame]


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
        assert ui.choose("Menu", items) == "13"
        assert ui.choose("Menu", items) == "13"
        assert ui.choose("Menu", items) == "29"


def test_short_menu_viewport_stays_fixed_while_selection_moves():
    items = [(str(index), f"Choice {index}") for index in range(4)]
    ui, screen = make_ui([curses.KEY_DOWN] * 3 + [27])
    with patch.object(curses, "doupdate"):
        assert ui.choose("Short menu", items) is None
    for frame in screen.frames:
        values = drawn_values(frame)
        assert all(f"Choice {index}" in " ".join(values) for index in range(4))


def test_long_menu_moves_only_after_selection_crosses_viewport_edges():
    items = [(str(index), f"Choice {index}") for index in range(20)]
    keys = [curses.KEY_DOWN] * 14 + [curses.KEY_UP] * 13 + [27]
    ui, screen = make_ui(keys)
    with patch.object(curses, "doupdate"):
        assert ui.choose("Long menu", items) is None

    # With 13 visible rows, selections 0..12 leave the first item fixed.
    assert all(any(value.startswith(("> ", "  ")) and "Choice 0" in value
                   for value in drawn_values(frame))
               for frame in screen.frames[:13])
    # Selecting item 13 moves only one row; item 1 becomes the first option.
    option_values = [value for value in drawn_values(screen.frames[13])
                     if value.startswith(("> ", "  "))]
    assert option_values[0][2:].strip() == "Choice 1"
    # Scrolling back does not move until the selection crosses the top edge.
    option_values = [value for value in drawn_values(screen.frames[-2])
                     if value.startswith(("> ", "  "))]
    assert option_values[0][2:].strip() == "Choice 2"
    option_values = [value for value in drawn_values(screen.frames[-1])
                     if value.startswith(("> ", "  "))]
    assert option_values[0][2:].strip() == "Choice 1"


def test_menu_page_navigation_uses_rows_left_after_summary():
    items = [(str(index), f"Choice {index}") for index in range(30)]
    summary = [f"Summary {index}" for index in range(5)]
    ui, _ = make_ui([curses.KEY_NPAGE, 10, curses.KEY_PPAGE, 10])
    with patch.object(curses, "doupdate"):
        # A 22-row panel has 7 item rows after a five-line summary.
        assert ui.choose("Summary menu", items, summary) == "7"
        assert ui.choose("Summary menu", items, summary) == "0"


def test_menu_resize_keeps_selection_inside_recalculated_viewport():
    items = [(str(index), f"Choice {index}") for index in range(20)]
    sizes = [(24, 80)] * 12 + [(18, 60)]
    ui, screen = make_ui([curses.KEY_DOWN] * 12 + [27], sizes=sizes)
    with patch.object(curses, "doupdate"):
        assert ui.choose("Resize menu", items) is None
    option_values = [value for value in drawn_values(screen.frames[-1])
                     if value.startswith(("> ", "  "))]
    assert option_values[0][2:].strip() == "Choice 6"
    assert any(value.startswith("> ") and value[2:].strip() == "Choice 12"
               for value in option_values)


def test_short_view_cannot_scroll_into_empty_rows():
    ui, screen = make_ui([curses.KEY_DOWN, curses.KEY_NPAGE, 27])
    with patch.object(curses, "doupdate"):
        ui.view("Short view", "one\ntwo\nthree")
    assert all("Line 1/3" in drawn_values(frame) for frame in screen.frames)


def test_long_view_stops_with_a_full_last_page():
    lines = [f"Line content {index}" for index in range(20)]
    ui, screen = make_ui([curses.KEY_NPAGE, curses.KEY_NPAGE, curses.KEY_DOWN, 27])
    with patch.object(curses, "doupdate"):
        ui.view("Long view", "\n".join(lines))
    values = drawn_values(screen.frames[-1])
    assert "Line 8/20" in values
    assert "Line content 7" in values
    assert "Line content 19" in values


def test_view_page_navigation_uses_real_visible_rows():
    lines = [f"Line content {index}" for index in range(20)]
    ui, screen = make_ui([curses.KEY_NPAGE, curses.KEY_PPAGE, 27], height=18)
    with patch.object(curses, "doupdate"):
        ui.view("Paged view", "\n".join(lines))
    assert "Line 8/20" in drawn_values(screen.frames[1])
    assert "Line 1/20" in drawn_values(screen.frames[-1])


def test_view_horizontal_scroll_is_bounded_by_content_width():
    ui, short_screen = make_ui([curses.KEY_RIGHT] * 3 + [curses.KEY_LEFT, 27], width=80)
    with patch.object(curses, "doupdate"):
        ui.view("Short line", "fits")
    assert "fits" in drawn_values(short_screen.frames[-1])

    long_line = "0123456789" * 8
    ui, long_screen = make_ui([curses.KEY_RIGHT] * 5 + [27], width=80)
    with patch.object(curses, "doupdate"):
        ui.view("Long line", long_line)
    # Panel width is 78, so 69 characters fit and max_left is 11.
    assert long_line[11:] in drawn_values(long_screen.frames[-1])


def test_resize_clamps_view_offsets_to_new_viewport():
    lines = [f"{index:02d}-" + "x" * 57 for index in range(20)]
    sizes = [(18, 50), (18, 50), (24, 80)]
    keys = [curses.KEY_NPAGE, curses.KEY_RIGHT, 27]
    ui, screen = make_ui(keys, sizes=sizes)
    with patch.object(curses, "doupdate"):
        ui.view("Resize view", "\n".join(lines))
    # Growing from 7 to 13 visible rows reduces max_top from 13 to 7, while
    # the wider panel makes the longest line fit and clamps left back to zero.
    values = drawn_values(screen.frames[-1])
    assert "Line 8/20" in values
    assert lines[7] in values


def test_graphical_setup_launchers_use_larger_font_without_changing_boot_gate():
    root = SCRIPT.parents[1]
    gate = (root / "lite/V-Link-Lite-Boot.sh").read_text(encoding="utf-8")
    overlay = (root / "lite/V-Link-Lite-Overlay.py").read_text(encoding="utf-8")
    assert gate.count("--font=monospace:size=16") == 1
    assert '"--font=monospace:size=16"' in overlay
    assert "foot --fullscreen --title='V-Link Lite Boot'" in gate


def test_mouse_toggle_applies_immediately_in_running_lite_session():
    ui, _ = make_ui([])
    settings = {"CURSOR_MODE": "visible", "MOUSE_ENABLED": "yes"}
    choices = iter(("mouse", "back"))
    summaries = []
    commands = []
    messages = []
    ui.choose = lambda _heading, _items, summary: (summaries.append(summary), next(choices))[1]
    ui.display_available = lambda: True
    ui.command = lambda args, timeout: (commands.append((args, timeout)), (0, ""))[1]
    ui.message = messages.append
    with patch.object(SETUP, "load_settings", side_effect=lambda _home: settings.copy()), \
         patch.object(SETUP, "save_settings", side_effect=lambda _home, value: settings.update(value)):
        ui.cursor_menu()
    assert settings["MOUSE_ENABLED"] == "no"
    assert commands == [(["/usr/local/bin/v-link-lite-cursor", "apply"], 12)]
    assert "Cursor mode: Hidden (mouse deactivated)" in summaries[-1]
    assert messages == ["Preference saved and applied."]


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
