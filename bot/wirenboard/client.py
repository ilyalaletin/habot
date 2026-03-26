import asyncio
import logging
from collections.abc import Callable, Awaitable

import aiomqtt

logger = logging.getLogger(__name__)


def parse_wb_state(payload: str) -> str:
    if payload == "1":
        return "on"
    if payload == "0":
        return "off"
    return payload


def build_wb_command_topic(status_topic: str) -> str:
    return f"{status_topic}/on"


class WBClient:
    def __init__(self, host: str, port: int = 1883, username: str | None = None, password: str | None = None) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._client: aiomqtt.Client | None = None
        self._on_state_change: Callable[[str, str], Awaitable[None]] | None = None

    def on_state_change(self, callback: Callable[[str, str], Awaitable[None]]) -> None:
        self._on_state_change = callback

    async def run(self, topics: list[str]) -> None:
        backoff = 1
        while True:
            try:
                async with aiomqtt.Client(self._host, port=self._port, username=self._username, password=self._password) as client:
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
        if self._client is None:
            raise RuntimeError("MQTT client not connected")
        await self._client.publish(topic, payload)
