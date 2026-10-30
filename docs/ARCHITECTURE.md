# Architecture — SPOT Trace History

_Reference snapshot: 12 October 2026, based on the latest Device Management UI ZIP provided in this conversation. Confirm against Git before implementation._

## Components and data flow

1. `config_flow.py`: each config entry (version 2) is one vehicle, a messenger in a SPOT public XML feed; see `docs/adr/0001-one-config-entry-per-vehicle.md`. The `user` step takes `feed_id` and an optional masked `password` and validates them with one request; the `vehicle` step offers the feed's recent and archived messengers not yet configured (a custom value allows typing an ID for a quiet feed), plus an optional name and icon. The unique ID is `spot:<feed>:<messenger>`, so a duplicate vehicle aborts. Errors distinguish `cannot_connect` (network/HTTP/parse), `feed_not_found` (SPOT `E-0160`), `feed_rejected` (any other SPOT error, shown with SPOT's text; covers rejected passwords, whose exact code is unverified) and `no_messenger`. A `reconfigure` step changes only the password; the feed and messenger are fixed because they key the tracker and the archive. An `import` step creates the vehicles split from a version 1 entry. The options flow is one form for the vehicle's `name` and `icon`, showing archive details read directly from the shared archive (no loaded coordinator required); it also updates the entry title.
2. `api.py`: uses HA's aiohttp client session to request the SPOT public REST XML `message.xml` endpoint; parses messenger ID/name, timestamp, coordinates and message type. Feed password is passed as a request parameter, so request failures are re-raised as `SpotAPIError` with a sanitized message (HTTP status or exception type only) that never includes the URL. SPOT's `E-0195` "no messages" error is treated as an empty page so quiet feeds can still be added and polled.
3. `coordinator.py`: a `FeedPoller` per (feed, password) in `hass.data` fetches the newest page into SQLite at most once per `FRESH_SECONDS` (half the poll interval), so vehicles on one feed share a request. `SpotCoordinator` (bound to its vehicle entry) polls every 300 seconds through its poller; its data is the vehicle's latest archived position, or None before the first fix. Expected feed, XML and SQLite failures become `UpdateFailed`; anything else is left for HA to log as unexpected. `__init__.py`: `async_setup` serves the bundled card JavaScript and registers the import actions and WebSocket commands once per HA start; `async_migrate_entry` splits version 1 feed entries into vehicles; `async_setup_entry` moves the vehicle's device from the feed entry it was split from (device identifiers are unique only within an entry; the entity follows its unique ID by itself) and stores the coordinator in `entry.runtime_data`. Commands and actions find vehicles through `hass.config_entries.async_loaded_entries`, so unloaded ones are skipped. Historical XML pagination/backfill is not implemented.
4. `store.py`: SQLite table `positions` keyed by `(feed,id)` with a uniqueness index on `(feed,device,time,lat,lon)`. Provides insert, latest, device listing, names and bounded track queries. DB path: HA config directory `/config/spot_trace_history.sqlite` in a typical deployment. `async_get_store(hass)` returns the single shared `Store` (kept in `hass.data[DOMAIN]`), used by every feed, trips and the options flow; it is independent of config entries.
5. `device_tracker.py`: creates the vehicle's one `TrackerEntity`. Tracker unique ID is `feed_id + '_' + messenger_id` (unchanged since version 1). Entities use `has_entity_name` with no entity name, so they take the device name (`vehicle_name`: the vehicle's name, else SPOT's messenger name, else the messenger ID); the device carries the messenger ID as `serial_number`. `options['enabled'] = False`, written only by the migration, sets `entity_registry_enabled_default` so a tracker switched off before the split is created disabled. `PARALLEL_UPDATES = 0`. `async_remove_config_entry_device` (in `__init__.py`) refuses to delete the vehicle's own device (delete the entry instead) and allows any leftover device; archived history is untouched.
   An optional icon from the vehicle's options is the entity default. Native device identifiers use `(DOMAIN, tracker_unique_id)` and manufacturer SPOT, enabling standard device area/label surfaces. Entity ID, visibility, native enabled flags, voice exposure, and native name/icon overrides remain in HA's registries.
6. `gpx.py`: parses GPX 1.1 track exports and generates synthetic point IDs. `gpx_import.py` plans per-track destinations among the loaded vehicles before writing: a track goes to the vehicle whose messenger ID it is mapped to (`device_mapping`), or whose messenger ID or archived SPOT name it matches; `feed_id`, `entry_id` and `feed_mapping` narrow the candidates. When only one vehicle remains, it takes a track it does not recognise only if no other track goes to it, so two trackers are never merged. After inserting, every loaded vehicle on an affected feed is refreshed.
   `sqlite_import.py` reads the observed SPOT iOS schema in read-only mode without querying account data. It validates required columns and source identities, skips invalid fixes, and preserves message types and `ios:<device_pk>:<public_key>` IDs. It shares the routing/insertion/refresh workflow with GPX. `import_paths.py` enforces config-directory containment and supported extensions for both services.
7. `www/spot-trace-history-card.js`: bundled custom Lovelace map card, queried through WebSockets, with device visibility controls, per-device overrides, and configurable tile URL/attribution. The map is rendered by Leaflet 1.9.4, vendored from npm in `www/leaflet/` (unmodified apart from LF line endings) (ESM build, CSS and BSD-2-Clause licence) and served at `/spot_trace_history/leaflet/`. The card imports it on first use, so it does not depend on Home Assistant's internal Leaflet or a CDN; `LEAFLET_VERSION` in the card must match the vendored file (checked by `scripts/validate_package.py`). Leaflet uses fractional zoom (`zoomSnap` 0.25) for smooth wheel and pinch zoom and a canvas renderer for long routes. Vehicle markers show the icon from the device options (returned by `spot_trace_history/devices`), or a card `icon` override, using HA's `ha-icon`.
8. `trips.py`: authenticated WebSocket list/create/update/delete commands for named calendar-date ranges. `store.py` adds a persistent `trips` table alongside positions (UUID, unique name, start/end dates). Trips are shared across feeds and independent of config entries. The card applies a selected trip's dates to its existing track queries; dates use the browser timezone and device selections remain active. Creation/editing use a native modal dialog with isolated name/date fields and inline errors. Editing preserves identity and accepts the unchanged name; cancel leaves saved values and the map filter untouched. Confirmed deletion removes only metadata. Duplicate names and invalid ranges roll back; mutations of missing IDs return `not_found`. Refresh reloads changes from other cards. Concurrent edits use last successful save; there is no optimistic version check yet. Multi-trip selection remains future work.

9. `diagnostics.py`: config entry diagnostics with the feed ID, password, messenger ID, vehicle name, entry title/unique ID and coordinates redacted (the feed ID grants read access to a shared feed). The feed and messenger IDs are also scrubbed from the last coordinator error, since SPOT error text can echo them. Includes coordinator status and the vehicle's archive summary (count, first/latest UTC times, latest message type).
10. UI text lives only in `translations/en.json` (custom integrations do not read `strings.json`), including service names/field descriptions and the `import_failed` exception; `services.yaml` holds only fields and selectors, and `icons.json` the service icons. `tests/test_translations.py` checks coverage. API requests use `aiohttp.ClientTimeout(total=30)`.

## Home Assistant surfaces

- Add a vehicle: Settings → Devices & services → Add integration → SPOT Trace History, enter the feed, then choose the messenger; repeat per vehicle, including other messengers on the same feed.
- Configure a vehicle: Configure → view feed ID, messenger ID, archived count, first/latest timestamps in UTC, and latest coordinates; edit the vehicle name and icon.
- Action: `spot_trace_history.import_gpx` with a config-relative GPX filename. `entry_id` selects one vehicle and `feed_id` limits routing to one feed's vehicles; combined exports are routed by mapped messenger IDs or archived names. Optional `feed_mapping` maps track names to configured feed IDs. Every destination is validated before inserts; invalid routing imports nothing. Database/runtime failures during insertion can still leave a partial multi-vehicle import; rerunning deduplicates fixes.
- Action: `spot_trace_history.import_sqlite` accepts a config-relative SPOT iOS database path (`.db`, `.sqlite`, `.sqlite3`) and the same destination/mapping fields. Mapping keys are app device names. Source app keys are not assumed to be XML messenger IDs. A complete export is required, including matching WAL files if present. This imports an existing file; it does not add a browser upload surface.
- WebSockets: `spot_trace_history/devices` returns each loaded vehicle that has archived positions, with its vehicle name and icon; `spot_trace_history/track` returns one vehicle's track (the `device` must be the entry's messenger), capped to 366 days and 50,000 rows.
- Card URL is served automatically at `/spot_trace_history/spot-trace-history-card.js`; JavaScript registration appends the installed manifest version through HA's integration loader (currently `?v=0.5.2`).

## Device options behavior

Trip playback supports client-side scrubbing and automatic animation of loaded history. A saved
trip enables the **Timeline** button, which opens the timeline as a panel absolutely positioned over the map (a sibling of the Leaflet container, so its events never reach the map) and never resizes the map; its bounds are the selected inclusive date period. The card renders no title; filters, trip controls and the vehicle legend share one wrapping row.
Binary search selects each vehicle's last fix at/before the cursor, without
interpolation; there is no marker before that vehicle's first loaded fix. Full
routes stay visible, and per-vehicle timestamps identify stale positions. Turning
timeline mode off restores latest markers. New track requests reset playback;
a request-generation guard prevents old responses from replacing newer results.
Existing date/participant/visibility filters and query limits still apply.
Play/Pause uses one requestAnimationFrame loop with real elapsed time and an
explicit simulated-seconds-per-second speed. Long frame gaps are capped at
250ms. Marker/text updates are capped at 10Hz and move the existing Leaflet
markers, retaining existing routes and tiles. Playback stops at the end (Replay),
pauses on scrubbing/visibility changes/disconnect, and is canceled for new history
queries or leaving the trip. Returning to a view does not resume automatically.

Trip participants are stored in the additive nullable `trips.devices` JSON
column as a list of `{feed_id, device}` references. NULL preserves all-vehicles
behavior for old trips; explicit empty lists are rejected. Create/update
WebSocket payloads accept `devices`; old clients omitting it on update preserve
existing participants. The dialog lists configured and previously saved
unavailable devices. Filtering matches stable feed/messenger identities rather
than config entry IDs and intersects participant membership with map visibility.
No positions are copied or removed when membership changes.

Entry shape (version 2):

```json
{"data": {"feed_id": "FEED_ID", "password": "", "device": "MESSENGER_ID"},
 "options": {"name": "Camper", "icon": "mdi:caravan"}}
```

Options updates trigger a config-entry reload. The flow uses HA's read-only `config_entry` property, supplied by its options-flow manager. Disabling the tracker entity does **not** delete historical positions or filter the map card. The options metadata is loaded through the executor from the SQLite archive, including GPX positions; latest means latest archived fix, not necessarily current live location.

## Packaging and validation

`scripts/validate_release.py` checks the built ZIP against every distributable
source file, rejects missing/extra/duplicate entries and mismatched manifests,
and verifies byte equality and CRC integrity. `check_packaged_card.cjs` executes
the archived JavaScript in a Node VM with minimal DOM doubles and tests
registration, timeline controls, and playback behavior. It prints the card hash.
CI builds/checks the archive; Release runs the same gate on its versioned ZIP
before committing version metadata or publishing. It cannot verify HA's installed
files, caching, or full browser layout.

Release versions are selected above both existing Git tags and GitHub release
names (including drafts). An existing release blocks version reuse even if its
tag is missing. After saving the version commit, the workflow creates/pushes the
tag explicitly, compares every archived file with that ref via `--ref`, and
verifies its remote commit after publishing. This matters because HACS is not
configured with `zip_release` and installs tagged repository contents rather
than the attached ZIP.

History actions are registered by `import_actions.py` with optional response
support and persistent notification summaries. Report parsers retain the legacy
list-returning parser API while counting skipped/source rows. `Store.insert`
returns the connection's inserted-row delta, so polling or concurrent imports
cannot inflate an import's added count. The shared history workflow returns
overall and destination counts and the valid source's UTC date range. Invalid
routing still fails before writes; insertion failures can be partial. Errors
replace the latest notification and do not return a success report. Notifications
require the manifest's `persistent_notification` dependency.

- HACS category: Integration. `hacs.json` declares minimum HA version `2026.09.3`.
- `manifest.json` includes `codeowners` (`@gregjones60`), `issue_tracker`, `config_flow`, `frontend`/`http`/`persistent_notification`/`websocket_api` dependencies, `cloud_polling`, documentation URL and version `0.5.2`.
- CI: Python 3.14, Node 22, `requirements_test.txt` (real Home Assistant test harness), `scripts/check.sh`, and hassfest.
- Version source: integration `manifest.json`. Local builds accept `--version X.Y.Z` to update manifest, package metadata, and README; otherwise they use the manifest version. Main releases automatically increment the patch of the highest stable version in the manifest or existing tags. After CI succeeds for a main push, release checks out the tested SHA, stamps metadata, builds, reruns checks, commits the version files back to main, and publishes the matching ZIP/tag at that commit. Releases are serialized. The bot push uses `GITHUB_TOKEN` and does not recursively trigger CI. A rejected push (branch protection or newer main commits) stops publication; no force push is used. PR and manual CI runs cannot publish. HACS uses published release tags for its displayed release version; branch installs can show a commit hash.
- Tests cover API, GPX, SQLite, the coordinator's shared polling and the tracker with Home Assistant test doubles, and JavaScript card basics. `tests/test_ha_integration.py` runs the integration in a real Home Assistant (pinned by `requirements_test.txt`) with the SPOT API mocked: entry setup/unload/reload, one tracker per vehicle, shared polling and per-password pollers, the version 1 split (identity, settings, disabled trackers, registry hand-over, untouched history and trips, entries with no messenger), card registration, actions and WebSocket commands registered once, setup retry without logging the password, quiet feeds, diagnostics redaction, translation placeholders, and the config and options flows end to end. These still do not validate frontend rendering or the bundled card inside a browser.

## Known constraints

- Prototype: live Home Assistant UI behavior not yet verified.
- Feed polling requests newest XML page; full historical XML pagination/backfill is not implemented.
- Public OSM tile usage can encounter HTTP 403; users may supply an authorized tile provider.
- The archive is persistent: migrations, pruning and removal must be explicitly designed and tested.
