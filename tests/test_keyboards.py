from bot.devices.models import Device
from bot.telegram.keyboards import (
    rooms_keyboard, room_devices_keyboard, switch_control_keyboard, dimmer_control_keyboard, back_keyboard,
)

def test_rooms_keyboard():
    kb = rooms_keyboard(["Kitchen", "Bedroom", "Hall"])
    buttons = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Kitchen" in buttons
    assert "Bedroom" in buttons
    assert len(kb.inline_keyboard) >= 1

def test_room_devices_keyboard():
    devices = [
        Device(id="ha:light.k", name="Light", room="Kitchen", type="switch", source="ha"),
        Device(id="ha:sensor.t", name="Temp", room="Kitchen", type="sensor", source="ha"),
    ]
    kb = room_devices_keyboard("Kitchen", devices)
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Light" in texts
    assert "Temp" not in texts
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert any("back:rooms" in c for c in callbacks)

def test_switch_control_keyboard():
    kb = switch_control_keyboard("ha:light.k", "Kitchen")
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("VKL" in t.upper() or "ON" in t.upper() for t in texts)
    assert any("VYKL" in t.upper() or "OFF" in t.upper() for t in texts)

def test_dimmer_control_keyboard():
    kb = dimmer_control_keyboard("ha:light.d", "Kitchen")
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "25%" in texts
    assert "50%" in texts
    assert "75%" in texts
    assert "100%" in texts
