"""Output routing; unknown and mixed routes are displayed but never written."""

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import ServiceValidationError

from .entity import NwpEntity
from .nwp220 import ROUTES

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(NwpRoute(entry.runtime_data, i) for i in range(4))


class NwpRoute(NwpEntity, SelectEntity):
    _attr_icon = "mdi:transit-connection-variant"

    def __init__(self, coordinator, index):
        super().__init__(coordinator, f"route_{index}", f"Dante output {index + 1} source")
        self.index = index

    @property
    def current_option(self):
        value = self.coordinator.data.routes[self.index]
        return ROUTES.get(value, "Mixed (read-only)" if value == -1 else f"Source {value} (read-only)")

    @property
    def options(self):
        options = list(ROUTES.values())
        if self.current_option not in options:
            options.append(self.current_option)
        return options

    async def async_select_option(self, option):
        value = next((key for key, label in ROUTES.items() if label == option), None)
        if value is None:
            raise ServiceValidationError("This route can only be observed; select a supported source")
        await self.coordinator.async_control(lambda: self.coordinator.client.set_route(self.index, value))
