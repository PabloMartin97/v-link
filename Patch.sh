#!/bin/sh
echo "Patching system for v3.0.3"

CONFIG_DIR="$HOME/.config/v-link"
UDEV_RULES_FILE="/etc/udev/rules.d/99-vlink.rules"

# Step 1: Remove old config files
if [ -d "$CONFIG_DIR" ]; then
    echo "Removing old config directory: $CONFIG_DIR"
    rm -rf "$CONFIG_DIR"
else
    echo "No existing config directory found at $CONFIG_DIR. Nothing to remove."
fi

echo "Patch completed. Rebooting now."
sleep 1

sudo reboot