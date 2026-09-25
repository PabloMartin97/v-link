"""V-Link service and console screens for V-Link Lite Setup."""

import time

from v_link_lite_support import read_snapshot

class VLinkMixin:
    def vlink_menu(self):
        while True:
            state = self.service_state("v-link.service", user=True)
            _, start_us = self.command(["systemctl", "--user", "show", "v-link.service",
                                        "-p", "ActiveEnterTimestampMonotonic", "--value"], 2)
            try:
                uptime = f"{max(0, int(time.monotonic() - int(start_us) / 1000000)) // 60} min" if state == "active" else "-"
            except ValueError:
                uptime = "unavailable"
            _, service = self.command(["systemctl", "--user", "show", "v-link.service",
                                       "-p", "ExecStart", "--value"], 2)
            mode = "UI only" if "--no-hardware" in service else "Hardware"
            summary = [f"Status: {state}", f"Uptime: {uptime}", f"Mode: {mode}",
                       f"Console: {'Available' if state == 'active' else 'Not running'}"]
            if self.startup:
                items = [("console", "Console"), ("logs", "Logs"),
                         ("status", "Technical status"), ("back", "Back")]
                heading = "V-Link starts after Continue"
            else:
                items = [("console", "Console"), ("restart", "Restart V-Link"),
                         ("stop", "Stop V-Link"), ("start", "Start V-Link"),
                         ("logs", "Logs"), ("status", "Technical status"),
                         ("back", "Back")]
                heading = "V-Link"
            choice = self.choose(heading, items, summary=summary)
            if choice in (None, "back"):
                return
            if choice in ("start", "stop", "restart"):
                self.busy(f"V-Link {choice}")
                status, output = self.command(["systemctl", "--user", choice, "v-link.service"], 10)
                self.message(f"V-Link {choice} completed." if status == 0
                             else f"V-Link {choice} failed: {output}")
            elif choice == "status":
                self.busy("Reading V-Link status")
                _, output = self.command(["systemctl", "--user", "status",
                                          "v-link.service", "--no-pager"], 4)
                self.view("V-Link service", output)
            elif choice == "console":
                self.console()
            elif choice == "logs":
                self.busy("Reading V-Link logs")
                _, output = self.command(["journalctl", "--user", "-u", "v-link.service",
                                          "-n", "80", "--no-pager"], 5)
                self.view("V-Link recent log", output)

    def console(self):
        """Read a runtime snapshot; never attach to or control the V-Link PID."""
        self.screen.timeout(1000)
        try:
            while True:
                state = self.service_state("v-link.service", user=True)
                _, pid_text = self.command(["systemctl", "--user", "show", "v-link.service",
                                            "-p", "MainPID", "--value"], 2)
                try:
                    pid = int(pid_text)
                except ValueError:
                    pid = 0
                snapshot = read_snapshot(self.uid, pid) if state == "active" and pid else None
                if self.frame("V-Link Console", "Q / Esc: Back   (updates every second)"):
                    if state != "active":
                        self.put(7, 5, "V-Link is not running.")
                    elif not snapshot:
                        self.put(7, 5, "Status unavailable.")
                    else:
                        lines = [f"V-Link {snapshot.get('version', '?')} | Boosted Moose",
                                 f"Device: {snapshot.get('device', 'unavailable')}",
                                 f"RTI: {'Up' if snapshot.get('rti') else 'Down'}   "
                                 f"IGN: {'High' if snapshot.get('ign') else 'Low'}", "",
                                 "Thread          Status"]
                        for name, running in snapshot.get("threads", []):
                            lines.append(f"{str(name).upper():<15} {'running' if running else 'stopped'}")
                        lines += ["", "Recent warnings"]
                        lines += snapshot.get("warnings", []) or ["No recent warnings."]
                        height, _ = self.size()
                        for row, line in enumerate(lines[:max(0, height - 9)]):
                            self.put(6 + row, 5, line)
                self.flush()
                if self.screen.getch() in (27, ord("q"), ord("Q")):
                    return
        finally:
            self.screen.timeout(-1)

