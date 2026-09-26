"""A switch is on when the audio channel is muted."""

from homeassistant.components.switch import SwitchEntity

from .entity import NwpEntity
from .nwp220 import CHANNELS

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(NwpMute(entry.runtime_data, i, label) for i, (_, label) in enumerate(CHANNELS))


class NwpMute(NwpEntity, SwitchEntity):
    _attr_icon = "mdi:volume-mute"

    def __init__(self, coordinator, index, label):
        super().__init__(coordinator, f"mute_{index}", f"{label} mute")
        self.index = index

    @property
    def is_on(self):
        return self.coordinator.data.mutes[self.index]

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_control(lambda: self.coordinator.client.set_mute(self.index, True))

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_control(lambda: self.coordinator.client.set_mute(self.index, False))
