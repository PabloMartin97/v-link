"""
Tests for the status table display functions in V-Link.py.

V-Link.py is loaded as a regular module (not __main__) so the startup
block is skipped and only the helper functions / globals are available.
"""

import importlib.util
import logging
import re
import subprocess
import sys
import types
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ─── ANSI helpers ─────────────────────────────────────────────────────────────

_ANSI = re.compile(r'\033\[[0-9;?]*[A-Za-z]')


def strip_ansi(s: str) -> str:
    return _ANSI.sub('', s)


# ─── Extra sys.modules mocks needed to import V-Link.py ───────────────────────
# conftest.py already provides: lgpio, board, busio, adafruit_ads1x15, uinput
# can, serial, socketio are real packages available via the production venv
# (tests/conftest.py ensures pytest runs with the venv interpreter).
# Only mock libraries that require physical Pi hardware and aren't already covered.

def _mock_module(name, **attrs):
    if name not in sys.modules:
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod
    return sys.modules[name]


# gpiod is used by some threads; lgpio_mock covers lgpio but gpiod may appear too
_mock_module('gpiod')


# ─── Load V-Link.py as a module (not __main__) ────────────────────────────────

_VLINK_PATH = Path(__file__).resolve().parents[2] / 'V-Link.py'


def _load_vlink():
    spec = importlib.util.spec_from_file_location('vlink_main', str(_VLINK_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_vmod = _load_vlink()


# ─── Helpers ──────────────────────────────────────────────────────────────────

class _MockVlink:
    rpiModel = 'Raspberry Pi 4'
    rpiProtocol = 'X11'


def _alive() -> MagicMock:
    t = MagicMock(spec=threading.Thread)
    t.is_alive.return_value = True
    return t


def _dead() -> MagicMock:
    t = MagicMock(spec=threading.Thread)
    t.is_alive.return_value = False
    return t


def _make_record(level: int, msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        name='vlink', level=level, pathname='', lineno=0,
        msg=msg, args=(), exc_info=None,
    )


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    """Reset all module-level display state before every test."""
    monkeypatch.setattr(_vmod, '_display_initialized', False)
    monkeypatch.setattr(_vmod, '_prev_display_snapshot', None)
    monkeypatch.setattr(_vmod, 'vlink', _MockVlink(), raising=False)
    _vmod._log_handler.buffer.clear()
    ss = _vmod.shared_state
    ss.liteMode = False
    ss.rtiStatus = False
    ss.ignStatus.clear()
    for key in list(ss.THREADS):
        ss.THREADS[key] = None


def _render(capsys) -> str:
    """Call display once and return the raw output (ANSI codes intact)."""
    _vmod.display_thread_states()
    out, _ = capsys.readouterr()
    return out


def _plain(capsys) -> str:
    """Call display once and return output with ANSI codes stripped."""
    return strip_ansi(_render(capsys))


def test_full_restart_reexecutes_after_browser_hardware_and_server_shutdown(monkeypatch):
    events = []
    monkeypatch.setattr(_vmod, 'logger', MagicMock())
    instance = _vmod.VLINK()
    instance.stop_thread = lambda name: events.append(('stop', name))
    monkeypatch.setattr(_vmod.shared_state, 'THREADS', {
        'server': _alive(), 'app': _alive(), 'rti': _alive(), 'ign': _alive(),
    })
    restart_event = threading.Event()
    restart_event.set()
    monkeypatch.setattr(_vmod.shared_state, 'restart_event', restart_event)
    monkeypatch.setattr(_vmod.sys, 'argv', [str(_VLINK_PATH), '--dev', '--nokiosk'])
    monkeypatch.setattr(_vmod.os, 'execv', lambda exe, args: events.append(('exec', exe, args)))
    monkeypatch.setattr(_vmod, 'ensure_lite_restart_overlay',
                        lambda: events.append(('overlay',)))

    instance.process_restart_event()

    assert events == [
        ('stop', 'app'), ('stop', 'rti'), ('stop', 'ign'), ('stop', 'server'),
        ('exec', sys.executable, [sys.executable, str(_VLINK_PATH), '--dev', '--nokiosk']),
    ]
    assert ('overlay',) not in events
    assert not restart_event.is_set()


def test_lite_restart_requests_overlay_before_stopping_browser(monkeypatch):
    events = []
    monkeypatch.setattr(_vmod, 'logger', MagicMock())
    instance = _vmod.VLINK()
    instance.stop_thread = lambda name: events.append(('stop', name))
    monkeypatch.setattr(_vmod.shared_state, 'liteMode', True)
    monkeypatch.setattr(_vmod.shared_state, 'THREADS', {
        'server': _alive(), 'app': _alive(), 'rti': _alive(),
    })
    restart_event = threading.Event()
    restart_event.set()
    monkeypatch.setattr(_vmod.shared_state, 'restart_event', restart_event)
    monkeypatch.setattr(_vmod, 'ensure_lite_restart_overlay',
                        lambda: events.append(('overlay',)) or False)
    monkeypatch.setattr(_vmod.os, 'execv', lambda *_args: events.append(('exec',)))

    instance.process_restart_event()

    assert events == [
        ('overlay',), ('stop', 'app'), ('stop', 'rti'), ('stop', 'server'), ('exec',),
    ]


def configure_overlay_test_paths(monkeypatch, tmp_path):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    executable = tmp_path / 'v-link-lite-overlay'
    executable.write_text('#!/bin/sh\n')
    executable.chmod(0o755)
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    monkeypatch.setenv('XDG_RUNTIME_DIR', str(runtime))
    monkeypatch.setattr(_vmod, 'LITE_OVERLAY', executable)
    monkeypatch.setattr(_vmod, 'PROC_ROOT', proc_root)
    monkeypatch.setattr(_vmod.os, 'kill', lambda _pid, _signal: None)
    return executable, runtime / _vmod.LITE_OVERLAY_MARKER, proc_root


def write_overlay_process(marker, proc_root, executable, pid=321):
    marker.write_text(f'{pid}\n')
    process = proc_root / str(pid)
    process.mkdir(exist_ok=True)
    (process / 'cmdline').write_bytes(
        b'/usr/bin/python3\0' + str(executable).encode() + b'\0')


def test_lite_overlay_marker_requires_matching_live_process(monkeypatch, tmp_path):
    executable, marker, proc_root = configure_overlay_test_paths(monkeypatch, tmp_path)
    write_overlay_process(marker, proc_root, executable)
    assert _vmod._lite_overlay_pid(marker) == 321

    (proc_root / '321/cmdline').write_bytes(b'/usr/bin/python3\0/tmp/not-the-overlay\0')
    assert _vmod._lite_overlay_pid(marker) is None

    write_overlay_process(marker, proc_root, executable)
    monkeypatch.setattr(_vmod.os, 'kill',
                        MagicMock(side_effect=ProcessLookupError))
    assert _vmod._lite_overlay_pid(marker) is None


def test_lite_restart_reuses_valid_mapped_overlay(monkeypatch, tmp_path):
    executable, marker, proc_root = configure_overlay_test_paths(monkeypatch, tmp_path)
    write_overlay_process(marker, proc_root, executable)
    popen = MagicMock(side_effect=AssertionError('must not launch a duplicate overlay'))
    monkeypatch.setattr(_vmod.subprocess, 'Popen', popen)

    assert _vmod.ensure_lite_restart_overlay() is True
    popen.assert_not_called()


def test_lite_restart_overlay_missing_warns_and_continues(monkeypatch, tmp_path):
    _executable, _marker, _proc_root = configure_overlay_test_paths(monkeypatch, tmp_path)
    missing = tmp_path / 'missing-overlay'
    monkeypatch.setattr(_vmod, 'LITE_OVERLAY', missing)
    test_logger = MagicMock()
    monkeypatch.setattr(_vmod, 'logger', test_logger)

    assert _vmod.ensure_lite_restart_overlay() is False
    assert 'unavailable' in test_logger.warning.call_args.args[0]


def test_lite_restart_overlay_maps_and_is_launched_detached(monkeypatch, tmp_path):
    executable, marker, proc_root = configure_overlay_test_paths(monkeypatch, tmp_path)
    launched = MagicMock()

    def popen(args, **kwargs):
        launched(args, **kwargs)
        write_overlay_process(marker, proc_root, executable)
        return MagicMock()

    monkeypatch.setattr(_vmod.subprocess, 'Popen', popen)
    monkeypatch.setattr(_vmod.time, 'monotonic', lambda: 0.0)

    assert _vmod.ensure_lite_restart_overlay() is True
    args, kwargs = launched.call_args
    assert args == ([str(executable)],)
    assert kwargs == {
        'stdin': subprocess.DEVNULL,
        'stdout': subprocess.DEVNULL,
        'stderr': subprocess.DEVNULL,
        'start_new_session': True,
        'close_fds': True,
    }


def test_lite_restart_overlay_timeout_warns_and_continues(monkeypatch, tmp_path):
    configure_overlay_test_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(_vmod.subprocess, 'Popen', MagicMock(return_value=MagicMock()))
    ticks = iter((10.0, 10.0, 15.0))
    monkeypatch.setattr(_vmod.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(_vmod.time, 'sleep', lambda _seconds: None)
    test_logger = MagicMock()
    monkeypatch.setattr(_vmod, 'logger', test_logger)

    assert _vmod.ensure_lite_restart_overlay() is False
    assert 'did not map in time' in test_logger.warning.call_args.args[0]


def test_lite_restart_removes_only_stale_marker_before_launch(monkeypatch, tmp_path):
    executable, marker, proc_root = configure_overlay_test_paths(monkeypatch, tmp_path)
    marker.write_text('987\n')
    process = proc_root / '987'
    process.mkdir()
    (process / 'cmdline').write_bytes(b'/usr/bin/python3\0/tmp/unrelated\0')

    def popen(_args, **_kwargs):
        assert not marker.exists()
        write_overlay_process(marker, proc_root, executable, pid=654)
        return MagicMock()

    monkeypatch.setattr(_vmod.subprocess, 'Popen', popen)
    monkeypatch.setattr(_vmod.time, 'monotonic', lambda: 0.0)
    assert _vmod.ensure_lite_restart_overlay() is True


class TestBacklightCanData:
    def test_reads_nested_sensor_data(self):
        from backend.shared.backlight_helper import BacklightController

        original_car_data = _vmod.shared_state.car_data
        try:
            _vmod.shared_state.car_data = {
                'data': {'light': '0.80'},
                'pollingrate': {},
                'timestamp': None,
            }

            assert BacklightController()._mode_from_can() == 'night'
        finally:
            _vmod.shared_state.car_data = original_car_data

    def test_supports_flat_sensor_data(self):
        from backend.shared.backlight_helper import BacklightController

        original_car_data = _vmod.shared_state.car_data
        try:
            _vmod.shared_state.car_data = {'light': 3.0}

            assert BacklightController()._mode_from_can() == 'day'
        finally:
            _vmod.shared_state.car_data = original_car_data


# ─── _RingBufferHandler ───────────────────────────────────────────────────────

class TestRingBufferHandler:
    def test_warning_is_captured(self):
        _vmod._log_handler.emit(_make_record(logging.WARNING, 'watch out'))
        assert any('watch out' in m for m in _vmod._log_handler.buffer)

    def test_debug_is_not_captured(self):
        _vmod._log_handler.emit(_make_record(logging.DEBUG, 'ignored'))
        assert not _vmod._log_handler.buffer

    def test_info_is_not_captured(self):
        _vmod._log_handler.emit(_make_record(logging.INFO, 'ignored'))
        assert not _vmod._log_handler.buffer

    def test_error_is_captured(self):
        _vmod._log_handler.emit(_make_record(logging.ERROR, 'broken'))
        assert any('broken' in m for m in _vmod._log_handler.buffer)

    def test_capacity_not_exceeded(self):
        for i in range(_vmod.LOG_CAPACITY + 5):
            _vmod._log_handler.emit(_make_record(logging.WARNING, f'msg {i}'))
        assert len(_vmod._log_handler.buffer) == _vmod.LOG_CAPACITY

    def test_oldest_evicted_when_full(self):
        for i in range(_vmod.LOG_CAPACITY + 1):
            _vmod._log_handler.emit(_make_record(logging.WARNING, f'msg {i}'))
        assert not any('msg 0' in m for m in _vmod._log_handler.buffer)

    def test_warning_colored_yellow(self):
        _vmod._log_handler.emit(_make_record(logging.WARNING, 'yellow'))
        assert '\033[33m' in _vmod._log_handler.buffer[0]

    def test_error_colored_red(self):
        _vmod._log_handler.emit(_make_record(logging.ERROR, 'red'))
        assert '\033[31m' in _vmod._log_handler.buffer[0]


# ─── Table content ────────────────────────────────────────────────────────────

class TestTableContent:
    def test_header_shows_version(self, capsys):
        assert f'V-Link {_vmod.VERSION}' in _plain(capsys)

    def test_header_shows_device_model(self, capsys):
        assert 'Raspberry Pi 4' in _plain(capsys)

    def test_header_shows_session_type(self, capsys):
        assert 'X11' in _plain(capsys)

    def test_rti_down(self, capsys):
        _vmod.shared_state.rtiStatus = False
        assert 'RTI: Down' in _plain(capsys)

    def test_rti_up(self, capsys):
        _vmod.shared_state.rtiStatus = True
        assert 'RTI: Up' in _plain(capsys)

    def test_ign_low(self, capsys):
        _vmod.shared_state.ignStatus.clear()
        assert 'IGN: Low' in _plain(capsys)

    def test_ign_high(self, capsys):
        _vmod.shared_state.ignStatus.set()
        assert 'IGN: High' in _plain(capsys)

    def test_all_thread_keys_present(self, capsys):
        output = _plain(capsys)
        for key in _vmod.shared_state.THREADS:
            assert key.upper() in output, f'Expected {key.upper()!r} in output'

    def test_alive_thread_shows_running(self, capsys):
        _vmod.shared_state.THREADS['can'] = _alive()
        output = _plain(capsys)
        can_line = next(l for l in output.splitlines() if 'CAN' in l)
        assert 'running' in can_line

    def test_dead_thread_shows_stopped(self, capsys):
        _vmod.shared_state.THREADS['can'] = None
        output = _plain(capsys)
        can_line = next(l for l in output.splitlines() if 'CAN' in l)
        assert 'stopped' in can_line

    def test_mixed_thread_states(self, capsys):
        _vmod.shared_state.THREADS['server'] = _alive()
        _vmod.shared_state.THREADS['can'] = None
        output = _plain(capsys)
        server_line = next(l for l in output.splitlines() if 'SERVER' in l)
        can_line = next(l for l in output.splitlines() if 'CAN' in l)
        assert 'running' in server_line
        assert 'stopped' in can_line

    def test_no_warnings_placeholder_when_buffer_empty(self, capsys):
        assert 'No recent warnings.' in _plain(capsys)

    def test_log_messages_shown_when_buffer_has_entries(self, capsys):
        _vmod._log_handler.emit(_make_record(logging.WARNING, 'disk almost full'))
        assert 'disk almost full' in _plain(capsys)

    def test_no_warnings_placeholder_hidden_when_buffer_has_entries(self, capsys):
        _vmod._log_handler.emit(_make_record(logging.WARNING, 'something'))
        assert 'No recent warnings.' not in _plain(capsys)

    def test_multiple_log_messages_all_shown(self, capsys):
        _vmod._log_handler.emit(_make_record(logging.WARNING, 'first issue'))
        _vmod._log_handler.emit(_make_record(logging.ERROR, 'second issue'))
        output = _plain(capsys)
        assert 'first issue' in output
        assert 'second issue' in output

    def test_warning_count_header_singular(self, capsys):
        _vmod._log_handler.emit(_make_record(logging.WARNING, 'one thing'))
        assert '1 recent warning' in _plain(capsys)

    def test_warning_count_header_plural(self, capsys):
        _vmod._log_handler.emit(_make_record(logging.WARNING, 'thing one'))
        _vmod._log_handler.emit(_make_record(logging.WARNING, 'thing two'))
        assert '2 recent warnings' in _plain(capsys)

    def test_warning_count_header_absent_when_no_warnings(self, capsys):
        output = _plain(capsys)
        import re
        assert not re.search(r'\d+ recent warning', output)


# ─── Render mechanics ─────────────────────────────────────────────────────────

class TestRenderMechanics:
    def test_first_render_hides_cursor(self, capsys):
        assert '\033[?25l' in _render(capsys)

    def test_first_render_sets_initialized_flag(self, capsys):
        assert _vmod._display_initialized is False
        _vmod.display_thread_states()
        capsys.readouterr()
        assert _vmod._display_initialized is True

    def test_first_render_no_home_escape(self, capsys):
        assert '\033[H' not in _render(capsys)

    def test_subsequent_render_uses_home_escape(self, capsys):
        _vmod.display_thread_states()
        capsys.readouterr()
        _vmod.shared_state.rtiStatus = True
        assert '\033[H' in _render(capsys)

    def test_subsequent_render_erases_each_line(self, capsys):
        _vmod.display_thread_states()
        capsys.readouterr()
        _vmod.shared_state.rtiStatus = True
        second = _render(capsys)
        after_home = second.split('\033[H', 1)[1]
        assert '\033[K' in after_home

    def test_cursor_not_restored_between_renders(self, capsys):
        # \033[?25h (show cursor) must NOT appear mid-session
        _vmod.display_thread_states()
        capsys.readouterr()
        assert '\033[?25h' not in _render(capsys)
