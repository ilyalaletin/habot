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

    async def call_service(self, domain: str, service: str, data: dict) -> None:
        assert self._session
        async with self._session.post(
            f"{self._url}/api/services/{domain}/{service}", json=data
        ) as resp:
            resp.raise_for_status()
