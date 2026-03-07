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

# Temporal hysteresis (seconds), per target mode
HOLD_TIME_S = {
    "night": 2.0,
    "dim": 1.5,
    "day": 3.0,
}

# Voltage thresholds from ambient light sensor
# voltage <= NIGHT_MAX_V => night
# voltage <= DIM_MAX_V   => dim
# voltage >  DIM_MAX_V   => day
NIGHT_MAX_V = 0.9
DIM_MAX_V = 2.4


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
    runtime_daylight = getattr(shared_state, "backlight_daylight", None)
    runtime_darkness = getattr(shared_state, "backlight_darkness", None)
    runtime_auto = getattr(shared_state, "backlight_auto_enabled", None)

    # Only read from disk if shared_state hasn't been initialized yet.
    if not isinstance(runtime_daylight, (int, float)) or not isinstance(runtime_darkness, (int, float)) or not isinstance(runtime_auto, bool):
        app = settings.load_settings("app") or {}
        daylight = _read_range_setting(app, "daylight_backlight", DEFAULT_DAYLIGHT)
        darkness = _read_range_setting(app, "darkness_backlight", DEFAULT_DARKNESS)
        auto_enabled = _read_toggle_setting(app, "auto_backlight", "autoOpen", DEFAULT_AUTO)

        if not isinstance(runtime_daylight, (int, float)):
            shared_state.backlight_daylight = daylight["value"]
            runtime_daylight = daylight["value"]
        else:
            daylight["value"] = runtime_daylight

        if not isinstance(runtime_darkness, (int, float)):
            shared_state.backlight_darkness = darkness["value"]
            runtime_darkness = darkness["value"]
        else:
            darkness["value"] = runtime_darkness

        if not isinstance(runtime_auto, bool):
            shared_state.backlight_auto_enabled = auto_enabled
            runtime_auto = auto_enabled
    else:
        daylight = {**DEFAULT_DAYLIGHT, "value": runtime_daylight}
        darkness = {**DEFAULT_DARKNESS, "value": runtime_darkness}
        auto_enabled = runtime_auto

    return {
        "daylight": daylight,
        "darkness": darkness,
        "auto": auto_enabled,
    }


# ============================================================
# Day/night temporal hysteresis
# ============================================================

class LightStateHysteresis:
    def __init__(self, hold_times):
        self.state = "day"
        self._candidate = None
        self._since = None
        self.hold_times = hold_times

    def update(self, target: str) -> str:
        now = time.monotonic()

        if target == self.state:
            self._candidate = None
            self._since = None
            return self.state

        if self._candidate != target:
            self._candidate = target
            self._since = now
            return self.state

        elapsed = now - self._since
        required = self.hold_times.get(target, 1.0)

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
        self._light_state = LightStateHysteresis(HOLD_TIME_S)

    # --------------------------------------------------------
    # CAN sensor interpretation
    # --------------------------------------------------------

    def _mode_from_can(self) -> str:
        """
        Interprets CAN light value and returns: day, dim, night.
        """
        raw = None

        # Preferred path: CAN listeners publish sensors into shared_state.car_data
        try:
            with shared_state.car_data_lock:
                raw = shared_state.car_data.get("light")
        except Exception:
            raw = None

        # Backward-compatible fallback
        if raw is None:
            raw = getattr(getattr(shared_state, "can", None), "light_raw", None)

        if raw is None:
            return "day"

        try:
            voltage = float(raw)
        except (TypeError, ValueError):
            return "day"

        if voltage <= NIGHT_MAX_V:
            return "night"
        if voltage <= DIM_MAX_V:
            return "dim"
        return "day"

    def _dim_profile(self, cfg):
        day = cfg["daylight"]
        night = cfg["darkness"]
        day_value = clamp(day["value"], day["min"], day["max"])
        night_value = clamp(night["value"], night["min"], night["max"])
        low = min(day["min"], night["min"])
        high = max(day["max"], night["max"])
        return {
            "value": clamp(int(round((day_value + night_value) / 2)), low, high),
            "min": low,
            "max": high,
        }


    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def update(self):
        """
        :return: (byte, changed, mode)
        """

        cfg = load_backlight_config()

        # 1. Read CAN and decide target mode
        target_mode = self._mode_from_can()

        # 2. Stable state with hysteresis
        state = self._light_state.update(target_mode)

        # 3. Profile selection
        if not cfg["auto"]:
            profile = cfg["daylight"]
            mode = "day"
        else:
            if state == "night":
                profile = cfg["darkness"]
                mode = "night"
            elif state == "dim":
                profile = self._dim_profile(cfg)
                mode = "dim"
            else:
                profile = cfg["daylight"]
                mode = "day"

        # 4. Slider -> byte
        step = clamp(profile["value"], profile["min"], profile["max"])
        byte, changed = self._mapper.map(step)

        shared_state.backlight_byte = byte

        return byte, changed, mode
