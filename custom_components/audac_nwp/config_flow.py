"""UI configuration with communication validation and host reconfiguration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .nwp220 import DEFAULT_PORT, Nwp220, NwpError


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return await self._configure("user", user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._configure("reconfigure", user_input)

    async def _configure(self, step, user_input):
        entry = self._get_reconfigure_entry() if step == "reconfigure" else None
        errors = {}
        if user_input is not None:
            data = {
                CONF_HOST: user_input[CONF_HOST].strip().lower(),
                CONF_PORT: user_input.get(CONF_PORT, entry.data[CONF_PORT] if entry else DEFAULT_PORT),
            }
            if any(
                e.entry_id != (entry.entry_id if entry else None) and e.data[CONF_HOST] == data[CONF_HOST]
                for e in self._async_current_entries()
            ):
                return self.async_abort(reason="already_configured")
            client = None
            try:
                client = Nwp220(data[CONF_HOST], data[CONF_PORT])
                await client.snapshot()
            except (NwpError, OSError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                if entry:
                    return self.async_update_reload_and_abort(entry, data_updates=data)
                # No reliable hardware identifier is exposed by the ASCII API.
                # Entry ID gives stable registry identity across host changes.
                return self.async_create_entry(title=f"AUDAC NWP220 ({data[CONF_HOST]})", data=data)
            finally:
                if client:
                    await client.close()
        defaults = user_input or (entry.data if entry else {})
        fields = {vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): cv.string}
        if self.show_advanced_options or entry:
            fields[vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT))] = cv.port
        return self.async_show_form(step_id=step, data_schema=vol.Schema(fields), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                }
            ),
        )
