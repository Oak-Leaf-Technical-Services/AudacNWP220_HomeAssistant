"""AUDAC NWP220 native UDP integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import NwpConfigEntry, NwpCoordinator
from .nwp220 import DEFAULT_PORT, Nwp220

PLATFORMS = [
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def send_command(call: ServiceCall) -> dict:
        registry = dr.async_get(hass)
        results = {}
        # Validate every target before sending to any device.
        coordinators = []
        for device_id in call.data["device_id"]:
            device = registry.async_get(device_id)
            entries = (
                []
                if device is None
                else [
                    entry
                    for entry_id in device.config_entries
                    if (entry := hass.config_entries.async_get_entry(entry_id)) is not None
                    and entry.domain == DOMAIN
                    and entry.state is ConfigEntryState.LOADED
                ]
            )
            if len(entries) != 1:
                raise ServiceValidationError("Target must be a loaded AUDAC NWP device")
            coordinators.append((device_id, entries[0].runtime_data))
        for device_id, coordinator in coordinators:
            message = await coordinator.async_control(lambda: coordinator.client.send_raw(call.data["command"]))
            results[device_id] = {
                "type": message.kind,
                "target": message.target,
                "command": message.command,
                "argument": message.argument,
            }
        return {"responses": results}

    hass.services.async_register(
        DOMAIN,
        "send_command",
        send_command,
        schema=vol.Schema(
            {
                vol.Required("device_id"): vol.All(cv.ensure_list, [cv.string], vol.Length(min=1)),
                vol.Required("command"): vol.All(cv.string, vol.Length(min=1, max=16384)),
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NwpConfigEntry) -> bool:
    client = Nwp220(entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT))
    coordinator = NwpCoordinator(hass, entry, client)
    entry.runtime_data = coordinator
    try:
        await coordinator.async_config_entry_first_refresh()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await client.close()
        raise

    async def stop_client(event):
        await client.close()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop_client))
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: NwpConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NwpConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.close()
        return True
    return False
