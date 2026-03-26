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
                msg = await ws.receive_json()
                if msg["type"] != "auth_required":
                    raise RuntimeError(f"Unexpected message: {msg}")
                await ws.send_json({"type": "auth", "access_token": self._token})
                msg = await ws.receive_json()
                if msg["type"] != "auth_ok":
                    raise RuntimeError(f"Auth failed: {msg}")
                logger.info("HA WebSocket authenticated")
                if self._on_connected:
                    await self._on_connected()
                await ws.send_json({"id": msg_id, "type": "subscribe_events", "event_type": "state_changed"})
                msg_id += 1
                async for raw_msg in ws:
                    if raw_msg.type == aiohttp.WSMsgType.TEXT:
                        data = raw_msg.json()
                        if data.get("type") == "event" and self._on_state_changed:
                            await self._on_state_changed(data["event"]["data"])
                    elif raw_msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
