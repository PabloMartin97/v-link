"""Unit tests for the Chromium application thread."""

from unittest.mock import MagicMock

from backend.threads import app as app_module


def test_start_browser_passes_each_chromium_flag_as_separate_argument(monkeypatch):
    """Adjacent Chromium flags must not be joined by a missing list comma."""
    browser_process = MagicMock(pid=1234)
    popen = MagicMock(return_value=browser_process)

    monkeypatch.setattr(app_module.os, 'makedirs', MagicMock())
    monkeypatch.setattr(app_module.APPThread, '_browser_executable', lambda self: 'chromium')
    monkeypatch.setattr(app_module.subprocess, 'Popen', popen)
    monkeypatch.setattr(app_module.shared_state, 'isKiosk', False)

    app_thread = app_module.APPThread(MagicMock())
    app_thread.start_browser()

    command = popen.call_args.args[0]

    assert '--no-default-browser-check' in command
    assert '--allow-insecure-localhost' in command
    assert all(argument.count('--') == 1 for argument in command[2:])
