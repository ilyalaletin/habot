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
from bot.notifications.engine import NotificationEngine
from bot.storage.db import Storage
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
            id=f"wb:{d.id}", name=d.name, room=d.room,
            type=d.type, source="wb", unit=d.unit,
        )
        for d in config.wirenboard.devices
    ]

    # Build topic -> device_id map for WB
    wb_topic_map: dict[str, str] = {}
    for d in config.wirenboard.devices:
        wb_topic_map[d.topic] = f"wb:{d.id}"

    # Init WB client
    wb_client = WBClient(
        host=config.mqtt.host, port=config.mqtt.port,
        username=config.mqtt.username, password=config.mqtt.password,
    )

    # Load hidden entities for registry
    hidden = await storage.get_hidden_entities()

    # Init registry with visibility
    registry = DeviceRegistry(ha_client, wb_devices, wb_publish=wb_client.publish, hidden=hidden)
    await registry.load()

    # Register WB command topics
    for d in config.wirenboard.devices:
        registry.set_wb_topic(f"wb:{d.id}", build_wb_command_topic(d.topic))

    # Init Telegram bot
    bot = Bot(token=config.telegram.token)
    dp = Dispatcher()

    # Init notification engine
    async def send_notification(text: str) -> None:
        await bot.send_message(config.telegram.chat_id, text)

    engine = NotificationEngine(
        storage, registry, send_notification,
        dedup_minutes=config.notifications.dedup_minutes,
    )

    router = make_router(registry, storage, chat_id=config.telegram.chat_id, engine=engine)
    dp.include_router(router)

    # HA WebSocket: state updates + rule evaluation
    ha_ws = HAWebSocket(config.homeassistant.url, config.homeassistant.token)

    async def on_ha_state_changed(data: dict) -> None:
        entity_id = data.get("entity_id", "")
        new_state = data.get("new_state", {})
        old_state = data.get("old_state", {})
        if not new_state:
            return

        old_val = old_state.get("state") if old_state else None
        state_val = new_state.get("state")
        if old_val == state_val:
            return

        # Update registry
        device_id = f"ha:{entity_id}"
        attrs = {
            k: v for k, v in new_state.get("attributes", {}).items()
            if k not in ("friendly_name", "unit_of_measurement")
        }
        registry.update_state(device_id, state_val, attrs)

        # Evaluate notification rules
        await engine.on_state_changed(device_id, state_val)

    async def on_ha_connected() -> None:
        logger.info("HA WebSocket connected, refetching states...")
        await registry.load()

    ha_ws.on_state_changed(on_ha_state_changed)
    ha_ws.on_connected(on_ha_connected)

    # WB MQTT: state updates + rule evaluation
    async def on_wb_state(topic: str, payload: str) -> None:
        device_id = wb_topic_map.get(topic)
        if device_id:
            state = parse_wb_state(payload)
            registry.update_state(device_id, state)
            await engine.on_state_changed(device_id, state)

    wb_client.on_state_change(on_wb_state)
    wb_topics = list(wb_topic_map.keys())

    # Periodic cleanup
    async def cleanup_loop() -> None:
        while True:
            await asyncio.sleep(86400)
            await storage.cleanup_history(config.database.history_retention_days)
            logger.info("History cleanup done")

    # Run all tasks
    logger.info("Starting habot...")

    # Start notification engine (resets fired, evaluates current states)
    await engine.start()

    async with asyncio.TaskGroup() as tg:
        tg.create_task(dp.start_polling(bot))
        tg.create_task(ha_ws.run())
        if wb_topics:
            tg.create_task(wb_client.run(wb_topics))
        tg.create_task(cleanup_loop())


if __name__ == "__main__":
    asyncio.run(main())
