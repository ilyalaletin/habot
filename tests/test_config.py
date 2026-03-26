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
