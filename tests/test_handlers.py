import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Chat

from bot.devices.models import Device
from bot.telegram.handlers import make_router


@pytest.fixture
def registry():
    mock = MagicMock()
    mock.get_rooms.return_value = ["Kitchen", "Bedroom"]
    mock.get_devices.return_value = [
        Device(id="ha:light.k", name="Kitchen Light", room="Kitchen", type="switch", source="ha", state="on"),
        Device(id="ha:sensor.t", name="Kitchen Temp", room="Kitchen", type="sensor", source="ha", state="23.5", unit="C"),
    ]
    mock.get_device.return_value = Device(id="ha:light.k", name="Kitchen Light", room="Kitchen", type="switch", source="ha", state="on")
    mock.find_devices.return_value = [
        Device(id="ha:light.k", name="Kitchen Light", room="Kitchen", type="switch", source="ha", state="on"),
    ]
    mock.set_state = AsyncMock()
    return mock


@pytest.fixture
def storage():
    mock = AsyncMock()
    mock.get_notification_settings.return_value = {"ha:sensor.temp": True, "ha:sensor.door": False}
    return mock


def test_make_router_returns_router(registry, storage):
    router = make_router(registry, storage, chat_id=-100123)
    assert router is not None
