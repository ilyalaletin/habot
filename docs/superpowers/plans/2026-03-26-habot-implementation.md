# habot Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot for smart home control via Home Assistant (REST + WebSocket) and Wirenboard (MQTT).

**Architecture:** Async monolith with a single event loop. DeviceRegistry unifies devices from HA and WB behind one interface. Telegram handlers interact only with the registry, never with protocol details. Notifications flow from HA WebSocket -> registry -> Telegram.

**Tech Stack:** Python 3.12, aiogram 3.x, aiomqtt 2.x, aiohttp 3.x, aiosqlite, pydantic 2.x, pyyaml, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-26-habot-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `bot/__init__.py` | Package marker |
| `bot/main.py` | Entry point: creates all components, runs event loop with asyncio.TaskGroup |
| `bot/config.py` | Pydantic models for config, loads YAML + env overrides |
| `bot/devices/models.py` | Device dataclass |
| `bot/devices/registry.py` | DeviceRegistry: unified device list, get/set operations, delegates to HA/WB clients |
| `bot/homeassistant/client.py` | HA REST API client: fetch states, areas, call services |
| `bot/homeassistant/websocket.py` | HA WebSocket client: auth, subscribe state_changed, reconnect with backoff |
| `bot/wirenboard/client.py` | MQTT client: subscribe to topics from config, publish commands, reconnect |
| `bot/storage/db.py` | SQLite: init schema, notification settings CRUD, history, cleanup |
| `bot/telegram/handlers.py` | aiogram Router: command handlers + callback query handlers |
| `bot/telegram/keyboards.py` | InlineKeyboardBuilder helpers for rooms, devices, controls |
| `bot/telegram/formatters.py` | Format device states, room summaries, notifications into text |
| `config.example.yaml` | Example configuration file |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image |
| `docker-compose.yml` | Compose service definition |
| `README.md` | Setup and usage docs |
| `tests/conftest.py` | Shared fixtures |
| `tests/test_config.py` | Config loading tests |
| `tests/test_models.py` | Device model tests |
| `tests/test_registry.py` | DeviceRegistry tests |
| `tests/test_ha_client.py` | HA REST client tests |
| `tests/test_wb_client.py` | WB MQTT client tests |
| `tests/test_storage.py` | SQLite storage tests |
| `tests/test_formatters.py` | Text formatting tests |
| `tests/test_keyboards.py` | Keyboard generation tests |
| `tests/test_handlers.py` | Telegram handler tests |

---

## Chunk 1: Foundation (Config, Models, Storage)

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `bot/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create requirements.txt**

```
aiogram~=3.17
aiomqtt~=2.3
aiohttp~=3.11
aiosqlite~=0.20
pydantic~=2.10
pydantic-settings~=2.7
pyyaml~=6.0
pytest~=8.3
pytest-asyncio~=0.25
aioresponses~=0.7
```

- [ ] **Step 2: Create package files**

Create `bot/__init__.py` (empty) and `tests/__init__.py` (empty).

Create `tests/conftest.py`:

```python
import asyncio
import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()
```

- [ ] **Step 3: Install dependencies**

Run: `cd /Users/ilya/dev/habot && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
Expected: all packages install successfully.

- [ ] **Step 4: Verify pytest runs**

Run: `cd /Users/ilya/dev/habot && .venv/bin/pytest --co -q`
Expected: "no tests ran" (no errors).

- [ ] **Step 5: Commit**

```bash
git init
git add requirements.txt bot/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: scaffold project with dependencies and test config"
```

---

### Task 2: Configuration (config.py)

**Files:**
- Create: `bot/config.py`
- Create: `config.example.yaml`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for config**

Create `tests/test_config.py`:

```python
import os
import pytest
from pathlib import Path
from bot.config import AppConfig, load_config


@pytest.fixture
def config_yaml(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("""
telegram:
  token: "BOT_TOKEN_123"
  chat_id: -1001234567890

homeassistant:
  url: "http://192.168.1.10:8123"
  token: "HA_TOKEN_456"

mqtt:
  host: "192.168.1.20"
  port: 1883

wirenboard:
  devices:
    - id: "wb-mr6c_1"
      name: "Relay"
      room: "Hall"
      type: "switch"
      topic: "/devices/wb-mr6c_1/controls/K1"
    - id: "wb-temp"
      name: "Temp"
      room: "Server"
      type: "sensor"
      topic: "/devices/wb-msw-v3_1/controls/Temperature"
      unit: "C"

database:
  path: "./data/habot.db"
  history_retention_days: 14
""")
    return cfg


def test_load_config_from_yaml(config_yaml: Path):
    config = load_config(config_yaml)
    assert config.telegram.token == "BOT_TOKEN_123"
    assert config.telegram.chat_id == -1001234567890
    assert config.homeassistant.url == "http://192.168.1.10:8123"
    assert config.mqtt.host == "192.168.1.20"
    assert config.mqtt.port == 1883
    assert len(config.wirenboard.devices) == 2
    assert config.wirenboard.devices[0].id == "wb-mr6c_1"
    assert config.wirenboard.devices[0].type == "switch"
    assert config.wirenboard.devices[1].unit == "C"
    assert config.database.history_retention_days == 14


def test_env_overrides_yaml(config_yaml: Path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "ENV_TOKEN")
    monkeypatch.setenv("HA_TOKEN", "ENV_HA_TOKEN")
    config = load_config(config_yaml)
    assert config.telegram.token == "ENV_TOKEN"
    assert config.homeassistant.token == "ENV_HA_TOKEN"


def test_default_database_values(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("""
telegram:
  token: "T"
  chat_id: 123
homeassistant:
  url: "http://localhost:8123"
  token: "H"
mqtt:
  host: "localhost"
wirenboard:
  devices: []
""")
    config = load_config(cfg)
    assert config.database.path == "./data/habot.db"
    assert config.database.history_retention_days == 30
    assert config.mqtt.port == 1883
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.config'`

- [ ] **Step 3: Implement config.py**

Create `bot/config.py`:

```python
import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class TelegramConfig(BaseModel):
    token: str
    chat_id: int


class HomeAssistantConfig(BaseModel):
    url: str
    token: str


class MqttConfig(BaseModel):
    host: str
    port: int = 1883
    username: str | None = None
    password: str | None = None


class WBDevice(BaseModel):
    id: str
    name: str
    room: str
    type: str
    topic: str
    unit: str | None = None


class WirenboardConfig(BaseModel):
    devices: list[WBDevice] = []


class DatabaseConfig(BaseModel):
    path: str = "./data/habot.db"
    history_retention_days: int = 30


class AppConfig(BaseModel):
    telegram: TelegramConfig
    homeassistant: HomeAssistantConfig
    mqtt: MqttConfig
    wirenboard: WirenboardConfig = WirenboardConfig()
    database: DatabaseConfig = DatabaseConfig()


def load_config(path: Path) -> AppConfig:
    with open(path) as f:
        data = yaml.safe_load(f)

    # Env overrides
    if env_token := os.environ.get("TELEGRAM_TOKEN"):
        data.setdefault("telegram", {})["token"] = env_token
    if env_ha := os.environ.get("HA_TOKEN"):
        data.setdefault("homeassistant", {})["token"] = env_ha

    return AppConfig(**data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 5: Create config.example.yaml**

```yaml
telegram:
  token: "YOUR_BOT_TOKEN"
  chat_id: -1001234567890  # ID of your group chat

homeassistant:
  url: "http://192.168.1.10:8123"
  token: "YOUR_HA_LONG_LIVED_TOKEN"

mqtt:
  host: "192.168.1.20"
  port: 1883
  # username: ""
  # password: ""

wirenboard:
  devices:
    - id: "wb-mr6c_1"
      name: "Relay Hall"
      room: "Hall"
      type: "switch"  # switch | dimmer | sensor
      topic: "/devices/wb-mr6c_1/controls/K1"

    - id: "wb-msw3_temp"
      name: "Temperature Server"
      room: "Server Room"
      type: "sensor"
      topic: "/devices/wb-msw-v3_1/controls/Temperature"
      unit: "C"

database:
  path: "./data/habot.db"
  history_retention_days: 30
```

- [ ] **Step 6: Commit**

```bash
git add bot/config.py config.example.yaml tests/test_config.py
git commit -m "feat: add config loading with pydantic validation and env overrides"
```

---

### Task 3: Device model (models.py)

**Files:**
- Create: `bot/devices/__init__.py`
- Create: `bot/devices/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_models.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement models.py**

Create `bot/devices/__init__.py` (empty).

Create `bot/devices/models.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/devices/ tests/test_models.py
git commit -m "feat: add Device dataclass with is_controllable property"
```

---

### Task 4: SQLite storage (db.py)

**Files:**
- Create: `bot/storage/__init__.py`
- Create: `bot/storage/db.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_storage.py`:

```python
import pytest
import pytest_asyncio
from bot.storage.db import Storage


@pytest_asyncio.fixture
async def storage(tmp_path):
    db_path = str(tmp_path / "test.db")
    s = Storage(db_path)
    await s.init()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_notification_enabled_by_default(storage: Storage):
    assert await storage.is_notification_enabled("ha:sensor.temp") is True


@pytest.mark.asyncio
async def test_disable_notification(storage: Storage):
    await storage.set_notification_enabled("ha:sensor.temp", False)
    assert await storage.is_notification_enabled("ha:sensor.temp") is False


@pytest.mark.asyncio
async def test_reenable_notification(storage: Storage):
    await storage.set_notification_enabled("ha:sensor.temp", False)
    await storage.set_notification_enabled("ha:sensor.temp", True)
    assert await storage.is_notification_enabled("ha:sensor.temp") is True


@pytest.mark.asyncio
async def test_add_and_get_history(storage: Storage):
    await storage.add_history("ha:sensor.temp", "Temperature: 38C")
    await storage.add_history("ha:sensor.temp", "Temperature: 39C")
    entries = await storage.get_known_entities()
    assert "ha:sensor.temp" in entries


@pytest.mark.asyncio
async def test_get_notification_settings(storage: Storage):
    await storage.add_history("ha:sensor.a", "msg1")
    await storage.add_history("ha:sensor.b", "msg2")
    await storage.set_notification_enabled("ha:sensor.a", False)
    settings = await storage.get_notification_settings()
    # Returns dict: entity_id -> enabled
    assert settings["ha:sensor.a"] is False
    assert settings["ha:sensor.b"] is True  # default


@pytest.mark.asyncio
async def test_cleanup_old_history(storage: Storage):
    await storage.add_history("ha:sensor.temp", "old msg")
    # Force the entry to be old by direct SQL
    await storage._execute(
        "UPDATE notification_history SET created_at = datetime('now', '-60 days')"
    )
    await storage.cleanup_history(retention_days=30)
    entities = await storage.get_known_entities()
    assert "ha:sensor.temp" not in entities
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_storage.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement db.py**

Create `bot/storage/__init__.py` (empty).

Create `bot/storage/db.py`:

```python
import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notification_settings (
    id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL UNIQUE,
    enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS notification_history (
    id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class Storage:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def _execute(self, sql: str, params: tuple = ()) -> None:
        assert self._db
        await self._db.execute(sql, params)
        await self._db.commit()

    async def is_notification_enabled(self, entity_id: str) -> bool:
        assert self._db
        cursor = await self._db.execute(
            "SELECT enabled FROM notification_settings WHERE entity_id = ?",
            (entity_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return True  # enabled by default
        return bool(row[0])

    async def set_notification_enabled(self, entity_id: str, enabled: bool) -> None:
        assert self._db
        await self._db.execute(
            """INSERT INTO notification_settings (entity_id, enabled)
               VALUES (?, ?)
               ON CONFLICT(entity_id) DO UPDATE SET enabled = ?""",
            (entity_id, int(enabled), int(enabled)),
        )
        await self._db.commit()

    async def add_history(self, entity_id: str, message: str) -> None:
        assert self._db
        await self._db.execute(
            "INSERT INTO notification_history (entity_id, message) VALUES (?, ?)",
            (entity_id, message),
        )
        await self._db.commit()

    async def get_known_entities(self) -> list[str]:
        assert self._db
        cursor = await self._db.execute(
            "SELECT DISTINCT entity_id FROM notification_history"
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def get_notification_settings(self) -> dict[str, bool]:
        assert self._db
        # All entities from history + settings
        entities = set(await self.get_known_entities())
        cursor = await self._db.execute("SELECT entity_id, enabled FROM notification_settings")
        settings_rows = await cursor.fetchall()
        result: dict[str, bool] = {}
        for entity_id in entities:
            result[entity_id] = True  # default
        for entity_id, enabled in settings_rows:
            entities.add(entity_id)
            result[entity_id] = bool(enabled)
        return result

    async def cleanup_history(self, retention_days: int) -> None:
        assert self._db
        await self._db.execute(
            "DELETE FROM notification_history WHERE created_at < datetime('now', ?)",
            (f"-{retention_days} days",),
        )
        await self._db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_storage.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/storage/ tests/test_storage.py
git commit -m "feat: add SQLite storage for notification settings and history"
```

---

## Chunk 2: Backend Clients (HA + WB)

### Task 5: Home Assistant REST client (client.py)

**Files:**
- Create: `bot/homeassistant/__init__.py`
- Create: `bot/homeassistant/client.py`
- Create: `tests/test_ha_client.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_ha_client.py`:

```python
import pytest
import pytest_asyncio
from aiohttp import ClientSession
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
        m.get(
            f"{HA_URL}/api/states",
            payload=[
                {
                    "entity_id": "light.kitchen",
                    "state": "on",
                    "attributes": {
                        "friendly_name": "Kitchen Light",
                        "brightness": 200,
                    },
                },
                {
                    "entity_id": "sensor.temp",
                    "state": "23.5",
                    "attributes": {
                        "friendly_name": "Temperature",
                        "unit_of_measurement": "C",
                    },
                },
            ],
        )
        states = await ha_client.get_states()
        assert len(states) == 2
        assert states[0]["entity_id"] == "light.kitchen"


@pytest.mark.asyncio
async def test_get_areas(ha_client: HAClient):
    with aioresponses() as m:
        m.get(
            f"{HA_URL}/api/areas",
            payload=[
                {"area_id": "kitchen", "name": "Kitchen"},
                {"area_id": "bedroom", "name": "Bedroom"},
            ],
        )
        areas = await ha_client.get_areas()
        assert len(areas) == 2
        assert areas[0]["name"] == "Kitchen"


@pytest.mark.asyncio
async def test_get_entity_registry(ha_client: HAClient):
    with aioresponses() as m:
        m.get(
            f"{HA_URL}/api/entities",
            payload=[
                {
                    "entity_id": "light.kitchen",
                    "area_id": "kitchen",
                    "device_id": "dev1",
                },
            ],
        )
        entities = await ha_client.get_entity_registry()
        assert entities[0]["entity_id"] == "light.kitchen"
        assert entities[0]["area_id"] == "kitchen"


@pytest.mark.asyncio
async def test_call_service(ha_client: HAClient):
    with aioresponses() as m:
        m.post(f"{HA_URL}/api/services/light/turn_on", payload=[])
        await ha_client.call_service("light", "turn_on", {"entity_id": "light.kitchen"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ha_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement client.py**

Create `bot/homeassistant/__init__.py` (empty).

Create `bot/homeassistant/client.py`:

```python
from aiohttp import ClientSession


class HAClient:
    def __init__(self, url: str, token: str) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._session: ClientSession | None = None

    async def start(self) -> None:
        self._session = ClientSession(
            headers={"Authorization": f"Bearer {self._token}"}
        )

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    async def _get(self, path: str) -> list[dict]:
        assert self._session
        async with self._session.get(f"{self._url}{path}") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_states(self) -> list[dict]:
        return await self._get("/api/states")

    async def get_areas(self) -> list[dict]:
        return await self._get("/api/areas")

    async def get_entity_registry(self) -> list[dict]:
        return await self._get("/api/entities")

    async def call_service(
        self, domain: str, service: str, data: dict
    ) -> None:
        assert self._session
        async with self._session.post(
            f"{self._url}/api/services/{domain}/{service}", json=data
        ) as resp:
            resp.raise_for_status()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ha_client.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/homeassistant/ tests/test_ha_client.py
git commit -m "feat: add Home Assistant REST API client"
```

---

### Task 6: Wirenboard MQTT client (client.py)

**Files:**
- Create: `bot/wirenboard/__init__.py`
- Create: `bot/wirenboard/client.py`
- Create: `tests/test_wb_client.py`

- [ ] **Step 1: Write failing tests**

The MQTT client is harder to unit test due to the broker dependency. We test the message parsing and command building logic, and the reconnect wrapper structure.

Create `tests/test_wb_client.py`:

```python
import pytest
from bot.wirenboard.client import WBClient, parse_wb_state, build_wb_command_topic


def test_parse_wb_state_numeric():
    assert parse_wb_state("23.5") == "23.5"


def test_parse_wb_state_binary():
    assert parse_wb_state("1") == "on"
    assert parse_wb_state("0") == "off"


def test_build_command_topic():
    topic = "/devices/wb-mr6c_1/controls/K1"
    assert build_wb_command_topic(topic) == "/devices/wb-mr6c_1/controls/K1/on"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_wb_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement client.py**

Create `bot/wirenboard/__init__.py` (empty).

Create `bot/wirenboard/client.py`:

```python
import asyncio
import logging
from collections.abc import Callable, Awaitable

import aiomqtt

logger = logging.getLogger(__name__)


def parse_wb_state(payload: str) -> str:
    """Parse Wirenboard MQTT payload into a normalized state string."""
    if payload == "1":
        return "on"
    if payload == "0":
        return "off"
    return payload


def build_wb_command_topic(status_topic: str) -> str:
    """Build the /on command topic from a status topic."""
    return f"{status_topic}/on"


class WBClient:
    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._client: aiomqtt.Client | None = None
        self._on_state_change: Callable[[str, str], Awaitable[None]] | None = None

    def on_state_change(
        self, callback: Callable[[str, str], Awaitable[None]]
    ) -> None:
        """Register callback(topic, payload) for state changes."""
        self._on_state_change = callback

    async def run(self, topics: list[str]) -> None:
        """Connect, subscribe to topics, and listen. Reconnects on failure."""
        backoff = 1
        while True:
            try:
                async with aiomqtt.Client(
                    self._host,
                    port=self._port,
                    username=self._username,
                    password=self._password,
                ) as client:
                    self._client = client
                    for topic in topics:
                        await client.subscribe(topic)
                    logger.info("MQTT connected, subscribed to %d topics", len(topics))
                    backoff = 1
                    async for message in client.messages:
                        payload = message.payload
                        if isinstance(payload, bytes):
                            payload = payload.decode()
                        topic_str = str(message.topic)
                        if self._on_state_change:
                            await self._on_state_change(topic_str, payload)
            except aiomqtt.MqttError as e:
                logger.warning("MQTT connection lost: %s. Reconnecting in %ds", e, backoff)
                self._client = None
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def publish(self, topic: str, payload: str) -> None:
        """Publish a command to MQTT."""
        if self._client is None:
            raise RuntimeError("MQTT client not connected")
        await self._client.publish(topic, payload)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_wb_client.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/wirenboard/ tests/test_wb_client.py
git commit -m "feat: add Wirenboard MQTT client with reconnection logic"
```

---

### Task 7: Home Assistant WebSocket client (websocket.py)

**Files:**
- Create: `bot/homeassistant/websocket.py`

- [ ] **Step 1: Implement websocket.py**

This component is integration-heavy (real WebSocket to HA). We implement it without unit tests and verify during integration testing.

Create `bot/homeassistant/websocket.py`:

```python
import asyncio
import logging
from collections.abc import Callable, Awaitable

import aiohttp

logger = logging.getLogger(__name__)


class HAWebSocket:
    def __init__(self, url: str, token: str) -> None:
        ws_url = url.replace("http://", "ws://").replace("https://", "wss://")
        self._url = f"{ws_url}/api/websocket"
        self._token = token
        self._on_state_changed: Callable[[dict], Awaitable[None]] | None = None
        self._on_connected: Callable[[], Awaitable[None]] | None = None

    def on_state_changed(self, callback: Callable[[dict], Awaitable[None]]) -> None:
        self._on_state_changed = callback

    def on_connected(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Called after (re)connect — use to refetch states."""
        self._on_connected = callback

    async def run(self) -> None:
        backoff = 1
        while True:
            try:
                await self._connect()
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                logger.warning("HA WebSocket error: %s. Reconnecting in %ds", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _connect(self) -> None:
        msg_id = 1
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self._url) as ws:
                # Auth phase
                msg = await ws.receive_json()
                if msg["type"] != "auth_required":
                    raise RuntimeError(f"Unexpected message: {msg}")

                await ws.send_json({"type": "auth", "access_token": self._token})
                msg = await ws.receive_json()
                if msg["type"] != "auth_ok":
                    raise RuntimeError(f"Auth failed: {msg}")

                logger.info("HA WebSocket authenticated")

                # Notify connected — triggers state refetch
                if self._on_connected:
                    await self._on_connected()

                # Subscribe to state_changed
                await ws.send_json({
                    "id": msg_id,
                    "type": "subscribe_events",
                    "event_type": "state_changed",
                })
                msg_id += 1

                # Listen for events
                async for raw_msg in ws:
                    if raw_msg.type == aiohttp.WSMsgType.TEXT:
                        data = raw_msg.json()
                        if (
                            data.get("type") == "event"
                            and self._on_state_changed
                        ):
                            await self._on_state_changed(data["event"]["data"])
                    elif raw_msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
```

- [ ] **Step 2: Commit**

```bash
git add bot/homeassistant/websocket.py
git commit -m "feat: add HA WebSocket client with auth and state_changed subscription"
```

---

## Chunk 3: DeviceRegistry

### Task 8: DeviceRegistry (registry.py)

**Files:**
- Create: `bot/devices/registry.py`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_registry.py`:

```python
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from bot.devices.models import Device
from bot.devices.registry import DeviceRegistry


@pytest.fixture
def ha_client():
    mock = AsyncMock()
    mock.get_states.return_value = [
        {
            "entity_id": "light.kitchen",
            "state": "on",
            "attributes": {
                "friendly_name": "Kitchen Light",
                "brightness": 200,
            },
        },
        {
            "entity_id": "sensor.kitchen_temp",
            "state": "23.5",
            "attributes": {
                "friendly_name": "Kitchen Temp",
                "unit_of_measurement": "C",
                "device_class": "temperature",
            },
        },
    ]
    mock.get_areas.return_value = [
        {"area_id": "kitchen", "name": "Kitchen"},
    ]
    mock.get_entity_registry.return_value = [
        {"entity_id": "light.kitchen", "area_id": "kitchen"},
        {"entity_id": "sensor.kitchen_temp", "area_id": "kitchen"},
    ]
    return mock


@pytest.fixture
def wb_devices():
    return [
        Device(
            id="wb:wb-relay",
            name="Server Relay",
            room="Server",
            type="switch",
            source="wb",
            state=None,
        )
    ]


@pytest.fixture
def wb_publish():
    return AsyncMock()


@pytest_asyncio.fixture
async def registry(ha_client, wb_devices, wb_publish):
    reg = DeviceRegistry(ha_client, wb_devices, wb_publish=wb_publish)
    await reg.load()
    # Register WB command topics
    from bot.wirenboard.client import build_wb_command_topic
    reg.set_wb_topic("wb:wb-relay", build_wb_command_topic("/devices/wb-relay/controls/K1"))
    return reg


@pytest.mark.asyncio
async def test_get_rooms(registry: DeviceRegistry):
    rooms = registry.get_rooms()
    assert "Kitchen" in rooms
    assert "Server" in rooms


@pytest.mark.asyncio
async def test_get_devices_by_room(registry: DeviceRegistry):
    devices = registry.get_devices("Kitchen")
    assert len(devices) == 2
    names = {d.name for d in devices}
    assert "Kitchen Light" in names
    assert "Kitchen Temp" in names


@pytest.mark.asyncio
async def test_get_device(registry: DeviceRegistry):
    d = registry.get_device("ha:light.kitchen")
    assert d is not None
    assert d.name == "Kitchen Light"
    assert d.state == "on"


@pytest.mark.asyncio
async def test_get_device_not_found(registry: DeviceRegistry):
    assert registry.get_device("ha:nonexistent") is None


@pytest.mark.asyncio
async def test_wb_device_in_registry(registry: DeviceRegistry):
    d = registry.get_device("wb:wb-relay")
    assert d is not None
    assert d.source == "wb"
    assert d.room == "Server"


@pytest.mark.asyncio
async def test_update_state(registry: DeviceRegistry):
    registry.update_state("ha:light.kitchen", "off", {"brightness": 0})
    d = registry.get_device("ha:light.kitchen")
    assert d.state == "off"
    assert d.attributes["brightness"] == 0


@pytest.mark.asyncio
async def test_set_state_ha(registry: DeviceRegistry, ha_client):
    await registry.set_state("ha:light.kitchen", "on", brightness=200)
    ha_client.call_service.assert_called_once_with(
        "light", "turn_on", {"entity_id": "light.kitchen", "brightness": 200}
    )


@pytest.mark.asyncio
async def test_set_state_wb(registry: DeviceRegistry, wb_publish):
    await registry.set_state("wb:wb-relay", "on")
    wb_publish.assert_called_once_with("/devices/wb-relay/controls/K1/on", "1")


@pytest.mark.asyncio
async def test_find_devices_by_name(registry: DeviceRegistry):
    results = registry.find_devices("kitchen")
    assert len(results) == 2  # light + temp


@pytest.mark.asyncio
async def test_find_devices_by_name_partial(registry: DeviceRegistry):
    results = registry.find_devices("light")
    assert len(results) == 1
    assert results[0].name == "Kitchen Light"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement registry.py**

Create `bot/devices/registry.py`:

```python
import logging

from bot.devices.models import Device

logger = logging.getLogger(__name__)

# Maps HA entity domain to our device type
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
    """Convert (entity_id, state) to (domain, service, data)."""
    domain = entity_id.split(".")[0]
    if state == "on":
        service = "turn_on"
    elif state == "off":
        service = "turn_off"
    else:
        # For dimmers: state is brightness percentage
        service = "turn_on"
    return domain, service, {"entity_id": entity_id}


class DeviceRegistry:
    def __init__(self, ha_client, wb_devices: list[Device], wb_publish=None) -> None:
        self._ha_client = ha_client
        self._wb_devices = wb_devices
        self._wb_publish = wb_publish  # async callable(topic, payload)
        self._devices: dict[str, Device] = {}
        self._wb_topic_map: dict[str, str] = {}  # device_id -> command_topic

    async def load(self) -> None:
        """Load devices from HA API and WB config."""
        # Fetch HA data
        states = await self._ha_client.get_states()
        areas = await self._ha_client.get_areas()
        entities = await self._ha_client.get_entity_registry()

        # Build area map: area_id -> name
        area_map = {a["area_id"]: a["name"] for a in areas}

        # Build entity -> area map
        entity_area = {}
        for e in entities:
            area_id = e.get("area_id")
            if area_id and area_id in area_map:
                entity_area[e["entity_id"]] = area_map[area_id]

        # Build HA devices
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
                attributes={
                    k: v
                    for k, v in attrs.items()
                    if k not in ("friendly_name", "unit_of_measurement")
                },
            )
            self._devices[device.id] = device

        # Add WB devices
        for d in self._wb_devices:
            self._devices[d.id] = d

        logger.info(
            "Registry loaded: %d HA devices, %d WB devices",
            len(self._devices) - len(self._wb_devices),
            len(self._wb_devices),
        )

    def get_rooms(self) -> list[str]:
        rooms = sorted({d.room for d in self._devices.values()})
        return rooms

    def get_devices(self, room: str) -> list[Device]:
        return [d for d in self._devices.values() if d.room == room]

    def get_device(self, device_id: str) -> Device | None:
        return self._devices.get(device_id)

    def find_devices(self, query: str) -> list[Device]:
        q = query.lower()
        return [d for d in self._devices.values() if q in d.name.lower()]

    def update_state(
        self, device_id: str, state: str, attributes: dict | None = None
    ) -> None:
        device = self._devices.get(device_id)
        if device:
            device.state = state
            if attributes:
                device.attributes.update(attributes)

    def set_wb_topic(self, device_id: str, command_topic: str) -> None:
        """Register the MQTT command topic for a WB device."""
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
            # WB uses "1"/"0" for switch commands
            payload = "1" if state == "on" else "0" if state == "off" else state
            await self._wb_publish(topic, payload)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_registry.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/devices/registry.py tests/test_registry.py
git commit -m "feat: add DeviceRegistry with HA/WB device loading and state management"
```

---

## Chunk 4: Telegram UI (Formatters, Keyboards, Handlers)

### Task 9: Text formatters (formatters.py)

**Files:**
- Create: `bot/telegram/__init__.py`
- Create: `bot/telegram/formatters.py`
- Create: `tests/test_formatters.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_formatters.py`:

```python
from bot.devices.models import Device
from bot.telegram.formatters import (
    format_device_state,
    format_room_summary,
    format_notification,
    format_help,
)


def _switch(name="Light", state="on", room="Kitchen"):
    return Device(id="ha:light.x", name=name, room=room, type="switch", source="ha", state=state)


def _dimmer(name="Dimmer", state="on", room="Kitchen", brightness=75):
    return Device(
        id="ha:light.y", name=name, room=room, type="dimmer", source="ha",
        state=state, attributes={"brightness": brightness},
    )


def _sensor(name="Temp", state="23.5", room="Kitchen", unit="C"):
    return Device(
        id="ha:sensor.z", name=name, room=room, type="sensor", source="ha",
        state=state, unit=unit,
    )


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_formatters.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement formatters.py**

Create `bot/telegram/__init__.py` (empty).

Create `bot/telegram/formatters.py`:

```python
from bot.devices.models import Device


def format_device_state(device: Device) -> str:
    if device.type == "sensor":
        unit = f" {device.unit}" if device.unit else ""
        return f"{device.name} -- {device.state}{unit}"
    elif device.type == "dimmer":
        if device.state == "off":
            return f"{device.name} -- VYKL"
        brightness = device.attributes.get("brightness")
        if brightness is not None:
            pct = round(brightness / 255 * 100)
            return f"{device.name} -- VKL ({pct}%)"
        return f"{device.name} -- VKL"
    else:
        state_text = "VKL" if device.state == "on" else "VYKL"
        return f"{device.name} -- {state_text}"


def format_room_summary(room: str, devices: list[Device]) -> str:
    lines = [f"<b>{room}</b>", ""]
    for d in devices:
        lines.append(format_device_state(d))
    return "\n".join(lines)


def format_notification(
    entity_id: str, friendly_name: str, old_state: str, new_state: str
) -> str:
    return f"{friendly_name}: {old_state} -> {new_state}"


def format_help() -> str:
    commands = [
        ("/help", "List of all commands"),
        ("/rooms", "List rooms"),
        ("/room <name>", "Room summary"),
        ("/on <name>", "Turn on device"),
        ("/off <name>", "Turn off device"),
        ("/set <name> <value>", "Set value (dimmer: 0-100)"),
        ("/status", "Full summary of all rooms"),
        ("/notifications", "Manage notifications (on/off)"),
    ]
    lines = ["<b>Available commands:</b>", ""]
    for cmd, desc in commands:
        lines.append(f"{cmd} -- {desc}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_formatters.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/telegram/ tests/test_formatters.py
git commit -m "feat: add Telegram message formatters for devices, rooms, and help"
```

---

### Task 10: Inline keyboards (keyboards.py)

**Files:**
- Create: `bot/telegram/keyboards.py`
- Create: `tests/test_keyboards.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_keyboards.py`:

```python
from bot.devices.models import Device
from bot.telegram.keyboards import (
    rooms_keyboard,
    room_devices_keyboard,
    switch_control_keyboard,
    dimmer_control_keyboard,
    back_keyboard,
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
    # Only controllable devices get buttons
    assert "Light" in texts
    assert "Temp" not in texts
    # Has back button
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_keyboards.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement keyboards.py**

Create `bot/telegram/keyboards.py`:

```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.devices.models import Device


def rooms_keyboard(rooms: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for room in rooms:
        builder.button(text=room, callback_data=f"room:{room}")
    builder.adjust(2)
    return builder.as_markup()


def room_devices_keyboard(
    room: str, devices: list[Device]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    controllable = [d for d in devices if d.is_controllable]
    for d in controllable:
        builder.button(text=d.name, callback_data=f"device:{d.id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="<- Back", callback_data="back:rooms"))
    return builder.as_markup()


def switch_control_keyboard(
    device_id: str, room: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Vykl", callback_data=f"set:{device_id}:off")
    builder.button(text="Vkl", callback_data=f"set:{device_id}:on")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text=f"<- Back to {room}", callback_data=f"room:{room}")
    )
    return builder.as_markup()


def dimmer_control_keyboard(
    device_id: str, room: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Vykl", callback_data=f"set:{device_id}:off")
    for pct in (25, 50, 75, 100):
        builder.button(text=f"{pct}%", callback_data=f"dim:{device_id}:{pct}")
    builder.adjust(5)
    builder.row(
        InlineKeyboardButton(text=f"<- Back to {room}", callback_data=f"room:{room}")
    )
    return builder.as_markup()


def back_keyboard(callback_data: str, label: str = "<- Back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=callback_data)]
        ]
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_keyboards.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/telegram/keyboards.py tests/test_keyboards.py
git commit -m "feat: add inline keyboard builders for rooms, devices, and controls"
```

---

### Task 11: Telegram handlers (handlers.py)

**Files:**
- Create: `bot/telegram/handlers.py`
- Create: `tests/test_handlers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_handlers.py`:

```python
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
    mock.get_device.return_value = Device(
        id="ha:light.k", name="Kitchen Light", room="Kitchen", type="switch", source="ha", state="on",
    )
    mock.find_devices.return_value = [
        Device(id="ha:light.k", name="Kitchen Light", room="Kitchen", type="switch", source="ha", state="on"),
    ]
    mock.set_state = AsyncMock()
    return mock


@pytest.fixture
def storage():
    mock = AsyncMock()
    mock.get_notification_settings.return_value = {
        "ha:sensor.temp": True,
        "ha:sensor.door": False,
    }
    return mock


def test_make_router_returns_router(registry, storage):
    router = make_router(registry, storage, chat_id=-100123)
    assert router is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_handlers.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement handlers.py**

Create `bot/telegram/handlers.py`:

```python
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery

from bot.devices.registry import DeviceRegistry
from bot.storage.db import Storage
from bot.telegram.formatters import (
    format_room_summary,
    format_device_state,
    format_help,
)
from bot.telegram.keyboards import (
    rooms_keyboard,
    room_devices_keyboard,
    switch_control_keyboard,
    dimmer_control_keyboard,
)


def make_router(
    registry: DeviceRegistry, storage: Storage, chat_id: int
) -> Router:
    router = Router()

    def _check_chat(msg_or_cb) -> bool:
        """Only respond in the configured chat."""
        chat = msg_or_cb.chat if hasattr(msg_or_cb, "chat") else msg_or_cb.message.chat
        return chat.id == chat_id

    # --- Commands ---

    @router.message(CommandStart())
    @router.message(Command("rooms"))
    async def cmd_rooms(message: Message) -> None:
        if not _check_chat(message):
            return
        rooms = registry.get_rooms()
        await message.answer("Rooms:", reply_markup=rooms_keyboard(rooms))

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        if not _check_chat(message):
            return
        await message.answer(format_help(), parse_mode="HTML")

    @router.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if not _check_chat(message):
            return
        rooms = registry.get_rooms()
        parts = []
        for room in rooms:
            devices = registry.get_devices(room)
            parts.append(format_room_summary(room, devices))
        await message.answer("\n\n".join(parts), parse_mode="HTML")

    @router.message(Command("room"))
    async def cmd_room(message: Message) -> None:
        if not _check_chat(message):
            return
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer("Usage: /room <name>")
            return
        room_name = args[1]
        devices = registry.get_devices(room_name)
        if not devices:
            # Try case-insensitive match
            for r in registry.get_rooms():
                if r.lower() == room_name.lower():
                    devices = registry.get_devices(r)
                    room_name = r
                    break
        if not devices:
            await message.answer(f"Room '{room_name}' not found.")
            return
        text = format_room_summary(room_name, devices)
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=room_devices_keyboard(room_name, devices),
        )

    @router.message(Command("on"))
    async def cmd_on(message: Message) -> None:
        if not _check_chat(message):
            return
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer("Usage: /on <device name>")
            return
        await _handle_device_command(message, args[1], "on")

    @router.message(Command("off"))
    async def cmd_off(message: Message) -> None:
        if not _check_chat(message):
            return
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer("Usage: /off <device name>")
            return
        await _handle_device_command(message, args[1], "off")

    @router.message(Command("set"))
    async def cmd_set(message: Message) -> None:
        if not _check_chat(message):
            return
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            await message.answer("Usage: /set <device name> <value>")
            return
        name, value = args[1], args[2]
        matches = registry.find_devices(name)
        controllable = [d for d in matches if d.is_controllable]
        if not controllable:
            await message.answer(f"Device '{name}' not found.")
            return
        if len(controllable) == 1:
            device = controllable[0]
            if device.type == "dimmer":
                brightness = int(round(int(value) / 100 * 255))
                await registry.set_state(device.id, "on", brightness=brightness)
            else:
                await registry.set_state(device.id, value)
            await message.answer(f"{device.name}: set to {value}")
        else:
            await _send_disambiguation(message, controllable)

    @router.message(Command("notifications"))
    async def cmd_notifications(message: Message) -> None:
        if not _check_chat(message):
            return
        await _send_notification_settings(message)

    async def _send_notification_settings(message: Message) -> None:
        settings = await storage.get_notification_settings()
        if not settings:
            await message.answer("No notification history yet.")
            return
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        builder = InlineKeyboardBuilder()
        for entity_id, enabled in sorted(settings.items()):
            builder.button(
                text=f"{'[x]' if enabled else '[ ]'} {entity_id}",
                callback_data=f"notif:{entity_id}:{'off' if enabled else 'on'}",
            )
        builder.adjust(1)
        await message.answer("Notifications:", reply_markup=builder.as_markup())

    # --- Callback handlers ---

    @router.callback_query(F.data.startswith("room:"))
    async def cb_room(callback: CallbackQuery) -> None:
        room_name = callback.data.removeprefix("room:")
        devices = registry.get_devices(room_name)
        text = format_room_summary(room_name, devices)
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=room_devices_keyboard(room_name, devices),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("device:"))
    async def cb_device(callback: CallbackQuery) -> None:
        device_id = callback.data.removeprefix("device:")
        device = registry.get_device(device_id)
        if not device:
            await callback.answer("Device not found")
            return
        text = format_device_state(device)
        if device.type == "dimmer":
            kb = dimmer_control_keyboard(device_id, device.room)
        else:
            kb = switch_control_keyboard(device_id, device.room)
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("set:"))
    async def cb_set(callback: CallbackQuery) -> None:
        _, device_id, state = callback.data.split(":", 2)
        await registry.set_state(device_id, state)
        device = registry.get_device(device_id)
        await callback.answer(f"{device.name}: {state}")
        # Refresh device view
        text = format_device_state(device)
        if device.type == "dimmer":
            kb = dimmer_control_keyboard(device_id, device.room)
        else:
            kb = switch_control_keyboard(device_id, device.room)
        await callback.message.edit_text(text, reply_markup=kb)

    @router.callback_query(F.data.startswith("dim:"))
    async def cb_dim(callback: CallbackQuery) -> None:
        _, device_id, pct_str = callback.data.split(":", 2)
        pct = int(pct_str)
        brightness = int(round(pct / 100 * 255))
        await registry.set_state(device_id, "on", brightness=brightness)
        device = registry.get_device(device_id)
        await callback.answer(f"{device.name}: {pct}%")
        text = format_device_state(device)
        kb = dimmer_control_keyboard(device_id, device.room)
        await callback.message.edit_text(text, reply_markup=kb)

    @router.callback_query(F.data.startswith("notif:"))
    async def cb_notif_toggle(callback: CallbackQuery) -> None:
        _, entity_id, action = callback.data.split(":", 2)
        enabled = action == "on"
        await storage.set_notification_enabled(entity_id, enabled)
        await callback.answer(f"{'Enabled' if enabled else 'Disabled'}: {entity_id}")
        # Refresh notifications list
        await _send_notification_settings(callback.message)

    @router.callback_query(F.data == "back:rooms")
    async def cb_back_rooms(callback: CallbackQuery) -> None:
        rooms = registry.get_rooms()
        await callback.message.edit_text("Rooms:", reply_markup=rooms_keyboard(rooms))
        await callback.answer()

    # --- Helpers ---

    async def _handle_device_command(
        message: Message, name: str, state: str
    ) -> None:
        matches = registry.find_devices(name)
        controllable = [d for d in matches if d.is_controllable]
        if not controllable:
            await message.answer(f"Device '{name}' not found.")
            return
        if len(controllable) == 1:
            device = controllable[0]
            await registry.set_state(device.id, state)
            await message.answer(f"{device.name}: {state}")
        else:
            await _send_disambiguation(message, controllable)

    async def _send_disambiguation(
        message: Message, devices: list
    ) -> None:
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        builder = InlineKeyboardBuilder()
        for d in devices:
            builder.button(text=d.name, callback_data=f"device:{d.id}")
        builder.adjust(1)
        await message.answer(
            "Multiple devices found. Choose one:",
            reply_markup=builder.as_markup(),
        )

    return router
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_handlers.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add bot/telegram/handlers.py tests/test_handlers.py
git commit -m "feat: add Telegram command handlers and callback query handlers"
```

---

## Chunk 5: Main Entry Point, Docker, and README

### Task 12: Main entry point (main.py)

**Files:**
- Create: `bot/main.py`

- [ ] **Step 1: Implement main.py**

Create `bot/main.py`:

```python
import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher

from bot.config import load_config
from bot.devices.models import Device
from bot.devices.registry import DeviceRegistry
from bot.homeassistant.client import HAClient
from bot.homeassistant.websocket import HAWebSocket
from bot.storage.db import Storage
from bot.telegram.formatters import format_notification
from bot.telegram.handlers import make_router
from bot.wirenboard.client import WBClient, parse_wb_state, build_wb_command_topic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config_path = Path(os.environ.get("CONFIG_PATH", "config.yaml"))
    config = load_config(config_path)

    # Init storage
    db_dir = Path(config.database.path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    storage = Storage(config.database.path)
    await storage.init()

    # Init HA client
    ha_client = HAClient(config.homeassistant.url, config.homeassistant.token)
    await ha_client.start()

    # Build WB devices from config
    wb_devices = [
        Device(
            id=f"wb:{d.id}",
            name=d.name,
            room=d.room,
            type=d.type,
            source="wb",
            unit=d.unit,
        )
        for d in config.wirenboard.devices
    ]

    # Build topic -> device_id map for WB
    wb_topic_map: dict[str, str] = {}
    for d in config.wirenboard.devices:
        wb_topic_map[d.topic] = f"wb:{d.id}"

    # Init WB client (needed for registry)
    wb_client = WBClient(
        host=config.mqtt.host,
        port=config.mqtt.port,
        username=config.mqtt.username,
        password=config.mqtt.password,
    )

    # Init registry with WB publish capability
    registry = DeviceRegistry(ha_client, wb_devices, wb_publish=wb_client.publish)
    await registry.load()

    # Register WB command topics
    for d in config.wirenboard.devices:
        registry.set_wb_topic(f"wb:{d.id}", build_wb_command_topic(d.topic))

    # Init Telegram bot
    bot = Bot(token=config.telegram.token)
    dp = Dispatcher()
    router = make_router(registry, storage, chat_id=config.telegram.chat_id)
    dp.include_router(router)

    # HA WebSocket: state updates + notifications
    ha_ws = HAWebSocket(config.homeassistant.url, config.homeassistant.token)

    async def on_ha_state_changed(data: dict) -> None:
        entity_id = data.get("entity_id", "")
        new_state = data.get("new_state", {})
        old_state = data.get("old_state", {})
        if not new_state:
            return

        # Skip if state didn't actually change
        old_val = old_state.get("state") if old_state else None
        if old_val == new_state.get("state"):
            return

        # Update registry
        device_id = f"ha:{entity_id}"
        state_val = new_state.get("state")
        attrs = {
            k: v
            for k, v in new_state.get("attributes", {}).items()
            if k not in ("friendly_name", "unit_of_measurement")
        }
        registry.update_state(device_id, state_val, attrs)

        # Send notification if enabled
        if await storage.is_notification_enabled(device_id):
            friendly_name = new_state.get("attributes", {}).get(
                "friendly_name", entity_id
            )
            text = format_notification(entity_id, friendly_name, old_val or "?", state_val)
            await storage.add_history(device_id, text)
            try:
                await bot.send_message(config.telegram.chat_id, text)
            except Exception as e:
                logger.error("Failed to send notification: %s", e)

    async def on_ha_connected() -> None:
        logger.info("HA WebSocket connected, refetching states...")
        await registry.load()

    ha_ws.on_state_changed(on_ha_state_changed)
    ha_ws.on_connected(on_ha_connected)

    # WB MQTT: state updates
    async def on_wb_state(topic: str, payload: str) -> None:
        device_id = wb_topic_map.get(topic)
        if device_id:
            state = parse_wb_state(payload)
            registry.update_state(device_id, state)

    wb_client.on_state_change(on_wb_state)

    wb_topics = list(wb_topic_map.keys())

    # Periodic cleanup
    async def cleanup_loop() -> None:
        while True:
            await asyncio.sleep(86400)  # daily
            await storage.cleanup_history(config.database.history_retention_days)
            logger.info("History cleanup done")

    # Run all tasks
    logger.info("Starting habot...")
    async with asyncio.TaskGroup() as tg:
        tg.create_task(dp.start_polling(bot))
        tg.create_task(ha_ws.run())
        if wb_topics:
            tg.create_task(wb_client.run(wb_topics))
        tg.create_task(cleanup_loop())


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify it imports without error**

Run: `.venv/bin/python -c "from bot.main import main; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add bot/main.py
git commit -m "feat: add main entry point with TaskGroup orchestration"
```

---

### Task 13: Docker files

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ bot/

CMD ["python", "-m", "bot.main"]
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
services:
  habot:
    build: .
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - habot-data:/app/data
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - HA_TOKEN=${HA_TOKEN}

volumes:
  habot-data:
```

- [ ] **Step 3: Create .dockerignore**

```
.venv/
__pycache__/
*.pyc
.git/
tests/
docs/
data/
.env
```

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: add Docker configuration"
```

---

### Task 14: README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# habot

Telegram bot for smart home control via Home Assistant and Wirenboard.

## Features

- Browse devices by room with inline buttons
- Control switches and dimmers
- Quick commands: /on, /off, /set, /status
- Real-time notifications from Home Assistant events
- Per-entity notification management (enable/disable)
- Wirenboard MQTT devices alongside HA devices

## Quick Start

1. Copy config:
   ```bash
   cp config.example.yaml config.yaml
   ```

2. Edit `config.yaml` with your settings (Telegram token, HA URL/token, MQTT host).

3. Create `.env` file:
   ```
   TELEGRAM_TOKEN=your_bot_token
   HA_TOKEN=your_ha_long_lived_token
   ```

4. Run:
   ```bash
   docker compose up -d
   ```

## Integration with Existing Docker Compose

If you already have Home Assistant and Wirenboard running in Docker, add habot to the same stack.

### Option A: Add to existing docker-compose.yml

Add the `habot` service to your existing `docker-compose.yml`:

```yaml
services:
  # ... your existing services (homeassistant, etc.)

  habot:
    build: /path/to/habot
    restart: unless-stopped
    volumes:
      - /path/to/habot/config.yaml:/app/config.yaml:ro
      - habot-data:/app/data
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - HA_TOKEN=${HA_TOKEN}
    networks:
      - default  # same network as HA and WB

volumes:
  habot-data:
```

In `config.yaml`, use Docker service names as hosts:

```yaml
homeassistant:
  url: "http://homeassistant:8123"  # Docker service name
mqtt:
  host: "wirenboard"  # or your MQTT broker service name
```

### Option B: Separate compose with shared network

If habot has its own `docker-compose.yml`, connect it to the existing network:

```yaml
services:
  habot:
    build: .
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - habot-data:/app/data
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - HA_TOKEN=${HA_TOKEN}
    networks:
      - ha-network

volumes:
  habot-data:

networks:
  ha-network:
    external: true
    name: homeassistant_default  # name of your HA network (check with: docker network ls)
```

Find your HA network name:
```bash
docker network ls | grep home
```

## Configuration

See `config.example.yaml` for all options. Environment variables `TELEGRAM_TOKEN` and `HA_TOKEN` override YAML values.

## Commands

| Command | Description |
|---------|-------------|
| /help | List all commands |
| /rooms | Browse rooms |
| /room <name> | Room summary |
| /on <name> | Turn on device |
| /off <name> | Turn off device |
| /set <name> <value> | Set value (dimmer: 0-100) |
| /status | Full summary |
| /notifications | Manage notifications |

## Supported Device Types (v1)

- **switch** — on/off control
- **dimmer** — brightness 0-100%
- **sensor** — read-only (temperature, humidity, etc.)
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and integration instructions"
```

---

### Task 15: Run full test suite

- [ ] **Step 1: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 2: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address test failures"
```
