# Media Module

## Purpose

The Media module provides one interface for projected phone media and audio files stored locally on the V-Link device or mounted storage.

It is responsible for:

- Receiving metadata, artwork, playback state, and projection source from CarPlay or Android Auto.
- Presenting projected media in the Now Playing screen.
- Sending previous, play/pause, and next commands to the projection dongle.
- Browsing local and mounted storage through a protected backend API.
- Browsing a user-selected directory through the browser File System Access API.
- Playing supported local audio files with the native HTML audio element.
- Coordinating audio focus between projected and local media.
- Routing projected media, navigation, call, Siri, and alert audio.
- Applying navigation ducking to projected and local media.
- Configuring navigation volume, call volume, ducking intensity, and microphone gain.

## Architecture

```text
Phone projection
       |
       v
Carlinkit / node-carplay
       |
       v
CarPlay.worker.ts
       |
       +-- media metadata/artwork --> Carplay.tsx --> Zustand media state
       |
       +-- PCM audio -------------> shared ring buffers --> PcmPlayer
       |
       +-- audio commands --------> routing, priority, ducking, mic control
       |
       <-- Now Playing controls / MMI commands

Mounted/local storage
       |
       +-- Flask /api/media -----------+
       |                               |
       +-- File System Access API -----+--> LocalMediaProvider --> <audio>
                                               |
                                               +-> NativePlayer
                                               +-> audio focus
                                               +-> navigation ducking

Music page
       |
       +-> projected Now Playing
       +-> local file browser
       +-> native local player
```

## Main Files

| File | Responsibility |
| --- | --- |
| `backend/media.py` | Defines the media API blueprint for safe roots, directory browsing, and audio-file streaming. |
| `backend/server.py` | Configures Flask and registers the media API blueprint. |
| `frontend/src/carplay/worker/CarPlay.worker.ts` | Receives projection messages and forwards media/audio data to React or shared audio buffers. |
| `frontend/src/carplay/Carplay.tsx` | Converts worker media/audio events into store updates and audio actions. |
| `frontend/src/carplay/mediaState.ts` | Defines projected media state and merges partial metadata/artwork updates. |
| `frontend/src/carplay/mediaCommands.ts` | Dispatches projected-media commands from UI components to the CarPlay runtime. |
| `frontend/src/carplay/useCarplayAudio.ts` | Creates PCM players, classifies routes, manages volume priority, ducking, and microphone gain. |
| `frontend/src/app/pages/music/Music.tsx` | Connects the Music page to projected media state. |
| `frontend/src/app/pages/music/components/NowPlaying.tsx` | Selects projected, local, browser, or empty media UI. |
| `frontend/src/app/pages/music/LocalMediaProvider.tsx` | Owns the native audio player, playlist, focus, persistence, shuffle, repeat, and folder access. |
| `frontend/src/app/pages/music/components/UsbMediaBrowser.tsx` | Browses backend-mounted locations or a browser-selected folder. |
| `frontend/src/app/pages/music/components/NativePlayer.tsx` | Renders local playback state and controls. |
| `frontend/src/app/pages/music/localMediaCommands.ts` | Routes global media keys to the native player. |
| `frontend/src/app/pages/settings/AudioSettings.tsx` | Renders audio sliders, microphone test, and reset controls. |
| `frontend/src/app/pages/settings/audioSettingsState.ts` | Persists and distributes audio settings and navigation-ducking events. |
| `frontend/src/store/Store.ts` | Stores projected media, projection source, and current audio focus. |
| `frontend/src/App.tsx` | Mounts the local-media provider and routes global key commands according to audio focus. |

## Global Media State

The Zustand application store contains two pieces of state used by the Media module.

### Projected media

`APP.system.carplay.media` has this shape:

```ts
interface CarplayMediaState {
  title: string
  artist: string
  album: string
  appName: string
  durationMs: number
  positionMs: number
  playbackStatus: number
  artworkBase64: string | null
}
```

The initial value contains empty strings, zero times/status, and no artwork.

`APP.system.carplay.source` identifies the connected projection protocol as `CarPlay`, `Android Auto`, or `null`.

### Audio focus

`APP.system.audioSource` is either:

- `carplay`: projected media owns normal media playback.
- `local`: the native HTML audio player owns normal media playback.

This value coordinates the two media players. It does not disable high-priority projected audio such as navigation, calls, Siri, or alerts.

## Projection Source Detection

When `node-carplay` reports a `Plugged` message, the projection worker reads `phoneType`:

- `AndroidAuto` and `AndroidMirror` become `Android Auto`.
- Other supported phone types become `CarPlay`.

The worker sends a `projectionSource` message to the React runtime, which stores the source in `APP.system.carplay.source`. The Music page uses it as a fallback label when the media application name is unavailable.

The source is cleared when the phone or dongle disconnects.

## Projected Metadata Pipeline

### From the dongle to the store

`CarPlay.worker.ts` forwards `node-carplay` media messages to the React runtime. In `Carplay.tsx`, the `media` worker event extracts `message.payload` and passes it to `mergeCarplayMedia()`.

The dongle sends metadata and artwork as separate payloads. The merge function deliberately updates only fields present in the new payload so a partial message does not erase previously received information.

### Metadata payloads

For payload `type === 1`, these dongle fields are mapped:

| Dongle field | Store field |
| --- | --- |
| `MediaSongName` | `title` |
| `MediaArtistName` | `artist` |
| `MediaAlbumName` | `album` |
| `MediaAPPName` | `appName` |
| `MediaSongDuration` | `durationMs` |
| `MediaSongPlayTime` | `positionMs` |
| `MediaPlayStatus` | `playbackStatus` |

`MediaPlayStatus` is handled even though the installed `node-carplay` TypeScript definition does not declare that optional field.

### Artwork payloads

Non-metadata payloads update `artworkBase64` without clearing title, artist, album, timing, or status.

The Now Playing helper accepts an already complete `data:` URL. Otherwise, it treats the value as JPEG base64 and adds:

```text
data:image/jpeg;base64,
```

### Playback status fallback

Metadata does not always provide timely play status. Audio commands therefore also update it:

- `AudioMediaStart` and `AudioOutputStart` set status to playing.
- `AudioMediaStop` and `AudioOutputStop` set status to stopped.
- Navigation, calls, Siri, alerts, and unrelated commands leave the existing media status unchanged.

When the phone disconnects, the source and complete projected-media object are cleared.

## Projected Now Playing Screen

`Music.tsx` reads projected media, phone connection, and source from the store and passes them to `NowPlaying`.

When projected audio owns focus, Now Playing displays:

- Album artwork or a music-note placeholder.
- Media app name, or projection source as fallback.
- Track title.
- Artist and album.
- Elapsed and total time.
- A progress bar derived from position/duration.
- Previous, play/pause, and next controls.
- A Local Media button.

Missing metadata is handled explicitly:

- Title falls back to “Now Playing”.
- Artist becomes “Unknown artist” when other media data exists.
- With no useful metadata, it displays “Metadata unavailable”.
- Invalid or zero duration produces zero progress and `0:00`.

When no phone is connected, the page shows an empty state with an option to open Local Media.

## Projected Media Commands

UI controls call `sendCarplayMediaCommand()`, which dispatches the internal `carplayMediaCommand` event. The persistent CarPlay runtime receives the event and sends a `keyCommand` message to its worker.

Supported commands are:

- `prev`
- `play`
- `pause`
- `playOrPause`
- `next`

The worker wraps the command in `SendCommand` and writes it to the dongle driver.

For responsive UI feedback, `playOrPause` optimistically toggles the stored playback status before confirmation arrives from the phone.

## Local Media Provider

`LocalMediaProvider` is mounted around the running application in `App.tsx`. This keeps the native `<audio>` element and selected playlist alive while the user changes pages.

The provider owns:

- Current folder name and track list.
- Current track index.
- Playback error.
- Playing/paused state.
- Position and duration in seconds.
- Shuffle state and shuffle history.
- Repeat mode.
- The hidden HTML audio element.
- Object URLs created for browser-selected files.

Supported extensions are:

- AAC
- FLAC
- M4A
- MP3
- OGG
- Opus
- WAV
- WebM

For browser-selected files, a valid `audio/*` MIME type is also accepted.

## Local Media Sources

There are two file-access strategies.

### Backend-mounted storage

The production UI first requests media locations from the Python backend. By default, the available roots are existing directories among:

```text
~/Music
/media
/mnt
```

This covers media stored in the Pi user's music directory and storage commonly mounted under `/media` or `/mnt`. Deployments can override this list through the Flask `MEDIA_ROOTS` configuration value.

### Browser directory picker

The Choose Folder action uses `window.showDirectoryPicker()` when supported. This is useful in development or when the user needs to select a directory directly through Chromium.

Only files in the selected directory are loaded; this browser path does not recursively scan subdirectories. Files are sorted by name using numeric-aware ordering.

The selected directory handle is stored in IndexedDB when possible. On a later session, the provider queries its read permission:

- If permission is still granted, the directory is loaded automatically.
- Otherwise, the handle is retained and permission is requested the next time the user selects Choose Folder.

IndexedDB and persistent handles are optional. Folder selection and playback continue to work when storage persistence is unavailable.

## Backend Media API

The backend provides three HTTP endpoints on port 4001. These endpoints intentionally do not require authentication because V-Link is designed to run in an isolated, air-gapped environment; deployments on a shared network must add an appropriate access-control boundary.

### `GET /api/media/roots`

Returns the currently available allowed roots:

```json
[
  { "name": "Music", "path": "/home/pi/Music" },
  { "name": "media", "path": "/media" }
]
```

### `GET /api/media/browse?path=...`

Returns the selected directory and its immediate entries:

```json
{
  "name": "Album",
  "path": "/media/usb/Album",
  "entries": [
    { "kind": "directory", "name": "Disc 2", "path": "/media/usb/Album/Disc 2" },
    { "kind": "file", "name": "01 Track.mp3", "path": "/media/usb/Album/01 Track.mp3" }
  ]
}
```

Hidden entries are omitted. Directories are sorted before files, then alphabetically. Directory and file checks do not follow symbolic links while listing.

### `GET /api/media/file?path=...`

Streams a supported audio file with Flask `send_file(..., conditional=True)`. Conditional responses allow the browser media element to request byte ranges and seek efficiently.

### Path security

Every requested path is normalized with `realpath()` and must equal an allowed root or remain below one. Requests escaping the allowed roots return HTTP 403. Missing directories/files and unsupported file extensions return HTTP 404.

This validation also prevents a path passed through a symbolic link from escaping the configured media roots.

## File Browser UI

`UsbMediaBrowser` attempts to load backend roots when it opens.

If the backend responds, the user can:

- Enter allowed roots and nested directories.
- See directories and supported audio files.
- Navigate back through a local path-history stack.
- Select a file, which turns the other files in that directory into the active playlist.

If the backend is unavailable, the component falls back to the browser-selected playlist and keeps the native Choose Folder action available.

The browser supports pointer input and MMI/key bindings. From the main Music view, Down opens the browser while Up remains reserved for switching top-level V-Link pages:

- Left/right changes the focused entry and wraps at the ends.
- Select enters a directory or starts a file.
- Back closes the browser and returns to the main Music view.
- The on-screen Back button moves to the previous backend directory, returns to roots, or closes the browser.
- The focused entry is scrolled into view.

## Starting Local Playback

When a local track is selected:

1. If a projected phone session exists, V-Link sends `pause` to the projection session.
2. `APP.system.audioSource` changes to `local` before playback begins.
3. The current playlist index and shuffle history are updated.
4. The HTML audio element receives either an object URL or backend file URL.
5. The chosen track identity is stored.
6. `audio.play()` starts playback.

Claiming audio focus before calling `play()` ensures projected media is muted before the first local audio sample reaches the speakers.

If local playback fails, focus returns to `carplay` and a user-facing error identifies the unsupported file.

When projected media later sends `AudioMediaStart`, focus switches back to `carplay`. The provider watches that value and pauses an active local player.

## Native Player

When local focus is active and a track exists, `NowPlaying` renders `NativePlayer` instead of projected metadata.

The native player displays:

- The filename without its extension as title.
- The selected folder name as secondary text.
- Remaining and total time.
- Shuffle, previous, play/pause, next, and repeat controls.
- A Browse Files action.

Local files currently do not parse embedded title, artist, album, or artwork tags. The filename and folder name provide the visible metadata.

### Shuffle

Shuffle chooses a random track different from the current one when possible. A history stack supports returning to previously selected shuffled tracks.

### Repeat

Repeat cycles through:

- `off`: stop at the end of the final track.
- `all`: return to the first track after the final track.
- `one`: restart the current track when it ends.

Without shuffle, Previous selects the preceding track or restarts the first track. Next advances normally and respects repeat-all at the end.

### Local keyboard/MMI control

The native player has five focusable controls. Left/right moves focus with wraparound; Select activates the focused control; Back opens the file browser.

Global next, previous, and play/pause bindings are intercepted in `App.tsx` while local audio owns focus. They are dispatched as `localMediaCommand` events and are not duplicated into the phone projection session.

## Local Playback Persistence

The provider uses three `localStorage` entries:

| Key | Stored value |
| --- | --- |
| `v-link-local-media-current-track` | Track kind, name, and backend source path when available. |
| `v-link-local-media-shuffle` | Shuffle enabled/disabled. |
| `v-link-local-media-repeat` | `off`, `all`, or `one`. |

Browser directory handles are stored separately in IndexedDB database `v-link-local-media`, object store `directories`, key `selected`.

The current playback position and playing/paused state are not persisted.

### Restore behavior

For a backend track, the provider requests its parent directory, rebuilds the playlist, and restores the selected file.

For a browser-selected file, the saved directory is reopened when permission allows and the matching filename is selected.

Automatic resume waits until projection-device detection is complete. It resumes local playback only when no dongle or phone session is connected. This prevents restored local media from competing with a projection session during application startup.

Browser autoplay restrictions may reject automatic resume. If that happens, audio focus returns to `carplay` without breaking manual local playback.

## Audio Pipeline

Projected PCM audio is handled separately from media metadata.

The projection worker creates one shared ring buffer for each unique combination of:

- Decoded sample frequency.
- Channel count.
- Dongle `audioType`.

`createAudioPlayerKey()` combines those values into a stable route key. `useCarplayPcmPlayers()` creates one `PcmPlayer` for each key and transfers its SharedArrayBuffer to the worker.

When audio arrives before its player exists, the worker queues up to eight PCM frames for that route, requests a buffer from React, and flushes the pending frames after registration.

## Audio Route Classification

The pure audio-routing reducer tracks the roles active on each route key:

| Route class | Triggering commands | Applied level |
| --- | --- | --- |
| Media | `AudioMediaStart`, unclassified `AudioOutputStart` | Full volume, muted when local media owns focus, ducked during navigation. |
| Navigation | `AudioNaviStart` | Configured navigation volume. |
| Call | `AudioPhonecallStart` | Configured call volume. |
| Priority | `AudioSiriStart`, `AudioAlertStart` | Full volume. |

A route can retain its media identity while a transient navigation, call, Siri, or alert role is active. This is important when the dongle mixes multiple roles into the same PCM route: the matching stop command removes only its own role, allowing the previous media policy to resume. `AudioOutputStart` is treated as media only if the key is not already known exclusively as navigation, call, or priority audio.

All matching stop commands update route state. Navigation activity is derived across every route, so stopping one navigation route does not release global ducking while another remains active. Route state is reset when the phone disconnects.

`getTargetVolume()` is the single policy entry point for dongle volume messages, route transitions, focus changes, and live settings changes. Its explicit priority order is navigation, calls, Siri/alerts, then focused or ducked media.

## Audio Priority and Focus

The effective policy implemented by the current code is:

1. Navigation, calls, Siri, and alerts remain audible at their configured/full levels.
2. Local and projected music are mutually exclusive normal media sources.
3. Starting local playback asks the phone to pause and mutes projected media routes.
4. Starting projected media claims `carplay` focus and pauses local playback.
5. Navigation instructions reduce whichever normal media source is active.

The route sets are independent because the dongle may use different PCM formats or `audioType` values for each purpose.

Calls and priority routes receive their own levels, but the code does not explicitly duck every separate media route when a call, Siri, or alert begins. Any additional mixing behavior in those cases may be controlled by the phone/dongle stream layout.

## Navigation Ducking

### Ducking amount

`navigationDuckingAmount` is expressed as 0–100%. It is converted to output amplitude with:

```ts
remaining = 1 - amount / 100
output = remaining * remaining
```

Examples:

| Setting | Output amplitude |
| --- | --- |
| 0% | 1.00 |
| 50% | 0.25 |
| 80% (default) | 0.04 |
| 100% | 0.00 |

The squared curve makes high ducking settings reduce media more strongly than a linear percentage.

### Projected media ducking

On `AudioNaviStart`:

- Navigation is ramped to the configured navigation volume over 200 ms.
- Known projected-media routes are ramped to the ducked level over 200 ms.
- If local focus is active, projected media remains fully muted.

On `AudioNaviStop`, projected media returns to full volume over 650 ms, unless local audio still owns focus.

If navigation and media share the same PCM route key, that route is reclassified as navigation. V-Link logs that projected-media ducking for the shared route is controlled by the phone, because one PCM player cannot independently attenuate two signals already mixed into the same stream.

### Local media ducking

Navigation start/stop also dispatches the global `v-link-navigation-ducking` event.

`LocalMediaProvider` listens for it and ramps the HTML audio element:

- Down to the calculated ducked level over 200 ms.
- Back to full volume over 650 ms.

The ramp uses smoothstep interpolation to avoid abrupt volume changes.

## Volume Ramping

`useCarplayPcmPlayers()` ramps projected PCM players with `requestAnimationFrame`. Starting a new ramp for the same route cancels its previous animation.

Each step interpolates from the tracked current volume to a clamped 0–1 target using smoothstep easing. `PcmPlayer.volume()` receives a very small duration because its duration parameter delays automation; V-Link performs the actual ramp itself.

Dongle `volumeDuration` messages are respected, but the target is overridden when route policy requires navigation volume, call volume, priority level, local-focus muting, or navigation ducking.

## Audio Settings Screen

The Settings sidebar contains a dedicated Audio page rendered by `AudioSettings.tsx`.

### Settings

| Setting | Default | Range | Purpose |
| --- | --- | --- | --- |
| Navigation instructions | 80% | 0–100% | Volume of projected navigation audio routes. |
| Phone calls | 85% | 0–100% | Volume of projected phone-call routes. |
| Navigation ducking intensity | 80% | 0–100% | Reduction applied to active music during navigation. |
| Microphone input gain | 0 dB | -20 to +2 dB | Gain applied before microphone audio is sent to projection. |

Slider changes save immediately and dispatch an in-page change event. `useAudioSettings()` subscribers receive updated values without reloading.

Restore Defaults resets all four values at once.

### Persistence

Audio settings are stored in browser `localStorage` under:

```text
v-link-audio-settings
```

They are not currently part of backend `app.json` and are therefore local to the Chromium profile. Clearing browser storage/profile data resets them to defaults.

If stored JSON is missing or invalid, the default settings are used.

## Microphone Gain and Test

### Projection microphone

The CarPlay audio hook requests a microphone MediaStream and builds this Web Audio graph:

```text
microphone MediaStream
        |
        v
MediaStreamAudioSourceNode
        |
        v
GainNode
        |
        v
MediaStreamDestination
        |
        v
WebMicrophone -> MessagePort -> projection worker -> dongle
```

The dB setting is converted to linear gain with:

```ts
gain = 10 ** (microphoneGainDb / 20)
```

Live changes use `setTargetAtTime()` with a short time constant, avoiding a hard discontinuity in microphone gain.

The dongle controls capture through `startRecordAudio` and `stopRecordAudio` commands.

### Microphone test

The Audio Settings page can independently request microphone access and build a temporary source → gain → analyser graph.

It samples the time-domain signal every animation frame, displays a peak meter, warns above 92% that the input is clipping, and suggests occasional peaks around 75%.

Stopping the test or leaving the page cancels animation, stops microphone tracks, closes the AudioContext, and resets the meter.

## Keybinding Interaction

The Media page reuses `dongle_bindings` from `app.json` for projected and local controls.

- From the main Music view, Down opens Local Media.
- In the browser, Left/Right changes the focused item, Select opens it, and Back returns to the main Music view.
- In projected Now Playing, Left/Right focuses Previous, Play/Pause, or Next and Select activates it.
- In Native Player, Left/Right/Select/Back operate its five controls and browser action.
- Up switches the top-level V-Link page from every Music subview.
- Global Next/Previous work outside the CarPlay view.
- When local focus is active, global media actions are routed only to local playback.
- When projected focus is active, they are sent to the CarPlay worker/dongle.

`Content.tsx` does not use the page-switch binding while the Music view is active, preventing the Music page's Select/navigation interaction from being mistaken for view cycling.

## UI Selection Logic

`NowPlaying` chooses its screen in this order:

1. If the file browser is open, render `UsbMediaBrowser`.
2. If local audio owns focus and a local track exists, render `NativePlayer`.
3. If no projected phone is connected, render the empty state and Local Media option.
4. Otherwise, render projected Now Playing.

This ordering lets local playback remain visible even without a phone and keeps browsing available from every Media state.

## Logging and Diagnostics

Projected audio route decisions are logged with command, `audioType`, `decodeType`, and derived route key. A specific warning is logged when navigation and media share a PCM route.

Frontend logs are sent through the `/log` Socket.IO namespace and written by the Pi backend to:

```text
~/v-link/logs/logfile.txt
```

Useful messages include:

- Audio player creation.
- Audio route classification.
- Shared navigation/media route detection.
- Microphone initialization failures.
- Projection metadata received in the browser console.

Local browser/file errors are primarily shown in the Media UI rather than sent to the backend logger.

## Testing

Current media-specific automated coverage is concentrated in `frontend/src/carplay/mediaState.test.ts`. It verifies:

- Partial metadata merges without clearing previous values.
- Artwork updates preserve metadata.
- Media/output audio start and stop commands derive playback status correctly.
- Unrelated audio commands do not change playback status.

The H.264 renderer and projection session state have separate tests under `frontend/src/carplay`.

Useful validation commands are:

```bash
cd frontend
npm run typecheck
npm test
```

The following areas currently require integration/manual testing because they depend on browser APIs, mounted storage, or real projection audio:

- Backend storage browsing and streaming.
- File System Access permissions and IndexedDB restoration.
- HTML audio codec support.
- Audio focus transitions.
- Navigation ducking and route sharing.
- Microphone gain and clipping meter.

## Troubleshooting

### Projected metadata is missing

- Confirm the phone media application publishes metadata through the projection protocol.
- Inspect the browser console for “Media metadata received”.
- Check whether artwork arrives separately from type-1 metadata.
- Audio may still play when the phone application does not expose title/artist data.

### Local storage locations do not appear

- Verify the directory exists under `~/Music`, `/media`, or `/mnt`.
- Confirm the V-Link backend user can read the directory.
- Check `/api/media/roots` and `/api/media/browse` responses.
- Hidden files and unsupported extensions are intentionally omitted.

### A local file cannot play

- Confirm the extension is supported by the module.
- Browser codec support may vary even for an accepted extension.
- Open the browser console/network panel and inspect `/api/media/file`.
- Verify the file remains mounted and readable.

### The selected folder is forgotten

- Check IndexedDB availability and File System Access API support.
- Chromium may require directory permission again after restart.
- Browser storage or profile cleanup removes saved handles and localStorage values.

### Projected and local music play together

- Inspect `APP.system.audioSource` and projected `AudioMediaStart` events.
- Confirm local track selection sends `pause` to the phone.
- Check route-classification logs to ensure the projected PCM stream is known as media.
- An unusual dongle audio route may remain unclassified until an appropriate start command arrives.

### Navigation does not duck music

- Confirm the dongle sends `AudioNaviStart` and `AudioNaviStop`.
- Check the navigation ducking setting.
- Inspect logs for a shared navigation/media PCM route.
- Shared routes depend on phone-side mixing for projected media, although local media still responds to the global ducking event.

### Call or navigation volume does not change

- Confirm the route was classified by `AudioPhonecallStart` or `AudioNaviStart`.
- Check the route key in frontend logs.
- Verify the Audio Settings values in the active Chromium profile.

### Microphone test or calls have no input

- Grant Chromium microphone permission.
- Check the selected OS audio input.
- Inspect logs for microphone initialization errors.
- Use the meter to verify signal before debugging the dongle path.

## Known Constraints

- Local tracks use filenames rather than embedded metadata tags.
- Local artwork is not extracted.
- Browser-selected directories are scanned only at their top level.
- Playback position is not restored between sessions.
- Audio settings are browser-local rather than stored in `app.json`.
- Calls, Siri, and alert starts receive priority levels, but do not explicitly duck all independent media routes.
- Route cleanup is explicit for navigation stop; other stop commands do not currently reclassify route sets.
- Backend media roots default to `~/Music`, `/media`, and `/mnt` unless overridden through Flask configuration.
