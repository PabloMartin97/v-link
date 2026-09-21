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
LOGO = Path("/usr/local/share/v-link-lite/logo.png")
READY = threading.Event()
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

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.set_halign(Gtk.Align.CENTER)
        content.set_valign(Gtk.Align.CENTER)
        content.pack_start(Gtk.Image.new_from_file(str(LOGO)), False, False, 0)
        self.message = Gtk.Label()
        self.message.set_markup(
            '<span foreground="white">V-Link is taking longer than expected. '
            'Press S for Settings.</span>'
        )
        self.message.set_no_show_all(True)
        content.pack_start(self.message, False, False, 0)
        self.window.add(content)
        self.window.show_all()

        GLib.timeout_add(50, self.check_handoff)
        GLib.timeout_add_seconds(45, self.show_timeout)

    def on_map(self, *_):
        # The installer waits for the overlay to map before starting V-Link.
        VISIBLE.touch()
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
        return False

    def check_setup(self):
        if self.setup_process.poll() is None:
            return True
        exit_code = self.setup_process.returncode
        self.setup_process = None
        if READY.is_set() or exit_code in (20, 21, 22):
            self.window.destroy()
        else:
            self.window.show_all()
        return False

    def check_handoff(self):
        if READY.is_set():
            self.window.destroy()
            return False
        return True

    def show_timeout(self):
        if not READY.is_set():
            self.timed_out = True
            self.message.show()
            GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        return False


def main():
    if not RUNTIME_DIR.is_dir() or not LOGO.is_file():
        raise RuntimeError("Lite overlay runtime or logo is missing")
    server = HTTPServer(("127.0.0.1", 40777), HandoffHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        Overlay()
        Gtk.main()
    finally:
        server.shutdown()
        server.server_close()
        VISIBLE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
