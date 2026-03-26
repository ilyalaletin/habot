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
    def __init__(self, ha_client, wb_devices: list[Device], wb_publish=None, hidden: set[str] | None = None) -> None:
        self._ha_client = ha_client
        self._wb_devices = wb_devices
        self._wb_publish = wb_publish
        self._devices: dict[str, Device] = {}
        self._wb_topic_map: dict[str, str] = {}
        self._hidden: set[str] = hidden or set()

    async def load(self) -> None:
        states = await self._ha_client.get_states()
        areas = await self._ha_client.get_areas()
        entities = await self._ha_client.get_entity_registry()
        devices_reg = await self._ha_client.get_device_registry()

        area_map = {a["area_id"]: a["name"] for a in areas}

        # Build device_id -> area_name map
        device_area = {}
        for d in devices_reg:
            area_id = d.get("area_id")
            if area_id and area_id in area_map:
                device_area[d["id"]] = area_map[area_id]

        # Build entity -> HA device mappings (for settings navigation)
        self._entity_to_ha_device: dict[str, str] = {}
        self._ha_device_names: dict[str, str] = {}

        for d in devices_reg:
            name = d.get("name_by_user") or d.get("name") or "Unknown"
            self._ha_device_names[d["id"]] = name

        for e in entities:
            device_id = e.get("device_id")
            if device_id:
                self._entity_to_ha_device[f"ha:{e['entity_id']}"] = device_id

        # Build entity_id -> area_name map
        # Priority: entity's own area_id > device's area_id
        entity_area = {}
        for e in entities:
            area_id = e.get("area_id")
            if area_id and area_id in area_map:
                entity_area[e["entity_id"]] = area_map[area_id]
            elif e.get("device_id") and e["device_id"] in device_area:
                entity_area[e["entity_id"]] = device_area[e["device_id"]]
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
        return sorted({d.room for d in self._devices.values() if d.id not in self._hidden})

    def get_all_rooms(self) -> list[str]:
        return sorted({d.room for d in self._devices.values()})

    def get_devices(self, room: str) -> list[Device]:
        return [d for d in self._devices.values() if d.room == room and d.id not in self._hidden]

    def get_all_devices(self, room: str) -> list[Device]:
        return [d for d in self._devices.values() if d.room == room]

    def set_hidden(self, entity_id: str, hidden: bool) -> None:
        if hidden:
            self._hidden.add(entity_id)
        else:
            self._hidden.discard(entity_id)

    def get_all_device_groups(self, room: str) -> list[tuple[str, str, list[Device]]]:
        """Returns (group_id, group_name, entities) for settings navigation."""
        all_in_room = self.get_all_devices(room)
        groups: dict[str, list[Device]] = {}
        group_names: dict[str, str] = {}

        for d in all_in_room:
            if d.source == "ha":
                ha_dev_id = self._entity_to_ha_device.get(d.id)
                if ha_dev_id:
                    groups.setdefault(ha_dev_id, []).append(d)
                    group_names[ha_dev_id] = self._ha_device_names.get(ha_dev_id, d.name)
                else:
                    key = f"_solo:{d.id}"
                    groups.setdefault(key, []).append(d)
                    group_names[key] = d.name
            else:
                groups.setdefault(d.id, []).append(d)
                group_names[d.id] = d.name

        result = []
        for gid in sorted(groups, key=lambda k: group_names.get(k, "")):
            result.append((gid, group_names[gid], groups[gid]))
        return result

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
