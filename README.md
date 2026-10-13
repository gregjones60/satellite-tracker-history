<p>
  <img src="branding/logo.png" alt="SPOT Trace History" width="250">
</p>

# SPOT Trace History v0.5.6 — multi-feed prototype + bundled card

Each SPOT XML feed is a **separate integration configuration entry**. To add another tracker, go to **Settings → Devices & services → Add integration → SPOT Trace History**, and enter that device's own feed ID (and password if needed). Repeat for each new device. A feed is not assumed to contain all devices.

The custom map card automatically queries devices across **all** configured SPOT feed entries, so the vehicle and trailer can be shown together. Do **not** set `entry_id` on the card unless you intentionally want to show just one feed. Each feed can be removed independently through Home Assistant's integrations page. The SQLite archive is retained on removal.

## Installation

Copy `custom_components/spot_trace_history` to `/config/custom_components/spot_trace_history` and restart Home Assistant. Add one integration entry per XML feed. The integration automatically serves and registers its bundled card JavaScript; **no `/config/www` folder or manual dashboard resource is needed**. Refresh the browser cache after updating.

For HACS, publish this repository with `custom_components/spot_trace_history` at its root, add the GitHub repository URL to HACS as a **custom integration repository**, install, and restart Home Assistant. HACS installation and update do not automatically create a GitHub repository.

The card asset is available at `/spot_trace_history/spot-trace-history-card.js?v=0.5.6` once Home Assistant has restarted. The version is read from the installed integration manifest. Home Assistant's frontend loads the bundled script automatically. If you previously registered `/local/spot-trace-history-card.js` manually, remove that old dashboard resource to avoid loading two card versions.

## Manage devices

Open **Settings → Devices & services → SPOT Trace History → Configure → Manage devices**
for the feed you want to manage. Select a tracker to see its feed ID, messenger
ID, stored position count, first/latest archived position times (UTC), and
latest coordinates. These details come from the local archive, including GPX
imports. They do not guarantee a fresh fix from the tracker.

You can change its friendly name or disable its Home Assistant device tracker.
Disabling the tracker keeps collecting positions and preserves map history.
Devices with the same name are distinguished by messenger ID in the selector.
This UI still needs validation in a live Home Assistant instance.

### Duplicate card script errors

If browser logs report that `spot-trace-history-card` has already been defined,
check your dashboard resources for an old manual `/local/spot-trace-history-card.js`
entry and remove it. The integration automatically loads its bundled script.
Reload the browser after removing the old resource. The bundled card tolerates
repeat loading, but the first registered version remains active for that page;
removing the old resource ensures the current bundled version is used. An old
manually copied script may still throw this error until its resource is removed.

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

## Import GPX history

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

### Combined exports with multiple feeds

You can import the SPOT web app's **download all** GPX export in one action.
Omit the top-level `feed_id` and `entry_id` to route tracks individually:

```yaml
action: spot_trace_history.import_gpx
data:
  filename: spot_exports/all_devices.gpx
  device_mapping:
    Bluey: "YOUR_VEHICLE_MESSENGER_ID"
    Ultimate: "YOUR_TRAILER_MESSENGER_ID"
```

The importer matches each messenger ID to the configured feed whose archive
already contains that device. Feed IDs cannot be calculated from messenger IDs.
If an ID has not been discovered or appears in multiple feeds, add an explicit
GPX track-to-feed mapping:

```yaml
action: spot_trace_history.import_gpx
data:
  filename: spot_exports/all_devices.gpx
  device_mapping:
    Bluey: "YOUR_VEHICLE_MESSENGER_ID"
    Ultimate: "YOUR_TRAILER_MESSENGER_ID"
  feed_mapping:
    Bluey: "YOUR_VEHICLE_FEED_ID"
    Ultimate: "YOUR_TRAILER_FEED_ID"
```

Both feeds must already be configured in Home Assistant. In the action UI, enter
`feed_mapping` as an object, just like `device_mapping`. Without explicit device
mapping, unique archived device names can also select a feed. Unknown or
ambiguous destinations cause an error before any tracks are imported. Each
track is archived only in its destination feed; repeated imports deduplicate
existing fixes. Existing explicit `feed_id`/`entry_id` imports still assign the
whole file to one feed.

### GPX track-to-device mapping format

The **GPX track-to-device mapping** field expects an object with GPX track names
as keys and SPOT messenger IDs as string values. In the action's YAML editor:

```yaml
device_mapping:
  Bluey: "YOUR_VEHICLE_MESSENGER_ID"
  Ultimate: "YOUR_TRAILER_MESSENGER_ID"
```

If the mapping field's object editor expects JSON, enter only the mapping:

```json
{
  "Bluey": "YOUR_VEHICLE_MESSENGER_ID",
  "Ultimate": "YOUR_TRAILER_MESSENGER_ID"
}
```

Track names must match the GPX `<trk><name>` text, including case; surrounding
whitespace is trimmed during import. Find messenger IDs under
**Configure → Manage devices**. The mapping applies only to the selected
destination feed when `feed_id` or `entry_id` is specified. Omit those fields
for combined exports and use `feed_mapping` when automatic routing is ambiguous.
Without an explicit mapping, the importer tries archived device names, then
uses the GPX track name as the device ID. Friendly-name overrides in Manage
devices are separate from those archived names.

**Important:** Import a combined export once using per-track routing. Do not
import the whole file separately into both feeds with top-level `feed_id` values;
that would assign all its tracks to each selected feed.

## Import the SPOT iOS database

Copy a complete SPOT iOS SQLite export to `/config/spot_exports/spot_app.db`.
After updating the integration and restarting Home Assistant, run
**Developer Tools → Actions → SPOT Trace History: Import SPOT iOS database**:

```yaml
action: spot_trace_history.import_sqlite
data:
  filename: spot_exports/spot_app.db
  device_mapping:
    Bluey: "YOUR_VEHICLE_MESSENGER_ID"
    Ultimate: "YOUR_TRAILER_MESSENGER_ID"
  feed_mapping:
    Bluey: "YOUR_VEHICLE_FEED_ID"
    Ultimate: "YOUR_TRAILER_FEED_ID"
```

Mapping keys are the app's device names, with surrounding whitespace trimmed.
The app database's numeric device IDs are separate from XML messenger IDs.
Both feeds must already be configured. Like GPX imports, you can omit
`feed_mapping` when the mapped messenger IDs or archived names identify exactly
one feed. `feed_id` or `entry_id` instead assigns all records to one destination.
The object fields accept YAML or JSON mappings as shown in the GPX section.

The importer reads `devices`, `messages`, and `message_types` from the observed
SPOT iOS schema, preserving timestamps, coordinates, names, and message types.
It opens the source read-only and never queries account/password tables.
Invalid coordinates or timestamps are skipped; unsupported databases, duplicate
device names, missing device/type records, and ambiguous routing produce errors
before records are inserted. Empty exports or exports with no valid locations
also produce an error. Supported extensions are `.db`, `.sqlite`, and `.sqlite3`.
Repeated imports and matching fixes already collected through XML/GPX are
deduplicated. Affected trackers and history queries refresh after import.

Use a complete, consistent export, rather than copying an actively written app
database on its own. If the export includes `-wal`/`-shm` companion files, keep
them with the database under their original matching names. Keep the original
backup outside Git: it can include account credentials. Files must be inside
the Home Assistant config directory; symlinks escaping that directory are
rejected. No direct browser file-upload page is provided; copy the export into
the config directory before running the action.

Validated against the supplied export: 21,011 valid fixes from 21,012 messages
were imported into a temporary archive, and a second import added no duplicates.
The source file remained unchanged. Live Home Assistant action/UI behavior
still needs validation.

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
