# Codex instructions — Satellite Tracker History

Read `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_HISTORY.md`, and `docs/ROADMAP.md` before making nontrivial changes. Inspect the actual source before assuming documentation is current.

## Purpose
Maintain a HACS-installable Home Assistant custom integration that ingests SPOT public XML feeds and Garmin inReach MapShare KML feeds, archives positions in SQLite, exposes GPS device trackers, imports historical GPX, and bundles a Lovelace map card.

## Invariants
- Each **vehicle** is a separate Home Assistant config entry (version 2): one tracker, `data['device']` in the feed `data['feed_id']` of `data['provider']` (`spot`, the default when absent, or `garmin`). For SPOT these are a messenger ID and shared feed ID; for Garmin, an IMEI and a MapShare name. The unique ID is `<provider>:<feed>:<device>`. A feed may hold several devices, each its own vehicle entry; vehicles on one feed share a poll (`coordinator.FeedPoller`). Never assume one feed contains all devices. See `docs/adr/0001-one-config-entry-per-vehicle.md`.
- Archive and tracker keys come from `vehicle.archive_feed`: SPOT uses the raw feed ID (unchanged since version 1); other providers use `<provider>:<feed>`, so feeds of different services never collide. See `docs/adr/0002-provider-prefixed-archive-feeds.md`.
- Version 1 entries were whole feeds; `async_migrate_entry` splits them without moving history, keeping tracker unique IDs (`<feed>_<messenger>`), entity IDs and devices. Keep that migration working.
- Up to v0.6.1 the integration was `spot_trace_history` (SPOT Trace History). After startup, and from the config flow's `legacy` step (HA does not load the integration at startup until it has entries), `async_take_over_legacy` recreates its entries under a lock (splitting version 1 feeds), each new entry moves its tracker entity (platform) and then its device (identifiers), and the old entries are removed. The first `Store.connect` of the archive runs `adopt_legacy_archive`: it renames `spot_trace_history.sqlite`, or merges it into an existing new archive and keeps it as `.migrated`. The card keeps `custom:spot-trace-history-card` as an alias. Keep the takeover and alias working; see `docs/adr/0003-rename-to-satellite-tracker-history.md`.
- The SQLite archive (`satellite_tracker_history.sqlite` in HA config) persists independently of config entries, keyed by feed and messenger; never delete history on vehicle removal without an explicit, reviewed data-retention feature.
- A vehicle's own settings are its entry's `options['name']` and optional `options['icon']`. `options['enabled'] = False` is only written by the migration, so a tracker that was switched off is created disabled. Standard entity/device area, labels, visibility, entity ID, and voice settings remain owned by HA registries; do not mirror them in config entry options.
- Disabling a tracker entity does **not** suppress polling, archival, or history visibility in the map card; disabling the vehicle's entry stops all three.
- Keep the bundled map card auto-served and auto-registered; no manual `/config/www` setup should be required.
- Protect against unsafe filesystem access in GPX import. Imports resolve every track to exactly one vehicle before writing, and never merge two tracks into one vehicle without a mapping.
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
- `custom_components/satellite_tracker_history/` — integration source
- `custom_components/satellite_tracker_history/config_flow.py` — vehicle setup and options UI
- `custom_components/satellite_tracker_history/device_tracker.py` — GPS entities
- `custom_components/satellite_tracker_history/store.py` — SQLite archive
- `custom_components/satellite_tracker_history/www/satellite-tracker-history-card.js` — bundled map card
- `tests/`, `tests-js/` — tests
- `scripts/check.sh`, `.github/workflows/ci.yml` — validation

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for gregjones60/satellite-tracker-history (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root (created lazily). See `docs/agents/domain.md`.
