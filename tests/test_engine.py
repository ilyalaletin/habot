import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from bot.notifications.engine import evaluate_condition, NotificationEngine


# --- evaluate_condition ---

def test_equal_string():
    assert evaluate_condition("on", "=", "on") is True
    assert evaluate_condition("off", "=", "on") is False


def test_equal_numeric_string():
    assert evaluate_condition("23.5", "=", "23.5") is True
    assert evaluate_condition("23.5", "=", "24") is False


def test_greater_than():
    assert evaluate_condition("35.5", ">", "35") is True
    assert evaluate_condition("35", ">", "35") is False
    assert evaluate_condition("34", ">", "35") is False


def test_less_than():
    assert evaluate_condition("4", "<", "5") is True
    assert evaluate_condition("5", "<", "5") is False


def test_greater_equal():
    assert evaluate_condition("35", ">=", "35") is True
    assert evaluate_condition("36", ">=", "35") is True
    assert evaluate_condition("34", ">=", "35") is False


def test_less_equal():
    assert evaluate_condition("5", "<=", "5") is True
    assert evaluate_condition("4", "<=", "5") is True
    assert evaluate_condition("6", "<=", "5") is False


def test_unavailable_state():
    assert evaluate_condition("unavailable", ">", "35") is False
    assert evaluate_condition("unknown", "=", "on") is False


def test_non_numeric_with_numeric_operator():
    assert evaluate_condition("on", ">", "35") is False
    assert evaluate_condition("abc", "<", "10") is False


def test_invalid_operator():
    assert evaluate_condition("10", "!=", "5") is False


# --- NotificationEngine ---

@pytest_asyncio.fixture
async def engine_deps(tmp_path):
    """Set up storage, registry mock, and send mock for engine tests."""
    from bot.storage.db import Storage

    db_path = str(tmp_path / "test.db")
    storage = Storage(db_path)
    await storage.init()

    registry = MagicMock()
    registry.is_hidden.return_value = False
    send_fn = AsyncMock()

    yield storage, registry, send_fn

    await storage.close()


@pytest_asyncio.fixture
async def engine(engine_deps):
    storage, registry, send_fn = engine_deps
    eng = NotificationEngine(storage, registry, send_fn)
    yield eng
    await eng.stop()


@pytest.mark.asyncio
async def test_immediate_rule_fires(engine_deps):
    storage, registry, send_fn = engine_deps
    eng = NotificationEngine(storage, registry, send_fn)

    device = MagicMock()
    device.name = "Temp Sensor"
    registry.get_device.return_value = device

    await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=0)
    await eng.on_state_changed("ha:sensor.temp", "36")

    send_fn.assert_called_once()
    assert "Temp Sensor" in send_fn.call_args[0][0]
    await eng.stop()


@pytest.mark.asyncio
async def test_hidden_entity_skips_notification(engine_deps):
    storage, registry, send_fn = engine_deps
    eng = NotificationEngine(storage, registry, send_fn)
    registry.is_hidden.return_value = True

    await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=0)
    await eng.on_state_changed("ha:sensor.temp", "36")

    send_fn.assert_not_called()
    await eng.stop()


@pytest.mark.asyncio
async def test_rule_does_not_fire_when_condition_false(engine_deps):
    storage, registry, send_fn = engine_deps
    eng = NotificationEngine(storage, registry, send_fn)
    registry.get_device.return_value = MagicMock(name="Temp")

    await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=0)
    await eng.on_state_changed("ha:sensor.temp", "30")

    send_fn.assert_not_called()
    await eng.stop()


@pytest.mark.asyncio
async def test_rule_does_not_refire(engine_deps):
    storage, registry, send_fn = engine_deps
    eng = NotificationEngine(storage, registry, send_fn)
    device = MagicMock()
    device.name = "Temp"
    registry.get_device.return_value = device

    await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=0)
    await eng.on_state_changed("ha:sensor.temp", "36")
    await eng.on_state_changed("ha:sensor.temp", "37")

    assert send_fn.call_count == 1
    await eng.stop()


@pytest.mark.asyncio
async def test_rule_refires_after_reset_different_state(engine_deps):
    storage, registry, send_fn = engine_deps
    eng = NotificationEngine(storage, registry, send_fn)
    device = MagicMock()
    device.name = "Temp"
    registry.get_device.return_value = device

    await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=0)
    await eng.on_state_changed("ha:sensor.temp", "36")  # fires
    await eng.on_state_changed("ha:sensor.temp", "30")  # resets fired
    await eng.on_state_changed("ha:sensor.temp", "37")  # fires again (different state text)

    assert send_fn.call_count == 2
    await eng.stop()


@pytest.mark.asyncio
async def test_dedup_identical_notification(engine_deps):
    storage, registry, send_fn = engine_deps
    eng = NotificationEngine(storage, registry, send_fn)
    device = MagicMock()
    device.name = "Motion"
    registry.get_device.return_value = device

    await storage.add_rule("ha:sensor.motion", "=", "on", hold_minutes=0)
    await eng.on_state_changed("ha:sensor.motion", "on")   # fires
    await eng.on_state_changed("ha:sensor.motion", "off")   # resets fired
    await eng.on_state_changed("ha:sensor.motion", "on")   # dedup: same text, skipped

    assert send_fn.call_count == 1
    await eng.stop()


@pytest.mark.asyncio
async def test_unavailable_state_cancels(engine_deps):
    storage, registry, send_fn = engine_deps
    eng = NotificationEngine(storage, registry, send_fn)
    registry.get_device.return_value = MagicMock(name="T")

    await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=0)
    await eng.on_state_changed("ha:sensor.temp", "36")  # fires
    assert send_fn.call_count == 1

    await eng.on_state_changed("ha:sensor.temp", "unavailable")  # resets
    await eng.on_state_changed("ha:sensor.temp", "37")  # fires again

    assert send_fn.call_count == 2
    await eng.stop()


@pytest.mark.asyncio
async def test_hold_timer_fires_after_delay(engine_deps):
    storage, registry, send_fn = engine_deps
    eng = NotificationEngine(storage, registry, send_fn)
    device = MagicMock()
    device.name = "Temp"
    device.state = "36"
    registry.get_device.return_value = device

    original_sleep = asyncio.sleep

    async def fast_sleep(seconds):
        await original_sleep(0)

    asyncio.sleep = fast_sleep
    try:
        await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=1)
        await eng.on_state_changed("ha:sensor.temp", "36")

        # Timer started, give event loop a tick
        await original_sleep(0.05)

        send_fn.assert_called_once()
    finally:
        asyncio.sleep = original_sleep
        await eng.stop()


@pytest.mark.asyncio
async def test_hold_timer_cancelled_when_condition_false(engine_deps):
    storage, registry, send_fn = engine_deps
    eng = NotificationEngine(storage, registry, send_fn)
    device = MagicMock()
    device.name = "Temp"
    device.state = "30"
    registry.get_device.return_value = device

    original_sleep = asyncio.sleep

    async def slow_sleep(seconds):
        await original_sleep(0.1)

    asyncio.sleep = slow_sleep
    try:
        await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=1)
        await eng.on_state_changed("ha:sensor.temp", "36")  # starts timer
        await eng.on_state_changed("ha:sensor.temp", "30")  # cancels timer

        await original_sleep(0.2)  # wait past timer
        send_fn.assert_not_called()
    finally:
        asyncio.sleep = original_sleep
        await eng.stop()


@pytest.mark.asyncio
async def test_on_rule_deleted_cancels_timer(engine_deps):
    storage, registry, send_fn = engine_deps
    eng = NotificationEngine(storage, registry, send_fn)
    device = MagicMock()
    device.name = "Temp"
    device.state = "30"
    registry.get_device.return_value = device

    original_sleep = asyncio.sleep

    async def slow_sleep(seconds):
        await original_sleep(0.1)

    asyncio.sleep = slow_sleep
    try:
        rule_id = await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=1)
        await eng.on_state_changed("ha:sensor.temp", "36")  # starts timer
        eng.on_rule_deleted(rule_id)  # cancels timer

        await original_sleep(0.2)
        send_fn.assert_not_called()
    finally:
        asyncio.sleep = original_sleep
        await eng.stop()


@pytest.mark.asyncio
async def test_startup_pass(engine_deps):
    storage, registry, send_fn = engine_deps
    eng = NotificationEngine(storage, registry, send_fn)

    device = MagicMock()
    device.name = "Temp"
    device.state = "36"
    registry.get_device.return_value = device

    await storage.add_rule("ha:sensor.temp", ">", "35", hold_minutes=0)
    # Manually set fired=1 to simulate pre-restart state
    rules = await storage.get_all_rules()
    await storage.set_rule_fired(rules[0]["id"], True)

    await eng.start()

    # start() resets fired and re-evaluates; condition is true so it fires
    send_fn.assert_called_once()
    await eng.stop()
