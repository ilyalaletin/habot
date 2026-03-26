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
    assert "🟢" in text

def test_format_switch_off():
    text = format_device_state(_switch(state="off"))
    assert "Light" in text
    assert "🔴" in text

def test_format_switch_unknown():
    text = format_device_state(_switch(state="unavailable"))
    assert "Light" in text
    assert "⚪" in text

def test_format_sensor():
    text = format_device_state(_sensor())
    assert "23.5" in text
    assert "C" in text
    assert "📊" in text

def test_format_room_summary():
    devices = [_switch(), _sensor(), _dimmer()]
    text = format_room_summary("Kitchen", devices)
    assert "Kitchen" in text
    assert "Light" in text
    assert "Temp" in text
    assert "23.5" in text

def test_format_room_summary_with_groups():
    groups = [
        ("dev1", "Climate Sensor", [_sensor(name="Temperature"), _sensor(name="Humidity", state="45", unit="%")]),
        ("dev2", "Ceiling Light", [_switch(name="Light")]),
    ]
    text = format_room_summary("Kitchen", groups=groups)
    assert "<b>Kitchen</b>" in text
    assert "<b>Climate Sensor</b>" in text
    assert "<b>Ceiling Light</b>" in text
    assert "Temperature" in text
    assert "Humidity" in text
    assert "Light" in text


def test_format_room_summary_solo_no_header():
    groups = [
        ("_solo:ha:sensor.z", "Temperature", [_sensor(name="Temperature")]),
    ]
    text = format_room_summary("Kitchen", groups=groups)
    assert "<b>Kitchen</b>" in text
    assert "Temperature" in text
    # Solo entities should NOT have a bold device header
    lines = text.split("\n")
    bold_lines = [l for l in lines if "<b>" in l]
    assert len(bold_lines) == 1  # only room name


def test_format_notification():
    text = format_notification("light.kitchen", "Kitchen Light", "off", "on")
    assert "Kitchen Light" in text
    assert "🔔" in text

def test_format_help():
    text = format_help()
    assert "/rooms" in text
    assert "/help" in text
    assert "/on" in text
    assert "/off" in text
    assert "/settings" in text
    assert "/cancel" in text
    assert "/menu" in text
    assert "/rules" in text
    assert "Список комнат" in text
