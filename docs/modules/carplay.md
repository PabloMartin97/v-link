# CarPlay Module

## Purpose

The CarPlay module provides phone projection through a compatible Carlinkit USB dongle. Despite its name, the current configuration also enables Android-oriented behavior through `androidWorkMode` and standardized display resolutions.

The projection runtime is implemented with browser APIs and frontend workers:

- Chromium uses WebUSB to discover, authorize, and communicate with the dongle.
- A projection worker runs `node-carplay` and separates USB parsing from the React UI.
- A render worker decodes H.264 with WebCodecs and draws frames on an offscreen canvas.
- Audio uses shared ring buffers and browser audio output.
- Microphone audio is captured through the MediaDevices API and returned to the dongle.
- React coordinates lifecycle state, navigation, settings, touch, and key commands.

The Python backend serves the application, persists the main application configuration, and receives frontend log messages. Carlinkit communication and stream decoding run in Chromium.

## Architecture

```text
Phone
  |
  v
Carlinkit USB dongle
  |
  v
Chromium WebUSB
  |
  v
CarPlay.worker.ts
  |
  +-- H.264 data --> MessageChannel --> Render.worker.ts
  |                                      |
  |                                      +-> WebCodecs VideoDecoder
  |                                      +-> WebGL/WebGL2/Canvas2D
  |                                      +-> OffscreenCanvas
  |
  +-- PCM audio --> SharedArrayBuffer --> PcmPlayer
  |
  +-- commands --> React/session store
  |
  <-- touch, key commands, microphone PCM

React/Zustand
  |
  +-> connection UI and phase state
  +-> navigation and content visibility
  +-> persistent dongle settings via Socket.IO /app
```

## Main Files

| File | Responsibility |
| --- | --- |
| `frontend/src/carplay/Carplay.tsx` | Owns the projection runtime, workers, WebUSB lifecycle, recovery, configuration, and canvas. |
| `frontend/src/carplay/worker/CarPlay.worker.ts` | Runs `node-carplay`, reads dongle messages, and sends commands back to the dongle. |
| `frontend/src/carplay/worker/render/Render.worker.ts` | Parses and decodes H.264 frames and selects a renderer. |
| `frontend/src/carplay/worker/render/lib/h264-utils.ts` | Parses H.264 bitstreams and SPS data. |
| `frontend/src/carplay/worker/render/lib/utils.ts` | Detects keyframes and creates WebCodecs decoder configuration. |
| `frontend/src/carplay/worker/render/*Renderer.ts` | Draws decoded `VideoFrame` objects using WebGL, WebGL2, Canvas2D, or experimental WebGPU. |
| `frontend/src/carplay/useCarplayAudio.ts` | Creates PCM players and manages microphone capture. |
| `frontend/src/carplay/useCarplayTouch.ts` | Converts pointer input into normalized projection touch events. |
| `frontend/src/carplay/sessionState.ts` | Defines the projection state machine and compatibility flags. |
| `frontend/src/app/pages/carplay/Carplay.tsx` | Shows the pairing/connection screen above the projection runtime. |
| `frontend/src/App.tsx` | Keeps the projection runtime mounted, calculates its size, and forwards key bindings. |
| `frontend/src/app/Content.tsx` | Controls when the connection UI or decoded projection is visible. |
| `frontend/src/store/Store.ts` | Holds projection lifecycle and interface state. |
| `backend/config/app.json` | Contains default dongle settings and key bindings. |
| `backend/settings.py` | Persists the complete application configuration containing CarPlay settings. |
| `frontend/vite.config.ts` | Adds browser isolation headers and worker/browser polyfills required by the runtime. |

## Runtime Layers

Two different React components share the name `Carplay`:

1. `frontend/src/carplay/Carplay.tsx` is the persistent projection runtime. `App.tsx` mounts it once after application startup so the USB, audio, and worker session can continue while the user visits another view.
2. `frontend/src/app/pages/carplay/Carplay.tsx` is the visible connection page managed by `Content.tsx`. It displays pairing and phone-connection status when no decoded stream is being shown.

Keeping the projection runtime mounted prevents navigation away from CarPlay from automatically tearing down an otherwise healthy phone session.

## Configuration

CarPlay configuration is stored in `backend/config/app.json` under `dongle_config`. The generic Settings page renders it in the Dongle section.

| Setting | Default | Meaning |
| --- | --- | --- |
| `fps` | `60` | Requested projection frame rate. Supported UI options are 30 and 60. |
| `dpi` | `160` | Logical density reported to the projection system. |
| `format` | `5` | Video format value forwarded to `node-carplay`. |
| `iBoxVersion` | `2` | Dongle protocol/version setting forwarded to the driver. |
| `boxName` | `CarPlay` | Display name reported by the dongle configuration. |
| `nightMode` | `false` | Requests night-mode presentation. |
| `mediaDelay` | `300` | Media audio delay in milliseconds. |
| `audioTransferMode` | `false` | Selects the dongle audio-transfer behavior. |
| `wifiType` | `5ghz` | Wireless band used by the dongle: 2.4 GHz or 5 GHz. |
| `micType` | `os` | Selects dongle microphone or operating-system/browser microphone handling. |
| `camera` | `false` | Camera-related option forwarded to the dongle library. |
| `piMost` | `false` | Enables the PiMOST-related dongle option. |
| `delay` | `0` | MMI/control delay forwarded to the dongle. |
| `useStandardizedResolution` | `false` | V-Link-only option that snaps Android Auto output to a standard resolution. |

`dongle_config` is flattened before it reaches `node-carplay`: each `{ value, label, ... }` setting becomes a simple key/value pair. `useStandardizedResolution` is removed because it belongs to V-Link rather than the dongle driver.

`androidWorkMode` is set to `true` when it is absent. The current CarPlay viewport width and height are then added to the flattened configuration.

### Resolution calculation

`App.tsx` observes the application container and writes the available projection size to `APP.system.carplaySize`. When the top bar is enabled, its height is subtracted from the projection height.

Normally, the measured size is sent directly to the dongle. When `useStandardizedResolution` is enabled, the runtime selects the first standard resolution that is at least as large in both dimensions:

- 800×480
- 960×540
- 1024×600
- 1280×720
- 1920×1080
- 2560×1440
- 3840×2160

If none is large enough, the measured size remains unchanged.

## Persistence

Both `dongle_config` and `dongle_bindings` are stored inside the main application settings file:

```text
~/.config/v-link/app.json
```

The flow is:

1. The frontend requests application settings from Socket.IO `/app`.
2. `Socket.tsx` stores the result in `APP.settings`.
3. The generic Settings page edits `dongle_config` or `dongle_bindings`.
4. Manual save or autosave emits `save` on `/app`.
5. `backend/settings.py` writes the complete application settings object to disk.
6. The values are loaded again during the next application session.

Changing dongle settings updates the memoized runtime configuration. A running dongle session is not automatically restarted solely because the settings object changes; the updated configuration is applied the next time a projection start message is sent.

## Browser Requirements

The runtime depends on browser APIs that are normally available in Chromium-based environments:

- WebUSB for Carlinkit communication and user authorization.
- Web Workers and transferable `MessagePort` objects.
- OffscreenCanvas for worker-side rendering.
- WebCodecs `VideoDecoder` for H.264 decoding.
- SharedArrayBuffer for low-overhead PCM audio exchange.
- WebGL, WebGL2, or Canvas2D for drawing decoded frames.
- MediaDevices/getUserMedia for microphone capture.

The Vite development server sets `Cross-Origin-Embedder-Policy: require-corp` and `Cross-Origin-Opener-Policy: same-origin`. These headers enable the cross-origin isolation required by SharedArrayBuffer in modern browsers. The production backend also applies isolation headers to served assets.

Vite aliases Node-style `stream`, `buffer`, and `events` dependencies to browser-compatible packages. It also injects `Buffer` into the production bundle because `node-carplay` expects it.

## Projection Session State

`sessionState.ts` provides one centralized state machine. The principal `phase` values are:

| Phase | Meaning |
| --- | --- |
| `idle` | No dongle session is available. |
| `ready` | A dongle is present but projection has not started or the phone disconnected. |
| `starting` | The runtime requested a new projection session. |
| `connected` | The phone/session connected, but decoded video has not yet been confirmed. |
| `streaming` | The render worker decoded its first video frame. |
| `error` | Projection startup or worker operation failed. |

The state machine derives legacy boolean fields used by existing UI code:

- `dongle`: a Carlinkit dongle is available.
- `phone`: phase is connected or streaming.
- `worker`: mirrors phone-session availability for legacy consumers.
- `stream`: phase is streaming.
- `connected`: historically means confirmed video, so it mirrors `stream`.
- `transport`: currently `dongle`, with types reserved for future native Android Auto or native CarPlay transports.
- `error`: the current projection failure message.

Normal transitions are:

```text
idle
  -> dongleDetected -> ready
  -> startRequested -> starting
  -> phoneConnected -> connected
  -> streamStarted  -> streaming
```

If the phone disconnects while the dongle remains, the phase returns to `ready`. If the dongle disconnects, the complete session returns to `idle`. A failure moves the phase to `error` while retaining knowledge that the dongle is still attached.

## Pairing and USB Lifecycle

### Existing authorization

On startup, the runtime calls `findDevice()`. This detects a previously authorized compatible dongle without displaying a browser permission prompt.

When a device is found:

1. The store transitions to `dongleDetected`.
2. `paired` becomes true.
3. An idle, ready, or failed session transitions to `startRequested`.
4. The runtime sends the current configuration to the projection worker.

### First-time pairing

The visible connection page checks `navigator.usb.getDevices()` up to 15 times at one-second intervals. If no authorized dongle exists, it displays “CLICK TO PAIR DONGLE”.

Clicking the button dispatches the internal `pairDongle` event. The persistent runtime receives it and calls `requestDevice()`, which opens the browser WebUSB device chooser. Browser security requires this request to originate from a user gesture.

### USB connect and disconnect

The runtime assigns handlers to `navigator.usb.onconnect` and `navigator.usb.ondisconnect`.

On connection, it clears any pending detach timer, updates the state, and checks/starts the device.

On disconnection, it waits four seconds before treating the dongle as removed. This debounce handles temporary USB detach/reattach behavior. If `findDevice()` still finds the dongle, the session is left intact. Otherwise, recovery timers are cleared, the worker receives `stop`, and the session transitions to `dongleDisconnected`.

## Projection Worker

`CarPlay.worker.ts` isolates the USB protocol and `node-carplay` runtime from React.

### Initialization

React creates two `MessageChannel` instances:

- The video channel connects the projection worker to the render worker.
- The microphone channel connects browser microphone capture back to the projection worker.

The `initialise` message transfers one end of each channel to the worker. Microphone buffers received by the worker are wrapped in `SendAudio` and written to the dongle driver.

### Starting and stopping

`startProjection()`:

1. Clears audio buffering state and video counters.
2. Saves the current configuration.
3. Finds the WebUSB dongle.
4. Constructs `CarplayWeb` from `node-carplay`.
5. Registers the dongle message handler.
6. Starts the driver.

Lifecycle operations are serialized through a promise chain so start and stop operations cannot run concurrently.

Before startup, the worker temporarily replaces `USBDevice.reset()` with a no-op. This avoids a reset performed by `node-carplay` disrupting the active WebUSB setup. The original method is restored after startup.

`stopProjection()` clears the active instance, audio buffers, and counters; sends a reset event to the renderer; and stops the driver.

### Worker commands

| React message | Worker action |
| --- | --- |
| `initialise` | Stores video and microphone ports. |
| `start` | Starts projection with the supplied dongle configuration. |
| `stop` | Stops projection and resets rendering/audio state. |
| `frame` | Sends a fresh-frame command to the dongle. |
| `touch` | Sends normalized coordinates and touch action. |
| `keyCommand` | Sends an MMI/media command. |
| `audioBuffer` | Registers a shared PCM ring buffer for one audio format/type pair. |

### Dongle messages

The worker handles the principal message categories as follows:

- Video payloads are copied into isolated ArrayBuffers and transferred to the render worker.
- Audio payloads are pushed into the correct shared ring buffer.
- The first audio frames are temporarily queued while React creates the required player/buffer.
- Other messages, including phone plug/unplug and commands, are forwarded to React.

Video payloads must be explicitly copied. A Node `Buffer` may be only a view into a larger WebUSB transfer; transferring its original backing buffer could detach memory still used by the dongle parser or include unrelated bytes.

The worker resets the dongle driver's internal `errorCount` whenever it receives a valid message.

## Video Pipeline

### Transfer and decode

H.264 data travels from the projection worker to the render worker through a transferred `MessagePort` without passing through React state.

The render worker:

1. Reads Annex-B NAL units.
2. Detects SPS and IDR units.
3. Parses SPS metadata to obtain codec, coded width, and coded height.
4. Creates or reconfigures a WebCodecs `VideoDecoder` when the stream format changes.
5. Labels IDR frames as keyframes and other frames as delta frames.
6. Decodes each `EncodedVideoChunk`.
7. Keeps only the latest pending decoded frame when rendering falls behind.

When the first decoded frame arrives, the render worker emits `streamStarted`. React then transitions the projection phase from `connected` to `streaming` and exposes the canvas as the active CarPlay interface.

### Renderer selection

The render worker attempts renderers in this order:

1. WebGL
2. WebGL2
3. Canvas2D

Experimental WebGPU support exists but is currently disabled in the candidate list.

Each decoded `VideoFrame` is closed after drawing to release browser video resources. Decoder failures, configuration changes, and projection stops reset the decoder and discard pending frames.

## Audio and Microphone

### Output audio

Audio is separated by decode type and audio type. Each unique pair receives an `AudioPlayerKey` and its own `PcmPlayer`.

When the worker encounters a new audio stream:

1. It requests a buffer from React.
2. `useCarplayAudio()` resolves the format through `decodeTypeMap`.
3. It creates and starts a `PcmPlayer` with the required sample rate and channel count.
4. It transfers the player's SharedArrayBuffer reference to the projection worker.
5. Pending PCM frames are pushed into the new ring buffer.

Navigation and media/output start commands select their corresponding players and volumes. Volume-duration messages apply timed volume changes. Current default media and navigation volumes are both hardcoded to `1`.

The shared buffer is sent again when requested even if a player already exists, because a projection restart clears the worker's references while the React audio hook remains mounted.

### Microphone

On initialization, `useCarplayAudio()` requests browser microphone permission with `getUserMedia({ audio: true })`. `WebMicrophone` writes captured audio to the microphone `MessagePort`.

Dongle commands control recording:

- `startRecordAudio` starts the microphone.
- `stopRecordAudio` stops it.

Microphone permission or initialization failures are logged. Audio players are stopped when the audio hook unmounts.

## Touch and Key Controls

### Touch

The projection surface listens for pointer down, move, up, and cancel events. It captures the pointer after a down event and converts coordinates to the normalized 0–1 range before sending `TouchAction.Down`, `Move`, or `Up` to the worker.

Because the container uses `touch-action: none`, browser gestures do not interfere with projection input.

### Keyboard/MMI bindings

Default controls are stored under `dongle_bindings` in `app.json`. Supported actions include navigation, select, back, home, playback, track selection, and phone accept/reject.

`App.tsx` maps browser key codes to these actions. Commands normally reach CarPlay only while the CarPlay view is active; `next` and `prev` remain available as background media commands.

`selectDown` automatically sends `selectUp` after 200 ms. This creates a complete press/release action from one physical key event.

The settings page allows bindings to be changed. While assigning a new key, application key processing is paused so the assignment itself is not forwarded to CarPlay.

## Connection UI and Navigation

The connection page displays different messages based on session state:

- No authorized dongle: “CLICK TO PAIR DONGLE”.
- Dongle connected without a phone: “CONNECT iPHONE / ANDROID DEVICE”.
- Phone connected but video not yet decoded: “LAUNCHING...”.

The chain-link icon changes color and animation as pairing, phone, and worker flags change.

`Content.tsx` watches the projection phase. Only `streaming` sets `APP.system.interface.carplay` to true. At that point, the connection UI becomes transparent/non-interactive and the persistent projection canvas is exposed. Before confirmed video, the normal CarPlay connection page remains visible.

If the dongle sends `requestHostUI`:

- With `general.exitToDash` enabled, V-Link switches to Dashboard.
- Otherwise, the navigation bar is shown over the current interface.

The TopBar phone icon reflects `APP.system.carplay.phone`.

## Recovery and Failure Handling

### Startup watchdog

When the phone reports connected, a 12-second watchdog waits for the render worker to decode video. If no stream starts, recovery requests a fresh frame from the dongle.

Recovery uses exponential delays:

- 1 second
- 2 seconds
- 4 seconds
- 8 seconds
- 15 seconds

The runtime stops after five recovery attempts. A successful `streamStarted` event clears timers and resets the retry counter.

Recovery intentionally does not close and reopen WebUSB. `node-carplay` may have a permanently pending `transferIn()` call, and closing the device can race that read and cause `AbortError` or `InvalidStateError`. Requesting a fresh frame preserves a healthy phone/audio session.

### Worker failure

If projection startup or a serialized lifecycle operation fails:

1. The session moves to `error` with the failure message.
2. The failure is logged.
3. The page reloads after three seconds.

Reloading terminates the worker and allows Chromium to release outstanding WebUSB operations safely.

### Decoder failure

H.264 parser/configuration/decode errors reset only the decoder. Later SPS and keyframes may establish a clean decoder configuration without restarting the entire USB session.

## Backend Responsibilities

The backend provides these services to the CarPlay module:

- Serve the compiled frontend and assets.
- Provide cross-origin isolation headers on served assets.
- Load and save `dongle_config` and `dongle_bindings` as part of `app.json` through `/app`.
- Receive frontend logs through the logging namespace.
- Run unrelated vehicle and system modules alongside the browser projection runtime.

WebUSB permission, dongle availability, decoding, and audio problems are diagnosed through Chromium and frontend logs.

## Troubleshooting

### The dongle is not detected

- Use a Chromium browser with WebUSB support.
- Click the pairing button to open the device chooser on first use.
- Confirm the dongle appears in `navigator.usb.getDevices()` after authorization.
- Check the USB cable, power, and port.
- Inspect Chromium console logs for WebUSB errors.

### The phone connects but video never appears

- Wait for the 12-second watchdog and frame-recovery attempts.
- Check render-worker logs for SPS, codec, or WebCodecs failures.
- Verify the requested resolution and FPS are supported by the dongle/display combination.
- Try disabling standardized resolution or using a smaller display size.
- Reload the page to release a stalled WebUSB read.

### Video appears but audio does not

- Confirm SharedArrayBuffer is available and the page is cross-origin isolated.
- Check whether a supported `decodeType` exists in `decodeTypeMap`.
- Inspect logs for PCM player creation or ring-buffer errors.
- Verify system audio output and browser audio permissions/policies.

### Voice input does not work

- Grant Chromium microphone permission.
- Confirm the correct `micType` is selected.
- Check for `Failed to init microphone` in frontend/backend logs.
- Verify that the dongle sends start/stop recording commands.

### Touch coordinates are incorrect

- Confirm the projection container matches the visible canvas dimensions.
- Check whether browser zoom or external CSS transforms alter the pointer rectangle.
- Verify the configured resolution and actual decoded stream aspect ratio.

### Settings do not take effect immediately

The runtime memoizes the latest configuration, but it sends that configuration when starting a projection session. Disconnect/reconnect the phone or dongle, or restart the application, so a fresh session uses the new values.

