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
- Rename `spot_trace_history.sqlite` to `satellite_tracker_history.sqlite` once, with SQLite's side
  files, unless the new file exists.
- Keep `custom:spot-trace-history-card` as an alias of the card, so dashboards keep working.
- The actions and WebSocket commands move to the new domain; automations calling the old actions must
  be updated.

## Consequences

- Upgrading needs one manual step: removing the old integration's folder.
- The takeover is ordinary config-flow and registry code that runs on every start, finding nothing to
  do once the old entries are gone.
- The old archive name and card element name remain in the code for as long as the takeover is kept.
