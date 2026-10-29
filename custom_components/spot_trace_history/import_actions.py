"""Register history actions and show their results in the HA frontend."""
import logging
import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.components import persistent_notification
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN
from .gpx_import import async_import_gpx
from .sqlite_import import async_import_sqlite
from .import_paths import import_source
from .import_feedback import import_message

_LOGGER = logging.getLogger(__name__)


def register_import_actions(hass, coordinators):
    """Register once from async_setup; coordinators(hass) returns the loaded feeds."""
    for service, importer, suffixes in [
        ('import_gpx', async_import_gpx, {'.gpx'}),
        ('import_sqlite', async_import_sqlite, {'.db', '.sqlite', '.sqlite3'}),
    ]:
        async def import_history(call, importer=importer, suffixes=suffixes):
            # Import only local files under the Home Assistant config directory.
            entries = coordinators(hass)
            try:
                source = import_source(hass.config.path(), call.data['filename'], suffixes)
                result = await importer(hass, entries, source, call.data)
            except Exception as exc:
                persistent_notification.async_create(hass, 'The import did not finish. See the action error for details.',
                    title='SPOT history import failed', notification_id=f'{DOMAIN}_import')
                if isinstance(exc, ValueError):
                    raise HomeAssistantError(str(exc), translation_domain=DOMAIN, translation_key='import_failed',
                                             translation_placeholders={'error': str(exc)}) from exc
                raise
            persistent_notification.async_create(hass, import_message(result),
                title='SPOT history import complete', notification_id=f'{DOMAIN}_import')
            _LOGGER.info('History import: %d added, %d duplicates, %d skipped',
                         result['added'], result['duplicates'], result['skipped'])
            if call.return_response:
                return result
        hass.services.async_register(DOMAIN, service, import_history,
            schema=vol.Schema({vol.Required('filename'): cv.string,
                               vol.Optional('feed_id'): cv.string,
                               vol.Optional('entry_id'): cv.string,
                               vol.Optional('feed_mapping'): vol.Schema({cv.string: cv.string}),
                               vol.Optional('device_mapping'): vol.Schema({cv.string: cv.string})}),
            supports_response=SupportsResponse.OPTIONAL)
