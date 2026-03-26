import pytest
from bot.wirenboard.client import WBClient, parse_wb_state, build_wb_command_topic

def test_parse_wb_state_numeric():
    assert parse_wb_state("23.5") == "23.5"

def test_parse_wb_state_binary():
    assert parse_wb_state("1") == "on"
    assert parse_wb_state("0") == "off"

def test_build_command_topic():
    topic = "/devices/wb-mr6c_1/controls/K1"
    assert build_wb_command_topic(topic) == "/devices/wb-mr6c_1/controls/K1/on"
