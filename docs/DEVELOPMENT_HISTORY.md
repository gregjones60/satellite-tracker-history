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
