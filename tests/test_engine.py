import pytest
from bot.notifications.engine import evaluate_condition


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
