import time
from .. import settings
from .shared_state import shared_state


# ============================================================
# Backlight levels table (16 steps, 1:1 index)
# The logical index is (slider - 1)
# ============================================================

BACKLIGHT_LEVELS = [
    0x20, 0x61, 0x62, 0x23,
    0x64, 0x25, 0x26, 0x67,
    0x68, 0x29, 0x2A, 0x2C,
    0x6B, 0x6D, 0x6E, 0x2F,
]


# ============================================================
# Defaults
# ============================================================

DEFAULT_DAYLIGHT = {"value": 15, "min": 1, "max": 16}
DEFAULT_DARKNESS = {"value": 5,  "min": 1, "max": 16}
DEFAULT_AUTO = True

# Temporal hysteresis (seconds)
ENTER_NIGHT_S = 2.0
EXIT_NIGHT_S  = 3.0


# ============================================================
# Utilities
# ============================================================

def clamp(value, low, high):
    return max(low, min(high, value))


def level_from_step(step: int) -> int:
    """
    step: slider value (1–16)
    """
    index = clamp(step - 1, 0, len(BACKLIGHT_LEVELS) - 1)
    return BACKLIGHT_LEVELS[index]


# ============================================================
# Config load (NO logic)
# ============================================================

def _read_range_setting(app, key, defaults):
    cfg = app.get(key, {}) if isinstance(app, dict) else {}
    if not isinstance(cfg, dict):
        return defaults.copy()

    value = cfg.get("value", defaults["value"])
    if isinstance(value, dict):
        value = value.get("value", defaults["value"])

    return {
        "value": value,
        "min": cfg.get("min", defaults["min"]),
        "max": cfg.get("max", defaults["max"]),
    }


def _read_toggle_setting(app, key, nested_key, default):
    cfg = app.get(key, {}) if isinstance(app, dict) else {}
    if isinstance(cfg, dict):
        nested = cfg.get(nested_key)
        if isinstance(nested, dict) and "value" in nested:
            return bool(nested.get("value", default))
        if "value" in cfg:
            return bool(cfg.get("value", default))
    return bool(default)


def load_backlight_config():
    app = settings.load_settings("app") or {}

    daylight = _read_range_setting(app, "daylight_backlight", DEFAULT_DAYLIGHT)
    darkness = _read_range_setting(app, "darkness_backlight", DEFAULT_DARKNESS)
    auto_enabled = _read_toggle_setting(app, "auto_backlight", "autoOpen", DEFAULT_AUTO)

    runtime_daylight = getattr(shared_state, "backlight_daylight", None)
    if isinstance(runtime_daylight, (int, float)):
        daylight["value"] = runtime_daylight
    else:
        shared_state.backlight_daylight = daylight["value"]

    runtime_darkness = getattr(shared_state, "backlight_darkness", None)
    if isinstance(runtime_darkness, (int, float)):
        darkness["value"] = runtime_darkness
    else:
        shared_state.backlight_darkness = darkness["value"]

    runtime_auto = getattr(shared_state, "backlight_auto_enabled", None)
    if isinstance(runtime_auto, bool):
        auto_enabled = runtime_auto
    else:
        shared_state.backlight_auto_enabled = auto_enabled

    return {
        "daylight": daylight,
        "darkness": darkness,
        "auto": auto_enabled,
    }


# ============================================================
# Day/night temporal hysteresis
# ============================================================

class LightStateHysteresis:
    def __init__(self, enter_night_s, exit_night_s):
        self.state = "day"
        self._candidate = None
        self._since = None
        self.enter_night_s = enter_night_s
        self.exit_night_s = exit_night_s

    def update(self, is_dark: bool) -> str:
        now = time.monotonic()
        target = "night" if is_dark else "day"

        if target == self.state:
            self._candidate = None
            self._since = None
            return self.state

        if self._candidate != target:
            self._candidate = target
            self._since = now
            return self.state

        elapsed = now - self._since
        required = (
            self.enter_night_s if target == "night"
            else self.exit_night_s
        )

        if elapsed >= required:
            self.state = target
            self._candidate = None
            self._since = None

        return self.state


# ============================================================
# Mapper + change detection
# ============================================================

class BacklightMapper:
    def __init__(self):
        self._last_byte = None

    def map(self, step: int):
        byte = level_from_step(step)
        changed = byte != self._last_byte
        if changed:
            self._last_byte = byte
        return byte, changed


# ============================================================
# Main controller (reads CAN + decides everything)
# ============================================================

class BacklightController:
    """
    FULL BACKLIGHT BRAIN

    - Reads CAN (shared state)
    - Decides if it's dark
    - Applies temporal hysteresis
    - Selects day/night profile
    - Translates slider -> byte
    - Detects changes
    """

    def __init__(self):
        self._mapper = BacklightMapper()
        self._light_state = LightStateHysteresis(
            ENTER_NIGHT_S,
            EXIT_NIGHT_S
        )

    # --------------------------------------------------------
    # CAN sensor interpretation
    # --------------------------------------------------------

    def _is_dark_from_can(self) -> bool:
        """
        Interprets the raw CAN light sensor value.
        Adjust here when you have real values.
        """
        raw = getattr(getattr(shared_state, "can", None), "light_raw", None)
        if raw is None:
            return False

        # Typical Volvo P2 example (adjustable)
        # 0x00–0x05 -> dark
        return raw <= 0x05


    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def update(self):
        """
        :return: (byte, changed, mode)
        """

        cfg = load_backlight_config()

        # 1. Read CAN and decide dark/bright
        is_dark = self._is_dark_from_can()

        # 2. Stable state with hysteresis
        state = self._light_state.update(is_dark)

        # 3. Profile selection
        if not cfg["auto"]:
            profile = cfg["daylight"]
            mode = "day"
        else:
            if state == "night":
                profile = cfg["darkness"]
                mode = "night"
            else:
                profile = cfg["daylight"]
                mode = "day"

        # 4. Slider -> byte
        step = clamp(profile["value"], profile["min"], profile["max"])
        byte, changed = self._mapper.map(step)

        shared_state.backlight_byte = byte

        return byte, changed, mode
