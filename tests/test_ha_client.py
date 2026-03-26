import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from aioresponses import aioresponses
from bot.homeassistant.client import HAClient

HA_URL = "http://ha.local:8123"
HA_TOKEN = "test_token"

@pytest_asyncio.fixture
async def ha_client():
    client = HAClient(HA_URL, HA_TOKEN)
    await client.start()
    yield client
    await client.close()

@pytest.mark.asyncio
async def test_get_states(ha_client: HAClient):
    with aioresponses() as m:
        m.get(f"{HA_URL}/api/states", payload=[
            {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen Light", "brightness": 200}},
            {"entity_id": "sensor.temp", "state": "23.5", "attributes": {"friendly_name": "Temperature", "unit_of_measurement": "C"}},
        ])
        states = await ha_client.get_states()
        assert len(states) == 2
        assert states[0]["entity_id"] == "light.kitchen"

@pytest.mark.asyncio
async def test_get_areas(ha_client: HAClient):
    ha_client._ws_command = AsyncMock(return_value=[
        {"area_id": "kitchen", "name": "Kitchen"},
        {"area_id": "bedroom", "name": "Bedroom"},
    ])
    areas = await ha_client.get_areas()
    assert len(areas) == 2
    assert areas[0]["name"] == "Kitchen"
    ha_client._ws_command.assert_called_once_with("config/area_registry/list")

@pytest.mark.asyncio
async def test_get_entity_registry(ha_client: HAClient):
    ha_client._ws_command = AsyncMock(return_value=[
        {"entity_id": "light.kitchen", "area_id": "kitchen", "device_id": "dev1"},
    ])
    entities = await ha_client.get_entity_registry()
    assert entities[0]["entity_id"] == "light.kitchen"
    assert entities[0]["area_id"] == "kitchen"
    ha_client._ws_command.assert_called_once_with("config/entity_registry/list")

@pytest.mark.asyncio
async def test_call_service(ha_client: HAClient):
    with aioresponses() as m:
        m.post(f"{HA_URL}/api/services/light/turn_on", payload=[])
        await ha_client.call_service("light", "turn_on", {"entity_id": "light.kitchen"})
