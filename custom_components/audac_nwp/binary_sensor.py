"""Connectivity means a successful complete poll, not merely an open UDP socket."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import NwpEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([NwpConnected(entry.runtime_data)])


class NwpConnected(NwpEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator, "connected", "Connected")

    @property
    def available(self):
        return True

    @property
    def is_on(self):
        return self.coordinator.last_update_success
