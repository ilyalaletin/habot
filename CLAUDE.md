# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Telegram bot for smart home control via Home Assistant (REST API + WebSocket) and Wirenboard (MQTT). Runs as an async monolith in a single Docker container. Operates in one Telegram group chat.

## Commands

```bash
# Tests
.venv/bin/pytest tests/ -v                    # all tests
.venv/bin/pytest tests/test_registry.py -v    # single file
.venv/bin/pytest tests/test_registry.py::test_get_rooms -v  # single test

# Run locally (requires config.yaml with real tokens)
unset HA_TOKEN && unset TELEGRAM_TOKEN && .venv/bin/python -m bot.main

# Docker
docker compose up -d
```

Note: `HA_TOKEN` and `TELEGRAM_TOKEN` env vars override config.yaml values. Unset them for local runs if they exist in your shell.

## Architecture

**Data flow:**
```
Telegram handlers -> DeviceRegistry -> HAClient (REST) or WBClient (MQTT publish)
HA WebSocket / MQTT subscribe -> DeviceRegistry (updates state) -> Notifications -> Telegram
```

**DeviceRegistry** (`bot/devices/registry.py`) is the central abstraction. Telegram handlers never touch HA or MQTT directly — they call registry methods. The registry loads devices from two sources:
- **HA**: states via REST API, areas/entities/devices via WebSocket commands (`config/area_registry/list`, `config/entity_registry/list`, `config/device_registry/list`)
- **WB**: devices defined in `config.yaml`, states via MQTT subscription

Room assignment follows the chain: entity -> device -> area (HA stores `area_id` on devices, not entities).

**Device IDs** use prefixed format: `ha:light.kitchen`, `wb:wb-mr6c_1`.

**main.py** orchestrates everything via `asyncio.TaskGroup`: Telegram polling, HA WebSocket listener, WB MQTT listener, daily cleanup task.

## Key Design Decisions

- HA `/api/areas` and `/api/entities` REST endpoints don't exist — use WebSocket commands instead (`HAClient._ws_command`)
- Notifications disabled by default per entity (`Storage.is_notification_enabled` returns `False` for unknown entities) to prevent flood on startup
- `/status` splits output into chunks < 4000 chars (Telegram message limit is 4096)
- HTML parse mode used for Telegram messages — escape `<>` in user-visible text with `html.escape()` or `&lt;`/`&gt;`
- WB MQTT uses Wirenboard convention: status topic `/devices/X/controls/Y`, command topic `/devices/X/controls/Y/on`, payloads `"1"`/`"0"` for switches

## Testing

Tests use `pytest-asyncio` in strict mode. HA REST calls mocked with `aioresponses`, HA WebSocket calls mocked by replacing `_ws_command` with `AsyncMock`. MQTT and WebSocket clients are integration-heavy and not unit tested.

## Specs and Plans

Design specs and implementation plans live in `docs/superpowers/specs/` and `docs/superpowers/plans/`.
