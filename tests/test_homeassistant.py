"""HA lifecycle, services, config flow, identity and coordinator behaviour."""

from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER, ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.audac_nwp.const import DOMAIN
from custom_components.audac_nwp.nwp220 import CommunicationError, Message, State


@pytest.fixture
def client():
    state = State((0.0,) * 12, (False,) * 12, (1, 2, 5, 6), "NWP220>1")
    mock = AsyncMock()
    mock.snapshot.return_value = state

    async def set_volume(index, value):
        values = list(mock.snapshot.return_value.levels)
        values[index] = value
        mock.snapshot.return_value = replace(mock.snapshot.return_value, levels=tuple(values))

    async def set_mute(index, value):
        values = list(mock.snapshot.return_value.mutes)
        values[index] = value
        mock.snapshot.return_value = replace(mock.snapshot.return_value, mutes=tuple(values))

    async def set_route(index, value):
        values = list(mock.snapshot.return_value.routes)
        values[index] = value
        mock.snapshot.return_value = replace(mock.snapshot.return_value, routes=tuple(values))

    mock.set_volume.side_effect = set_volume
    mock.set_mute.side_effect = set_mute
    mock.set_route.side_effect = set_route
    mock.send_raw.return_value = Message("CLIENT>1", "NWP220>1", "GET_RSP", "ALL_OUT", "ROUTE", "1^2^5^6^0^0^0^0")
    with (
        patch("custom_components.audac_nwp.Nwp220", return_value=mock),
        patch("custom_components.audac_nwp.config_flow.Nwp220", return_value=mock),
    ):
        yield mock


@pytest.fixture
async def entry(hass, client):
    entry = MockConfigEntry(domain=DOMAIN, title="Test NWP", data={"host": "192.0.2.1", "port": 8711})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry


def entity_id(hass, entry, domain, key):
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")


async def test_setup_controls_and_unload(hass, entry, client):
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(entities) == 32
    assert sum(e.disabled_by is not None for e in entities) == 2
    number = entity_id(hass, entry, "number", "volume_11")
    switch = entity_id(hass, entry, "switch", "mute_11")
    select = entity_id(hass, entry, "select", "route_3")
    await hass.services.async_call("number", "set_value", {"entity_id": number, "value": -12}, blocking=True)
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    await hass.services.async_call("select", "select_option", {"entity_id": select, "option": "XLR 1"}, blocking=True)
    assert float(hass.states.get(number).state) == -12
    assert hass.states.get(switch).state == "on"
    assert hass.states.get(select).state == "XLR 1"
    assert await hass.config_entries.async_unload(entry.entry_id)
    client.close.assert_awaited_once()


async def test_outage_recovery(hass, entry, client):
    number = entity_id(hass, entry, "number", "volume_0")
    connected = entity_id(hass, entry, "binary_sensor", "connected")
    client.snapshot.side_effect = CommunicationError("offline")
    await entry.runtime_data.async_refresh()
    assert hass.states.get(number).state == "unavailable"
    assert hass.states.get(connected).state == "off"
    client.snapshot.side_effect = None
    await entry.runtime_data.async_refresh()
    assert float(hass.states.get(number).state) == 0
    assert hass.states.get(connected).state == "on"


async def test_write_failure_is_not_optimistic(hass, entry, client):
    client.set_mute.side_effect = CommunicationError("no acknowledgement")
    switch = entity_id(hass, entry, "switch", "mute_0")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    assert hass.states.get(switch).state == "unavailable"


async def test_mixed_unknown_route_is_read_only(hass, entry, client):
    client.snapshot.return_value = replace(client.snapshot.return_value, routes=(-1, 9, 5, 6))
    await entry.runtime_data.async_refresh()
    select = entity_id(hass, entry, "select", "route_0")
    assert hass.states.get(select).state == "Mixed (read-only)"
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": select, "option": "Mixed (read-only)"}, blocking=True
        )
    client.set_route.assert_not_called()


async def test_raw_action_and_unloaded_target(hass, entry, client):
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    command = "#|NWP220||GET_REQ^ALL_OUT^ROUTE||U|"
    result = await hass.services.async_call(
        DOMAIN, "send_command", {"device_id": device.id, "command": command}, blocking=True, return_response=True
    )
    assert result["responses"][device.id]["argument"] == "1^2^5^6^0^0^0^0"
    client.send_raw.assert_awaited_once_with(command)
    await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "send_command", {"device_id": device.id, "command": command}, blocking=True
        )


async def test_flow_validation_and_duplicate(hass, client):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": "Panel.local"})
    assert result["type"] == "create_entry"
    assert result["data"] == {"host": "panel.local", "port": 8711}
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={"host": "panel.local"}
    )
    assert result["reason"] == "already_configured"


async def test_failed_flow_closes_client(hass, client):
    client.snapshot.side_effect = CommunicationError("offline")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={"host": "panel.local"}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    client.close.assert_awaited_once()


async def test_initial_failure_retry(hass, client):
    client.snapshot.side_effect = CommunicationError("offline")
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.1", "port": 8711})
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    client.close.assert_awaited_once()


async def test_reconfigure_preserves_registry_identity(hass, entry, client):
    before = entity_id(hass, entry, "number", "volume_0")
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        data={"host": "192.0.2.2", "port": 8711},
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data["host"] == "192.0.2.2"
    assert entity_id(hass, entry, "number", "volume_0") == before


async def test_options(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 30})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.runtime_data.update_interval.total_seconds() == 30
