"""Diagnostics screens for V-Link Lite Setup."""

from v_link_lite_support import format_size, system_details

class DiagnosticsMixin:
    def diagnostics(self):
        self.busy("Running quick diagnostics")
        internet, _ = self.command(["curl", "--head", "--silent", "--fail",
                                    "--output", "/dev/null", "--connect-timeout", "2",
                                    "--max-time", "3", "https://www.debian.org/"], 4)
        chromium, _ = self.command(["pgrep", "-u", str(self.uid), "-x", "chromium"], 2)
        udiskie, _ = self.command(["pgrep", "-u", str(self.uid), "-x", "udiskie"], 2)
        _, mounts = self.command(["findmnt", "-rn", "-o", "TARGET"], 3)
        media_count = sum(path.startswith((f"/run/media/{self.username}/",
                                           f"/media/{self.username}/"))
                          for path in mounts.splitlines())
        _, ip_address = self.command(["ip", "-o", "-4", "address", "show", "scope", "global"], 2)
        addresses = ", ".join(line.split()[3] for line in ip_address.splitlines()
                              if len(line.split()) > 3) or "unavailable"
        _, uptime = self.command(["uptime", "-p"], 2)
        return "\n".join([
            f"NetworkManager: {self.service_state('NetworkManager.service')}",
            f"Internet: {'OK' if internet == 0 else 'unavailable'}",
            f"PipeWire: {self.service_state('pipewire.service', user=True)}",
            f"WirePlumber: {self.service_state('wireplumber.service', user=True)}",
            f"Wayland: {'OK' if self.display_available() else 'unavailable'}",
            f"V-Link service: {self.service_state('v-link.service', user=True)}",
            f"Chromium: {'running' if chromium == 0 else 'not running'}",
            f"udisks2: {self.service_state('udisks2.service')}",
            f"udiskie: {'running' if udiskie == 0 else 'not running'}",
            f"Local media mounts: {media_count}",
            f"IP address: {addresses}",
            f"Uptime: {uptime or 'unavailable'}",
        ])

    def diagnostics_menu(self):
        while True:
            self.busy("Reading system diagnostics")
            data = system_details(self.command)
            power = data["power"]
            if power is None or power["unknown_bits"]:
                throttle = "unavailable"
            else:
                throttle = "ACTIVE" if power["throttled_now"] or power["frequency_capped_now"] else "OK"
            total = data["ram_total"]
            used = data["ram_used"]
            disk_total = data["disk_total"]
            disk_used = data["disk_used"]
            summary = [
                f"CPU: {data['cpu']} %" if data["cpu"] is not None else "CPU: unavailable",
                f"Temperature: {data['temperature']:.1f} °C" if data["temperature"] is not None else "Temperature: unavailable",
                f"RAM: {round(100 * used / total)} %" if total and used is not None else "RAM: unavailable",
                f"Root disk: {round(100 * disk_used / disk_total)} %" if disk_total else "Root disk: unavailable",
                f"Throttling: {throttle}   Undervoltage: " +
                ("unavailable" if power is None or power["unknown_bits"] else
                 "ACTIVE" if power["undervoltage_now"] else "No"),
            ]
            choice = self.choose("Diagnostics", [
                ("system", "System details"), ("network", "Network details"),
                ("audio", "Audio details"), ("storage", "Storage details"),
                ("vlink", "V-Link details"), ("back", "Back")], summary=summary)
            if choice in (None, "back"):
                return
            if choice == "system":
                self.view("System details", self.format_system_details(data))
            elif choice == "network":
                self.view("Network details", self.network_status())
            elif choice == "audio":
                _, output = self.command(["wpctl", "status"], 3)
                self.view("Audio details", output)
            elif choice == "storage":
                self.view("Storage details", self.storage_status())
            else:
                self.view("V-Link details", self.diagnostics())

    @staticmethod
    def format_system_details(data):
        power = data["power"]
        def yes_no(value):
            return "Yes" if value else "No"
        def ratio(used, total):
            return (f"{format_size(used)} / {format_size(total)} "
                    f"({round(100 * used / total)} %)") if used is not None and total else "unavailable"
        lines = [
            f"Model: {data['model']}", f"CPU cores: {data['cores']}",
            f"CPU usage: {data['cpu']} %" if data["cpu"] is not None else "CPU usage: unavailable",
            f"Load: {data['load']}",
            f"Temperature: {data['temperature']:.1f} °C" if data["temperature"] is not None else "Temperature: unavailable",
            f"RAM used / total: {ratio(data['ram_used'], data['ram_total'])}",
            f"RAM available: {format_size(data['ram_available'])}",
            f"Root used / total: {ratio(data['disk_used'], data['disk_total'])}",
            f"Uptime: {data['uptime'] // 60} min" if data["uptime"] is not None else "Uptime: unavailable",
        ]
        if power is None or power["unknown_bits"]:
            lines.append("Power/throttling: unavailable")
        else:
            lines.extend([
                f"Current throttling: {yes_no(power['throttled_now'])}",
                f"Current undervoltage: {yes_no(power['undervoltage_now'])}",
                f"Throttling since boot: {yes_no(power['throttled_seen'])}",
                f"Undervoltage since boot: {yes_no(power['undervoltage_seen'])}",
                f"Frequency capped now/since boot: {yes_no(power['frequency_capped_now'])} / {yes_no(power['frequency_capped_seen'])}",
                f"Soft temp limit now/since boot: {yes_no(power['soft_temp_now'])} / {yes_no(power['soft_temp_seen'])}",
                f"Technical power value: {power['raw']}",
            ])
        return "\n".join(lines)

