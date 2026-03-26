import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from bot.devices.models import Device
from bot.devices.registry import DeviceRegistry


@pytest.fixture
def ha_client():
    mock = AsyncMock()
    mock.get_states.return_value = [
        {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen Light", "brightness": 200}},
        {"entity_id": "sensor.kitchen_temp", "state": "23.5", "attributes": {"friendly_name": "Kitchen Temp", "unit_of_measurement": "C", "device_class": "temperature"}},
    ]
    mock.get_areas.return_value = [{"area_id": "kitchen", "name": "Kitchen"}]
    mock.get_entity_registry.return_value = [
        {"entity_id": "light.kitchen", "area_id": None, "device_id": "dev1"},
        {"entity_id": "sensor.kitchen_temp", "area_id": None, "device_id": "dev1"},
    ]
    mock.get_device_registry.return_value = [
        {"id": "dev1", "area_id": "kitchen", "name": "Multi Sensor", "name_by_user": "Kitchen Sensor"},
    ]
    return mock


@pytest.fixture
def wb_devices():
    return [Device(id="wb:wb-relay", name="Server Relay", room="Server", type="switch", source="wb", state=None)]


@pytest.fixture
def wb_publish():
    return AsyncMock()


@pytest_asyncio.fixture
async def registry(ha_client, wb_devices, wb_publish):
    reg = DeviceRegistry(ha_client, wb_devices, wb_publish=wb_publish)
    await reg.load()
    from bot.wirenboard.client import build_wb_command_topic
    reg.set_wb_topic("wb:wb-relay", build_wb_command_topic("/devices/wb-relay/controls/K1"))
    return reg


@pytest.mark.asyncio
async def test_get_rooms(registry: DeviceRegistry):
    rooms = registry.get_rooms()
    assert "Kitchen" in rooms
    assert "Server" in rooms


@pytest.mark.asyncio
async def test_get_devices_by_room(registry: DeviceRegistry):
    devices = registry.get_devices("Kitchen")
    assert len(devices) == 2
    names = {d.name for d in devices}
    assert "Kitchen Light" in names
    assert "Kitchen Temp" in names


@pytest.mark.asyncio
async def test_get_device(registry: DeviceRegistry):
    d = registry.get_device("ha:light.kitchen")
    assert d is not None
    assert d.name == "Kitchen Light"
    assert d.state == "on"


@pytest.mark.asyncio
async def test_get_device_not_found(registry: DeviceRegistry):
    assert registry.get_device("ha:nonexistent") is None


@pytest.mark.asyncio
async def test_wb_device_in_registry(registry: DeviceRegistry):
    d = registry.get_device("wb:wb-relay")
    assert d is not None
    assert d.source == "wb"
    assert d.room == "Server"


@pytest.mark.asyncio
async def test_update_state(registry: DeviceRegistry):
    registry.update_state("ha:light.kitchen", "off", {"brightness": 0})
    d = registry.get_device("ha:light.kitchen")
    assert d.state == "off"
    assert d.attributes["brightness"] == 0


@pytest.mark.asyncio
async def test_set_state_ha(registry: DeviceRegistry, ha_client):
    await registry.set_state("ha:light.kitchen", "on", brightness=200)
    ha_client.call_service.assert_called_once_with("light", "turn_on", {"entity_id": "light.kitchen", "brightness": 200})


@pytest.mark.asyncio
async def test_set_state_wb(registry: DeviceRegistry, wb_publish):
    await registry.set_state("wb:wb-relay", "on")
    wb_publish.assert_called_once_with("/devices/wb-relay/controls/K1/on", "1")


@pytest.mark.asyncio
async def test_find_devices_by_name(registry: DeviceRegistry):
    results = registry.find_devices("kitchen")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_find_devices_by_name_partial(registry: DeviceRegistry):
    results = registry.find_devices("light")
    assert len(results) == 1
    assert results[0].name == "Kitchen Light"


@pytest.mark.asyncio
async def test_get_devices_filters_hidden(ha_client, wb_devices, wb_publish):
    reg = DeviceRegistry(ha_client, wb_devices, wb_publish=wb_publish, hidden={"ha:sensor.kitchen_temp"})
    await reg.load()
    devices = reg.get_devices("Kitchen")
    assert len(devices) == 1
    assert devices[0].name == "Kitchen Light"


@pytest.mark.asyncio
async def test_get_all_devices_includes_hidden(ha_client, wb_devices, wb_publish):
    reg = DeviceRegistry(ha_client, wb_devices, wb_publish=wb_publish, hidden={"ha:sensor.kitchen_temp"})
    await reg.load()
    devices = reg.get_all_devices("Kitchen")
    assert len(devices) == 2


@pytest.mark.asyncio
async def test_get_rooms_excludes_fully_hidden(ha_client, wb_devices, wb_publish):
    reg = DeviceRegistry(ha_client, wb_devices, wb_publish=wb_publish, hidden={"ha:light.kitchen", "ha:sensor.kitchen_temp"})
    await reg.load()
    rooms = reg.get_rooms()
    assert "Kitchen" not in rooms
    assert "Server" in rooms


@pytest.mark.asyncio
async def test_get_all_rooms_includes_fully_hidden(ha_client, wb_devices, wb_publish):
    reg = DeviceRegistry(ha_client, wb_devices, wb_publish=wb_publish, hidden={"ha:light.kitchen", "ha:sensor.kitchen_temp"})
    await reg.load()
    rooms = reg.get_all_rooms()
    assert "Kitchen" in rooms
    assert "Server" in rooms


@pytest.mark.asyncio
async def test_set_hidden(registry: DeviceRegistry):
    registry.set_hidden("ha:light.kitchen", True)
    devices = registry.get_devices("Kitchen")
    assert all(d.id != "ha:light.kitchen" for d in devices)
    registry.set_hidden("ha:light.kitchen", False)
    devices = registry.get_devices("Kitchen")
    assert any(d.id == "ha:light.kitchen" for d in devices)


@pytest.mark.asyncio
async def test_get_all_device_groups_ha(registry: DeviceRegistry):
    groups = registry.get_all_device_groups("Kitchen")
    # Both HA entities belong to the same device "dev1"
    ha_groups = [g for g in groups if g[0] == "dev1"]
    assert len(ha_groups) == 1
    group_id, group_name, entities = ha_groups[0]
    assert group_name == "Kitchen Sensor"  # name_by_user preferred
    assert len(entities) == 2


@pytest.mark.asyncio
async def test_get_all_device_groups_wb(registry: DeviceRegistry):
    groups = registry.get_all_device_groups("Server")
    assert len(groups) == 1
    group_id, group_name, entities = groups[0]
    assert group_name == "Server Relay"
    assert len(entities) == 1


@pytest.mark.asyncio
async def test_get_all_device_groups_empty_room(registry: DeviceRegistry):
    groups = registry.get_all_device_groups("Nonexistent")
    assert groups == []


@pytest.mark.asyncio
async def test_get_device_groups_filters_hidden(ha_client, wb_devices, wb_publish):
    reg = DeviceRegistry(ha_client, wb_devices, wb_publish=wb_publish, hidden={"ha:sensor.kitchen_temp"})
    await reg.load()
    groups = reg.get_device_groups("Kitchen")
    # dev1 group should have only 1 entity (light), temp is hidden
    ha_groups = [g for g in groups if g[0] == "dev1"]
    assert len(ha_groups) == 1
    _, _, entities = ha_groups[0]
    assert len(entities) == 1
    assert entities[0].id == "ha:light.kitchen"


@pytest.mark.asyncio
async def test_get_device_groups_skips_fully_hidden_group(ha_client, wb_devices, wb_publish):
    reg = DeviceRegistry(ha_client, wb_devices, wb_publish=wb_publish, hidden={"ha:light.kitchen", "ha:sensor.kitchen_temp"})
    await reg.load()
    groups = reg.get_device_groups("Kitchen")
    assert groups == []
