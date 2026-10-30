# 2. Provider-prefixed archive feeds

Date: 2026-10-30

## Status

Accepted.

## Context

The archive keys every position by `(feed, device)`, and tracker unique IDs are `<feed>_<device>`.
Until now every feed was a SPOT feed ID. Supporting Garmin inReach MapShare adds a second kind of feed,
named by the MapShare owner, so a MapShare name and a SPOT feed ID could be the same string. Existing
SPOT history, trips and entity IDs depend on the current keys and must not change.

## Decision

The archive feed key comes from one function, `vehicle.archive_feed(entry.data)`:

- SPOT uses the raw feed ID, exactly as before.
- Every other provider uses `<provider>:<feed>`, for example `garmin:YourName`.

The entry stores the raw feed (`data['feed_id']`) and `data['provider']`. Entries created before
providers existed have no `provider` and are treated as SPOT, so no migration is needed. The config
entry's unique ID is `<provider>:<feed>:<device>` for every provider, and the tracker unique ID is
`<archive feed>_<device>`.

Each provider has a client with `fetch(since)`. The shared poller asks for positions since the feed's
newest archived fix, or 30 days back when there is none; SPOT ignores `since`, and Garmin sends it as
`d1`, without which a MapShare returns only the latest points.

## Consequences

- SPOT keys are untouched; Garmin history can never mix with a SPOT feed of the same name.
- Trips and the card's `feed_id` use the archive key, so a Garmin participant is stored as
  `garmin:<name>`.
- Adding another service means a client with `fetch(since)`, a manufacturer name, a config step and
  its error mapping; the archive and vehicle model need no change.
