from bot.devices.models import Device


def test_device_creation():
    d = Device(
        id="ha:light.kitchen",
        name="Kitchen Light",
        room="Kitchen",
        type="switch",
        source="ha",
    )
    assert d.id == "ha:light.kitchen"
    assert d.state is None
    assert d.unit is None
    assert d.attributes == {}


def test_device_with_state():
    d = Device(
        id="wb:wb-temp",
        name="Temp",
        room="Server",
        type="sensor",
        source="wb",
        state="23.5",
        unit="C",
        attributes={"precision": 0.1},
    )
    assert d.state == "23.5"
    assert d.unit == "C"
    assert d.attributes["precision"] == 0.1


def test_device_is_controllable():
    switch = Device(id="x", name="x", room="x", type="switch", source="ha")
    dimmer = Device(id="x", name="x", room="x", type="dimmer", source="ha")
    sensor = Device(id="x", name="x", room="x", type="sensor", source="ha")
    assert switch.is_controllable is True
    assert dimmer.is_controllable is True
    assert sensor.is_controllable is False
