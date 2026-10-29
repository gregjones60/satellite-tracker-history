"""Authenticated WebSocket commands for named archive date ranges."""
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.helpers import config_validation as cv

from .store import async_get_store

DEVICES = vol.Any(None, [vol.Schema({vol.Required('feed_id'): cv.string, vol.Required('device'): cv.string})])


@websocket_api.websocket_command({vol.Required('type'): 'spot_trace_history/trips'})
@websocket_api.async_response
async def ws_trips(hass, connection, msg):
    store = async_get_store(hass)
    trips = await hass.async_add_executor_job(store.list_trips)
    connection.send_result(msg['id'], trips)


@websocket_api.websocket_command({
    vol.Required('type'): 'spot_trace_history/create_trip',
    vol.Required('name'): cv.string,
    vol.Required('start_date'): cv.string,
    vol.Required('end_date'): cv.string,
    vol.Optional('devices'): DEVICES,
})
@websocket_api.async_response
async def ws_create_trip(hass, connection, msg):
    store = async_get_store(hass)
    try:
        trip = await hass.async_add_executor_job(store.create_trip, msg['name'], msg['start_date'], msg['end_date'], msg.get('devices'))
    except ValueError as exc:
        connection.send_error(msg['id'], 'invalid_trip', str(exc))
        return
    connection.send_result(msg['id'], trip)


@websocket_api.websocket_command({
    vol.Required('type'): 'spot_trace_history/update_trip',
    vol.Required('trip_id'): cv.string,
    vol.Required('name'): cv.string,
    vol.Required('start_date'): cv.string,
    vol.Required('end_date'): cv.string,
    vol.Optional('devices'): DEVICES,
})
@websocket_api.async_response
async def ws_update_trip(hass, connection, msg):
    store = async_get_store(hass)
    try:
        trip = await hass.async_add_executor_job(store.update_trip, msg['trip_id'], msg['name'],
                                                msg['start_date'], msg['end_date'], msg.get('devices', ...))
    except ValueError as exc:
        connection.send_error(msg['id'], 'invalid_trip', str(exc))
        return
    except KeyError as exc:
        connection.send_error(msg['id'], 'not_found', exc.args[0])
        return
    connection.send_result(msg['id'], trip)


@websocket_api.websocket_command({
    vol.Required('type'): 'spot_trace_history/delete_trip',
    vol.Required('trip_id'): cv.string,
})
@websocket_api.async_response
async def ws_delete_trip(hass, connection, msg):
    store = async_get_store(hass)
    try:
        await hass.async_add_executor_job(store.delete_trip, msg['trip_id'])
    except KeyError as exc:
        connection.send_error(msg['id'], 'not_found', exc.args[0])
        return
    connection.send_result(msg['id'], {'deleted': msg['trip_id']})
