import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN
from .api import SpotAPI

class SpotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors={}
        if user_input is not None:
            try:
                await SpotAPI(self.hass, user_input['feed_id'], user_input.get('password','')).page()
            except Exception:
                errors['base']='cannot_connect'
            else:
                await self.async_set_unique_id(user_input['feed_id'])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title='SPOT '+user_input['feed_id'][-6:], data=user_input)
        return self.async_show_form(step_id='user', data_schema=vol.Schema({vol.Required('feed_id'):str, vol.Optional('password',default=''):str}), errors=errors)
