# 1. One config entry per vehicle

Date: 2026-10-30

## Status

Accepted.

## Context

Up to v0.5.17 each config entry was a SPOT shared feed, and every messenger in that feed became a
device tracker under it. Settings for each messenger lived in `options['devices'][messenger_id]`,
and the options flow was a menu of the feed's devices. The integration is going to support other
tracker services, starting with Garmin inReach MapShare, where the natural unit is also a device
within a shared feed. Treating the feed as the parent of its devices made the vehicle, which is
what users name, place in an area and show on the map, a second-class object.

## Decision

A config entry is one vehicle: one tracker in one feed. The entry stores the feed ID, its
password and the messenger ID, and its options hold only the vehicle's name and icon.

- Several vehicles may use the same feed. They share one fetch per poll through a `FeedPoller`
  keyed by feed and password, so a wrong password on one entry cannot affect another.
- The archive keeps its `(feed, device)` keys, so no history moves. Trips already reference
  vehicles by feed and messenger ID.
- Tracker unique IDs stay `<feed>_<messenger>`, so entity IDs, areas and labels survive.
- The entry's unique ID is `spot:<feed>:<messenger>`; the provider prefix leaves room for other
  tracker services.
- Turning a tracker off is done with Home Assistant's own entity or entry disabling, not an
  integration option.

Version 1 entries are migrated by splitting: the original entry keeps an enabled messenger that
already has a tracker, and every other messenger in the archive or the old settings becomes a new
entry through an import flow. Each new entry takes over its device from the feed entry when it
sets up, because device identifiers are only unique within a config entry. A messenger whose
tracker was switched off gets `options['enabled'] = False`, which only sets the entity's
registry default, so it is created disabled.

## Consequences

- Adding a feed with several messengers means adding it once per messenger.
- History imports target vehicles. A track that a vehicle does not recognise may only be imported
  into it on its own, so two trackers' history is never merged without an explicit mapping.
- Archive-only devices from old GPX imports become vehicles on migration; users can delete those
  entries without losing history.
- A feed entry that never received a position has no messenger to keep. It migrates with no
  device and fails setup with a message asking the user to add the vehicle again.
- If Home Assistant stops between updating the original entry and creating the others, the
  remaining messengers are not split on the next start; they can be added through the config flow,
  and their history is still in the archive.
