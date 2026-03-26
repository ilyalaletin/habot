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
