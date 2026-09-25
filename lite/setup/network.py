"""Network screens for V-Link Lite Setup."""

import curses
import subprocess

class NetworkMixin:
    def network_status(self):
        self.busy("Reading network status")
        _, devices = self.command(["nmcli", "-f", "DEVICE,TYPE,STATE,CONNECTION",
                                   "device", "status"], timeout=3)
        _, addresses = self.command(["ip", "-brief", "-4", "address", "show"], timeout=2)
        return f"NetworkManager devices:\n{devices}\n\nIPv4 addresses:\n{addresses}"

    def open_nmtui(self):
        self.busy("Opening Network configuration")
        curses.def_prog_mode()
        curses.endwin()
        try:
            result = subprocess.run(["nmtui"], env=self.env, check=False)
            error = "" if result.returncode == 0 else f"nmtui exited with status {result.returncode}."
        except FileNotFoundError:
            error = "nmtui is unavailable."
        except OSError as exc:
            error = str(exc)
        finally:
            curses.reset_prog_mode()
            self.screen.touchwin()
        if error:
            self.message(error)

    def network_menu(self):
        while True:
            self.busy("Reading network")
            code, raw = self.command(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION",
                                      "device", "status"], 3)
            summary = ["Ethernet: unavailable", "Wi-Fi: unavailable", "IP: unavailable"]
            if code == 0:
                connected_device = None
                for line in raw.splitlines():
                    parts = line.split(":", 3)
                    if len(parts) < 4:
                        continue
                    device, kind, state, connection = parts
                    if kind == "ethernet":
                        summary[0] = f"Ethernet: {state}"
                    elif kind == "wifi":
                        summary[1] = f"Wi-Fi: {state}"
                        if state == "connected":
                            _, wifi = self.command(["nmcli", "-t", "-f", "IN-USE,SSID",
                                                    "device", "wifi", "list", "--rescan", "no"], 2)
                            ssid = next((entry[2:] for entry in wifi.splitlines() if entry.startswith("*:")), "")
                            if ssid:
                                summary[1] += f"  SSID: {ssid}"
                    if state == "connected" and kind in ("ethernet", "wifi"):
                        connected_device = connected_device or device
                if connected_device:
                    _, ip = self.command(["nmcli", "-g", "IP4.ADDRESS", "device", "show", connected_device], 2)
                    summary[2] = f"IP: {ip.splitlines()[0] if ip else 'unavailable'}"
            choice = self.choose("Network", [
                ("configure", "Configure network"), ("details", "Technical details"),
                ("back", "Back")], summary=summary)
            if choice in (None, "back"):
                return
            if choice == "configure":
                self.open_nmtui()
            else:
                self.view("Network details", self.network_status())

