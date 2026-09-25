"""Storage screens for V-Link Lite Setup."""

import json

class StorageMixin:
    def storage_status(self):
        _, devices = self.command(["lsblk", "-o", "NAME,LABEL,FSTYPE,SIZE,TRAN,MOUNTPOINT"], 4)
        udisks = self.service_state("udisks2.service")
        udiskie, _ = self.command(["pgrep", "-u", str(self.uid), "-x", "udiskie"], 2)
        return (f"Storage devices and mounts:\n{devices}\n\n"
                f"udisks2: {udisks}\nudiskie: {'running' if udiskie == 0 else 'not running'}")

    def storage_menu(self):
        while True:
            code, output = self.command(["lsblk", "-J", "-o",
                                          "NAME,LABEL,FSTYPE,SIZE,TRAN,MOUNTPOINT,RM,TYPE"], 4)
            devices = []
            if code == 0:
                try:
                    def collect(node, usb=False):
                        usb = usb or node.get("tran") == "usb"
                        if usb and (node.get("type") == "part" or
                                    (node.get("type") == "disk" and not node.get("children"))):
                            devices.append(f"{node.get('label') or node.get('name')}: {node.get('size')}  "
                                           f"{node.get('fstype') or 'unknown'}  "
                                           f"{'Mounted' if node.get('mountpoint') else 'Not mounted'}")
                        for child in node.get("children") or []:
                            collect(child, usb)
                    for device in json.loads(output).get("blockdevices", []):
                        collect(device)
                except (TypeError, ValueError, AttributeError):
                    pass
            udiskie, _ = self.command(["pgrep", "-u", str(self.uid), "-x", "udiskie"], 2)
            choice = self.choose("Storage / USB", [
                ("refresh", "Refresh"), ("details", "Technical details"), ("back", "Back")],
                summary=(devices[:3] or ["No removable USB volumes found."]) +
                        [f"Automount: {'OK' if udiskie == 0 else 'unavailable'}"])
            if choice in (None, "back"):
                return
            if choice == "details":
                self.view("Storage details", self.storage_status())

