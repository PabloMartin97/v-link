"""Offline microphone processing owned by V-Link Lite, never by V-Link itself."""

import array
import json
import math
import os
import re
import select
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


CONFIG_NAME = "90-v-link-microphone.conf"
MARKER = "# Managed by V-Link Lite Setup"
SOURCE_NAME = "v_link_lite_processed_microphone"
SOURCE_LABEL = "V-Link Processed Microphone"
NODE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,200}$")
PRESETS = {
    "echo": {"noise": False, "agc": False, "high_pass": False},
    # The PCM2912A's 100 nF input capacitor already gives ~80 Hz high-pass.
    # AGC defaults off because PipeWire's WebRTC plugin warns it can hurt AEC.
    "calls": {"noise": True, "agc": False, "high_pass": False},
}


class AudioError(Exception):
    """A recoverable Lite audio setup error."""


def config_path(home):
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path(home) / ".config") / "pipewire/pipewire.conf.d" / CONFIG_NAME


def _owned_path(path):
    if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_uid != os.getuid())):
        raise AudioError("The Lite microphone file is unsafe or belongs to another user.")
    for parent in (path.parent, path.parent.parent):
        if parent.is_symlink() or (parent.exists() and (not parent.is_dir() or parent.stat().st_uid != os.getuid())):
            raise AudioError("The PipeWire configuration directory is unsafe.")


def read_profile(home):
    path = config_path(home)
    _owned_path(path)
    if not path.exists():
        return {"preset": "off", "physical": "", **PRESETS["calls"]}
    content = path.read_text(encoding="utf-8")
    if not content.startswith(MARKER + "\n"):
        raise AudioError("A non-Lite PipeWire file uses the Lite microphone filename.")
    try:
        metadata = json.loads(content.splitlines()[1].removeprefix("# Lite profile: "))
        if content.splitlines()[1] != "# Lite profile: " + json.dumps(metadata, sort_keys=True):
            raise ValueError("invalid metadata")
        if metadata["preset"] not in {"echo", "calls", "custom"} or not NODE_NAME.fullmatch(metadata["physical"]):
            raise ValueError("invalid profile")
        if any(type(metadata[key]) is not bool for key in ("noise", "agc", "high_pass")):
            raise ValueError("invalid switches")
    except (IndexError, KeyError, ValueError, TypeError) as error:
        raise AudioError("The Lite microphone configuration is damaged; Off can remove it.") from error
    return metadata


def render_config(profile):
    preset = profile["preset"]
    physical = profile["physical"]
    if preset not in {"echo", "calls", "custom"} or not NODE_NAME.fullmatch(physical):
        raise AudioError("Select a valid physical microphone first.")
    switches = {key: profile[key] for key in ("noise", "agc", "high_pass")}
    if any(type(value) is not bool for value in switches.values()):
        raise AudioError("Invalid processing switches.")
    if preset != "custom" and switches != PRESETS[preset]:
        raise AudioError("Preset settings do not match the selected preset.")
    metadata = {"preset": preset, "physical": physical, **switches}
    bool_value = lambda value: "true" if value else "false"
    return f'''{MARKER}
# Lite profile: {json.dumps(metadata, sort_keys=True)}
context.modules = [
  {{ name = libpipewire-module-echo-cancel
    args = {{
      library.name = aec/libspa-aec-webrtc
      monitor.mode = true
      capture.props = {{ target.object = "{physical}" }}
      source.props = {{
        node.name = "{SOURCE_NAME}"
        node.description = "{SOURCE_LABEL}"
      }}
      aec.args = {{
        webrtc.noise_suppression = {bool_value(switches["noise"])}
        webrtc.gain_control = {bool_value(switches["agc"])}
        webrtc.high_pass_filter = {bool_value(switches["high_pass"])}
      }}
    }}
  }}
]
'''


def _write_config(path, content):
    _owned_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _owned_path(path)
    if path.exists() and not path.read_text(encoding="utf-8").startswith(MARKER + "\n"):
        raise AudioError("Refusing to replace a PipeWire file not owned by Lite.")
    if content is None:
        path.unlink(missing_ok=True)
        return
    fd, temporary = tempfile.mkstemp(prefix=".v-link-microphone.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_installed_config(home):
    path = config_path(home)
    _owned_path(path)
    if not path.exists():
        return True
    profile = read_profile(home)
    if path.read_text(encoding="utf-8") != render_config(profile):
        raise AudioError("The Lite microphone fragment does not match its validated profile.")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise AudioError("The Lite microphone fragment must have mode 0600.")
    return True


def nodes(payload, kind=None):
    try:
        objects = json.loads(payload)
    except (TypeError, ValueError) as error:
        raise AudioError("Could not read the PipeWire graph.") from error
    result = []
    for item in objects:
        if not isinstance(item, dict):
            continue
        props = (item.get("info") or {}).get("props") or {}
        if kind and props.get("media.class") != kind:
            continue
        name = props.get("node.name")
        if isinstance(item.get("id"), int) and isinstance(name, str):
            result.append({"id": item["id"], "name": name,
                           "label": str(props.get("node.description") or props.get("node.nick") or name),
                           "kind": props.get("media.class", "")})
    return result


def physical_sources(payload):
    return [item for item in nodes(payload, "Audio/Source")
            if item["name"] != SOURCE_NAME and not item["name"].endswith(".monitor")
            and NODE_NAME.fullmatch(item["name"])]


def _run(args, env, timeout=6):
    try:
        result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AudioError(f"{args[0]} could not run: {error}") from error
    if result.returncode:
        raise AudioError((result.stderr or result.stdout).strip()[:220] or f"{args[0]} failed.")
    return result.stdout


def graph(env):
    return _run(["pw-dump"], env, 5)


def current_default_source(env):
    try:
        output = _run(["wpctl", "inspect", "@DEFAULT_AUDIO_SOURCE@"], env, 3)
    except AudioError:
        return ""
    match = re.search(r'^\s*node\.name\s*=\s*"([^"]+)"', output, re.MULTILINE)
    return match.group(1) if match else ""


def _select_source(name, env, required=True):
    for item in nodes(graph(env), "Audio/Source"):
        if item["name"] == name:
            _run(["wpctl", "set-default", str(item["id"])], env, 4)
            return True
    if required:
        raise AudioError(f"Microphone source not available: {name}")
    return False


def _wait_for_source(name, env):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            if _select_source(name, env, required=False):
                return
        except AudioError:
            pass
        time.sleep(0.25)
    raise AudioError(f"Microphone source did not appear: {name}")


def _restart(env):
    _run(["systemctl", "--user", "restart", "pipewire.service", "pipewire-pulse.service",
          "wireplumber.service"], env, 18)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            _run(["wpctl", "status"], env, 2)
            return
        except AudioError:
            time.sleep(0.25)
    raise AudioError("PipeWire did not recover after restart.")


def apply_profile(home, profile, env):
    """Apply a fragment transactionally; Off stays possible after a broken graph."""
    path = config_path(home)
    _owned_path(path)
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old is not None and not old.startswith(MARKER + "\n"):
        raise AudioError("Refusing to change a PipeWire file not owned by Lite.")
    old_default = current_default_source(env)
    previous_physical = ""
    if old is not None:
        try:
            previous_physical = read_profile(home)["physical"]
        except AudioError:
            pass
    new = None if profile["preset"] == "off" else render_config(profile)
    physical = profile.get("physical") or previous_physical
    if new is not None:
        available = {item["name"] for item in physical_sources(graph(env))}
        if physical not in available:
            raise AudioError("Selected physical microphone is not connected.")
    if new == old:
        if new is not None:
            _wait_for_source(SOURCE_NAME, env)
        elif physical:
            _select_source(physical, env, required=False)
        return
    try:
        _write_config(path, new)
        _restart(env)
        if new is not None:
            _wait_for_source(SOURCE_NAME, env)
        else:
            available = physical_sources(graph(env))
            preferred = next((item for item in available if item["name"] == physical), None)
            if preferred is None and available:
                preferred = available[0]
            if preferred is not None:
                _select_source(preferred["name"], env)
        if new is not None and current_default_source(env) != SOURCE_NAME:
            raise AudioError("The processed microphone did not become the default source.")
    except (AudioError, OSError) as error:
        if new is None:
            # Leave Off in place: it is the emergency recovery path.
            raise AudioError(f"Lite processing removed, but audio restart failed: {error}") from error
        try:
            _write_config(path, old)
            _restart(env)
            if old_default:
                _select_source(old_default, env, required=False)
        except (AudioError, OSError) as rollback_error:
            raise AudioError(f"{error}; rollback also failed: {rollback_error}") from error
        raise AudioError(f"{error}; previous microphone configuration restored.") from error


def dbfs(amplitude):
    return -90.0 if amplitude <= 0 else max(-90.0, 20 * math.log10(amplitude / 32768.0))


def pcm_metrics(chunk):
    """Compute one mono S16LE window without retaining voice samples."""
    samples = array.array("h")
    samples.frombytes(chunk[:len(chunk) & ~1])
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return {"rms": -90.0, "peak": -90.0, "clipping": False}
    peak = max(abs(sample) for sample in samples)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    clipped = sum(abs(sample) >= 32113 for sample in samples) >= 3
    return {"rms": dbfs(rms), "peak": dbfs(peak), "clipping": clipped}


def noise_floor(windows):
    values = sorted(window["rms"] for window in windows)
    return -90.0 if not values else values[max(0, len(values) // 4)]


def recommend_level(current, quiet, normal, loud):
    """Conservative source volume; never boost a noisy or clipped recording."""
    if normal >= -10 or loud >= -3:
        change_db = min(0.0, -7.0 - loud)
    elif quiet > -35 or normal - quiet < 12:
        change_db = 0.0
    else:
        change_db = min(6.0, -17.0 - normal, -7.0 - loud)
    change_db = max(-12.0, change_db)
    return round(max(0.05, min(1.0, current * 10 ** (change_db / 20))), 2)


class Capture:
    """A bounded, raw-PCM PipeWire capture. stdout never reaches disk."""

    def __init__(self, source, env):
        if not NODE_NAME.fullmatch(source):
            raise AudioError("Invalid microphone target.")
        self.source = source
        self.env = env
        self.process = None
        self.pending = bytearray()

    def __enter__(self):
        try:
            self.process = subprocess.Popen(
                ["pw-record", "--target", self.source, "--rate", "48000", "--channels", "1",
                 "--format", "s16", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=self.env, start_new_session=True)
        except OSError as error:
            raise AudioError(f"Could not open microphone capture: {error}") from error
        return self

    def window(self, timeout=0.12):
        if self.process.poll() is not None:
            raise AudioError("Microphone capture stopped; check that it is connected.")
        ready, _, _ = select.select([self.process.stdout], [], [], timeout)
        if not ready:
            return None
        self.pending.extend(os.read(self.process.stdout.fileno(), 9600))
        if len(self.pending) < 9600:
            return None
        chunk = bytes(self.pending[:9600])
        del self.pending[:9600]
        return pcm_metrics(chunk)

    def __exit__(self, *_args):
        if self.process is not None:
            if self.process.poll() is None:
                try:
                    self.process.terminate()
                except ProcessLookupError:
                    pass
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    self.process.kill()
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=2)
            self.process.stdout.close()
