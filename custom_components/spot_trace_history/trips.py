"""Authenticated WebSocket commands for named archive date ranges."""
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.helpers import config_validation as cv

from .store import Store


@websocket_api.websocket_command({vol.Required('type'): 'spot_trace_history/trips'})
@websocket_api.async_response
async def ws_trips(hass, connection, msg):
    store = Store(hass.config.path('spot_trace_history.sqlite'))
    trips = await hass.async_add_executor_job(store.list_trips)
    connection.send_result(msg['id'], trips)


@websocket_api.websocket_command({
    vol.Required('type'): 'spot_trace_history/create_trip',
    vol.Required('name'): cv.string,
    vol.Required('start_date'): cv.string,
    vol.Required('end_date'): cv.string,
})
@websocket_api.async_response
async def ws_create_trip(hass, connection, msg):
    store = Store(hass.config.path('spot_trace_history.sqlite'))
    try:
        trip = await hass.async_add_executor_job(store.create_trip, msg['name'], msg['start_date'], msg['end_date'])
    except ValueError as exc:
        connection.send_error(msg['id'], 'invalid_trip', str(exc))
        return
    connection.send_result(msg['id'], trip)
