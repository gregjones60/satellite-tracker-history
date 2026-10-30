# 3. Rename to Satellite Tracker History

Date: 2026-10-30

## Status

Accepted.

## Context

The integration began as SPOT Trace History (`spot_trace_history`) and now supports Garmin inReach
MapShare as well. A Home Assistant domain is the integration's folder name: config entries, entity
registry entries (by platform) and device identifiers all carry it, and nothing in Home Assistant moves
them to a new domain. HACS installs one integration per repository, so a release cannot ship both the
old and the new folder.

## Decision

Rename to Satellite Tracker History (`satellite_tracker_history`) in v0.7.0, without trademarks in the
name, and take over the old domain's state in the new integration:

- After Home Assistant has started, if the old integration is not loaded, recreate each of its entries
  through the `import` flow (splitting version 1 feed entries into vehicles), then remove the old
  entry. If it is loaded, do nothing and raise a `legacy_installed` repair issue, because its entities
  cannot be moved while loaded and both would poll the same feeds.
- Each new entry, while setting up, changes its tracker entity's platform to the new domain, then
  moves its device to the new entry with new identifiers. The entity goes first: moving a device
  deletes the entities its old entry still owns. Unique IDs and entity IDs do not change.
- Bring in `spot_trace_history.sqlite` when the archive is first opened: rename it, with SQLite's side
  files, or, if `satellite_tracker_history.sqlite` already exists, merge its positions and trips in
  and keep it as `spot_trace_history.sqlite.migrated`.
- Keep `custom:spot-trace-history-card` as an alias of the card, so dashboards keep working.
- The actions and WebSocket commands move to the new domain; automations calling the old actions must
  be updated.

Amended in v0.7.1: Home Assistant only loads an integration at startup once it has entries of its own,
so in v0.7.0 the startup takeover never ran on an upgraded install, and opening the setup form created
an empty new archive that blocked the rename. The config flow now starts with a `legacy` step that runs
the takeover (serialised with the startup one by a lock), and the archive is merged rather than left
behind when both files exist.

## Consequences

- Upgrading needs two manual steps: removing the old integration's folder, then adding Satellite
  Tracker History, which offers the takeover.
- The takeover is ordinary config-flow and registry code that runs on every start, finding nothing to
  do once the old entries are gone.
- The old archive name and card element name remain in the code for as long as the takeover is kept.
