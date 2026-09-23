# Future V-Link Lite update integration

This is a design note, not an updater implementation. Lite is a deployment mode
of V-Link, not a fork, product, release channel or independent version. Merge
`lite/` into `dev` and ship it in every ordinary V-Link release, including
Desktop releases. Desktop simply does not execute Lite infrastructure.

## One release, two deployment modes

```text
Stage one V-Link release (V-Link.py, backend/, frontend/, updater/, lite/)
  -> update V-Link application files, including versioned lite/, always
  -> is <app>/.v-link-lite-runtime present?
       no  -> finish Desktop update
       yes -> migrate deployed Lite infrastructure
           -> run Check-Lite
           -> reboot if the migration requires it
```

The release version is authoritative. An internal Lite schema/platform revision
may select migrations (for example, V-Link 3.2.0 and Lite schema 4), but there
must be no second “V-Link Lite version” or `V-Link-Lite.zip`. A single common
release archive must eventually support installation and updates for both modes.
The common release payload must include everything needed to install and
migrate Lite. That is broader than `lite/`: the current installer also consumes
`resources/dtoverlays/` and `frontend/public/assets/svg/logos/`. Review the
complete installer input set when integrating Lite with `Package.sh`; do not
change `Package.sh` as part of this design note.

## Versioned code versus deployed infrastructure

`<app>/lite/` is versioned source and travels with every release. Deployed Lite
files are a separate system state: `/usr/local/bin/v-link-lite-setup`,
`v-link-lite-cursor`, `v_link_lite_audio.py`, `v_link_lite_display.py`,
`v_link_lite_support.py`,
`/usr/local/libexec/v-link-lite-{boot,overlay,prepare-splash}`, and Lite-owned
systemd, labwc, LightDM and boot configuration. These must be synchronized only
on a runtime marked with `.v-link-lite-runtime`. Updating source without these
copies produces a dangerous V-Link N+1 / Lite infrastructure N mismatch.

Classify each migration target before writing:

1. Fully Lite-managed files may be replaced atomically after validation.
2. Shared files containing a marked Lite block may have only that block edited;
   preserve other content and the original backup.
3. User-owned choices must not be reset: `settings.conf`, other PipeWire files,
   microphone processing preferences, selected devices, network preferences and
   similar state. Migrate their schema only when necessary and safely.

Migrations must be idempotent: create missing managed files, update only files
known to be ours, avoid duplicate blocks, validate after changes, and leave
Desktop untouched. A conceptual `migrate_lite_platform()` follows application
staging and precedes the final health check; it is **not implemented here**.

## Integration with the common updater

The common updater has now been merged into `BoostedMoose/v-link` `dev`. Before
implementing Lite migration, synchronize `little-os-test` with the current
upstream `dev`, review the updater and packager as merged, and extend their
normal transaction. Do not replace them or create an independent Lite updater.

The old Lite download path expects `V-Link.zip.sha256`. The updater/packager now
present in `dev` uses the newer release digest/manifest mechanism instead.
Future integration must adopt that common mechanism and review the full Lite
payload described above; it must not preserve a parallel legacy checksum path.

The desired transaction is:

```text
stage and validate common release
  -> stage app + versioned lite/
  -> if Lite runtime: stage/migrate deployed Lite files
  -> validate application and Check-Lite
  -> commit both parts together
  -> reboot if needed
```

On critical failure, restore both application and Lite-managed infrastructure
while preserving user settings. A successful app update followed by a failed
Lite migration is an unsuccessful update. Keep enough previous state for safe
downgrade and handle interrupted updates, ownership, mode and boot files.
Coordinate this with the common updater's transaction and keepalive design;
do not duplicate its release metadata or lifecycle.

## Current kiosk constraints to retain

Lite Setup is separate from V-Link's running service and available during boot
or by SSH. V-Link microphone gain 0 dB is the reference when calibrating the
PipeWire source level in Lite; an update must not silently change the shared
V-Link setting. The labwc keyboard hardening reserves `F1`–`F12`, `Menu`, `Shift+F10`,
`Shift+Escape`, `Alt+Tab`, `Alt+F4`, several Alt/Ctrl browser navigation and
editing shortcuts, Ctrl+0–9, Ctrl+F4/F5/F6 and Ctrl+plus/minus/equal (see
`lite/V-Link-Lite-Cursor.py` for the authoritative list). The splash gate uses
`S` for Setup. Do not reuse reserved combinations as ordinary app shortcuts.
