"""Channel attenuation controls in whole decibels."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfSoundPressure

from .entity import NwpEntity
from .nwp220 import CHANNELS

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(NwpVolume(entry.runtime_data, i, label) for i, (_, label) in enumerate(CHANNELS))


class NwpVolume(NwpEntity, NumberEntity):
    _attr_native_min_value = -90
    _attr_native_max_value = 0
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfSoundPressure.DECIBEL
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:volume-high"

    def __init__(self, coordinator, index, label):
        super().__init__(coordinator, f"volume_{index}", f"{label} level")
        self.index = index

    @property
    def native_value(self):
        return self.coordinator.data.levels[self.index]

    async def async_set_native_value(self, value):
        await self.coordinator.async_control(lambda: self.coordinator.client.set_volume(self.index, value))
