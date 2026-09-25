"""Audio and microphone screens for V-Link Lite Setup."""

import curses
import json
import re
import shutil
import time
from pathlib import Path

import v_link_lite_audio as lite_audio

from .ui import is_socket

AUDIO_SAMPLE = "/usr/share/sounds/alsa/Front_Center.wav"


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

class AudioMixin:
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

