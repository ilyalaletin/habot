import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


def evaluate_condition(state: str, operator: str, value: str) -> bool:
    """Evaluate a rule condition against a state value.

    Returns False for unavailable/unknown states and unparseable numeric comparisons.
    """
    if state in ("unavailable", "unknown"):
        return False
    if operator == "=":
        return state == value
    try:
        state_f = float(state)
        value_f = float(value)
    except (ValueError, TypeError):
        return False
    if operator == ">":
        return state_f > value_f
    if operator == "<":
        return state_f < value_f
    if operator == ">=":
        return state_f >= value_f
    if operator == "<=":
        return state_f <= value_f
    return False


class NotificationEngine:
    def __init__(
        self,
        storage,
        registry,
        send_fn: Callable[[str], Awaitable[None]],
        dedup_minutes: int = 60,
    ) -> None:
        self._storage = storage
        self._registry = registry
        self._send = send_fn
        self._dedup_minutes = dedup_minutes
        self._hold_timers: dict[int, asyncio.Task] = {}

    async def start(self) -> None:
        """Reset all fired flags and run initial evaluation pass."""
        await self._storage.reset_all_fired()
        all_rules = await self._storage.get_all_rules()
        rules_by_entity: dict[str, list[dict]] = {}
        for rule in all_rules:
            rules_by_entity.setdefault(rule["entity_id"], []).append(rule)
        for entity_id, rules in rules_by_entity.items():
            device = self._registry.get_device(entity_id)
            if device and device.state:
                await self._evaluate_rules(entity_id, device.state, rules)

    async def on_state_changed(self, entity_id: str, new_state: str) -> None:
        """Evaluate all rules for entity after state change."""
        if self._registry.is_hidden(entity_id):
            return
        rules = await self._storage.get_rules_for_entity(entity_id)
        if not rules:
            return
        await self._evaluate_rules(entity_id, new_state, rules)

    def on_rule_deleted(self, rule_id: int) -> None:
        """Cancel hold timer for deleted rule."""
        self._cancel_timer(rule_id)

    async def stop(self) -> None:
        """Cancel all hold timers."""
        for task in self._hold_timers.values():
            task.cancel()
        self._hold_timers.clear()

    async def _evaluate_rules(
        self, entity_id: str, state: str, rules: list[dict]
    ) -> None:
        if state in ("unavailable", "unknown"):
            for rule in rules:
                self._cancel_timer(rule["id"])
                if rule["fired"]:
                    await self._storage.set_rule_fired(rule["id"], False)
                    rule["fired"] = False
            return

        for rule in rules:
            condition_met = evaluate_condition(state, rule["operator"], rule["value"])

            if not condition_met:
                if rule["fired"]:
                    await self._storage.set_rule_fired(rule["id"], False)
                    rule["fired"] = False
                self._cancel_timer(rule["id"])
            elif not rule["fired"]:
                if rule["hold_minutes"] == 0:
                    await self._fire_rule(rule, entity_id, state)
                else:
                    self._start_hold_timer(rule, entity_id)

    async def _fire_rule(
        self, rule: dict, entity_id: str, state: str
    ) -> None:
        device = self._registry.get_device(entity_id)
        name = device.name if device else entity_id
        text = f"🔔 {name}: {state} ({rule['operator']} {rule['value']})"

        # Dedup: skip if last notification for this entity within window is identical
        last = await self._storage.get_last_notification(entity_id, within_minutes=self._dedup_minutes)
        if last == text:
            logger.debug("Dedup: skipping identical notification for %s", entity_id)
            await self._storage.set_rule_fired(rule["id"], True)
            rule["fired"] = True
            return

        await self._storage.set_rule_fired(rule["id"], True)
        rule["fired"] = True
        await self._storage.add_history(entity_id, text, rule_id=rule["id"])
        try:
            await self._send(text)
        except Exception as e:
            logger.error("Failed to send notification: %s", e)

    def _start_hold_timer(self, rule: dict, entity_id: str) -> None:
        if rule["id"] in self._hold_timers:
            return

        async def _timer() -> None:
            await asyncio.sleep(rule["hold_minutes"] * 60)
            device = self._registry.get_device(entity_id)
            if device and device.state:
                if evaluate_condition(device.state, rule["operator"], rule["value"]):
                    await self._fire_rule(rule, entity_id, device.state)
            self._hold_timers.pop(rule["id"], None)

        self._hold_timers[rule["id"]] = asyncio.create_task(_timer())

    def _cancel_timer(self, rule_id: int) -> None:
        task = self._hold_timers.pop(rule_id, None)
        if task:
            task.cancel()
