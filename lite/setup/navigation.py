"""Main navigation and power actions for V-Link Lite Setup."""



class NavigationMixin:
    def power_action(self, action):
        choice = self.choose(f"Confirm {action}?", [("no", "Cancel"), ("yes", f"Yes, {action}")])
        if choice != "yes":
            return None
        self.busy(f"Requesting {action}")
        args = ["sudo", "-n", "/usr/sbin/reboot"] if action == "reboot" else [
            "sudo", "-n", "/usr/sbin/shutdown", "-h", "now"]
        status, output = self.command(args, 5)
        if status == 0:
            return 20 if action == "reboot" else 21
        self.message(f"Could not {action}: {output}")
        return None

    def main_menu(self):
        items = [("network", "Network"), ("audio", "Audio"),
                 ("display", "Display / Input"), ("storage", "Storage / USB"),
                 ("vlink", "V-Link"), ("diagnostics", "Diagnostics"),
                 ("terminal", "Terminal"),
                 ("continue", "Continue to V-Link / Exit Setup"),
                 ("reboot", "Reboot"), ("shutdown", "Shutdown")]
        while True:
            choice = self.choose("Choose a maintenance task", items)
            if choice in (None, "continue"):
                return 0
            if choice == "network":
                self.network_menu()
            elif choice == "audio":
                self.audio_menu()
            elif choice == "display":
                self.display_menu()
            elif choice == "storage":
                self.storage_menu()
            elif choice == "vlink":
                self.vlink_menu()
            elif choice == "diagnostics":
                self.diagnostics_menu()
            elif choice == "terminal":
                self.open_terminal()
            elif choice in ("reboot", "shutdown"):
                result = self.power_action(choice)
                if result is not None:
                    return result

