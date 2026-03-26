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
HA WebSocket / MQTT subscribe -> DeviceRegistry (updates state) -> NotificationEngine (rule eval) -> Telegram
Settings UI (FSM) -> Storage (rules/visibility CRUD) -> DeviceRegistry (hidden set)
```

**DeviceRegistry** (`bot/devices/registry.py`) is the central abstraction. Telegram handlers never touch HA or MQTT directly — they call registry methods. The registry loads devices from two sources:
- **HA**: states via REST API, areas/entities/devices via WebSocket commands (`config/area_registry/list`, `config/entity_registry/list`, `config/device_registry/list`)
- **WB**: devices defined in `config.yaml`, states via MQTT subscription

Room assignment follows the chain: entity -> device -> area (HA stores `area_id` on devices, not entities).

The registry supports **visibility filtering**: `get_rooms()`/`get_devices()` exclude hidden entities, while `get_all_rooms()`/`get_all_devices()` return everything (used by settings UI). `get_all_device_groups()` groups entities by HA device for settings navigation.

**NotificationEngine** (`bot/notifications/engine.py`) evaluates per-entity rules (operator + threshold + optional hold timer). On state change, rules are checked; if a condition is met and not already fired, a notification is sent. Hold timers delay notification until the condition persists for N minutes. On startup, all fired flags are reset and current states are re-evaluated.

**Storage** (`bot/storage/db.py`) manages three tables: `entity_visibility` (hidden entities), `notification_rules` (per-entity rules with operator/value/hold/fired), `notification_history` (with optional rule_id).

**Device IDs** use prefixed format: `ha:light.kitchen`, `wb:wb-mr6c_1`.

**main.py** orchestrates everything via `asyncio.TaskGroup`: Telegram polling, HA WebSocket listener, WB MQTT listener, daily cleanup task. Both HA and WB state change callbacks feed into `NotificationEngine.on_state_changed()`.

## Key Design Decisions

- HA `/api/areas` and `/api/entities` REST endpoints don't exist — use WebSocket commands instead (`HAClient._ws_command`)
- Notifications use rule-based engine: per-entity rules with operator (`>`, `<`, `>=`, `<=`, `=`), threshold value, and optional hold timer (minutes). Rules are stored in SQLite and evaluated on every state change. A rule fires once and resets when the condition becomes false.
- `/settings` command provides inline keyboard UI for visibility toggles and notification rule management. Uses aiogram FSM (`AddRuleStates`) for multi-step rule creation (operator -> value -> hold time).
- Entity visibility: hidden entities are excluded from `/status`, `/rooms`, device listings. Settings UI shows all entities including hidden ones. Hidden set is loaded from DB on startup and kept in sync in `DeviceRegistry._hidden`.
- `/status` splits output into chunks < 4000 chars (Telegram message limit is 4096)
- HTML parse mode used for Telegram messages — escape `<>` in user-visible text with `html.escape()` or `&lt;`/`&gt;`
- WB MQTT uses Wirenboard convention: status topic `/devices/X/controls/Y`, command topic `/devices/X/controls/Y/on`, payloads `"1"`/`"0"` for switches
- Callback data scheme uses short prefixes (`s:`, `sv:`, `sn:`, `bk:`) to stay under Telegram's 64-byte limit

## Testing

Tests use `pytest-asyncio` in strict mode. HA REST calls mocked with `aioresponses`, HA WebSocket calls mocked by replacing `_ws_command` with `AsyncMock`. MQTT and WebSocket clients are integration-heavy and not unit tested.

## Specs and Plans

Design specs and implementation plans live in `docs/superpowers/specs/` and `docs/superpowers/plans/`.
