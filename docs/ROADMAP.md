# Roadmap — SPOT Trace History

_Status as of 12 October 2026. Proposed priorities, not committed release dates._

## P0 — Verify the Device Management UI

- [x] Initial options flow for selecting a discovered device and editing name / tracker enabled flag (implemented in supplied Device UI snapshot).
- [x] Persist per-device options and reload config entry after updates.
- [ ] Confirm menu, dropdown, placeholders, save and reload in a live Home Assistant instance.
- [ ] Add automated tests for options flow, missing devices, persisted settings, reload behavior and tracker suppression.
- [ ] Confirm whether disabled tracker entities should be removed from the entity registry or simply not instantiated; design migration-safe semantics.
- [ ] Update `translations/en.json` to match `strings.json` options text and validate hassfest.

## P1 — Improve device management

- [ ] Decide on archive-safe remove/hide/archive semantics, including confirmation UX. Do **not** delete history by default.
- [ ] Add clear per-device metadata (feed, messenger ID, latest fix, first/last position, point count).
- [ ] Consider device discovery and naming for archived-only GPX tracks.
- [ ] Decide whether per-device polling/retention controls are appropriate: polling is currently per feed, not per messenger.

## P2 — Feed management and history

- [ ] Review editing feed credentials/settings and deleting feed config entries independently of history.
- [ ] Implement optional historical XML backfill/pagination with API rate and retry considerations.
- [ ] Design explicit archive backup, retention, prune and export features with safeguards.
- [ ] Reconcile version labels (`0.5.0` URL/README versus `0.5.2` manifest/package).

## P3 — Quality and release

- [ ] Run Python/JS tests, hassfest and HACS packaging checks for each release.
- [ ] Test install, update, multiple feeds, restart, reload and GPX import on a live supported Home Assistant version.
- [ ] Review card map tile errors and authorized tile-provider configuration UX.
- [ ] Add release notes, update docs and publish through existing CI/release workflow.

## Non-goals unless explicitly requested

- Replacing the built-in map renderer with a new mapping library.
- Automatically deleting SQLite positions when a device or feed is removed.
- Assuming a SPOT feed uniquely represents one messenger/device.
