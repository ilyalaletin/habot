import aiohttp
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

    async def _ws_command(self, command_type: str) -> list[dict]:
        """Execute a WebSocket command and return the result."""
        ws_url = self._url.replace("http://", "ws://").replace("https://", "wss://")
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"{ws_url}/api/websocket") as ws:
                msg = await ws.receive_json()
                if msg["type"] != "auth_required":
                    raise RuntimeError(f"Unexpected: {msg}")
                await ws.send_json({"type": "auth", "access_token": self._token})
                msg = await ws.receive_json()
                if msg["type"] != "auth_ok":
                    raise RuntimeError(f"Auth failed: {msg}")
                await ws.send_json({"id": 1, "type": command_type})
                msg = await ws.receive_json()
                return msg.get("result", [])

    async def get_states(self) -> list[dict]:
        return await self._get("/api/states")

    async def get_areas(self) -> list[dict]:
        return await self._ws_command("config/area_registry/list")

    async def get_entity_registry(self) -> list[dict]:
        return await self._ws_command("config/entity_registry/list")

    async def get_device_registry(self) -> list[dict]:
        return await self._ws_command("config/device_registry/list")

    async def call_service(self, domain: str, service: str, data: dict) -> None:
        assert self._session
        async with self._session.post(
            f"{self._url}/api/services/{domain}/{service}", json=data
        ) as resp:
            resp.raise_for_status()
