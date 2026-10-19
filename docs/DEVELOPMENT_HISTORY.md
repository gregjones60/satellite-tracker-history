# Development history and decisions

_Compiled from this ChatGPT Project conversation and the uploaded source snapshot on 12 October 2026. This is a decision log, not a claim that every feature was verified in a running HA installation._

## Initial integration and distribution

- Created a Home Assistant custom integration for SPOT Trace History, with public XML feed polling, SQLite position history, GPX import, device trackers, and a bundled history map card.
- Chose **one configuration entry per SPOT feed**, not a single integration entry aggregating every feed. Multiple devices can still be discovered within one feed. Card can aggregate across entries.
- Packaged as a **HACS Integration**, not a theme/template/dashboard.
- Addressed hassfest feedback: added the `http` manifest dependency and documentation URL, and defined `CONFIG_SCHEMA` for a config-entry-only integration.
- Created integration branding assets; branding appeared in HA Integrations after deployment, while HACS icon appearance was initially inconsistent. Branding repository propagation is distinct from local assets.

## Map and history

- Added automatically registered bundled map card; users need not manually copy JS to `/config/www`.
- Added card device visibility and per-device labels/colors; supports multi-feed display.
- Added GPX import per feed and optional GPX-track-name to messenger-ID mapping.
- Added tile-provider customization after default map tile 403 reports, and reduced tile churn during panning. Current manifest version is `0.5.2`; README retains some `0.5.0` headings.

## Device Management UI — first implementation (12 October 2026)

- Started Home Assistant **Options → Manage devices** flow instead of building a separate web UI.
- Flow enumerates devices already present in the SQLite archive for the selected feed, shows stored point count and messenger ID, and allows friendly name and tracker enabled/disabled changes.
- Stored settings in config entry options keyed by messenger ID; added options update listener to reload entry; tracker respects configured names and enabled flag.
- **Deliberate decision:** disabled means *do not load/create the HA tracker*, **not** stop archiving messages. Avoid losing historical data from a multi-device feed.
- Prior work reported 7 Python tests passing and clean `git diff --check` for this implementation. These were reported at the time, not re-run by this documentation task.
- Device UI ZIP was generated for manual import into IntelliJ; this package is the baseline for these docs. Do not assume it has already been merged into the user's local Git working tree.

## Collaboration / Codex handoff

- User prefers working in IntelliJ with Codex and wants previous architectural decisions retained.
- ChatGPT Project conversation history does not automatically appear as full context in a separate Codex session. Repository `AGENTS.md` and these docs are the portable source of truth. Keep them updated with subsequent decisions.

## Options-flow test coverage (12 October 2026)

- Added ten passing options-step test cases using lightweight HA test doubles, real voluptuous schemas, and a temporary SQLite archive. Tests cover feed isolation, names/enabled defaults, selection metadata, saving while preserving other options and archive rows, and empty/missing-device paths.
- Added one strict expected-failure test for the known modern HA constructor incompatibility (`self.config_entry` is read-only). Step tests explicitly bypass that constructor so the remaining behavior can be tested. The compatibility test must be updated when the constructor is fixed.
- Added voluptuous to local and CI test dependency instructions. Real HA UI, option persistence/reloads, and tracker suppression still need validation.

## Release version handling (12 October 2026)

- Kept manifest version `0.5.2` as the version source and replaced the card's fixed `0.5.0` cache parameter with the installed manifest version from HA's loader.
- Added `build_release.py --version X.Y.Z` to update manifest/package versions together; ordinary builds use the manifest version. Added seven tests for archive metadata, synchronization, version tags, invalid versions, and bytecode exclusion.
- Release workflow verifies that the committed manifest matches the tag, builds with the tag version, validates it, and uploads only the matching archive. HACS requires a published GitHub release to display a release version rather than a branch commit hash; this change does not itself publish a release.

## CI and automatic main releases (12 October 2026)

- Changed CI to run for pushes to any branch, retaining PR/manual triggers.
- Replaced tag-triggered releases with successful CI completion for main pushes only. Release checks out the exact tested SHA, derives the tag from the manifest, and publishes the matching archive. Existing tags are preserved: a different commit requires a version bump. This supersedes the manual tag-push process above.
- Fixed first-release tag detection after GitHub returned 422 for an absent tag at the commits endpoint. The release guard now checks the Git reference endpoint first (missing reference: 404), then resolves existing tags to commits. Seven JavaScript tests cover missing tags, annotated tag resolution, version conflicts, and API error propagation.
- Added automatic patch increments after releases continued building the fixed manifest version. Main releases now choose one patch above the highest stable manifest/tag version, update all version metadata and README, validate the build, and commit the version files back to main before publishing. Six additional tests cover selection and successive release builds. This supersedes manual patch bumps; local explicit-version builds remain supported. Bot pushes require repository permission and never force changes.

## Device archive metadata (12 October 2026)

- Added feed ID, first/latest archived position times in UTC, and latest coordinates to device settings alongside messenger ID and point count. Reads remain feed-specific, including archived GPX tracks. Selector labels now include messenger IDs so duplicate friendly names can be distinguished.
- Fixed the options-flow constructor to let HA supply its read-only config entry. Tests now exercise the normal constructor; the previous expected failure passes. Synchronized English translations and tested their placeholders against the form.
- Validation: 37 Python tests and 10 JavaScript tests passed, with no expected failures; compilation, package metadata, and whitespace checks passed. Live HA UI and hassfest execution remain unverified. The release workflow will assign the next version when this feature is pushed to main.

## Combined GPX exports (12 October 2026)

- Added per-track routing for the SPOT web app's combined GPX downloads. Messenger IDs do not encode feed IDs; routing uses already-archived membership or explicit `feed_mapping` (track name to configured feed ID). Unknown/ambiguous destinations fail before any inserts. Explicit top-level feed/entry targeting retains its previous whole-file behavior.
- The file is parsed once, fixes are remapped and deduplicated per destination, and affected coordinators refresh. Existing import path restrictions are retained. This supersedes the earlier requirement to split multi-feed exports manually.
- Added 11 importer tests using the combined fixture and real temporary SQLite archives. Validation: 48 Python tests, 10 JavaScript tests, compilation and package checks pass. Live HA action UI and hassfest execution remain unverified.

## SPOT iOS SQLite import (13 October 2026)

- Added `spot_trace_history.import_sqlite` using the observed iOS tables (`devices`, `messages`, `message_types`), Unix-second timestamps, text coordinates, source message keys, and preserved message types. Account/password tables are never queried. The source is opened read-only.
- Reused GPX destination planning and coordinator refreshes, retaining single-feed targeting and per-name device/feed mappings. Invalid locations are skipped; unsupported schemas, duplicate device names, orphaned messages, and ambiguous routing abort before archive writes. Extracted shared config-directory path validation and excluded local `db/` exports from Git.
- Added synthetic parser/import/path tests. Full checks: 64 Python tests, 10 JavaScript tests passed. Two imports of the real export into a temporary archive retained 21,011 fixes (8,886 Ultimate, 12,125 Bluey); one invalid fix was skipped and the source checksum remained unchanged. No private database contents were added to tests or source control. Live HA and hassfest execution remain unverified.

## Duplicate frontend script registration (13 October 2026)

- Wrapped the card script in a private scope and guarded custom-element and card-picker registration. Added behavioral tests that load the script twice and load it after an existing definition. An old manual `/local/` resource must still be removed: existing definitions cannot be replaced on a loaded page, and older scripts lack these guards.

## Map zoom and parent sizing (13 October 2026)

- Added accessible on-map +/− buttons using the same bounded zoom function as wheel events. Buttons disable at zoom limits; their pointer events do not start map dragging.
- Replaced the fixed map height with a flex layout filling a sized parent, preserving controls and a 420px fallback basis for parents without a height. The map retains a 200px minimum height. Documented HA Panel view for full-width display and the parent-height requirement.
- Validation: 64 Python tests and 13 JavaScript tests pass, including button/wheel behavior and limits. Browser/HA visual layout remains unverified.

## Named trips (13 October 2026)

- Added shared persistent trip definitions with unique names and inclusive calendar start/end dates, stored in an additive SQLite table. Trips do not change or copy positions and persist independently of feed entries.
- Added authenticated WebSocket create/list commands and card controls to save the chosen dates and select a trip. Selection loads that range for visible devices; editing dates returns to custom mode. Refresh reloads trips from other cards. Dates use the existing browser-timezone interpretation; track query bounds remain enforced.
- Added storage/migration, validation, WebSocket, and card behavior tests. Editing/deleting definitions and multi-trip filtering remain future work. Live HA rendering remains unverified.

## Trip editing and deletion (13 October 2026)

- Added update/delete commands and map controls for selected trips. Editing preserves the trip ID; cancel restores saved dates. Deleting asks for confirmation, removes only trip metadata, and leaves the map's dates in custom mode without deleting positions.
- Reused name/date validation, retained duplicate-name uniqueness, and added explicit missing-trip errors for stale selections. Concurrent edits currently use the last successful save; conflict detection and multi-trip selection remain future work.
- Validation: 78 Python tests and 20 JavaScript tests pass, covering update rollback, preserved history, missing IDs, save failures, cancel, and confirmation. Live HA UI remains unverified.

## Trip dialogs (13 October 2026)

- Replaced inline trip name/edit fields with native modal create/edit dialogs. Editing prefills the existing name/date range and submits an update by trip ID; changing dates does not require a new name. Dialog date fields are independent of map dates until a successful save. Cancel/Escape closes without writing or changing the filter; errors retain input inside the dialog. Submission disables Save/Cancel while awaiting the server.
- Updated frontend tests and added a backend regression for date changes with an unchanged name. Live HA rendering/focus behavior remains unverified.

## Trip vehicles (13 October 2026)

- Added vehicle checkboxes and an explicit all-vehicles option to create/edit dialogs. Trip filtering now includes membership as well as dates. Participants use stable feed ID + messenger ID references; removed devices remain visible as unavailable when editing so selections are not silently lost.
- Added a nullable JSON column to trips without changing positions. Old trips retain all-vehicles semantics; explicit selections must contain a vehicle, duplicate references are normalized, and old client updates preserve membership when the field is omitted.
- Validation: 86 Python tests and 23 JavaScript tests pass, including migration, persistence, payloads, feed isolation, excluded trailers, unavailable participants, and legacy behavior. Live HA dialog validation remains unverified.

## Icons and native HA device settings (13 October 2026)

- Added the standard HA IconSelector to device options; icons persist per messenger and are exposed as tracker defaults. Clearing restores the automatic icon. Options saves preserve unrelated per-device settings.
- Added native device info with stable feed/messenger identity, name, and SPOT manufacturer. Area/labels and the screenshot's entity ID, visibility, enabled, and voice controls use HA's standard entity/device settings. Native name/icon overrides remain authoritative; no parallel registry settings are stored in integration options.
- Synchronized English translations and added options/tracker tests for icon persistence/clearing, identity across renames/feeds, disabled tracker suppression, and later discovery. Validation: 89 Python tests and 23 JavaScript tests pass; live HA registry/UI behavior remains unverified.

## Year filtering (13 October 2026)

- Added a Year dropdown beside the map dates, populated from included devices' archive ranges plus the current year. Selection applies the full calendar year, clears trip restrictions, retains visibility choices, and refreshes tracks. Manual dates and trip selection synchronize the year control.
- Changed route fitting to iterative bounds so large yearly queries across several vehicles do not exceed JavaScript argument limits. Existing query caps remain.
- Validation: 89 Python tests and 26 JavaScript tests pass, including leap-year boundaries, empty metadata, card-scoped years, and 160,000-point route fitting. Live HA UI remains unverified.

## Mouse zoom precision (19 October 2026)

- Replaced per-event wheel jumps with normalized accumulated movement, one-step caps, and a 120ms minimum between wheel zoom steps. Small gestures no longer cause immediate level changes; pauses/direction changes discard leftover movement. No delayed timers continue zooming after input stops.
- Anchored wheel zoom under the pointer by adjusting the map centre around the new scale. Integer tile zoom levels and centre-based +/− controls are retained.
- Added tests for trackpad accumulation/rate limiting, cursor anchoring, bounds, delta units, zero movement, and gesture resets. Live HA/browser gesture feel remains unverified.
