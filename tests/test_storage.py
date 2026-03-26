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
