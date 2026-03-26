import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entity_visibility (
    entity_id TEXT PRIMARY KEY,
    hidden INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notification_rules (
    id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL,
    operator TEXT NOT NULL,
    value TEXT NOT NULL,
    hold_minutes INTEGER DEFAULT 0,
    fired INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notification_history (
    id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL,
    rule_id INTEGER,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_MIGRATION = """
DROP TABLE IF EXISTS notification_settings;
"""


class Storage:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        # Migrate: drop old tables
        await self._db.executescript(_MIGRATION)
        # Check if old notification_history schema needs migration (no rule_id column)
        cursor = await self._db.execute("PRAGMA table_info(notification_history)")
        columns = {row[1] for row in await cursor.fetchall()}
        if columns and "rule_id" not in columns:
            await self._db.execute("DROP TABLE notification_history")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def _execute(self, sql: str, params: tuple = ()) -> None:
        assert self._db
        await self._db.execute(sql, params)
        await self._db.commit()

    # --- Visibility ---

    async def is_entity_hidden(self, entity_id: str) -> bool:
        assert self._db
        cursor = await self._db.execute(
            "SELECT hidden FROM entity_visibility WHERE entity_id = ?",
            (entity_id,),
        )
        row = await cursor.fetchone()
        return bool(row[0]) if row else False

    async def set_entity_hidden(self, entity_id: str, hidden: bool) -> None:
        assert self._db
        await self._db.execute(
            """INSERT INTO entity_visibility (entity_id, hidden)
               VALUES (?, ?)
               ON CONFLICT(entity_id) DO UPDATE SET hidden = ?""",
            (entity_id, int(hidden), int(hidden)),
        )
        await self._db.commit()

    async def get_hidden_entities(self) -> set[str]:
        assert self._db
        cursor = await self._db.execute(
            "SELECT entity_id FROM entity_visibility WHERE hidden = 1"
        )
        rows = await cursor.fetchall()
        return {r[0] for r in rows}

    # --- Notification Rules ---

    async def add_rule(
        self, entity_id: str, operator: str, value: str, hold_minutes: int = 0
    ) -> int:
        assert self._db
        cursor = await self._db.execute(
            """INSERT INTO notification_rules (entity_id, operator, value, hold_minutes)
               VALUES (?, ?, ?, ?)""",
            (entity_id, operator, value, hold_minutes),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_rules_for_entity(self, entity_id: str) -> list[dict]:
        assert self._db
        cursor = await self._db.execute(
            "SELECT id, entity_id, operator, value, hold_minutes, fired "
            "FROM notification_rules WHERE entity_id = ?",
            (entity_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "entity_id": r[1], "operator": r[2],
                "value": r[3], "hold_minutes": r[4], "fired": bool(r[5]),
            }
            for r in rows
        ]

    async def get_all_rules(self) -> list[dict]:
        assert self._db
        cursor = await self._db.execute(
            "SELECT id, entity_id, operator, value, hold_minutes, fired "
            "FROM notification_rules"
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "entity_id": r[1], "operator": r[2],
                "value": r[3], "hold_minutes": r[4], "fired": bool(r[5]),
            }
            for r in rows
        ]

    async def delete_rule(self, rule_id: int) -> None:
        assert self._db
        await self._db.execute(
            "DELETE FROM notification_rules WHERE id = ?", (rule_id,)
        )
        await self._db.commit()

    async def set_rule_fired(self, rule_id: int, fired: bool) -> None:
        assert self._db
        await self._db.execute(
            "UPDATE notification_rules SET fired = ? WHERE id = ?",
            (int(fired), rule_id),
        )
        await self._db.commit()

    async def reset_all_fired(self) -> None:
        assert self._db
        await self._db.execute("UPDATE notification_rules SET fired = 0")
        await self._db.commit()

    # --- History ---

    async def add_history(
        self, entity_id: str, message: str, rule_id: int | None = None
    ) -> None:
        assert self._db
        await self._db.execute(
            "INSERT INTO notification_history (entity_id, rule_id, message) VALUES (?, ?, ?)",
            (entity_id, rule_id, message),
        )
        await self._db.commit()

    async def get_known_entities(self) -> list[str]:
        assert self._db
        cursor = await self._db.execute(
            "SELECT DISTINCT entity_id FROM notification_history"
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def cleanup_history(self, retention_days: int) -> None:
        assert self._db
        await self._db.execute(
            "DELETE FROM notification_history WHERE created_at < datetime('now', ?)",
            (f"-{retention_days} days",),
        )
        await self._db.commit()
