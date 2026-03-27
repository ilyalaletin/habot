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


class NotificationsConfig(BaseModel):
    dedup_minutes: int = 60


class DatabaseConfig(BaseModel):
    path: str = "./data/habot.db"
    history_retention_days: int = 30


class AppConfig(BaseModel):
    telegram: TelegramConfig
    homeassistant: HomeAssistantConfig
    mqtt: MqttConfig
    wirenboard: WirenboardConfig = WirenboardConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    database: DatabaseConfig = DatabaseConfig()


def load_config(path: Path) -> AppConfig:
    with open(path) as f:
        data = yaml.safe_load(f)

    # Env overrides
    if env_token := os.environ.get("TELEGRAM_TOKEN"):
        data.setdefault("telegram", {})["token"] = env_token
    if env_ha := os.environ.get("HA_TOKEN"):
        data.setdefault("homeassistant", {})["token"] = env_ha
    if env_dedup := os.environ.get("NOTIFICATION_DEDUP_MINUTES"):
        data.setdefault("notifications", {})["dedup_minutes"] = int(env_dedup)

    return AppConfig(**data)
