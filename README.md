<p>
  <img src="branding/logo.png" alt="SPOT Trace History" width="250">
</p>

# SPOT Trace History v0.5.3 — multi-feed prototype + bundled card

Each SPOT XML feed is a **separate integration configuration entry**. To add another tracker, go to **Settings → Devices & services → Add integration → SPOT Trace History**, and enter that device's own feed ID (and password if needed). Repeat for each new device. A feed is not assumed to contain all devices.

The custom map card automatically queries devices across **all** configured SPOT feed entries, so the vehicle and trailer can be shown together. Do **not** set `entry_id` on the card unless you intentionally want to show just one feed. Each feed can be removed independently through Home Assistant's integrations page. The SQLite archive is retained on removal.

## Installation

Copy `custom_components/spot_trace_history` to `/config/custom_components/spot_trace_history` and restart Home Assistant. Add one integration entry per XML feed. The integration automatically serves and registers its bundled card JavaScript; **no `/config/www` folder or manual dashboard resource is needed**. Refresh the browser cache after updating.

For HACS, publish this repository with `custom_components/spot_trace_history` at its root, add the GitHub repository URL to HACS as a **custom integration repository**, install, and restart Home Assistant. HACS installation and update do not automatically create a GitHub repository.

The card asset is available at `/spot_trace_history/spot-trace-history-card.js?v=0.5.3` once Home Assistant has restarted. The version is read from the installed integration manifest. Home Assistant's frontend loads the bundled script automatically. If you previously registered `/local/spot-trace-history-card.js` manually, remove that old dashboard resource to avoid loading two card versions.

## Example card

```yaml
type: custom:spot-trace-history-card
title: Vehicle and camper trailer
days: 30
devices:
  Bluey:
    name: Vehicle
    color: '#1976d2'
    enabled: true
  Ultimate:
    name: Camper Trailer
    color: '#e65100'
    enabled: true
```

The card uses XML messenger IDs when present, or GPX track names for archived-only devices. For unambiguous per-feed overrides, use a key in the form `<entry_id>:<messenger_id>`. The card provides a visibility checkbox for each device. New devices appear after their feed is configured and polled, and the card is reloaded.

## Import GPX separately for each feed

Put exports under `/config/spot_exports/` and run **Developer Tools → Actions**:

```yaml
action: spot_trace_history.import_gpx
data:
  filename: spot_exports/vehicle.gpx
  feed_id: YOUR_VEHICLE_FEED_ID
  device_mapping:
    Bluey: YOUR_VEHICLE_MESSENGER_ID
```

Repeat with the trailer's GPX and feed ID. The optional `device_mapping` maps the GPX track name to the messenger ID used by the XML feed. Without this mapping, GPX tracks that don't match an XML messenger name may appear as a separate archived-only device. You may use `entry_id` instead of `feed_id` to select the destination.

**Important:** If a single GPX export contains multiple devices, do not import that whole export into both feeds. Export each device separately or split the GPX tracks first. The importer assigns *all* tracks in a file to the selected feed.

## Limitations

Experimental, not live-tested. Latest 50 XML messages polled per feed; complete XML pagination is not implemented. The historical website export must be imported manually. Card queries are limited to 366 days and 50,000 points per device. Back up `/config/spot_trace_history.sqlite`. All map tiles require internet connectivity and are served by OpenStreetMap.

## Release notes 0.5.0

- Card served from the integration directory and registered via Home Assistant frontend startup, with versioned URL for cache busting.
- Repository structured for GitHub and HACS custom repository installation.
- No changes to existing feed entries or SQLite archive.

**Compatibility:** uses Home Assistant `StaticPathConfig` and `frontend.add_extra_js_url`; intended for modern Home Assistant releases. Not tested in a live HA instance.


### Map tile providers (v0.5.2)

The card accepts `tile_url` and `tile_attribution` options. For example, with a tile provider you have permission to use:

```yaml
type: custom:spot-trace-history-card
title: SPOT History
tile_url: "https://your-authorized-tile-server.example/{z}/{x}/{y}.png"
tile_attribution: "© OpenStreetMap contributors, tiles © Your Provider"
```

Use a tile service that permits your usage, observe its attribution and API-key requirements. The default OpenStreetMap public tile server can return HTTP 403 when it blocks clients. This release does not circumvent blocks. If a 403 occurs, use an authorized alternative or investigate network/proxy headers and caching.

## v0.5.2: reduced map tile traffic
- Retains tile image elements while panning instead of destroying and recreating all images.
- Keeps a one-tile viewport buffer; offscreen tiles beyond that buffer are removed.
- Applies `strict-origin-when-cross-origin` to tile image requests.
- Shows a warning when tile requests fail.
- Uses the browser's normal HTTP cache; does not prefetch bulk map tiles or add cache-busting query parameters.
- Keeps independent XML feeds, device visibility and configurable tile provider.

The card is a small built-in SVG/tile renderer, not Leaflet. The changes
optimise that existing renderer without adding a new mapping dependency.
