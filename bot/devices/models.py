from dataclasses import dataclass, field


@dataclass
class Device:
    id: str
    name: str
    room: str
    type: str  # switch, dimmer, sensor
    source: str  # "ha" or "wb"
    state: str | None = None
    unit: str | None = None
    attributes: dict = field(default_factory=dict)

    @property
    def is_controllable(self) -> bool:
        return self.type in ("switch", "dimmer")
