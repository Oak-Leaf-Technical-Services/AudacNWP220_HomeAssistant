"""Protocol diagnostics, without invented hardware identifiers."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import NwpEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([NwpAddress(entry.runtime_data)])


class NwpAddress(NwpEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:identifier"

    def __init__(self, coordinator):
        super().__init__(coordinator, "protocol_address", "Protocol address")

    @property
    def native_value(self):
        return self.coordinator.data.address
