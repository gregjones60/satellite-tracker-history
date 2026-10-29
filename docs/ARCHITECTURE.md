# Architecture — SPOT Trace History

_Reference snapshot: 12 October 2026, based on the latest Device Management UI ZIP provided in this conversation. Confirm against Git before implementation._

## Components and data flow

1. `config_flow.py`: creates one config entry per SPOT public XML feed (`feed_id`, optional `password`), using the trimmed feed ID as the unique ID (duplicates abort before any API call). The password uses a masked selector. Errors distinguish `cannot_connect` (network/HTTP/parse), `feed_not_found` (SPOT `E-0160`) and `feed_rejected` (any other SPOT error, shown with SPOT's text; covers rejected passwords, whose exact code is unverified). A `reconfigure` step changes only the password, validates it, then updates and reloads the entry; the feed ID is fixed because it keys trackers and the archive. Its options flow lists discovered devices from the shared archive (no loaded coordinator required) and edits per-device `name` and `enabled` settings.
2. `api.py`: uses HA's aiohttp client session to request the SPOT public REST XML `message.xml` endpoint; parses messenger ID/name, timestamp, coordinates and message type. Feed password is passed as a request parameter, so request failures are re-raised as `SpotAPIError` with a sanitized message (HTTP status or exception type only) that never includes the URL. SPOT's `E-0195` "no messages" error is treated as an empty page so quiet feeds can still be added and polled.
3. `coordinator.py`: `SpotCoordinator` (bound to its config entry) polls each feed every 300 seconds, inserts points into SQLite and publishes the latest position per messenger. Expected feed, XML and SQLite failures become `UpdateFailed`; anything else is left for HA to log as unexpected. `__init__.py`: `async_setup` serves the bundled card JavaScript and registers the import actions and WebSocket commands once per HA start; `async_setup_entry` stores the coordinator in `entry.runtime_data`. Commands and actions find feeds through `hass.config_entries.async_loaded_entries`, so unloaded feeds are skipped. Historical XML pagination/backfill is not implemented.
4. `store.py`: SQLite table `positions` keyed by `(feed,id)` with a uniqueness index on `(feed,device,time,lat,lon)`. Provides insert, latest, device listing, names and bounded track queries. DB path: HA config directory `/config/spot_trace_history.sqlite` in a typical deployment. `async_get_store(hass)` returns the single shared `Store` (kept in `hass.data[DOMAIN]`), used by every feed, trips and the options flow; it is independent of config entries.
5. `device_tracker.py`: creates a `TrackerEntity` for each discovered messenger ID from the coordinator, except IDs disabled through config entry options. Name can be overridden. Tracker unique ID is `feed_id + '_' + messenger_id`. Entities use `has_entity_name` with no entity name, so they take the device name (configured name, else messenger name); the device carries the messenger ID as `serial_number`. `PARALLEL_UPDATES = 0`. `async_remove_config_entry_device` (in `__init__.py`) allows deleting a device only when it has no enabled tracker; archived history is untouched.
   An optional integration icon is exposed as the entity default. Native device identifiers use `(DOMAIN, tracker_unique_id)` and manufacturer SPOT, enabling standard device area/label surfaces. Entity ID, visibility, native enabled flags, voice exposure, and native name/icon overrides remain in HA's registries. Icons are selected through the standard HA IconSelector in device options.
6. `gpx.py`: parses GPX 1.1 track exports and generates synthetic point IDs. `gpx_import.py` plans per-track destinations before writing: explicit single-feed imports remain supported; combined exports resolve mapped messenger IDs or archived names to one configured feed, with optional `feed_mapping` for unknown/ambiguous tracks.
   `sqlite_import.py` reads the observed SPOT iOS schema in read-only mode without querying account data. It validates required columns and source identities, skips invalid fixes, and preserves message types and `ios:<device_pk>:<public_key>` IDs. It shares the routing/insertion/refresh workflow with GPX. `import_paths.py` enforces config-directory containment and supported extensions for both services.
7. `www/spot-trace-history-card.js`: bundled custom Lovelace map card, queried through WebSockets, with device visibility controls, per-device overrides, and configurable tile URL/attribution. It uses a lightweight SVG/tile renderer rather than Leaflet.
8. `trips.py`: authenticated WebSocket list/create/update/delete commands for named calendar-date ranges. `store.py` adds a persistent `trips` table alongside positions (UUID, unique name, start/end dates). Trips are shared across feeds and independent of config entries. The card applies a selected trip's dates to its existing track queries; dates use the browser timezone and device selections remain active. Creation/editing use a native modal dialog with isolated name/date fields and inline errors. Editing preserves identity and accepts the unchanged name; cancel leaves saved values and the map filter untouched. Confirmed deletion removes only metadata. Duplicate names and invalid ranges roll back; mutations of missing IDs return `not_found`. Refresh reloads changes from other cards. Concurrent edits use last successful save; there is no optimistic version check yet. Multi-trip selection remains future work.

9. `diagnostics.py`: config entry diagnostics with the feed ID, password, entry title/unique ID and any coordinates redacted (the feed ID grants read access to a shared feed). Includes coordinator status and a per-messenger archive summary (counts, first/latest UTC times, latest message type, tracker enabled).
10. UI text lives only in `translations/en.json` (custom integrations do not read `strings.json`), including service names/field descriptions and the `import_failed` exception; `services.yaml` holds only fields and selectors, and `icons.json` the service icons. `tests/test_translations.py` checks coverage. API requests use `aiohttp.ClientTimeout(total=30)`.

## Home Assistant surfaces

- Add integration: Settings → Devices & services → Add integration → SPOT Trace History; repeat for independent feeds.
- Configure existing feed: Options → Manage devices → select messenger → view feed ID, messenger ID, archived count, first/latest timestamps in UTC, and latest coordinates; edit friendly name and tracker enabled flag. Selector labels include messenger IDs to distinguish duplicate names.
- Action: `spot_trace_history.import_gpx` with a config-relative GPX filename. `feed_id` or `entry_id` selects one destination for all tracks; omitting them permits combined exports routed by mapped messenger IDs or unique archived names. Optional `feed_mapping` maps track names to configured feed IDs. Every destination is validated before inserts; invalid routing imports nothing. Database/runtime failures during insertion can still leave a partial multi-feed import; rerunning deduplicates fixes.
- Action: `spot_trace_history.import_sqlite` accepts a config-relative SPOT iOS database path (`.db`, `.sqlite`, `.sqlite3`) and the same destination/mapping fields. Mapping keys are app device names. Source app keys are not assumed to be XML messenger IDs. A complete export is required, including matching WAL files if present. This imports an existing file; it does not add a browser upload surface.
- WebSockets: `spot_trace_history/devices` returns devices from all active feed entries, including archived-only ones; `spot_trace_history/track` returns one feed/device's track, capped to 366 days and 50,000 rows.
- Card URL is served automatically at `/spot_trace_history/spot-trace-history-card.js`; JavaScript registration appends the installed manifest version through HA's integration loader (currently `?v=0.5.2`).

## Device options behavior

Trip playback supports client-side scrubbing and automatic animation of loaded history. A saved
trip enables the timeline, whose bounds are the selected inclusive date period.
Binary search selects each vehicle's last fix at/before the cursor, without
interpolation; there is no marker before that vehicle's first loaded fix. Full
routes stay visible, and per-vehicle timestamps identify stale positions. Turning
timeline mode off restores latest markers. New track requests reset playback;
a request-generation guard prevents old responses from replacing newer results.
Existing date/participant/visibility filters and query limits still apply.
Play/Pause uses one requestAnimationFrame loop with real elapsed time and an
explicit simulated-seconds-per-second speed. Long frame gaps are capped at
250ms. Marker/text updates are capped at 10Hz and use a separate SVG marker
layer, retaining existing routes and tiles. Playback stops at the end (Replay),
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

Options shape:

```json
{"devices": {"MESSENGER_ID": {"name": "Camper", "enabled": true, "icon": "mdi:caravan"}}}
```

Options updates trigger a config-entry reload. The flow uses HA's read-only `config_entry` property, supplied by its options-flow manager. Disabling the tracker does **not** delete historical positions or filter the map card. Device lists depend on already-stored positions, so a new feed with no messages may show no devices. Metadata is loaded through the executor from the selected feed's SQLite archive, including GPX positions; latest means latest archived fix, not necessarily current live location. Friendly names never replace the messenger ID used for settings.

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
- Tests cover API, GPX, SQLite, JavaScript card basics, and options-flow steps using real voluptuous schemas and Home Assistant test doubles. Options tests use the real constructor and cover feed isolation, selection, defaults, saving without mutating existing options, archive preservation, empty/missing devices, metadata, duplicate names, timestamp fallback, and English translation placeholders. The constructor compatibility regression now passes. `tests/test_ha_integration.py` runs the integration in a real Home Assistant (pinned by `requirements_test.txt`) with the SPOT API mocked: entry setup/unload/reload, tracker entities and devices, card registration, actions and WebSocket commands registered once, setup retry without logging the password, quiet feeds, disabled-device suppression after an options change, and the config and options flows end to end. These still do not validate frontend rendering or the bundled card inside a browser.

## Known constraints

- Prototype: live Home Assistant UI behavior not yet verified.
- Feed polling requests newest XML page; full historical XML pagination/backfill is not implemented.
- Public OSM tile usage can encounter HTTP 403; users may supply an authorized tile provider.
- The archive is persistent: migrations, pruning and removal must be explicitly designed and tested.
