import logging

from bot.devices.models import Device

logger = logging.getLogger(__name__)

_DOMAIN_TYPE_MAP = {
    "light": "dimmer",
    "switch": "switch",
    "sensor": "sensor",
    "binary_sensor": "sensor",
    "input_boolean": "switch",
}


def _ha_entity_to_type(entity_id: str) -> str:
    domain = entity_id.split(".")[0]
    return _DOMAIN_TYPE_MAP.get(domain, "sensor")


def _ha_state_to_service(entity_id: str, state: str) -> tuple[str, str, dict]:
    domain = entity_id.split(".")[0]
    if state == "on":
        service = "turn_on"
    elif state == "off":
        service = "turn_off"
    else:
        service = "turn_on"
    return domain, service, {"entity_id": entity_id}


class DeviceRegistry:
    def __init__(self, ha_client, wb_devices: list[Device], wb_publish=None) -> None:
        self._ha_client = ha_client
        self._wb_devices = wb_devices
        self._wb_publish = wb_publish
        self._devices: dict[str, Device] = {}
        self._wb_topic_map: dict[str, str] = {}

    async def load(self) -> None:
        states = await self._ha_client.get_states()
        areas = await self._ha_client.get_areas()
        entities = await self._ha_client.get_entity_registry()
        area_map = {a["area_id"]: a["name"] for a in areas}
        entity_area = {}
        for e in entities:
            area_id = e.get("area_id")
            if area_id and area_id in area_map:
                entity_area[e["entity_id"]] = area_map[area_id]
        for s in states:
            entity_id = s["entity_id"]
            attrs = s.get("attributes", {})
            room = entity_area.get(entity_id, "Unassigned")
            device = Device(
                id=f"ha:{entity_id}",
                name=attrs.get("friendly_name", entity_id),
                room=room,
                type=_ha_entity_to_type(entity_id),
                source="ha",
                state=s.get("state"),
                unit=attrs.get("unit_of_measurement"),
                attributes={k: v for k, v in attrs.items() if k not in ("friendly_name", "unit_of_measurement")},
            )
            self._devices[device.id] = device
        for d in self._wb_devices:
            self._devices[d.id] = d
        logger.info("Registry loaded: %d HA devices, %d WB devices", len(self._devices) - len(self._wb_devices), len(self._wb_devices))

    def get_rooms(self) -> list[str]:
        return sorted({d.room for d in self._devices.values()})

    def get_devices(self, room: str) -> list[Device]:
        return [d for d in self._devices.values() if d.room == room]

    def get_device(self, device_id: str) -> Device | None:
        return self._devices.get(device_id)

    def find_devices(self, query: str) -> list[Device]:
        q = query.lower()
        return [d for d in self._devices.values() if q in d.name.lower()]

    def update_state(self, device_id: str, state: str, attributes: dict | None = None) -> None:
        device = self._devices.get(device_id)
        if device:
            device.state = state
            if attributes:
                device.attributes.update(attributes)

    def set_wb_topic(self, device_id: str, command_topic: str) -> None:
        self._wb_topic_map[device_id] = command_topic

    async def set_state(self, device_id: str, state: str, **attrs) -> None:
        device = self._devices.get(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")
        if device.source == "ha":
            entity_id = device_id.removeprefix("ha:")
            domain, service, data = _ha_state_to_service(entity_id, state)
            data.update(attrs)
            await self._ha_client.call_service(domain, service, data)
        elif device.source == "wb":
            if not self._wb_publish:
                raise RuntimeError("WB publish not configured")
            topic = self._wb_topic_map.get(device_id)
            if not topic:
                raise ValueError(f"No MQTT topic for {device_id}")
            payload = "1" if state == "on" else "0" if state == "off" else state
            await self._wb_publish(topic, payload)
