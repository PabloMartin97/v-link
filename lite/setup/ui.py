"""Shared curses infrastructure for V-Link Lite Setup."""

import curses
import stat
import subprocess
import textwrap
from pathlib import Path

TITLE = "V-Link Lite Setup"


def is_socket(path):
    try:
        return stat.S_ISSOCK(path.stat().st_mode)
    except OSError:
        return False

class BaseUI:
    def __init__(self, screen, startup, uid, username, env):
        self.screen = screen
        self.startup = startup
        self.uid = uid
        self.username = username
        self.env = env
        self.home = Path(env.get("HOME") or Path.home())
        self.menu_positions = {}
        self.panel_top = 0
        self.panel_left = 0
        self.panel_height = 0
        self.panel_width = 0
        self.normal = curses.A_NORMAL
        self.selected = curses.A_REVERSE | curses.A_BOLD
        if curses.has_colors():
            try:
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
                curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
                self.normal = curses.color_pair(1)
                self.selected = curses.color_pair(2) | curses.A_BOLD
            except curses.error:
                pass
        self.screen.bkgd(" ", curses.A_NORMAL)
        self.screen.keypad(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass

    def put(self, row, col, value, attribute=None):
        if not (0 <= row < self.panel_height and 0 <= col < self.panel_width - 1):
            return
        try:
            self.screen.addnstr(self.panel_top + row, self.panel_left + col,
                                  str(value), self.panel_width - col - 1,
                                  self.normal if attribute is None else attribute)
        except curses.error:
            pass

    def size(self):
        return self.panel_height, self.panel_width

    def frame(self, heading, footer="Arrows: move   Space/Enter: select   Esc: back"):
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        if height < 14 or width < 48:
            self.screen.addnstr(0, 0, "Resize terminal to at least 48x14 (Esc exits).",
                                max(0, width - 1))
            self.screen.noutrefresh()
            curses.doupdate()
            return False
        self.panel_height = min(height - 2, 28)
        self.panel_width = min(width - 2, 84)
        self.panel_top = (height - self.panel_height) // 2
        self.panel_left = (width - self.panel_width) // 2
        panel_height, panel_width = self.size()
        for row in range(panel_height):
            self.put(row, 0, " " * (panel_width - 1))
        self.put(1, max(2, (panel_width - len(TITLE)) // 2), TITLE,
                 self.normal | curses.A_BOLD)
        self.put(2, 2, "-" * (panel_width - 5))
        self.put(4, 4, heading, self.normal | curses.A_BOLD)
        self.put(panel_height - 2, 2, footer)
        return True

    def flush(self):
        self.screen.noutrefresh()
        curses.doupdate()

    def choose(self, heading, items, summary=None):
        """One curses session across all menus; no terminal teardown."""
        selected = min(self.menu_positions.get(heading, 0), len(items) - 1)
        first = 0
        visible = 1
        while True:
            if self.frame(heading):
                height, width = self.size()
                summary_lines = (summary or [])[:max(0, min(5, height - 11))]
                for row, line in enumerate(summary_lines):
                    self.put(6 + row, 5, line)
                start = 7 + len(summary_lines) if summary_lines else 6
                visible = max(1, height - start - 3)
                selected = min(max(0, selected), len(items) - 1)
                first = min(max(0, first), max(0, len(items) - visible))
                if selected < first:
                    first = selected
                elif selected >= first + visible:
                    first = selected - visible + 1
                for offset, (_, label) in enumerate(items[first:first + visible]):
                    index = first + offset
                    prefix = "> " if index == selected else "  "
                    self.put(start + offset, 5, (prefix + label).ljust(width - 11),
                             self.selected if index == selected else self.normal)
                if len(items) > visible:
                    self.put(height - 3, 5, f"{selected + 1}/{len(items)}")
            self.flush()
            key = self.screen.getch()
            if key in (27, curses.KEY_BACKSPACE, 127, 8):
                return None
            if key in (curses.KEY_UP, ord("k")):
                selected = max(0, selected - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                selected = min(len(items) - 1, selected + 1)
            elif key == curses.KEY_HOME:
                selected = 0
            elif key == curses.KEY_END:
                selected = len(items) - 1
            elif key == curses.KEY_PPAGE:
                selected = max(0, selected - visible)
            elif key == curses.KEY_NPAGE:
                selected = min(len(items) - 1, selected + visible)
            elif key in (ord(" "), 10, 13, curses.KEY_ENTER, curses.KEY_RIGHT):
                self.menu_positions[heading] = selected
                return items[selected][0]
            self.menu_positions[heading] = selected

    def busy(self, action):
        if self.frame(action, "Please wait..."):
            self.put(7, 6, "Working...")
        self.flush()

    def view(self, heading, content):
        lines = str(content).splitlines() or ["(no information)"]
        top = 0
        left = 0
        visible = 1
        max_top = 0
        max_left = 0
        while True:
            if self.frame(heading, "Up/Down: scroll   PgUp/PgDn: page   Esc/Enter: back"):
                height, width = self.size()
                visible = max(1, height - 9)
                content_width = max(1, width - 9)
                max_top = max(0, len(lines) - visible)
                max_left = max(0, max(map(len, lines)) - content_width)
                top = min(max(0, top), max_top)
                left = min(max(0, left), max_left)
                for offset, line in enumerate(lines[top:top + visible]):
                    self.put(6 + offset, 4, line[left:left + content_width])
                self.put(height - 3, 4, f"Line {top + 1}/{len(lines)}")
            self.flush()
            key = self.screen.getch()
            if key in (27, ord(" "), 10, 13, curses.KEY_ENTER, curses.KEY_BACKSPACE, 127):
                return
            if key == curses.KEY_UP:
                top = max(0, top - 1)
            elif key == curses.KEY_DOWN:
                top = min(max_top, top + 1)
            elif key == curses.KEY_PPAGE:
                top = max(0, top - visible)
            elif key == curses.KEY_NPAGE:
                top = min(max_top, top + visible)
            elif key == curses.KEY_LEFT:
                left = max(0, left - 8)
            elif key == curses.KEY_RIGHT:
                left = min(max_left, left + 8)

    def message(self, message):
        wrapped = textwrap.wrap(str(message), width=max(30, self.panel_width - 12))
        self.view(TITLE, "\n".join(wrapped))

    def input_number(self, heading, initial="75"):
        value = initial
        fresh = True
        while True:
            if self.frame(heading, "Arrows: +/- 5   Space/Enter: save   Esc: cancel"):
                self.put(7, 6, f"Volume: {value}%")
            self.flush()
            key = self.screen.getch()
            if key == 27:
                return None
            if key in (ord(" "), 10, 13, curses.KEY_ENTER):
                if value.isdigit() and 0 <= int(value) <= 100:
                    return int(value)
                self.message("Enter a whole number from 0 to 100.")
            elif key in (curses.KEY_LEFT, curses.KEY_DOWN,
                         curses.KEY_RIGHT, curses.KEY_UP):
                current = int(value) if value.isdigit() and 0 <= int(value) <= 100 else 75
                step = -5 if key in (curses.KEY_LEFT, curses.KEY_DOWN) else 5
                value = str(min(100, max(0, current + step)))
                fresh = True
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                value = value[:-1]
                fresh = False
            elif ord("0") <= key <= ord("9") and len(value) < 3:
                if fresh:
                    value = ""
                value += chr(key)
                fresh = False

    def command(self, args, timeout=5):
        try:
            result = subprocess.run(args, capture_output=True, text=True,
                                    timeout=timeout, env=self.env, check=False)
            return result.returncode, (result.stdout + result.stderr).strip()
        except FileNotFoundError:
            return 127, f"{args[0]} is unavailable."
        except subprocess.TimeoutExpired:
            return 124, "Operation timed out."
        except OSError as error:
            return 1, str(error)

    def service_state(self, name, user=False):
        args = ["systemctl"] + (["--user"] if user else []) + ["is-active", name]
        _, output = self.command(args, timeout=2)
        state = output.splitlines()[0] if output else ""
        return state if state in {"active", "inactive", "failed", "activating",
                                  "deactivating", "reloading"} else "unavailable"
