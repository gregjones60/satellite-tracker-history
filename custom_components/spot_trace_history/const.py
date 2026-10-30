"""Constants for SPOT Trace History."""

DOMAIN = "spot_trace_history"
INTERVAL = 300
ARCHIVE_FILENAME = "spot_trace_history.sqlite"

# Each config entry is one vehicle: the tracker `device` in the feed `feed_id` of a `provider`.
# SPOT: a shared feed ID and messenger ID. Garmin: a MapShare name and the device's IMEI.
CONF_PROVIDER = "provider"
PROVIDER_SPOT = "spot"
PROVIDER_GARMIN = "garmin"
CONF_FEED_ID = "feed_id"
# The Garmin setup form field; it accepts a MapShare name or link and is stored as `feed_id`.
CONF_MAPSHARE = "mapshare"
CONF_PASSWORD = "password"
CONF_DEVICE = "device"
CONF_NAME = "name"
CONF_ICON = "icon"
# Only written by the version 1 migration, for messengers whose tracker had been switched off.
CONF_ENABLED = "enabled"
# Version 1 entries were whole feeds, with per-messenger settings under this option.
CONF_DEVICES = "devices"
