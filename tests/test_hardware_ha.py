"""Opt-in HA-to-device control tests; only run on an authorized test panel."""

import asyncio
import os
from unittest.mock import patch

import pytest
import pytest_socket
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.audac_nwp.const import DOMAIN
from custom_components.audac_nwp.nwp220 import ROUTES

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not os.environ.get("AUDAC_TEST_HOST"), reason="No test hardware requested"),
]


async def test_ha_controls_real_device(hass):
    pytest_socket.socket_allow_hosts(["127.0.0.1", os.environ["AUDAC_TEST_HOST"]])
    entry = MockConfigEntry(
        domain=DOMAIN, title="Hardware test", data={"host": os.environ["AUDAC_TEST_HOST"], "port": 8711}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    original = coordinator.data
    registry = er.async_get(hass)
    number = registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_volume_11")
    switch = registry.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_mute_11")
    select = registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_route_3")
    assert original.routes[3] in ROUTES
    try:
        await hass.services.async_call("number", "set_value", {"entity_id": number, "value": -1}, blocking=True)
        assert float(hass.states.get(number).state) == -1
        await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
        assert hass.states.get(switch).state == "on"
        await hass.services.async_call(
            "select", "select_option", {"entity_id": select, "option": "XLR 1"}, blocking=True
        )
        assert hass.states.get(select).state == "XLR 1"
        direct = await coordinator.client.snapshot()
        assert direct == coordinator.data
        # Simulate lost inbound datagrams, without changing device/network settings.
        with patch.object(coordinator.client, "_received", return_value=None):
            await coordinator.async_refresh()
        assert hass.states.get(number).state == "unavailable"
        await asyncio.sleep(1.1)
        await coordinator.async_refresh()
        assert float(hass.states.get(number).state) == -1
    finally:
        await coordinator.client.set_route(3, original.routes[3])
        await coordinator.client.set_volume(11, original.levels[11])
        await coordinator.client.set_mute(11, original.mutes[11])
        await coordinator.async_refresh()
        assert coordinator.data == original
        assert await hass.config_entries.async_unload(entry.entry_id)
