"""Home Assistant test fixtures. Protocol tests remain runnable with unittest."""

import pytest


@pytest.fixture(autouse=True)
def enable_custom_integrations_fixture(enable_custom_integrations):
    yield


def pytest_collection_modifyitems(items):
    for item in items:
        if "test_protocol.py" in str(item.fspath) or "test_hardware_ha.py" in str(item.fspath):
            item.add_marker(pytest.mark.enable_socket)
