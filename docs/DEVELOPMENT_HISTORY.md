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
