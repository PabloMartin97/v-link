"""Display and input screens for V-Link Lite Setup."""

from decimal import Decimal

from v_link_lite_support import load_settings, save_settings
import v_link_lite_display as lite_display

class DisplayMixin:
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

    def display_available(self):
        return lite_display.wayland_available(self.env)

