# Codex instructions — SPOT Trace History

Read `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_HISTORY.md`, and `docs/ROADMAP.md` before making nontrivial changes. Inspect the actual source before assuming documentation is current.

## Purpose
Maintain a HACS-installable Home Assistant custom integration that ingests SPOT public XML feeds, archives positions in SQLite, exposes GPS device trackers, imports historical GPX, and bundles a Lovelace map card.

## Invariants
- Each SPOT feed is a **separate Home Assistant config entry**. A feed may contain multiple messenger IDs. Never assume one feed contains all devices.
- The SQLite archive (`spot_trace_history.sqlite` in HA config) persists independently of config entries; never delete history on feed/device removal without an explicit, reviewed data-retention feature.
- Per-device settings are stored in the owning config entry's `options['devices'][messenger_id]`. Currently `name`, `enabled`, and optional `icon` are supported. Standard entity/device area, labels, visibility, entity ID, and voice settings remain owned by HA registries; do not mirror them in config entry options.
- `enabled=false` disables creation/loading of the device tracker; it **does not** suppress XML polling, archival, or history visibility in the map card.
- Keep the bundled map card auto-served and auto-registered; no manual `/config/www` setup should be required.
- Protect against unsafe filesystem access in GPX import and preserve feed-specific import targeting.
- Never log feed passwords or other credentials.

## Workflow
1. Review relevant implementation and tests, and explain intended changes briefly.
2. Keep changes minimal, compatible with current config entries and archive schema, and add tests for behavior changes.
3. Run `bash scripts/check.sh` (requires Python pytest and Node.js). If dependencies are unavailable, report which checks did not run.
4. Validate Home Assistant integration manifest/config/options flows and HACS packaging where possible; passing unit tests alone does not prove HA UI compatibility.
5. Update relevant docs and translations when adding user-facing settings; avoid promising live behavior not tested in HA.
6. Show a concise diff summary and any remaining risks.

## Current priorities
Validate the first Device Management options UI in a real HA instance; then improve tests, editing/removal semantics, feed management, and historical data controls. See `docs/ROADMAP.md`.

## Important paths
- `custom_components/spot_trace_history/` — integration source
- `custom_components/spot_trace_history/config_flow.py` — feed setup and device options UI
- `custom_components/spot_trace_history/device_tracker.py` — GPS entities
- `custom_components/spot_trace_history/store.py` — SQLite archive
- `custom_components/spot_trace_history/www/spot-trace-history-card.js` — bundled map card
- `tests/`, `tests-js/` — tests
- `scripts/check.sh`, `.github/workflows/ci.yml` — validation
