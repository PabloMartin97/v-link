#!/usr/bin/env python3
"""Cover Chromium's first window until the V-Link splash is ready."""

import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell


RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
VISIBLE = RUNTIME_DIR / "v-link-lite-overlay-visible"
SPLASH = Path("/usr/local/share/v-link-lite/splash.png")
READY = threading.Event()
SLOW_BOOT_SECONDS = 45
MAX_COVER_SECONDS = 120
HANDOFF_GRACE_MS = 500
PIXEL = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01"
         b"\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


class HandoffHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path != "/ready":
            self.send_error(404)
            return
        READY.set()
        self.send_response(200)
        self.send_header("Content-Type", "image/gif")
        self.send_header("Content-Length", str(len(PIXEL)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(PIXEL)

    def log_message(self, *_):
        pass


class Overlay:
    def __init__(self):
        self.setup_process = None
        self.timed_out = False
        self.handoff_scheduled = False

        self.window = Gtk.Window()
        self.window.set_decorated(False)
        self.window.connect("destroy", lambda *_: Gtk.main_quit())
        self.window.connect("map-event", self.on_map)
        self.window.connect("key-press-event", self.on_key)
        black = Gdk.RGBA()
        black.parse("black")
        self.window.override_background_color(Gtk.StateFlags.NORMAL, black)

        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_namespace(self.window, "v-link-lite-splash")
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self.window, edge, True)
        GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.NONE)

        content = Gtk.Overlay()
        splash = Gtk.Image.new_from_file(str(SPLASH))
        splash.set_halign(Gtk.Align.CENTER)
        splash.set_valign(Gtk.Align.CENTER)
        content.add(splash)

        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        controls.set_halign(Gtk.Align.CENTER)
        controls.set_valign(Gtk.Align.CENTER)
        self.message = Gtk.Label()
        self.message.set_markup(
            '<span foreground="white">V-Link is taking longer than expected. '
            'Press S for Settings.</span>'
        )
        self.message.set_no_show_all(True)
        controls.pack_start(self.message, False, False, 0)
        self.continue_button = Gtk.Button(label="Continue to V-Link")
        self.continue_button.set_no_show_all(True)
        self.continue_button.connect("clicked", lambda *_: self.window.destroy())
        controls.pack_start(self.continue_button, False, False, 0)
        content.add_overlay(controls)
        self.window.add(content)
        self.window.show_all()

        GLib.timeout_add(50, self.check_handoff)
        GLib.timeout_add_seconds(SLOW_BOOT_SECONDS, self.show_timeout)
        GLib.timeout_add_seconds(MAX_COVER_SECONDS, self.absolute_timeout)

    def on_map(self, *_):
        # The installer waits for the overlay to map before starting V-Link.
        temporary = VISIBLE.with_name(f'.{VISIBLE.name}.{os.getpid()}')
        try:
            temporary.write_text(f'{os.getpid()}\n', encoding='ascii')
            temporary.replace(VISIBLE)
        finally:
            temporary.unlink(missing_ok=True)
        return False

    def on_key(self, _window, event):
        if self.timed_out and event.keyval in (Gdk.KEY_s, Gdk.KEY_S) and self.setup_process is None:
            self.window.hide()
            try:
                self.setup_process = subprocess.Popen([
                    "foot", "--fullscreen", "--font=monospace:size=16",
                    "--title=V-Link Lite Setup",
                    "--app-id=v-link-lite-setup", "/usr/local/bin/v-link-lite-setup",
                ])
            except OSError:
                self.window.show_all()
                return True
            GLib.timeout_add(100, self.check_setup)
            return True
        if self.timed_out and event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.window.destroy()
            return True
        return False

    def check_setup(self):
        if self.setup_process.poll() is None:
            return True
        exit_code = self.setup_process.returncode
        self.setup_process = None
        if READY.is_set():
            self.schedule_handoff()
        elif exit_code in (20, 21, 22):
            self.window.destroy()
        else:
            self.window.show_all()
        return False

    def schedule_handoff(self):
        if not self.handoff_scheduled:
            self.handoff_scheduled = True
            GLib.timeout_add(HANDOFF_GRACE_MS, self.finish_handoff)

    def finish_handoff(self):
        self.window.destroy()
        return False

    def check_handoff(self):
        if READY.is_set():
            self.schedule_handoff()
            return False
        return True

    def show_timeout(self):
        if not READY.is_set():
            self.timed_out = True
            self.message.show()
            self.continue_button.show()
            GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        return False

    def absolute_timeout(self):
        # Normal handoff wins. A changed frontend must not leave a working
        # kiosk permanently hidden; Setup keeps its own window if open.
        if not READY.is_set():
            self.window.destroy()
        return False


def main():
    if not RUNTIME_DIR.is_dir() or not SPLASH.is_file():
        raise RuntimeError("Lite overlay runtime or splash is missing")
    server = HTTPServer(("127.0.0.1", 40777), HandoffHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        Overlay()
        Gtk.main()
    finally:
        server.shutdown()
        server.server_close()
        try:
            if int(VISIBLE.read_text(encoding="ascii").strip()) == os.getpid():
                VISIBLE.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    main()
