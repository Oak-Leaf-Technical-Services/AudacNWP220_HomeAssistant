"""Explicit Bluetooth actions; disabled by default to avoid accidental activation."""

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import NwpEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        NwpBluetooth(entry.runtime_data, command, label)
        for command, label in (("BT_PAIR", "Bluetooth pairing"), ("BT_PAIR_CANCEL", "Cancel Bluetooth pairing"))
    )


class NwpBluetooth(NwpEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:bluetooth"

    def __init__(self, coordinator, command, label):
        super().__init__(coordinator, command.lower(), label)
        self.command = command

    async def async_press(self):
        if self.command == "BT_PAIR_CANCEL":
            await self.coordinator.async_control(self.coordinator.client.cancel_pairing)
        else:
            await self.coordinator.async_control(lambda: self.coordinator.client.bluetooth(self.command))
