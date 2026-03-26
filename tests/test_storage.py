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


# --- Visibility ---

@pytest.mark.asyncio
async def test_entity_visible_by_default(storage: Storage):
    assert await storage.is_entity_hidden("ha:sensor.temp") is False


@pytest.mark.asyncio
async def test_hide_entity(storage: Storage):
    await storage.set_entity_hidden("ha:sensor.temp", True)
    assert await storage.is_entity_hidden("ha:sensor.temp") is True


@pytest.mark.asyncio
async def test_unhide_entity(storage: Storage):
    await storage.set_entity_hidden("ha:sensor.temp", True)
    await storage.set_entity_hidden("ha:sensor.temp", False)
    assert await storage.is_entity_hidden("ha:sensor.temp") is False


@pytest.mark.asyncio
async def test_get_hidden_entities(storage: Storage):
    await storage.set_entity_hidden("ha:sensor.a", True)
    await storage.set_entity_hidden("ha:sensor.b", True)
    await storage.set_entity_hidden("ha:sensor.c", False)
    hidden = await storage.get_hidden_entities()
    assert hidden == {"ha:sensor.a", "ha:sensor.b"}


# --- Notification Rules ---

@pytest.mark.asyncio
async def test_add_and_get_rule(storage: Storage):
    rule_id = await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=10)
    assert rule_id > 0
    rules = await storage.get_rules_for_entity("ha:sensor.temp")
    assert len(rules) == 1
    assert rules[0]["operator"] == ">"
    assert rules[0]["value"] == "35"
    assert rules[0]["hold_minutes"] == 10
    assert rules[0]["fired"] is False


@pytest.mark.asyncio
async def test_multiple_rules_per_entity(storage: Storage):
    await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=10)
    await storage.add_rule("ha:sensor.temp", "<", "5", hold_minutes=0)
    rules = await storage.get_rules_for_entity("ha:sensor.temp")
    assert len(rules) == 2


@pytest.mark.asyncio
async def test_delete_rule(storage: Storage):
    rule_id = await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=0)
    await storage.delete_rule(rule_id)
    rules = await storage.get_rules_for_entity("ha:sensor.temp")
    assert len(rules) == 0


@pytest.mark.asyncio
async def test_set_rule_fired(storage: Storage):
    rule_id = await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=0)
    await storage.set_rule_fired(rule_id, True)
    rules = await storage.get_rules_for_entity("ha:sensor.temp")
    assert rules[0]["fired"] is True


@pytest.mark.asyncio
async def test_reset_all_fired(storage: Storage):
    r1 = await storage.add_rule("ha:sensor.a", ">", "10", hold_minutes=0)
    r2 = await storage.add_rule("ha:sensor.b", "<", "5", hold_minutes=0)
    await storage.set_rule_fired(r1, True)
    await storage.set_rule_fired(r2, True)
    await storage.reset_all_fired()
    all_rules = await storage.get_all_rules()
    assert all(r["fired"] is False for r in all_rules)


@pytest.mark.asyncio
async def test_get_all_rules(storage: Storage):
    await storage.add_rule("ha:sensor.a", ">", "10", hold_minutes=0)
    await storage.add_rule("ha:sensor.b", "<", "5", hold_minutes=5)
    all_rules = await storage.get_all_rules()
    assert len(all_rules) == 2


# --- History ---

@pytest.mark.asyncio
async def test_add_history_with_rule_id(storage: Storage):
    rule_id = await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=0)
    await storage.add_history("ha:sensor.temp", "Temp > 35", rule_id=rule_id)
    entities = await storage.get_known_entities()
    assert "ha:sensor.temp" in entities


@pytest.mark.asyncio
async def test_add_history_without_rule_id(storage: Storage):
    await storage.add_history("ha:sensor.temp", "Some event")
    entities = await storage.get_known_entities()
    assert "ha:sensor.temp" in entities


@pytest.mark.asyncio
async def test_cleanup_old_history(storage: Storage):
    await storage.add_history("ha:sensor.temp", "old msg")
    await storage._execute(
        "UPDATE notification_history SET created_at = datetime('now', '-60 days')"
    )
    await storage.cleanup_history(retention_days=30)
    entities = await storage.get_known_entities()
    assert "ha:sensor.temp" not in entities
