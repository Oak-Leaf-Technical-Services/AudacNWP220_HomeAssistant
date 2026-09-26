"""Support diagnostics without network identifiers or raw command history."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    state = coordinator.data
    return {
        "transport": "UDP",
        "port": entry.data.get("port", 8711),
        "poll_interval": coordinator.update_interval.total_seconds(),
        "last_update_success": coordinator.last_update_success,
        "identity_source": "config_entry_id",
        "state": None
        if state is None
        else {
            "levels": state.levels,
            "mutes": state.mutes,
            "routes": state.routes,
        },
    }
