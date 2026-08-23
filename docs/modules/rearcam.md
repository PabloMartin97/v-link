# Rear Camera Module

## Purpose

The rear camera module displays a browser video-input stream, controls camera power through GPIO, reacts automatically to the vehicle's reverse signal, and provides configurable parking guidelines.

The module is split across the backend and frontend:

- The backend reads the reverse GPIO input, controls the camera-power GPIO output, persists application settings, migrates old rear-camera settings, and publishes state through Socket.IO.

- The frontend selects and opens the video device through the browser MediaDevices API, renders the video and guidelines, switches views when reverse is engaged, and provides the rear-camera settings UI.

## Architecture

```text
Reverse GPIO input (BCM 20)
        |
        v
CAMThread -> shared_state.reverseStatus
        |
        v
ServerThread.monitor_reverse_state()
        |
        v
Socket.IO /sys: reverse
        |
        v
Socket.tsx -> APP.system.reverse
        |
        v
Content.tsx -> opens Rearcam view

Rearcam view mounted
        |
        +-> Socket.IO /rearcam: mount -> CameraGPIO (BCM 26) -> camera power
        |
        +-> navigator.mediaDevices.getUserMedia() -> browser video stream
        |
        +-> Standard SVG or Custom SVG guidelines
```

Rear-camera preferences are not stored in a separate `rearcam.json` file. They are part of the main application configuration under `reverseCam` and are persisted through the `/app` namespace.

## Main Files

| File | Responsibility |
| --- | --- |
| `backend/config/app.json` | Default rear-camera schema and values. |
| `backend/settings.py` | Loads, saves, validates, and migrates the rear-camera settings block. |
| `backend/threads/cam.py` | Reads the reverse input and controls the camera-power output. |
| `backend/server.py` | Publishes reverse state and exposes rear-camera GPIO Socket.IO events. |
| `frontend/src/socket/Namespaces.tsx` | Maps the frontend `cam` socket to `/rearcam`. |
| `frontend/src/socket/Socket.tsx` | Loads application settings and stores reverse/camera state in Zustand. |
| `frontend/src/app/Content.tsx` | Performs automatic navigation into and out of the Rearcam view. |
| `frontend/src/app/pages/rearcam/Rearcam.tsx` | Opens the browser video stream and renders guidelines and errors. |
| `frontend/src/app/pages/settings/RearcamSettings.tsx` | Renders controls dedicated to rear-camera configuration. |
| `frontend/src/app/pages/settings/Settings.tsx` | Integrates the rear-camera editor with global save/autosave behavior. |
| `frontend/src/app/sidebars/NavBar.tsx` | Shows or hides manual Rearcam navigation. |

## Configuration Schema

The default configuration lives in `backend/config/app.json` under `reverseCam`. The schema version is stored at `constants.rearcam_settings_version`.

`constants.rearcam_settings_reset_notice` records whether the one-time migration warning still needs to be shown. It is set to `true` only when an incompatible rear-camera block is reset.

| Setting | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | Shows Rearcam in manual navigation and view cycling. It does not disable automatic reverse activation. |
| `delay` | `7` | Seconds to wait after reverse is disengaged before returning to the previous view. |
| `deviceSelectionMode` | `auto` | Uses browser automatic selection or the saved `deviceId`. |
| `deviceId` | `default` | Browser device ID for a manually selected video input. |
| `videoResolution` | `Auto` | Preferred capture resolution. Supported presets are 640×360, 854×480, and 1280×720. |
| `videoFps` | `Auto` | Preferred video standard: automatic, PAL (25 FPS), or NTSC (30 FPS). |
| `guidelineMode` | `Standard` | Guideline display mode: Off, Standard, or Custom. |
| `guidelineNearWidth` | `80` | Width of the custom guides nearest to the vehicle, as a percentage. |
| `guidelineFarWidth` | `35` | Width of the far end of the custom guides, as a percentage. |
| `guidelineLength` | `55` | Custom guide length scaling. |
| `guidelineVerticalPosition` | `45` | Vertical position of the custom guide overlay. |
| `guidelineOpacity` | `100` | Custom guide opacity. |
| `guidelineLineThickness` | `65` | Custom guide line-thickness scaling. |

The strings used by enumerated settings are case-sensitive. For example, the renderer expects `Standard` and `Custom`, not lowercase variants.

## Persistence and Migration

### Persistence

The frontend Zustand store holds settings only while the application is running. Permanent storage is handled by the backend:

1. The frontend loads settings from the `/app` Socket.IO namespace.
2. Editing rear-camera settings updates the complete in-memory application settings object.
3. `Settings.tsx` sends that object with `socket.app.emit('save', settings)`.
4. The backend writes it to `~/.config/v-link/app.json`.
5. The same file is loaded on the next application start.

The `/rearcam` namespace intentionally ignores `load` and `save` configuration events. It controls hardware state only.

### Schema migration

`backend/settings.py` treats rear-camera schema changes as an explicit format boundary. It does not recursively combine old and new rear-camera objects.

At startup, `_rearcam_schema_is_current()` checks that:

- The saved block has exactly the current keys.
- Each setting has exactly the current structural fields.
- Labels, options, ranges, and steps match the current schema.
- Saved values have compatible types.
- Enumerated values are supported. A saved camera device ID is allowed to differ from the default.

If the schema version is missing/outdated or the structure is incompatible, only `reverseCam` is replaced with a deep copy of the current defaults. Unrelated application settings are preserved.

This reset deliberately removes legacy fields and structures, including:

- `deviceLabel`
- `videoWidth`
- `videoHeight`
- Numeric legacy `videoFps` values
- Object-based legacy `deviceSelectionMode.options` entries

After migration, `rearcam_settings_version` is updated, `rearcam_settings_reset_notice` is enabled, and the clean configuration is saved. Because the new default is `Standard`, upgraded legacy installations return to the standard static guidelines.

On the first subsequent visit to Rearcam, a red warning is rendered over the camera page. The frontend immediately persists the notice as acknowledged while keeping it visible for that mounted visit. It therefore remains pending across application restarts until Rearcam is actually opened, but does not appear again on later visits.

When the rear-camera schema changes again, increment `REARCAM_SETTINGS_VERSION` in `backend/settings.py` and `constants.rearcam_settings_version` in `backend/config/app.json` together.

## Backend

### Reverse input

`CAMThread` in `backend/threads/cam.py` reads the reverse signal from GPIO chip 0, BCM line 20 by default.

The input is active-high and is polled every 50 ms. A 120 ms debounce prevents short electrical changes from being interpreted as a gear change. Stable transitions set or clear `shared_state.reverseStatus`.

`ServerThread.monitor_reverse_state()` checks this shared event every 100 ms and emits a boolean `reverse` event on the `/sys` namespace whenever it changes. A newly connected `/sys` client also receives the current ignition and reverse state.

### Camera-power output

`CameraGPIO` controls GPIO chip 0, BCM line 26 by default. The driver is created lazily the first time a rear-camera hardware event needs it.

Its public operations are:

- `set(on)`: sets the logical camera power state.
- `get()`: returns the last requested logical state, not a fresh physical GPIO read.
- `toggle()`: inverts the logical state.
- `level()`: reads the electrical level when possible.
- `cleanup()`: switches the output off and releases the GPIO chip.

Cleanup is registered with `atexit` so the camera output is turned off when the process exits normally.

### Rear-camera Socket.IO namespace

The backend registers `/rearcam` as a supported module and provides these events:

| Client event | Backend action | Response |
| --- | --- | --- |
| `mount` | Sets camera-power GPIO on. | `state` and `camera/status`. |
| `unmount` | Sets camera-power GPIO off. | `state` and `camera/status`. |
| `status` | Returns the last requested logical GPIO state. | `camera/status`. |
| `toggle` | Inverts the camera-power GPIO. | `state` and `camera/status`. |
| `ping` | Reports the current rear-camera GPIO state. | `state`. |
| `load` | Returns an empty settings object. | `settings: {}`. |
| `save` | Intentionally does nothing for rearcam. | None. |

`camera/status` contains:

```json
{
  "on": true,
  "error": "optional error message"
}
```

Compatibility aliases `rearcam:mount` and `rearcam:unmount` also exist on the root namespace.

Hardware exceptions are logged and sent to the frontend as `on: false` with an error message.

## Frontend

### Socket and store state

`Namespaces.tsx` exposes the backend `/rearcam` namespace as `socket.cam`:

```ts
cam: io("ws://localhost:4001/rearcam")
```

`Socket.tsx` listens for:

- `/sys` `reverse` and writes the value to `APP.system.reverse`.
- `/rearcam` `camera/status` and writes `on` and `error` to `APP.system.rearcam` and `APP.system.rearcamError`.
- `/rearcam` `state` and updates `APP.system.rearcam`.

Application configuration received from `/app` is stored in `APP.settings`, including the complete `reverseCam` block.

### Automatic navigation

`Content.tsx` watches `APP.system.reverse` independently of the `enabled` navigation preference.

When reverse becomes active:

1. Any pending exit timer is cancelled.
2. The current view is remembered.
3. The application switches immediately to `Rearcam` without the normal page-transition delay.

When reverse becomes inactive:

1. Rearcam remains visible for `reverseCam.delay` seconds.
2. The application returns to the remembered view, or Dashboard when no previous view is available.

The `enabled` setting only controls whether Rearcam appears in the navbar and normal view cycling. Automatic reverse navigation still works when it is disabled.

### Rearcam component lifecycle

When `Rearcam.tsx` mounts, it emits `mount` through `socket.cam`, powering the camera through the backend. It emits `unmount` when leaving the view.

The browser video lifecycle is separate from GPIO power:

1. Existing MediaStream tracks are stopped.
2. Browser constraints are built from the saved settings.
3. `navigator.mediaDevices.getUserMedia()` opens the video input.
4. The stream is assigned to the `<video>` element and playback starts.
5. The component waits up to 10 seconds for actual video data.
6. The state becomes `playing`, or a user-facing error is displayed.

Each open request receives an internal request ID. If settings change or the user leaves while an asynchronous request is still running, the stale stream is stopped instead of replacing the current stream.

The camera is reopened when device selection, device ID, resolution, or video standard changes. A browser `devicechange` event also triggers a retry unless camera permission was denied.

### Browser video constraints

Resolution and frame rate use `ideal` constraints, allowing Chromium to choose a supported fallback:

- PAL requests an ideal 25 FPS.
- NTSC requests an ideal 30 FPS.
- A resolution preset requests its parsed width and height.
- Auto leaves the corresponding constraint unset.

A manually selected camera uses an `exact` device ID only when that ID currently exists. If a saved device is disconnected or its ID changes after moving USB ports, the component falls back to browser selection for that session without deleting the saved preference.

### Error handling

The component provides specific messages for:

- Permission denied.
- No video device found.
- Device present but unreadable or already in use.
- Unsupported constraints.
- Browser security restrictions.
- Aborted startup.
- Playback or decoding failure.
- No frames received within 10 seconds.
- A stream ending after startup, including device disconnection.

All active MediaStream tracks are stopped when the component unmounts, a request becomes stale, or an error occurs.

## Guidelines

### Off

No parking guideline overlay is rendered.

### Standard

The static asset `/assets/svg/graphics/guidelines.svg` is centered over the video at 90% width. This is the default mode and represents the guidelines used by previous installations.

### Custom

The custom mode creates an SVG overlay from colored line segments and crossbars. Near width, far width, length, vertical position, opacity, and thickness are read from settings and clamped to safe rendering ranges.

Green, yellow, and red sections indicate progressively closer guide areas. The geometry is currently static relative to the screen and does not use steering-angle data.

## Settings UI

The Settings sidebar opens the `rearcam` settings page. `Settings.tsx` passes the current `reverseCam` block to `RearcamSettings.tsx` and receives a complete updated block through `onChange`.

`RearcamSettings.tsx` is responsible for:

- Enumerating browser `videoinput` devices.
- Generating fallback names when browser permissions hide device labels.
- Numbering devices with duplicate labels.
- Refreshing the device list on `devicechange`.
- Keeping a disconnected saved device visible as “Saved camera (not currently available)”.
- Rendering string values as selects, booleans as toggles, and numbers as inputs.
- Hiding custom geometry fields unless guideline mode is `Custom`.

The component does not save directly. `Settings.tsx` merges the changed `reverseCam` block into the full application settings and uses the existing manual-save or debounced autosave flow. This ensures rear-camera changes are persisted through `/app` in the same way as all other application settings.

## Troubleshooting

### Rearcam opens but displays no video

- Confirm the capture device appears as a browser `videoinput`.
- Check camera power, video cable, grabber input channel, and PAL/NTSC selection.
- Try Auto resolution and Auto FPS.
- Verify Chromium camera permissions.
- Ensure another application is not using the device.

### The saved camera is unavailable

USB device IDs may change when a capture device is moved to another port. Reconnect it, select the current device in Settings, and save again. Until then, Rearcam falls back to automatic device selection for that session.

### Rearcam does not open when reverse is engaged

- Verify the reverse signal reaches BCM 20.
- Check backend logs for reverse GPIO initialization/read errors.
- Confirm `/sys` emits the `reverse` event and the frontend socket is connected.
- The `Show in Navigation` toggle does not control automatic reverse activation.

### Camera power does not switch

- Verify the power-control circuit is connected to BCM 26.
- Check that the backend process has GPIO permissions.
- Inspect `/rearcam` `camera/status` errors and backend logs.
- Remember that `CameraGPIO.get()` reports the requested logical state, not independently verified physical power.

### Rear-camera preferences reset after an update

This happens intentionally when the saved rear-camera version or structure is incompatible with the current schema. Only the `reverseCam` block is reset; configure it once in the new format and save it. Other application settings should remain unchanged.

## Future Work

The current custom guides are static. Dynamic-guidelines will be implemented reading a configurable steering-angle CAN signal and add center offset, direction, and curve-strength calibration before rendering curved guide paths.
