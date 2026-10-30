<p>
  <img src="branding/logo.png" alt="SPOT Trace History" width="250">
</p>

# SPOT Trace History v0.5.17 — multi-feed prototype + bundled card

Each **vehicle** is a separate integration configuration entry: one tracker, which for SPOT is one messenger in a SPOT shared feed. To add a vehicle, go to **Settings → Devices & services → Add integration → SPOT Trace History**, enter the feed ID (and password if needed), then choose the vehicle's messenger. The list shows messengers the feed has reported recently or the archive holds; if the feed has been quiet, type the messenger ID. Add the same feed again for each other messenger on it. Vehicles that share a feed are polled together, with one request per feed.

The password field is masked. To change a password later, open the vehicle's
**⋮** menu on the integration page and choose **Reconfigure**. The feed and
messenger cannot be changed, because they identify the vehicle's tracker and
archived history.

The custom map card automatically shows **all** configured vehicles together. Do **not** set `entry_id` on the card unless you intentionally want to show just one vehicle. Each vehicle can be removed independently through Home Assistant's integrations page. The SQLite archive is retained on removal.

### Upgrading from feed entries

Up to v0.5.17, each integration entry was a whole feed and held all its
messengers. The first start after upgrading splits each feed entry into one
entry per messenger: every messenger in the archive or the old device settings
becomes a vehicle. Nothing else has to be set up again:

- The tracker keeps its entity ID, device, area and labels, and its history and
  trips are unchanged.
- Names and icons from **Manage devices** become each vehicle's own settings.
- A tracker that was switched off stays off as a disabled entity, and positions
  are still collected and shown on the map.
- A feed entry that never received any position has no messenger to keep, so it
  shows an error asking you to delete it and add the vehicle again.

Vehicles split this way include archive-only devices created by earlier GPX
imports. Delete any you don't want; their history stays in the archive.

## Installation

Copy `custom_components/spot_trace_history` to `/config/custom_components/spot_trace_history` and restart Home Assistant. Add one integration entry per vehicle. The integration automatically serves and registers its bundled card JavaScript; **no `/config/www` folder or manual dashboard resource is needed**. Refresh the browser cache after updating.

For HACS, publish this repository with `custom_components/spot_trace_history` at its root, add the GitHub repository URL to HACS as a **custom integration repository**, install, and restart Home Assistant. HACS installation and update do not automatically create a GitHub repository.

The card asset is available at `/spot_trace_history/spot-trace-history-card.js?v=0.5.17` once Home Assistant has restarted. The version is read from the installed integration manifest. Home Assistant's frontend loads the bundled script automatically. If you previously registered `/local/spot-trace-history-card.js` manually, remove that old dashboard resource to avoid loading two card versions.

## Vehicle settings

Open **Settings → Devices & services → SPOT Trace History**, choose the vehicle
and click **Configure** to see its feed ID, messenger ID, stored position count,
first/latest archived position times (UTC), and latest coordinates. These details
come from the local archive, including GPX imports. They do not guarantee a
fresh fix from the tracker.

You can name the vehicle and choose its icon. Leave the name empty to use the
name SPOT reports. The **Icon** picker accepts Material Design Icons such as
`mdi:car-estate` or `mdi:caravan`; clear it to restore the default icon. The map
card shows the vehicle with the same name and icon. Each tracker is
associated with a native Home Assistant device, with a stable identity across
renames and integration reloads. The tracker takes its name from that device:
the vehicle name becomes the device name, and the device page shows the
messenger ID as its serial number. A name you give the device on its own Home
Assistant device page takes precedence.

For the standard settings shown in Home Assistant's entity editor—entity ID,
area, labels, enabled/visible flags, and voice assistant exposure—open the tracker
under **Settings → Devices & services → Entities**, then open its settings.
You can assign an area or labels on its native device page too. Native entity
name/icon overrides take precedence over the integration's defaults; clear an
override there if you want to use the vehicle's settings.
These settings are managed by HA's registries, so they are not duplicated in
the integration options. See [HA entity customization](https://www.home-assistant.io/docs/configuration/customizing-devices/).

To stop the tracker but keep collecting positions and map history, disable the
tracker entity. To stop polling as well, disable the vehicle's integration entry,
which also hides it from the map. Deleting the entry keeps its archived history,
and adding the same feed and messenger again brings it back.

For bug reports, use **Download diagnostics** on the vehicle's **⋮** menu. The
file redacts the feed ID, password, coordinates, messenger ID and vehicle name.
It includes the vehicle's archive summary (position count and first/latest
times) and the last update status.
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
days: 30
devices:
  Bluey:
    name: Vehicle
    color: '#1976d2'
    enabled: true
  Ultimate:
    name: Camper Trailer
    color: '#e65100'
    icon: mdi:caravan
    enabled: true
```

The card's `devices` keys may be a vehicle's messenger ID, its name, or, to be unambiguous, `<entry_id>:<messenger_id>`. The card provides a visibility checkbox for each vehicle. A new vehicle appears once it has archived positions and the card is reloaded.

The map uses [Leaflet](https://leafletjs.com) 1.9.4, which is bundled with the
integration and needs no internet access beyond the map tiles. It has **+ / −
zoom buttons**, smooth mouse-wheel, trackpad and pinch zoom, drag-to-pan, and
**Fit routes**. Each vehicle's latest position, or its position on the trip
timeline, is marked in its route colour with the icon chosen in the
vehicle's integration settings. A card `icon` setting overrides that icon, and a
vehicle without an icon is shown as a dot.

The card has no title of its own, so name it with your dashboard (for example
a heading card or the view title); a `title` option is ignored. Its filters
(year, dates, trip, buttons and vehicle checkboxes) share one row, wrapping
onto more rows only on narrow screens. The card fills its parent's width and
available height, with the map using the space below the filters. When the dashboard provides no fixed parent
height, the map uses a 420px fallback basis. Its minimum map height is 200px.
For a full-width view, place this card as the only card in a
[Panel view](https://www.home-assistant.io/dashboards/panel/). Full-height sizing
requires the containing layout to supply a height; a normal dashboard column
still controls the card's available width and space. Live HA layout validation
remains necessary.

## Named trips

Use the **Year** dropdown beside the date fields to show January 1 through
December 31 of a particular year. Years are drawn from the first/last archived
positions of devices included by the card, plus the current year; a listed year
may have gaps in its history. Selecting a year refreshes the map and clears the
trip filter while retaining your device visibility choices. Editing dates
returns the year selector to **Custom dates**, unless they match a full year.
The existing 50,000-position limit per device still applies.

On the map card, choose **From** and **To**, then click **New trip**. A dialog
opens with those dates; enter a name and click **Create trip**. Choose a saved
trip from the **Trip** dropdown to load
that period immediately. In the dialog, select the **Vehicles involved**—for
example, check the vehicle and leave the camper trailer unchecked for a weekend
away without it. Alternatively choose **All vehicles (including future trackers)**.
Selecting a trip filters both its period and participants; map device checkboxes
can narrow the display further. Changing either date returns the selector to **Custom dates**; click
**Refresh** to apply those dates and reload the saved-trip list.

Trips are shared across this integration's feeds and cards, and persist in
`spot_trace_history.sqlite` across restarts. They save inclusive calendar dates,
interpreted in the browser's timezone like the existing date controls. Names
must be unique and contain 1–100 characters. Trip periods are capped at 366
calendar days; the existing track query limit of 366 elapsed days and 50,000
positions per device still applies. Creating a trip does not copy or alter GPS
records; future positions inside its period are included automatically.

To change a saved trip, select it and click **Edit trip**. The dialog opens with
its existing name and dates. Change the name or dates, then click **Save changes**.
You can keep the original name when changing dates. **Cancel** or Escape closes
the dialog without changing the trip or map filter. Editing keeps the existing
trip ID. Save errors appear inside the dialog and retain the entered values.
Vehicle selections can be changed in the same dialog. Each participant is
identified by feed ID and messenger ID, so identically named vehicles remain
distinct. Selections survive removing/re-adding a feed. An unavailable vehicle
remains listed and selected in the editor until you uncheck it. Trips created
before vehicle selection was added include all vehicles by default; editing
them lets you choose specific participants. Select at least one vehicle unless
you use the all-vehicles option. Vehicle selection changes no archived positions.

To remove a trip, select it and click **Delete trip**, then confirm. This removes
only its definition; all GPS records remain. The displayed dates remain as
custom dates, so the current map does not disappear. Click **Refresh** to see
changes made by another card. Missing trips or duplicate names produce an error
instead of silently replacing another trip.

Selecting multiple trips remains future work. Live Home Assistant UI validation
remains necessary.

### Explore a trip timeline

Select a saved trip, then click **Timeline**. The timeline opens as a panel
floating over the top-right of the map, so the map keeps its size; close it with
**×**, **Escape** or **Timeline** again. Closing the panel does not stop
playback. Enable **Explore trip timeline** in the panel, then drag
the **Time** slider (or use its keyboard arrow keys) to move vehicle markers to
their last recorded fix at or before that time. The full routes remain visible
for context. Vehicles with no fix yet in the loaded period have no marker.
Each vehicle's latest recorded timestamp is listed below the slider, in your
browser's timezone, so gaps do not imply continuous movement or live tracking.

Click **Play** to advance automatically and **Pause** to stop at the current
position. **Speed** selects trip time per real second: 1 minute, 10 minutes,
1 hour (default), 6 hours, or 1 day. You can change speed while playing. At the
end, playback stops and the button becomes **Replay**. Scrubbing pauses playback
so you can inspect a particular moment. Hiding the browser tab or leaving the
dashboard also pauses it; returning does not automatically resume.

Turn the timeline off to restore end-of-route markers. Loading different dates,
trips, or visible vehicles resets timeline mode; leaving the trip filter closes
the panel and disables **Timeline**. Playback moves markers without redrawing full routes on each tick and does
not make additional history requests. It uses loaded history and its query limits,
so a vehicle reaching 50,000 points is flagged as potentially incomplete.

## Import GPX history

### Import results

After either GPX or SQLite import, check **Notifications** in Home Assistant.
The completion report shows newly added locations, duplicates ignored, invalid
or unnamed records skipped, total source records, destination feed count, and
the date range of valid source records in UTC. Reimporting a complete file can
correctly show **0 added** with all valid records counted as duplicates.
The latest import replaces the previous notification; failures replace it with
an error notification. If an insertion fails after another feed was written,
the import may be partial; retrying deduplicates existing fixes.

Both actions also support optional response data for Developer Tools and
automations (`response_variable`). The response contains `total`, `valid`,
`added`, `duplicates`, `skipped`, `start_time`, `end_time`, and per-destination
counts. Dates describe valid source records, including duplicates, rather than
only newly inserted records. Existing automations need no changes.

After updating, restart HA to register the actions' response support. To see
older imports on the map, refresh it and choose the matching **Year** or date
range; importing does not change the map's default recent-history filter.

Put exports under `/config/spot_exports/` and run **Developer Tools → Actions**:

```yaml
action: spot_trace_history.import_gpx
data:
  filename: spot_exports/vehicle.gpx
  feed_id: YOUR_VEHICLE_FEED_ID
  device_mapping:
    Bluey: YOUR_VEHICLE_MESSENGER_ID
```

Repeat with the trailer's GPX. The optional `device_mapping` maps the GPX track name to the messenger ID of the vehicle it belongs to. To import a single-track GPX into one vehicle without a mapping, pass that vehicle's `entry_id` instead. A file with several tracks always needs each track to identify its vehicle, so two trackers' history is never merged into one vehicle.

### Combined exports with several vehicles

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

The importer sends each track to the configured vehicle with that messenger ID.
If the same messenger ID is configured on two feeds, add an explicit GPX
track-to-feed mapping:

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

Both vehicles must already be configured in Home Assistant. In the action UI,
enter `feed_mapping` as an object, just like `device_mapping`. Without explicit
device mapping, a track name matching a vehicle's archived SPOT name or
messenger ID selects that vehicle, and a feed with only one vehicle takes a track
it does not recognise if that track is the only one going to it. Unknown or
ambiguous destinations cause an error before any tracks are imported. Each
track is archived only for its destination vehicle; repeated imports deduplicate
existing fixes. A top-level `feed_id` limits the import to that feed's vehicles.

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
whitespace is trimmed during import. Find each vehicle's messenger ID under its
**Configure** dialog. Use `feed_mapping` when automatic routing is ambiguous.
Without an explicit mapping, the importer matches archived SPOT names and
messenger IDs; vehicle names set in the integration are separate from those
archived names.

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
Both vehicles must already be configured. Like GPX imports, you can omit
`feed_mapping` when the mapped messenger IDs or archived names identify exactly
one vehicle, and `entry_id` imports a single-device database into one vehicle.
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

Experimental, not live-tested. Latest 50 XML messages polled per feed, shared by the vehicles on it; complete XML pagination is not implemented. The historical website export must be imported manually. Card queries are limited to 366 days and 50,000 points per device. Back up `/config/spot_trace_history.sqlite`. All map tiles require internet connectivity and are served by OpenStreetMap.

## Release notes 0.5.0

- Card served from the integration directory and registered via Home Assistant frontend startup, with versioned URL for cache busting.
- Repository structured for GitHub and HACS custom repository installation.
- No changes to existing feed entries or SQLite archive.

**Compatibility:** uses Home Assistant `StaticPathConfig` and `frontend.add_extra_js_url`; intended for modern Home Assistant releases. Not tested in a live HA instance.


### Map tile providers (v0.5.2)

The card accepts `tile_url` and `tile_attribution` options. For example, with a tile provider you have permission to use:

```yaml
type: custom:spot-trace-history-card
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
