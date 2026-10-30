"""Constants for SPOT Trace History."""

DOMAIN = "spot_trace_history"
INTERVAL = 300
ARCHIVE_FILENAME = "spot_trace_history.sqlite"

# Each config entry is one vehicle: the tracker `device` (a SPOT messenger ID) in the feed `feed_id`.
CONF_FEED_ID = "feed_id"
CONF_PASSWORD = "password"
CONF_DEVICE = "device"
CONF_NAME = "name"
CONF_ICON = "icon"
# Only written by the version 1 migration, for messengers whose tracker had been switched off.
CONF_ENABLED = "enabled"
# Version 1 entries were whole feeds, with per-messenger settings under this option.
CONF_DEVICES = "devices"
