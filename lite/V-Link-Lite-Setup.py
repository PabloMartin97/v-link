#!/usr/bin/env python3
"""Persistent, unprivileged maintenance screen for V-Link Lite."""

import curses
from decimal import Decimal
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
import v_link_lite_audio as lite_audio
import v_link_lite_display as lite_display


TITLE = "V-Link Lite Setup"
AUDIO_SAMPLE = "/usr/share/sounds/alsa/Front_Center.wav"
TERMINAL_RC = "/usr/local/share/v-link-lite/terminal.bashrc"


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
        if not lite_display.wayland_available(env):
            env.pop("WAYLAND_DISPLAY", None)
            if is_socket(bus):
                try:
                    manager = subprocess.run(["systemctl", "--user", "show-environment"],
                                             capture_output=True, text=True, timeout=2, env=env)
                    for line in manager.stdout.splitlines():
                        if line.startswith("WAYLAND_DISPLAY="):
                            env["WAYLAND_DISPLAY"] = line.split("=", 1)[1]
                            if lite_display.wayland_available(env):
                                break
                            env.pop("WAYLAND_DISPLAY", None)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if not lite_display.wayland_available(env):
                candidates = [path.name for path in login_runtime.glob("wayland-*")
                              if not path.is_symlink() and path.is_socket() and path.stat().st_uid == uid]
                if len(candidates) == 1:
                    env["WAYLAND_DISPLAY"] = candidates[0]
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
            if key in (27, 10, 13, curses.KEY_ENTER, curses.KEY_BACKSPACE, 127):
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

    def open_terminal(self):
        curses.def_prog_mode()
        curses.endwin()
        try:
            result = subprocess.run(
                ["/bin/bash", "--noprofile", "--rcfile", TERMINAL_RC, "-i"],
                env=self.env, check=False)
            error = ("" if result.returncode == 0 else
                     f"Terminal exited with status {result.returncode}.")
        except FileNotFoundError:
            error = "The Lite maintenance terminal is unavailable."
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
            choice = self.choose("Audio session unavailable", [
                ("microphone", "Microphone / recover Processing Off"), ("back", "Back")],
                summary=["PipeWire is unavailable. You can still remove Lite processing."])
            if choice == "microphone":
                self.microphone_menu(audio_available=False)
            return
        while True:
            _, sink = self.command(["wpctl", "inspect", "@DEFAULT_AUDIO_SINK@"], 3)
            _, source = self.command(["wpctl", "inspect", "@DEFAULT_AUDIO_SOURCE@"], 3)
            def label(payload):
                match = re.search(r'node.description = "([^"]+)"', payload)
                return match.group(1) if match else "not selected"
            _, output_volume = self.command(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], 2)
            _, input_volume = self.command(["wpctl", "get-volume", "@DEFAULT_AUDIO_SOURCE@"], 2)
            try:
                processing = lite_audio.read_profile(self.home)["preset"]
            except lite_audio.AudioError:
                processing = "configuration error"
            summary = [f"Output: {label(sink)}", f"Output volume: {output_volume or 'unavailable'}",
                       f"Microphone: {label(source)}", f"Input volume: {input_volume or 'unavailable'}",
                       f"Call processing: {processing}"]
            choice = self.choose("Audio", [
                ("output", "Select output"), ("microphone", "Microphone"),
                ("output_volume", "Output volume"),
                ("test", "Test speakers"), ("status", "Technical status"),
                ("back", "Back")], summary=summary)
            if choice in (None, "back"):
                return
            if choice == "output":
                self.select_audio_device("Audio/Sink")
            elif choice == "microphone":
                self.microphone_menu()
            elif choice == "output_volume":
                self.set_volume("@DEFAULT_AUDIO_SINK@", "Output volume")
            elif choice == "test":
                self.test_audio()
            elif choice == "status":
                self.busy("Reading PipeWire status")
                _, output = self.command(["wpctl", "status"], 3)
                try:
                    profile = lite_audio.read_profile(self.home)
                    details = (f"\n\nLite microphone processing: {profile['preset']}\n"
                               f"Physical source: {profile['physical'] or 'not selected'}\n"
                               f"Processed source: {lite_audio.SOURCE_NAME if profile['preset'] != 'off' else 'off'}\n"
                               f"AEC: {'on' if profile['preset'] != 'off' else 'off'}\n"
                               f"AGC: {'on' if profile['agc'] and profile['preset'] != 'off' else 'off'}\n"
                               f"Noise suppression: {'on (fixed strength)' if profile['noise'] and profile['preset'] != 'off' else 'off'}\n"
                               f"High-pass: {'on' if profile['high_pass'] and profile['preset'] != 'off' else 'off'}\n"
                               f"PipeWire: {self.service_state('pipewire.service', user=True)}\n"
                               f"WirePlumber: {self.service_state('wireplumber.service', user=True)}")
                except lite_audio.AudioError as error:
                    details = f"\n\nLite microphone config: {error}"
                self.view("PipeWire status", output + details)

    def physical_microphones(self):
        try:
            return lite_audio.physical_sources(lite_audio.graph(self.env))
        except lite_audio.AudioError:
            return []

    def selected_physical_microphone(self, profile, sources):
        by_name = {source["name"]: source for source in sources}
        current = lite_audio.current_default_source(self.env)
        return (by_name.get(profile["physical"]) or by_name.get(current)
                or (sources[0] if sources else None))

    def select_microphone(self, profile, sources):
        if not sources:
            self.message("No physical microphone is connected.")
            return
        choice = self.choose("Select physical microphone", [
            (source["name"], source["label"]) for source in sources] + [("back", "Back")])
        if choice in (None, "back"):
            return
        selected = next((source for source in sources if source["name"] == choice), None)
        if selected is None:
            return
        self.busy("Selecting microphone")
        try:
            if profile["preset"] == "off":
                lite_audio._select_source(choice, self.env)
            else:
                lite_audio.apply_profile(self.home, {**profile, "physical": choice}, self.env)
            self.message("Physical microphone selected. Open a new call to use it.")
        except lite_audio.AudioError as error:
            self.message(f"Microphone selection failed: {error}")

    def apply_microphone_preset(self, profile, preset, physical):
        self.busy("Applying microphone processing")
        try:
            if preset == "off":
                lite_audio.apply_profile(self.home, {"preset": "off", "physical": physical or ""}, self.env)
            else:
                if not physical:
                    raise lite_audio.AudioError("Connect and select a physical microphone first.")
                options = lite_audio.PRESETS[preset] if preset != "custom" else {
                    key: profile[key] for key in ("noise", "agc", "high_pass")}
                lite_audio.apply_profile(self.home, {"preset": preset, "physical": physical, **options}, self.env)
            self.message("Processing applied. Open a new call to use the selected microphone.")
        except lite_audio.AudioError as error:
            self.message(f"Processing could not be applied: {error}")

    def processing_menu(self, profile, physical):
        choice = self.choose("Microphone processing", [
            ("off", "Off (physical microphone)"),
            ("echo", "Echo cancellation"),
            ("calls", "Calls / Car (conservative starting point)"),
            ("custom", "Custom (saved advanced switches)"),
            ("back", "Back")], summary=[f"Current: {profile['preset']}",
                "Calls / Car: AEC + fixed noise reduction; AGC/HPF off.",
                "Applying can briefly reset audio. Test with a new call."])
        if choice not in (None, "back"):
            self.apply_microphone_preset(profile, choice, physical)

    def advanced_microphone_menu(self, profile, physical):
        if not physical:
            self.message("Connect and select a physical microphone first.")
            return
        pending = {key: profile[key] for key in ("noise", "agc", "high_pass")}
        while True:
            choice = self.choose("Advanced microphone processing", [
                ("noise", f"Noise suppression: {'On (fixed strength)' if pending['noise'] else 'Off'}"),
                ("agc", f"Automatic gain: {'On' if pending['agc'] else 'Off'}"),
                ("high_pass", f"Extra high-pass filter: {'On' if pending['high_pass'] else 'Off'}"),
                ("restore", "Restore Calls / Car starting point"),
                ("apply", "Apply as Custom"), ("back", "Back")],
                summary=["AEC stays on when processing is active.",
                         "The microphone circuit already filters below ~80 Hz.",
                         "AGC may reduce AEC quality; test it in a real call."])
            if choice in (None, "back"):
                return
            if choice in pending:
                pending[choice] = not pending[choice]
            elif choice == "restore":
                self.apply_microphone_preset(profile, "calls", physical)
                return
            elif choice == "apply":
                self.busy("Applying custom processing")
                try:
                    lite_audio.apply_profile(self.home, {"preset": "custom", "physical": physical, **pending}, self.env)
                    self.message("Custom processing applied. Open a new call to use it.")
                except lite_audio.AudioError as error:
                    self.message(f"Custom processing failed: {error}")
                return

    def microphone_menu(self, audio_available=True):
        while True:
            try:
                profile = lite_audio.read_profile(self.home)
            except lite_audio.AudioError as error:
                profile = {"preset": "invalid", "physical": "", **lite_audio.PRESETS["calls"]}
                config_error = str(error)
            else:
                config_error = ""
            sources = self.physical_microphones() if audio_available else []
            physical = self.selected_physical_microphone(profile, sources) if sources else None
            physical_name = physical["name"] if physical else profile["physical"]
            input_level = "unavailable"
            if physical:
                status, output = self.command(["wpctl", "get-volume", str(physical["id"])], 2)
                match = re.search(r"Volume:\s*([0-9.]+)", output) if status == 0 else None
                if match:
                    input_level = f"{float(match.group(1)) * 100:.0f}%"
            items = []
            if audio_available:
                items.extend([("select", "Select input"), ("level", "Input level"),
                              ("live", "Live level"), ("calibrate", "Auto calibrate")])
            items.append(("processing", "Processing preset / Off"))
            if audio_available:
                items.extend([("advanced", "Advanced processing"), ("details", "Technical details")])
            items.append(("back", "Back"))
            choice = self.choose("Microphone", items, summary=[
                f"Device: {physical['label'] if physical else 'unavailable'}",
                f"Input level: {input_level}",
                f"Processing: {profile['preset']}",
                "Input level is PipeWire source volume, not analogue gain.",
                config_error or ("Audio session unavailable; Off remains available." if not audio_available
                                 else "For Lite calibration, use V-Link microphone gain 0 dB.")])
            if choice in (None, "back"):
                return
            if choice == "processing":
                if not audio_available:
                    self.apply_microphone_preset(profile, "off", physical_name)
                else:
                    self.processing_menu(profile, physical_name)
            elif choice == "select":
                self.select_microphone(profile, sources)
            elif choice == "level":
                if physical:
                    self.set_volume(str(physical["id"]), "Input level")
                else:
                    self.message("No physical microphone is connected.")
            elif choice == "live":
                self.live_microphone_level(physical_name)
            elif choice == "calibrate":
                self.calibrate_microphone(physical)
            elif choice == "advanced":
                self.advanced_microphone_menu(profile, physical_name)
            elif choice == "details":
                self.view("Microphone details", f"Physical: {physical_name or 'unavailable'}\n"
                          f"Default: {lite_audio.current_default_source(self.env) or 'unavailable'}\n"
                          f"Processed: {lite_audio.SOURCE_NAME if profile['preset'] != 'off' else 'off'}\n"
                          f"Preset: {profile['preset']}\nAEC: {'on' if profile['preset'] not in ('off', 'invalid') else 'off'}\n"
                          f"Noise: {'on (fixed strength)' if profile['noise'] and profile['preset'] not in ('off', 'invalid') else 'off'}\n"
                          f"AGC: {'on' if profile['agc'] and profile['preset'] not in ('off', 'invalid') else 'off'}\n"
                          f"Extra high-pass: {'on' if profile['high_pass'] and profile['preset'] not in ('off', 'invalid') else 'off'}")

    def live_microphone_level(self, source):
        if not source:
            self.message("No physical microphone is connected.")
            return
        windows = []
        peak = -90.0
        self.screen.timeout(0)
        try:
            with lite_audio.Capture(source, self.env) as capture:
                while True:
                    metrics = capture.window()
                    if metrics:
                        windows.append(metrics)
                        windows = windows[-100:]
                        peak = max(peak, metrics["peak"])
                    current = metrics or (windows[-1] if windows else {"rms": -90, "peak": -90, "clipping": False})
                    if self.frame("Microphone level", "Esc: Back"):
                        width = 24
                        filled = max(0, min(width, round((current["rms"] + 70) / 65 * width)))
                        self.put(7, 6, "[" + "#" * filled + "." * (width - filled) + "]")
                        self.put(9, 6, f"Current: {current['rms']:.1f} dBFS")
                        self.put(10, 6, f"Peak: {peak:.1f} dBFS")
                        self.put(11, 6, f"Quiet-window estimate: {lite_audio.noise_floor(windows):.1f} dBFS")
                        self.put(12, 6, f"Clipping: {'YES' if current['clipping'] else 'No'}")
                    self.flush()
                    if self.screen.getch() in (27, curses.KEY_BACKSPACE, 127):
                        return
        except lite_audio.AudioError as error:
            self.screen.timeout(-1)
            self.message(f"Live level unavailable: {error}")
        finally:
            self.screen.timeout(-1)

    def _calibration_phase(self, capture, heading, seconds):
        windows = []
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            metric = capture.window()
            if metric:
                windows.append(metric)
            if self.frame("Automatic microphone setup", "Esc: Cancel"):
                self.put(7, 6, heading)
                self.put(9, 6, f"Remaining: {max(0, deadline - time.monotonic()):.1f} s")
                if metric:
                    self.put(11, 6, f"Level: {metric['rms']:.1f} dBFS")
            self.flush()
            if self.screen.getch() == 27:
                return None
        if not windows:
            raise lite_audio.AudioError("No microphone samples arrived.")
        return windows

    def calibrate_microphone(self, physical):
        if physical is None:
            self.message("No physical microphone is connected.")
            return
        source = physical["name"]
        self.screen.timeout(0)
        try:
            with lite_audio.Capture(source, self.env) as capture:
                quiet = self._calibration_phase(capture, "Keep quiet for 3 seconds", 3)
                if quiet is None:
                    return
                normal = self._calibration_phase(capture, "Speak normally for 5 seconds", 5)
                if normal is None:
                    return
                loud = self._calibration_phase(capture, "Speak loudly for 2 seconds", 2)
                if loud is None:
                    return
        except lite_audio.AudioError as error:
            self.screen.timeout(-1)
            self.message(f"Calibration stopped: {error}")
            return
        finally:
            self.screen.timeout(-1)
        floor = lite_audio.noise_floor(quiet)
        speech = sorted(item["rms"] for item in normal)[len(normal) // 2]
        loud_peak = max(item["peak"] for item in loud)
        clipping = any(item["clipping"] for item in normal + loud)
        status, output = self.command(["wpctl", "get-volume", str(physical["id"])], 3)
        match = re.search(r"Volume:\s*([0-9.]+)", output) if status == 0 else None
        if match is None:
            self.message("Could not read input level; no changes were made.")
            return
        old_level = float(match.group(1))
        proposed = lite_audio.recommend_level(old_level, floor, speech, loud_peak)
        decision = self.choose("Automatic microphone setup", [
            ("apply", "Apply input level and Calls / Car"), ("cancel", "Cancel")],
            summary=[f"Noise: {floor:.1f} dBFS  Speech: {speech:.1f} dBFS",
                     f"Loud peak: {loud_peak:.1f} dBFS  Clipping: {'YES' if clipping else 'No'}",
                     f"Recommended input level: {proposed * 100:.0f}%",
                     "Calls / Car: AEC + fixed noise reduction; AGC off."])
        if decision != "apply":
            return
        self.busy("Applying microphone calibration")
        try:
            lite_audio.apply_profile(self.home, {"preset": "calls", "physical": source,
                           **lite_audio.PRESETS["calls"]}, self.env)
        except lite_audio.AudioError as error:
            self.message(f"Calibration processing failed: {error}")
            return
        refreshed = next((item for item in self.physical_microphones()
                          if item["name"] == source), None)
        if refreshed is None:
            self.message("Calls / Car is active, but the microphone disconnected before its level could be set.")
            return
        status, output = self.command(["wpctl", "set-volume", str(refreshed["id"]),
                                       f"{proposed:.2f}"], 4)
        if status:
            self.message(f"Calls / Car is active, but its input level was not changed: {output}")
            return
        self.message("Calibration applied. Test a new call; adjust Advanced processing if needed.")

    def display_status(self):
        if not self.display_available():
            return "Wayland display unavailable in this session."
        _, output = self.command(["wlr-randr"], 4)
        return output or "Could not query Wayland outputs."

    def display_menu(self):
        while True:
            raw = self.display_status()
            try:
                active_outputs = lite_display.active_outputs(lite_display.parse_outputs(raw))
            except lite_display.DisplayError:
                active_outputs = []
            output = active_outputs[0]["name"] if active_outputs else "unavailable"
            active = next((mode["token"] for head in active_outputs for mode in head["modes"]
                           if mode["current"]), "unavailable")
            choice = self.choose("Display / Input", [
                ("status", "Display status"), ("resolution", "Resolution / refresh rate"),
                ("cursor", "Cursor and mouse"),
                ("details", "Technical details"), ("back", "Back")],
                summary=[f"Display: {output}", f"Mode: {active[:60]}"])
            if choice in (None, "back"):
                return
            if choice == "cursor":
                self.cursor_menu()
            elif choice == "resolution":
                self.resolution_menu()
            elif choice == "details":
                self.view("Display details", raw)
            else:
                self.view("Display status", f"Display: {output}\nMode: {active}")

    def resolution_menu(self):
        try:
            settings = load_settings(self.home)
        except ValueError as error:
            self.message(f"Invalid Lite settings: {error}")
            return
        outputs = []
        if self.display_available():
            try:
                outputs = lite_display.active_outputs(lite_display.query_outputs(self.env))
            except lite_display.DisplayError as error:
                self.message(f"Could not read display modes: {error}")
        selected = None
        if outputs:
            selected = lite_display.find_output(outputs, settings["DISPLAY_OUTPUT"])
            if selected is None and len(outputs) == 1:
                selected = outputs[0]
            elif selected is None:
                choice = self.choose("Select display output", [
                    (output["name"], output["name"]) for output in outputs] + [("back", "Back")],
                    summary=["Several outputs are active; choose the one to configure."])
                if choice in (None, "back"):
                    return
                selected = lite_display.find_output(outputs, choice)
        items = [("auto", "Auto / Preferred (next graphical login)")]
        if selected:
            items.extend((mode["token"],
                          f"{mode['width']}x{mode['height']} @ {Decimal(mode['refresh']):.2f} Hz"
                          f"{' [current]' if mode['current'] else ''}"
                          f"{' [preferred]' if mode['preferred'] else ''}")
                         for mode in selected["modes"])
        items.append(("back", "Back"))
        choice = self.choose("Resolution / refresh rate", items,
                             summary=[f"Output: {selected['name'] if selected else 'no active Wayland output'}",
                                      f"Saved: {settings['DISPLAY_MODE']}",
                                      "Fixed modes require an active Wayland output." if not selected else
                                      "Modes come from the connected display."])
        if choice in (None, "back"):
            return
        if choice == "auto":
            settings["DISPLAY_MODE"] = "auto"
            settings["DISPLAY_OUTPUT"] = ""
            try:
                save_settings(self.home, settings)
                self.message("Auto / Preferred saved. The compositor will choose the mode at the next graphical login.")
            except (OSError, ValueError) as error:
                self.message(f"Could not save display preference: {error}")
            return
        if selected is None:
            self.message("No active Wayland output; no fixed mode was saved.")
            return
        try:
            lite_display.apply_mode(selected["name"], choice, self.env)
        except lite_display.DisplayError as error:
            self.message(f"Display mode was not applied or saved: {error}")
            return
        settings["DISPLAY_MODE"] = choice
        settings["DISPLAY_OUTPUT"] = selected["name"]
        try:
            save_settings(self.home, settings)
        except (OSError, ValueError) as error:
            self.message(f"Display changed now, but the preference could not be saved: {error}")
            return
        try:
            lite_display.refresh_current_splash(self.home, self.env)
            lite_display.restart_background(self.env)
        except lite_display.DisplayError as error:
            self.message(f"Display mode applied and saved, but the Lite splash could not be refreshed: {error}")
            return
        self.message("Display mode and matching Lite splash applied and saved. The next graphical boot will use them if still available.")

    def cursor_menu(self):
        while True:
            try:
                settings = load_settings(self.home)
            except ValueError as error:
                self.message(f"Invalid Lite settings: {error}")
                return
            mode = ("Hidden (mouse deactivated)" if settings["MOUSE_ENABLED"] == "no"
                    else settings["CURSOR_MODE"].title())
            mouse = "Activated" if settings["MOUSE_ENABLED"] == "yes" else "Deactivated"
            apply_now = not self.startup and self.display_available()
            choice = self.choose("Cursor and mouse", [
                ("auto", "Cursor: Auto"), ("visible", "Cursor: Visible"),
                ("mouse", "Toggle mouse activated / deactivated"),
                ("test", "Hide cursor now (test)"), ("back", "Back")],
                summary=[f"Cursor mode: {mode}", f"Mouse: {mouse}",
                         "Mouse off also hides the pointer, regardless of cursor mode.",
                         "Changes apply now." if apply_now else
                         "Changes apply after Continue or the next graphical boot."])
            if choice in (None, "back"):
                return
            if choice in ("auto", "visible", "mouse"):
                if choice == "mouse":
                    settings["MOUSE_ENABLED"] = "no" if settings["MOUSE_ENABLED"] == "yes" else "yes"
                else:
                    settings["CURSOR_MODE"] = choice
                try:
                    save_settings(self.home, settings)
                    action = "apply" if apply_now else "sync-config"
                    status, output = self.command(["/usr/local/bin/v-link-lite-cursor", action],
                                                  12 if apply_now else 3)
                    if status == 0:
                        self.message("Preference saved and applied." if apply_now else
                                     "Preference saved. It applies after Continue or the next graphical boot.")
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
        return lite_display.wayland_available(self.env)

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
                 ("terminal", "Terminal"),
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
            elif choice == "terminal":
                self.open_terminal()
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
