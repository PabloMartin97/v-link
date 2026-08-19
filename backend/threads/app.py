import threading
import time
import sys
import os
import subprocess
import signal
import shutil
import urllib.error
import urllib.request
from ..shared.shared_state import shared_state

class APPThread(threading.Thread):
    def __init__(self, logger):
        super().__init__()
        self.logger = logger

        self.url = f'http://localhost:{5173 if shared_state.vite else 4001}'
        self.browser = None
        self._stop_event = threading.Event()


    def run(self):
        while not self._stop_event.is_set():
            if(shared_state.toggle_app.is_set()):
                self.stop_thread()
                break

            if self.browser is None:
                try:
                    self.wait_for_frontend()
                    self.start_browser()
                except (OSError, subprocess.SubprocessError) as error:
                    self.logger.error(f'[Browser] Could not start Chromium: {error}')
                    self._stop_event.wait(3)
                continue

            exit_code = self.browser.poll()
            if exit_code is not None:
                self.logger.warning(f'[Browser] Chromium exited with code {exit_code}; restarting.')
                self.browser = None
                self._stop_event.wait(2)
                continue

            self._stop_event.wait(.1)

    def wait_for_frontend(self, timeout=30):
        deadline = time.monotonic() + timeout
        while not self._stop_event.is_set() and time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(self.url, timeout=1) as response:
                    if response.status < 500:
                        return
            except (urllib.error.URLError, TimeoutError):
                self._stop_event.wait(.25)

        if self._stop_event.is_set():
            raise OSError('browser startup cancelled')
        raise OSError(f'frontend did not become ready at {self.url} within {timeout}s')

    def stop_thread(self):
        self._stop_event.set()
        self.close_browser()
        shared_state.toggle_app.clear()

    def _browser_executable(self):
        preferred = 'chromium'
        fallback = 'chromium-browser'

        if shutil.which(preferred):
            return preferred
        if shutil.which(fallback):
            self.logger.warning(f'[Browser] "{preferred}" not found, using "{fallback}" instead.')
            return fallback

        return preferred


    def start_browser(self):
        profile_dir = os.path.expanduser('~/.config/v-link/chromium-profile')
        os.makedirs(profile_dir, exist_ok=True)

        standard_flags = [
            '--enable-experimental-web-platform-features',
            '--enable-features=SharedArrayBuffer',
            '--autoplay-policy=no-user-gesture-required',
            '--use-fake-ui-for-media-stream',
            '--noerrdialogs',
            '--disable-session-crashed-bubble',
            '--password-store=basic',
            '--log-level=1',
            f'--user-data-dir={profile_dir}',
            '--no-first-run',
            '--no-default-browser-check',
            '--allow-insecure-localhost',
            '--ozone-platform=wayland',
            '--unsafely-treat-insecure-origin-as-secure=http://localhost:4001,http://localhost:5173'
        ]

        if shared_state.isKiosk:
            mode = [
                '--kiosk',
                '--start-maximized'
            ]
        else:
            mode = [
                '--disable-resize',
                '--window-size=1280,720'
            ]

        flags = standard_flags + mode

        # Final command as list
        command = [self._browser_executable(), self.url] + flags

        self.browser = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            # Keep Chromium errors in the systemd journal for diagnosis.
            stderr=None,
            stdin=subprocess.DEVNULL
        )
        #self.browser = subprocess.Popen(command)
        self.logger.info(f'[Browser] Chromium browser started with PID: "{self.browser.pid}"')


    def close_browser(self):
        if self.browser:
            try:
                # First, terminate the main browser process gracefully
                self.browser.terminate()

                # Wait for the process to exit (timeout to avoid hanging)
                try:
                    self.browser.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.logger.warning('[Browser] Chromium did not close in time; Trying to kill thread.')
                    self.browser.kill()
                    self.browser.wait()

                # Then kill any remaining child processes (optional safety)
                subprocess.run(['pkill', '-P', str(self.browser.pid)], check=False)

            except Exception as e:
                self.logger.error(f'[Browser] Error stopping chromium: {e}')
        else:
            self.logger.error('[Browser] Chromium not found on this system.')
