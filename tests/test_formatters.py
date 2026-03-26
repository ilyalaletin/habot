from bot.devices.models import Device
from bot.telegram.formatters import (
    format_device_state, format_room_summary, format_notification, format_help,
)

def _switch(name="Light", state="on", room="Kitchen"):
    return Device(id="ha:light.x", name=name, room=room, type="switch", source="ha", state=state)

def _dimmer(name="Dimmer", state="on", room="Kitchen", brightness=75):
    return Device(id="ha:light.y", name=name, room=room, type="dimmer", source="ha", state=state, attributes={"brightness": brightness})

def _sensor(name="Temp", state="23.5", room="Kitchen", unit="C"):
    return Device(id="ha:sensor.z", name=name, room=room, type="sensor", source="ha", state=state, unit=unit)

def test_format_switch_on():
    text = format_device_state(_switch(state="on"))
    assert "Light" in text
    assert "ON" in text.upper() or "VKL" in text.upper()

def test_format_sensor():
    text = format_device_state(_sensor())
    assert "23.5" in text
    assert "C" in text

def test_format_room_summary():
    devices = [_switch(), _sensor(), _dimmer()]
    text = format_room_summary("Kitchen", devices)
    assert "Kitchen" in text
    assert "Light" in text
    assert "Temp" in text
    assert "23.5" in text

def test_format_notification():
    text = format_notification("light.kitchen", "Kitchen Light", "off", "on")
    assert "Kitchen Light" in text

def test_format_help():
    text = format_help()
    assert "/rooms" in text
    assert "/help" in text
    assert "/on" in text
    assert "/off" in text
    assert "/settings" in text
    assert "/cancel" in text
    assert "/notifications" not in text
