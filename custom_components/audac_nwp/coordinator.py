"""One polling coordinator and one UDP client per configured panel."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .nwp220 import Nwp220, NwpError, State

LOGGER = logging.getLogger(__name__)
type NwpConfigEntry = ConfigEntry[NwpCoordinator]


class NwpCoordinator(DataUpdateCoordinator[State]):
    def __init__(self, hass: HomeAssistant, entry: NwpConfigEntry, client: Nwp220):
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            always_update=False,
        )
        self.client = client
        self.entry = entry
        # Keep the full snapshot and SET+readback atomic with respect to HA work.
        self.operation_lock = asyncio.Lock()

    async def _async_update_data(self) -> State:
        async with self.operation_lock:
            try:
                return await self.client.snapshot()
            except NwpError as err:
                raise UpdateFailed(str(err)) from err

    async def async_control(self, operation: Callable[[], Awaitable[Any]]) -> Any:
        async with self.operation_lock:
            try:
                result = await operation()
                state = await self.client.snapshot()
            except ValueError as err:
                raise ServiceValidationError(str(err)) from err
            except NwpError as err:
                self.async_set_update_error(UpdateFailed(str(err)))
                raise HomeAssistantError(f"AUDAC command failed: {err}") from err
            self.async_set_updated_data(state)
            return result
