#!/usr/bin/env python3
"""Persistent, unprivileged maintenance screen for V-Link Lite."""

import curses
import fcntl
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v_link_lite_support import (load_settings, save_settings, system_details,
                                 format_size, read_snapshot)


TITLE = "V-Link Lite Setup"
AUDIO_SAMPLE = "/usr/share/sounds/alsa/Front_Center.wav"


def is_socket(path):
    try:
        return stat.S_ISSOCK(path.stat().st_mode)
    except OSError:
        return False


def runtime_directory(uid, home):
    """Use the private login runtime, or a private home directory for SSH."""
    candidate = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}")
    if not (candidate.is_dir() and candidate.stat().st_uid == uid
            and stat.S_IMODE(candidate.stat().st_mode) == 0o700):
        candidate = home / ".local/state/v-link-lite-setup"
        if candidate.is_symlink():
            raise RuntimeError("Unsafe Setup state directory.")
        candidate.mkdir(mode=0o700, parents=True, exist_ok=True)
        if candidate.stat().st_uid != uid:
            raise RuntimeError("Setup state directory is not owned by this user.")
        candidate.chmod(0o700)
    if stat.S_IMODE(candidate.stat().st_mode) != 0o700:
        raise RuntimeError("Setup runtime directory must be private to this user.")
    return candidate


def session_environment(uid):
    env = os.environ.copy()
    login_runtime = Path(f"/run/user/{uid}")
    if login_runtime.is_dir() and login_runtime.stat().st_uid == uid:
        env["XDG_RUNTIME_DIR"] = str(login_runtime)
        bus = login_runtime / "bus"
        if is_socket(bus):
            env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={bus}")
    return env


def parse_audio_nodes(payload, kind):
    """Return current PipeWire node IDs and their best available human labels."""
    nodes = []
    for obj in json.loads(payload):
        if not isinstance(obj, dict):
            continue
        props = (obj.get("info") or {}).get("props") or {}
        node_id = obj.get("id")
        if props.get("media.class") != kind or not isinstance(node_id, int):
            continue
        label = next((str(props[key]) for key in (
            "node.description", "node.nick", "device.description", "node.name"
        ) if props.get(key)), "Audio device")
        nodes.append((node_id, " ".join(label.split())))
    return nodes


class SetupUI:
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

    def frame(self, heading, footer="Arrows: move   Enter: select   Esc: back"):
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
        while True:
            if self.frame(heading):
                height, width = self.size()
                summary_lines = (summary or [])[:max(0, min(5, height - 11))]
                for row, line in enumerate(summary_lines):
                    self.put(6 + row, 5, line)
                start = 7 + len(summary_lines) if summary_lines else 6
                visible = max(1, height - start - 3)
                first = min(max(0, selected - visible // 2),
                            max(0, len(items) - visible))
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
                selected = max(0, selected - max(1, self.panel_height - 10))
            elif key == curses.KEY_NPAGE:
                selected = min(len(items) - 1, selected + max(1, self.panel_height - 10))
            elif key in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT):
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
        while True:
            if self.frame(heading, "Up/Down: scroll   PgUp/PgDn: page   Esc/Enter: back"):
                height, width = self.size()
                visible = max(1, height - 9)
                for offset, line in enumerate(lines[top:top + visible]):
                    self.put(6 + offset, 4, line[left:left + width - 9])
                self.put(height - 3, 4, f"Line {top + 1}/{len(lines)}")
            self.flush()
            key = self.screen.getch()
            if key in (27, 10, 13, curses.KEY_ENTER, curses.KEY_BACKSPACE, 127):
                return
            if key == curses.KEY_UP:
                top = max(0, top - 1)
            elif key == curses.KEY_DOWN:
                top = min(max(0, len(lines) - 1), top + 1)
            elif key == curses.KEY_PPAGE:
                top = max(0, top - 10)
            elif key == curses.KEY_NPAGE:
                top = min(max(0, len(lines) - 1), top + 10)
            elif key == curses.KEY_LEFT:
                left = max(0, left - 8)
            elif key == curses.KEY_RIGHT:
                left += 8

    def message(self, message):
        wrapped = textwrap.wrap(str(message), width=max(30, self.panel_width - 12))
        self.view(TITLE, "\n".join(wrapped))

    def input_number(self, heading, initial="75"):
        value = initial
        fresh = True
        while True:
            if self.frame(heading, "Digits: 0-100   Enter: save   Esc: cancel"):
                self.put(7, 6, f"Volume: {value}%")
            self.flush()
            key = self.screen.getch()
            if key == 27:
                return None
            if key in (10, 13, curses.KEY_ENTER):
                if value.isdigit() and 0 <= int(value) <= 100:
                    return int(value)
                self.message("Enter a whole number from 0 to 100.")
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

    def network_status(self):
        self.busy("Reading network status")
        _, devices = self.command(["nmcli", "-f", "DEVICE,TYPE,STATE,CONNECTION",
                                   "device", "status"], timeout=3)
        _, addresses = self.command(["ip", "-brief", "-4", "address", "show"], timeout=2)
        return f"NetworkManager devices:\n{devices}\n\nIPv4 addresses:\n{addresses}"

    def open_nmtui(self):
        self.busy("Opening Network configuration")
        curses.def_prog_mode()
        curses.endwin()
        try:
            result = subprocess.run(["nmtui"], env=self.env, check=False)
            error = "" if result.returncode == 0 else f"nmtui exited with status {result.returncode}."
        except FileNotFoundError:
            error = "nmtui is unavailable."
        except OSError as exc:
            error = str(exc)
        finally:
            curses.reset_prog_mode()
            self.screen.touchwin()
        if error:
            self.message(error)

    def network_menu(self):
        while True:
            self.busy("Reading network")
            code, raw = self.command(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION",
                                      "device", "status"], 3)
            summary = ["Ethernet: unavailable", "Wi-Fi: unavailable", "IP: unavailable"]
            if code == 0:
                connected_device = None
                for line in raw.splitlines():
                    parts = line.split(":", 3)
                    if len(parts) < 4:
                        continue
                    device, kind, state, connection = parts
                    if kind == "ethernet":
                        summary[0] = f"Ethernet: {state}"
                    elif kind == "wifi":
                        summary[1] = f"Wi-Fi: {state}"
                        if state == "connected":
                            _, wifi = self.command(["nmcli", "-t", "-f", "IN-USE,SSID",
                                                    "device", "wifi", "list", "--rescan", "no"], 2)
                            ssid = next((entry[2:] for entry in wifi.splitlines() if entry.startswith("*:")), "")
                            if ssid:
                                summary[1] += f"  SSID: {ssid}"
                    if state == "connected" and kind in ("ethernet", "wifi"):
                        connected_device = connected_device or device
                if connected_device:
                    _, ip = self.command(["nmcli", "-g", "IP4.ADDRESS", "device", "show", connected_device], 2)
                    summary[2] = f"IP: {ip.splitlines()[0] if ip else 'unavailable'}"
            choice = self.choose("Network", [
                ("configure", "Configure network"), ("details", "Technical details"),
                ("back", "Back")], summary=summary)
            if choice in (None, "back"):
                return
            if choice == "configure":
                self.open_nmtui()
            else:
                self.view("Network details", self.network_status())

    def audio_ready(self):
        bus = Path(f"/run/user/{self.uid}/bus")
        if not is_socket(bus):
            self.message("Audio session unavailable. A running user PipeWire session is required.")
            return False
        self.busy("Connecting to PipeWire")
        self.command(["systemctl", "--user", "start", "pipewire.service", "wireplumber.service"], 5)
        self.command(["systemctl", "--user", "start", "pipewire-pulse.service"], 5)
        status, _ = self.command(["wpctl", "status"], 3)
        if status:
            self.message("Audio session unavailable. Check PipeWire and WirePlumber.")
            return False
        return True

    def select_audio_device(self, kind):
        self.busy("Reading audio devices")
        status, payload = self.command(["pw-dump"], 4)
        if status:
            self.message(f"Unable to read PipeWire devices: {payload}")
            return
        try:
            nodes = parse_audio_nodes(payload, kind)
        except (TypeError, ValueError) as error:
            self.message(f"Unable to parse PipeWire devices: {error}")
            return
        if not nodes:
            self.message("No audio devices of this type are available.")
            return
        label = "Output device" if kind == "Audio/Sink" else "Input device"
        items = [(str(node_id), name) for node_id, name in nodes]
        items.append(("back", "Back"))
        choice = self.choose(label, items)
        if choice in (None, "back"):
            return
        self.busy("Changing default audio device")
        status, output = self.command(["wpctl", "set-default", choice], 4)
        self.message("Default audio device updated." if status == 0
                     else f"Could not change audio device: {output}")

    def set_volume(self, target, label):
        status, output = self.command(["wpctl", "get-volume", target], 3)
        match = re.search(r"Volume:\s*([0-9.]+)", output) if status == 0 else None
        initial = str(min(100, round(float(match.group(1)) * 100))) if match else "75"
        value = self.input_number(label, initial)
        if value is None:
            return
        self.busy("Setting volume")
        status, output = self.command(["wpctl", "set-volume", target, f"{value}%"], 4)
        self.message(f"Volume set to {value}%." if status == 0
                     else f"Could not change volume: {output}")

    def test_audio(self):
        if Path(AUDIO_SAMPLE).is_file() and shutil.which("pw-play"):
            args = ["pw-play", AUDIO_SAMPLE]
        else:
            args = ["speaker-test", "-c", "2", "-t", "sine", "-s", "1"]
        self.busy("Testing audio output")
        status, output = self.command(args, 6)
        self.message("Audio test completed." if status == 0
                     else f"Audio test failed: {output}")

    def audio_menu(self):
        if not self.audio_ready():
            return
        while True:
            _, sink = self.command(["wpctl", "inspect", "@DEFAULT_AUDIO_SINK@"], 3)
            _, source = self.command(["wpctl", "inspect", "@DEFAULT_AUDIO_SOURCE@"], 3)
            def label(payload):
                match = re.search(r'node.description = "([^"]+)"', payload)
                return match.group(1) if match else "not selected"
            _, output_volume = self.command(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], 2)
            _, input_volume = self.command(["wpctl", "get-volume", "@DEFAULT_AUDIO_SOURCE@"], 2)
            summary = [f"Output: {label(sink)}", f"Output volume: {output_volume or 'unavailable'}",
                       f"Input: {label(source)}", f"Input volume: {input_volume or 'unavailable'}"]
            choice = self.choose("Audio", [
                ("output", "Select output"), ("input", "Select input"),
                ("output_volume", "Output volume"), ("input_volume", "Input volume"),
                ("test", "Test speakers"), ("status", "Technical status"),
                ("back", "Back")], summary=summary)
            if choice in (None, "back"):
                return
            if choice == "output":
                self.select_audio_device("Audio/Sink")
            elif choice == "input":
                self.select_audio_device("Audio/Source")
            elif choice == "output_volume":
                self.set_volume("@DEFAULT_AUDIO_SINK@", "Output volume")
            elif choice == "input_volume":
                self.set_volume("@DEFAULT_AUDIO_SOURCE@", "Input volume")
            elif choice == "test":
                self.test_audio()
            elif choice == "status":
                self.busy("Reading PipeWire status")
                _, output = self.command(["wpctl", "status"], 3)
                self.view("PipeWire status", output)

    def display_status(self):
        display = self.env.get("WAYLAND_DISPLAY", "")
        path = Path(display) if display.startswith("/") else Path(self.env.get("XDG_RUNTIME_DIR", "/nonexistent")) / display
        if not display or not is_socket(path):
            return "Wayland display unavailable in this session."
        _, output = self.command(["wlr-randr"], 4)
        return output or "Could not query Wayland outputs."

    def display_menu(self):
        while True:
            raw = self.display_status()
            lines = raw.splitlines()
            active = next((line.strip() for line in lines if "(current)" in line), "unavailable")
            output = ("unavailable" if raw.startswith("Wayland display unavailable") else
                      next((line.split()[0] for line in lines if line and not line[0].isspace()), "unavailable"))
            choice = self.choose("Display / Input", [
                ("status", "Display status"), ("cursor", "Cursor and mouse"),
                ("details", "Technical details"), ("back", "Back")],
                summary=[f"Display: {output}", f"Mode: {active[:60]}"])
            if choice in (None, "back"):
                return
            if choice == "cursor":
                self.cursor_menu()
            elif choice == "details":
                self.view("Display details", raw)
            else:
                self.view("Display status", f"Display: {output}\nMode: {active}")

    def cursor_menu(self):
        while True:
            try:
                settings = load_settings(self.home)
            except ValueError as error:
                self.message(f"Invalid Lite settings: {error}")
                return
            mode = settings["CURSOR_MODE"].title()
            mouse = "Activated" if settings["MOUSE_ENABLED"] == "yes" else "Deactivated"
            choice = self.choose("Cursor and mouse", [
                ("auto", "Cursor: Auto"), ("visible", "Cursor: Visible"),
                ("mouse", "Toggle mouse activated / deactivated"),
                ("test", "Hide cursor now (test)"), ("back", "Back")],
                summary=[f"Cursor mode: {mode}", f"Mouse: {mouse}",
                         "Mouse off also hides the pointer, regardless of cursor mode.",
                         "Changes to mouse input take effect at next boot."])
            if choice in (None, "back"):
                return
            if choice in ("auto", "visible", "mouse"):
                if choice == "mouse":
                    settings["MOUSE_ENABLED"] = "no" if settings["MOUSE_ENABLED"] == "yes" else "yes"
                else:
                    settings["CURSOR_MODE"] = choice
                try:
                    save_settings(self.home, settings)
                    status, output = self.command(["/usr/local/bin/v-link-lite-cursor", "sync-config"], 3)
                    if status == 0:
                        self.message("Preference saved. It applies after Continue or the next graphical boot.")
                    else:
                        self.message(f"Preference saved, but labwc configuration failed: {output}")
                except (OSError, ValueError) as error:
                    self.message(f"Could not save preference: {error}")
            elif choice == "test":
                if not self.display_available():
                    self.message("Wayland display unavailable in this session.")
                else:
                    status, output = self.command(["/usr/local/bin/v-link-lite-cursor", "hide"], 3)
                    self.message("Cursor hidden. Press Esc to return; enabled mouse movement restores it."
                                 if status == 0 else f"Cursor test failed: {output}")

    def storage_status(self):
        _, devices = self.command(["lsblk", "-o", "NAME,LABEL,FSTYPE,SIZE,TRAN,MOUNTPOINT"], 4)
        udisks = self.service_state("udisks2.service")
        udiskie, _ = self.command(["pgrep", "-u", str(self.uid), "-x", "udiskie"], 2)
        return (f"Storage devices and mounts:\n{devices}\n\n"
                f"udisks2: {udisks}\nudiskie: {'running' if udiskie == 0 else 'not running'}")

    def storage_menu(self):
        while True:
            code, output = self.command(["lsblk", "-J", "-o",
                                          "NAME,LABEL,FSTYPE,SIZE,TRAN,MOUNTPOINT,RM,TYPE"], 4)
            devices = []
            if code == 0:
                try:
                    def collect(node, usb=False):
                        usb = usb or node.get("tran") == "usb"
                        if usb and (node.get("type") == "part" or
                                    (node.get("type") == "disk" and not node.get("children"))):
                            devices.append(f"{node.get('label') or node.get('name')}: {node.get('size')}  "
                                           f"{node.get('fstype') or 'unknown'}  "
                                           f"{'Mounted' if node.get('mountpoint') else 'Not mounted'}")
                        for child in node.get("children") or []:
                            collect(child, usb)
                    for device in json.loads(output).get("blockdevices", []):
                        collect(device)
                except (TypeError, ValueError, AttributeError):
                    pass
            udiskie, _ = self.command(["pgrep", "-u", str(self.uid), "-x", "udiskie"], 2)
            choice = self.choose("Storage / USB", [
                ("refresh", "Refresh"), ("details", "Technical details"), ("back", "Back")],
                summary=(devices[:3] or ["No removable USB volumes found."]) +
                        [f"Automount: {'OK' if udiskie == 0 else 'unavailable'}"])
            if choice in (None, "back"):
                return
            if choice == "details":
                self.view("Storage details", self.storage_status())

    def vlink_menu(self):
        while True:
            state = self.service_state("v-link.service", user=True)
            _, start_us = self.command(["systemctl", "--user", "show", "v-link.service",
                                        "-p", "ActiveEnterTimestampMonotonic", "--value"], 2)
            try:
                uptime = f"{max(0, int(time.monotonic() - int(start_us) / 1000000)) // 60} min" if state == "active" else "-"
            except ValueError:
                uptime = "unavailable"
            _, service = self.command(["systemctl", "--user", "show", "v-link.service",
                                       "-p", "ExecStart", "--value"], 2)
            mode = "UI only" if "--no-hardware" in service else "Hardware"
            summary = [f"Status: {state}", f"Uptime: {uptime}", f"Mode: {mode}",
                       f"Console: {'Available' if state == 'active' else 'Not running'}"]
            if self.startup:
                items = [("console", "Console"), ("logs", "Logs"),
                         ("status", "Technical status"), ("back", "Back")]
                heading = "V-Link starts after Continue"
            else:
                items = [("console", "Console"), ("restart", "Restart V-Link"),
                         ("stop", "Stop V-Link"), ("start", "Start V-Link"),
                         ("logs", "Logs"), ("status", "Technical status"),
                         ("back", "Back")]
                heading = "V-Link"
            choice = self.choose(heading, items, summary=summary)
            if choice in (None, "back"):
                return
            if choice in ("start", "stop", "restart"):
                self.busy(f"V-Link {choice}")
                status, output = self.command(["systemctl", "--user", choice, "v-link.service"], 10)
                self.message(f"V-Link {choice} completed." if status == 0
                             else f"V-Link {choice} failed: {output}")
            elif choice == "status":
                self.busy("Reading V-Link status")
                _, output = self.command(["systemctl", "--user", "status",
                                          "v-link.service", "--no-pager"], 4)
                self.view("V-Link service", output)
            elif choice == "console":
                self.console()
            elif choice == "logs":
                self.busy("Reading V-Link logs")
                _, output = self.command(["journalctl", "--user", "-u", "v-link.service",
                                          "-n", "80", "--no-pager"], 5)
                self.view("V-Link recent log", output)

    def console(self):
        """Read a runtime snapshot; never attach to or control the V-Link PID."""
        self.screen.timeout(1000)
        try:
            while True:
                state = self.service_state("v-link.service", user=True)
                _, pid_text = self.command(["systemctl", "--user", "show", "v-link.service",
                                            "-p", "MainPID", "--value"], 2)
                try:
                    pid = int(pid_text)
                except ValueError:
                    pid = 0
                snapshot = read_snapshot(self.uid, pid) if state == "active" and pid else None
                if self.frame("V-Link Console", "Q / Esc: Back   (updates every second)"):
                    if state != "active":
                        self.put(7, 5, "V-Link is not running.")
                    elif not snapshot:
                        self.put(7, 5, "Status unavailable.")
                    else:
                        lines = [f"V-Link {snapshot.get('version', '?')} | Boosted Moose",
                                 f"Device: {snapshot.get('device', 'unavailable')}",
                                 f"RTI: {'Up' if snapshot.get('rti') else 'Down'}   "
                                 f"IGN: {'High' if snapshot.get('ign') else 'Low'}", "",
                                 "Thread          Status"]
                        for name, running in snapshot.get("threads", []):
                            lines.append(f"{str(name).upper():<15} {'running' if running else 'stopped'}")
                        lines += ["", "Recent warnings"]
                        lines += snapshot.get("warnings", []) or ["No recent warnings."]
                        height, _ = self.size()
                        for row, line in enumerate(lines[:max(0, height - 9)]):
                            self.put(6 + row, 5, line)
                self.flush()
                if self.screen.getch() in (27, ord("q"), ord("Q")):
                    return
        finally:
            self.screen.timeout(-1)

    def diagnostics(self):
        self.busy("Running quick diagnostics")
        internet, _ = self.command(["curl", "--head", "--silent", "--fail",
                                    "--output", "/dev/null", "--connect-timeout", "2",
                                    "--max-time", "3", "https://www.debian.org/"], 4)
        chromium, _ = self.command(["pgrep", "-u", str(self.uid), "-x", "chromium"], 2)
        udiskie, _ = self.command(["pgrep", "-u", str(self.uid), "-x", "udiskie"], 2)
        _, mounts = self.command(["findmnt", "-rn", "-o", "TARGET"], 3)
        media_count = sum(path.startswith((f"/run/media/{self.username}/",
                                           f"/media/{self.username}/"))
                          for path in mounts.splitlines())
        _, ip_address = self.command(["ip", "-o", "-4", "address", "show", "scope", "global"], 2)
        addresses = ", ".join(line.split()[3] for line in ip_address.splitlines()
                              if len(line.split()) > 3) or "unavailable"
        _, uptime = self.command(["uptime", "-p"], 2)
        return "\n".join([
            f"NetworkManager: {self.service_state('NetworkManager.service')}",
            f"Internet: {'OK' if internet == 0 else 'unavailable'}",
            f"PipeWire: {self.service_state('pipewire.service', user=True)}",
            f"WirePlumber: {self.service_state('wireplumber.service', user=True)}",
            f"Wayland: {'OK' if self.display_available() else 'unavailable'}",
            f"V-Link service: {self.service_state('v-link.service', user=True)}",
            f"Chromium: {'running' if chromium == 0 else 'not running'}",
            f"udisks2: {self.service_state('udisks2.service')}",
            f"udiskie: {'running' if udiskie == 0 else 'not running'}",
            f"Local media mounts: {media_count}",
            f"IP address: {addresses}",
            f"Uptime: {uptime or 'unavailable'}",
        ])

    def diagnostics_menu(self):
        while True:
            self.busy("Reading system diagnostics")
            data = system_details(self.command)
            power = data["power"]
            if power is None or power["unknown_bits"]:
                throttle = "unavailable"
            else:
                throttle = "ACTIVE" if power["throttled_now"] or power["frequency_capped_now"] else "OK"
            total = data["ram_total"]
            used = data["ram_used"]
            disk_total = data["disk_total"]
            disk_used = data["disk_used"]
            summary = [
                f"CPU: {data['cpu']} %" if data["cpu"] is not None else "CPU: unavailable",
                f"Temperature: {data['temperature']:.1f} °C" if data["temperature"] is not None else "Temperature: unavailable",
                f"RAM: {round(100 * used / total)} %" if total and used is not None else "RAM: unavailable",
                f"Root disk: {round(100 * disk_used / disk_total)} %" if disk_total else "Root disk: unavailable",
                f"Throttling: {throttle}   Undervoltage: " +
                ("unavailable" if power is None or power["unknown_bits"] else
                 "ACTIVE" if power["undervoltage_now"] else "No"),
            ]
            choice = self.choose("Diagnostics", [
                ("system", "System details"), ("network", "Network details"),
                ("audio", "Audio details"), ("storage", "Storage details"),
                ("vlink", "V-Link details"), ("back", "Back")], summary=summary)
            if choice in (None, "back"):
                return
            if choice == "system":
                self.view("System details", self.format_system_details(data))
            elif choice == "network":
                self.view("Network details", self.network_status())
            elif choice == "audio":
                _, output = self.command(["wpctl", "status"], 3)
                self.view("Audio details", output)
            elif choice == "storage":
                self.view("Storage details", self.storage_status())
            else:
                self.view("V-Link details", self.diagnostics())

    @staticmethod
    def format_system_details(data):
        power = data["power"]
        def yes_no(value):
            return "Yes" if value else "No"
        def ratio(used, total):
            return (f"{format_size(used)} / {format_size(total)} "
                    f"({round(100 * used / total)} %)") if used is not None and total else "unavailable"
        lines = [
            f"Model: {data['model']}", f"CPU cores: {data['cores']}",
            f"CPU usage: {data['cpu']} %" if data["cpu"] is not None else "CPU usage: unavailable",
            f"Load: {data['load']}",
            f"Temperature: {data['temperature']:.1f} °C" if data["temperature"] is not None else "Temperature: unavailable",
            f"RAM used / total: {ratio(data['ram_used'], data['ram_total'])}",
            f"RAM available: {format_size(data['ram_available'])}",
            f"Root used / total: {ratio(data['disk_used'], data['disk_total'])}",
            f"Uptime: {data['uptime'] // 60} min" if data["uptime"] is not None else "Uptime: unavailable",
        ]
        if power is None or power["unknown_bits"]:
            lines.append("Power/throttling: unavailable")
        else:
            lines.extend([
                f"Current throttling: {yes_no(power['throttled_now'])}",
                f"Current undervoltage: {yes_no(power['undervoltage_now'])}",
                f"Throttling since boot: {yes_no(power['throttled_seen'])}",
                f"Undervoltage since boot: {yes_no(power['undervoltage_seen'])}",
                f"Frequency capped now/since boot: {yes_no(power['frequency_capped_now'])} / {yes_no(power['frequency_capped_seen'])}",
                f"Soft temp limit now/since boot: {yes_no(power['soft_temp_now'])} / {yes_no(power['soft_temp_seen'])}",
                f"Technical power value: {power['raw']}",
            ])
        return "\n".join(lines)

    def display_available(self):
        display = self.env.get("WAYLAND_DISPLAY", "")
        path = Path(display) if display.startswith("/") else Path(self.env.get("XDG_RUNTIME_DIR", "/nonexistent")) / display
        return bool(display and is_socket(path))

    def power_action(self, action):
        choice = self.choose(f"Confirm {action}?", [("no", "Cancel"), ("yes", f"Yes, {action}")])
        if choice != "yes":
            return None
        self.busy(f"Requesting {action}")
        args = ["sudo", "-n", "/usr/sbin/reboot"] if action == "reboot" else [
            "sudo", "-n", "/usr/sbin/shutdown", "-h", "now"]
        status, output = self.command(args, 5)
        if status == 0:
            return 20 if action == "reboot" else 21
        self.message(f"Could not {action}: {output}")
        return None

    def main_menu(self):
        items = [("network", "Network"), ("audio", "Audio"),
                 ("display", "Display / Input"), ("storage", "Storage / USB"),
                 ("vlink", "V-Link"), ("diagnostics", "Diagnostics"),
                 ("continue", "Continue to V-Link / Exit Setup"),
                 ("reboot", "Reboot"), ("shutdown", "Shutdown")]
        while True:
            choice = self.choose("Choose a maintenance task", items)
            if choice in (None, "continue"):
                return 0
            if choice == "network":
                self.network_menu()
            elif choice == "audio":
                self.audio_menu()
            elif choice == "display":
                self.display_menu()
            elif choice == "storage":
                self.storage_menu()
            elif choice == "vlink":
                self.vlink_menu()
            elif choice == "diagnostics":
                self.diagnostics_menu()
            elif choice in ("reboot", "shutdown"):
                result = self.power_action(choice)
                if result is not None:
                    return result


def main(argv):
    if len(argv) > 1 or (argv and argv[0] != "--startup"):
        print("Usage: v-link-lite-setup [--startup]", file=sys.stderr)
        return 2
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("V-Link Lite Setup requires an interactive terminal.", file=sys.stderr)
        return 2
    if os.geteuid() == 0:
        print("Run V-Link Lite Setup as the kiosk user, not root.", file=sys.stderr)
        return 2
    uid = os.getuid()
    account = pwd.getpwuid(uid)
    home = Path(account.pw_dir)
    if not home.is_dir():
        print("Could not determine the current user home directory.", file=sys.stderr)
        return 2
    try:
        runtime = runtime_directory(uid, home)
        fd = os.open(runtime / "v-link-lite-setup.lock",
                     os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if os.fstat(fd).st_uid != uid or not stat.S_ISREG(os.fstat(fd).st_mode):
                raise RuntimeError("Unsafe Setup lock file.")
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("V-Link Lite Setup is already running.", file=sys.stderr)
                return 22 if argv else 0
            env = session_environment(uid)
            return curses.wrapper(lambda screen: SetupUI(screen, bool(argv), uid,
                                                          account.pw_name, env).main_menu())
        finally:
            os.close(fd)
    except (RuntimeError, OSError, curses.error) as error:
        print(f"V-Link Lite Setup: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
