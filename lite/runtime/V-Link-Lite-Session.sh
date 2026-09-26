#!/bin/sh

# wlroots visibility culling can expose a transient white frame when the
# Lite layer-shell splash is removed over fullscreen Chromium.
export WLR_SCENE_DISABLE_VISIBILITY=1

exec /usr/bin/labwc
