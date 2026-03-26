from bot.devices.models import Device
from bot.telegram.keyboards import (
    rooms_keyboard, room_devices_keyboard, switch_control_keyboard, dimmer_control_keyboard, back_keyboard,
    settings_root_keyboard,
    settings_rooms_keyboard,
    settings_devices_keyboard,
    visibility_entities_keyboard,
    notification_entities_keyboard,
    notification_rules_keyboard,
    operator_keyboard,
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


def test_settings_root_keyboard():
    kb = settings_root_keyboard()
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert len(texts) == 2
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "s:vis" in callbacks
    assert "s:ntf" in callbacks


def test_settings_rooms_keyboard():
    kb = settings_rooms_keyboard(["Kitchen", "Bedroom"], prefix="sv")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "sv:r:Kitchen" in callbacks
    assert "sv:r:Bedroom" in callbacks
    assert any("bk:s" in c for c in callbacks)  # back button


def test_settings_devices_keyboard():
    groups = [
        ("dev1", "Multi Sensor", []),
        ("dev2", "Light", []),
    ]
    kb = settings_devices_keyboard(groups, "Kitchen", prefix="sv")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "sv:d:Kitchen:0" in callbacks
    assert "sv:d:Kitchen:1" in callbacks


def test_visibility_entities_keyboard():
    devices = [
        Device(id="ha:sensor.temp", name="Temperature", room="Kitchen", type="sensor", source="ha"),
        Device(id="ha:sensor.voltage", name="Voltage", room="Kitchen", type="sensor", source="ha"),
    ]
    hidden = {"ha:sensor.voltage"}
    kb = visibility_entities_keyboard(devices, hidden, "Kitchen")
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("[x]" in t and "Temperature" in t for t in texts)
    assert any("[ ]" in t and "Voltage" in t for t in texts)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert any("sv:t:Kitchen:ha:sensor.temp" in c for c in callbacks)


def test_notification_entities_keyboard():
    devices = [
        Device(id="ha:sensor.temp", name="Temperature", room="Kitchen", type="sensor", source="ha"),
    ]
    kb = notification_entities_keyboard(devices, "Kitchen")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "sn:e:ha:sensor.temp" in callbacks


def test_notification_rules_keyboard():
    rules = [
        {"id": 1, "operator": ">", "value": "35", "hold_minutes": 10, "fired": False},
        {"id": 2, "operator": "<", "value": "5", "hold_minutes": 0, "fired": False},
    ]
    kb = notification_rules_keyboard(rules, "ha:sensor.temp", "Kitchen")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert any("sn:x:ha:sensor.temp:1" in c for c in callbacks)
    assert any("sn:a:ha:sensor.temp" in c for c in callbacks)


def test_operator_keyboard():
    kb = operator_keyboard()
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert ">" in texts
    assert "<" in texts
    assert ">=" in texts
    assert "<=" in texts
    assert "=" in texts
    assert "Cancel" in texts
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "sn:cancel" in callbacks
