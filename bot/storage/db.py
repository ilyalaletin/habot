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
            return False  # disabled by default, enable via /notifications
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
            result[entity_id] = False  # default is disabled
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
