# Architecture — SPOT Trace History

_Reference snapshot: 12 October 2026, based on the latest Device Management UI ZIP provided in this conversation. Confirm against Git before implementation._

## Components and data flow

1. `config_flow.py`: creates one config entry per SPOT public XML feed (`feed_id`, optional `password`), using the feed ID as the unique ID. Its options flow lists discovered devices from the archive and edits per-device `name` and `enabled` settings.
2. `api.py`: uses HA's aiohttp client session to request the SPOT public REST XML `message.xml` endpoint; parses messenger ID/name, timestamp, coordinates and message type. Feed password is passed as a request parameter.
3. `__init__.py`: `SpotCoordinator` polls each feed every 300 seconds, inserts points into SQLite and publishes the latest position per messenger. It registers the GPX import service, WebSocket commands, and bundled card JavaScript. Backfill scaffolding exists but is not scheduled; do not describe full pagination as implemented.
4. `store.py`: SQLite table `positions` keyed by `(feed,id)` with a uniqueness index on `(feed,device,time,lat,lon)`. Provides insert, latest, device listing, names and bounded track queries. DB path: HA config directory `/config/spot_trace_history.sqlite` in a typical deployment.
5. `device_tracker.py`: creates a `TrackerEntity` for each discovered messenger ID from the coordinator, except IDs disabled through config entry options. Name can be overridden. Tracker unique ID is `feed_id + '_' + messenger_id`.
6. `gpx.py`: parses GPX 1.1 track exports, optionally maps GPX track names to SPOT messenger IDs, and generates synthetic point IDs. Imports target a selected feed.
7. `www/spot-trace-history-card.js`: bundled custom Lovelace map card, queried through WebSockets, with device visibility controls, per-device overrides, and configurable tile URL/attribution. It uses a lightweight SVG/tile renderer rather than Leaflet.

## Home Assistant surfaces

- Add integration: Settings → Devices & services → Add integration → SPOT Trace History; repeat for independent feeds.
- Configure existing feed: Options → Manage devices → select messenger → edit friendly name and tracker enabled flag.
- Action: `spot_trace_history.import_gpx` with a config-relative GPX filename and `feed_id` or `entry_id` to select the feed.
- WebSockets: `spot_trace_history/devices` returns devices from all active feed entries, including archived-only ones; `spot_trace_history/track` returns one feed/device's track, capped to 366 days and 50,000 rows.
- Card URL is served automatically at `/spot_trace_history/spot-trace-history-card.js`; JavaScript registration appends the installed manifest version through HA's integration loader (currently `?v=0.5.2`).

## Device options behavior

Options shape:

```json
{"devices": {"MESSENGER_ID": {"name": "Camper", "enabled": true}}}
```

Options updates trigger a config-entry reload. Disabling the tracker does **not** delete historical positions or filter the map card. Device lists depend on already-stored positions, so a new feed with no messages may show no devices.

## Packaging and validation

- HACS category: Integration. `hacs.json` declares minimum HA version `2026.09.3`.
- `manifest.json` includes `config_flow`, `http` dependency, `cloud_polling`, documentation URL and version `0.5.2`.
- CI: Python 3.13, Node 22, `scripts/check.sh`, and hassfest.
- Version source: integration `manifest.json`. Local builds accept `--version X.Y.Z` to update manifest, package metadata, and README; otherwise they use the manifest version. Main releases automatically increment the patch of the highest stable version in the manifest or existing tags. After CI succeeds for a main push, release checks out the tested SHA, stamps metadata, builds, reruns checks, commits the version files back to main, and publishes the matching ZIP/tag at that commit. Releases are serialized. The bot push uses `GITHUB_TOKEN` and does not recursively trigger CI. A rejected push (branch protection or newer main commits) stops publication; no force push is used. PR and manual CI runs cannot publish. HACS uses published release tags for its displayed release version; branch installs can show a commit hash.
- Tests cover API, GPX, SQLite, JavaScript card basics, and options-flow steps using real voluptuous schemas and Home Assistant test doubles. Options tests cover feed isolation, selection, defaults, saving without mutating existing options, archive preservation, and empty/missing devices. A strict expected-failure test records the constructor's assignment to modern HA's read-only `config_entry` property. These tests do not validate HA rendering, persistence, reload lifecycle, or tracker suppression.

## Known constraints

- Prototype: live Home Assistant UI behavior not yet verified.
- Feed polling requests newest XML page; full historical XML pagination/backfill is not implemented.
- Public OSM tile usage can encounter HTTP 403; users may supply an authorized tile provider.
- The archive is persistent: migrations, pruning and removal must be explicitly designed and tested.
