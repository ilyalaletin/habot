# Settings: Visibility + Notification Rules

## Overview

Two new features accessible via `/settings` command:
1. **Entity Visibility** — hide "junk" entities (zigbee signal, voltage, etc.) from bot UI
2. **Notification Rules** — per-entity rules with operators, thresholds, and hold timers

## Entity Visibility

### Behavior
- Hidden entities do not appear in `/rooms`, `/status`, room summaries, or device control screens
- Hidden entities remain in the registry and receive state updates (for notification rules)
- Visibility is toggled via Settings UI, defaults to visible

### Storage

```sql
CREATE TABLE entity_visibility (
    entity_id TEXT PRIMARY KEY,
    hidden INTEGER DEFAULT 0
);
```

No record = visible. Record with `hidden = 1` = hidden.

### Impact on DeviceRegistry

- `get_devices(room)` — returns only entities with `hidden = 0`
- New `get_all_devices(room)` — all entities including hidden (for settings UI)
- `get_rooms()` — rooms with at least one visible entity (used for `/rooms`, `/status`)
- New `get_all_rooms()` — all rooms including fully-hidden ones (used for `/settings` navigation — allows adding notification rules for hidden entities)
- New `get_ha_devices_in_room(room) -> list[tuple[str, str, list[Device]]]` — returns `(device_id, device_name, entities)` tuples. Keyed by device_id (unique), display name resolved separately. Needed for settings navigation.
- At load time, store mapping `entity_id -> device_name` from device registry

## Notification Rules

### Rule Model

Each rule defines a condition that triggers a Telegram notification:

- **entity_id** — which entity to watch
- **operator** — `>`, `<`, `>=`, `<=`, `=`
- **value** — threshold ("35", "on", "off")
- **hold_minutes** — how long the condition must hold before firing (0 = immediately)
- **fired** — whether the rule has already fired (prevents repeat notifications)

Multiple rules per entity are supported.

### Storage

```sql
CREATE TABLE notification_rules (
    id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL,
    operator TEXT NOT NULL,
    value TEXT NOT NULL,
    hold_minutes INTEGER DEFAULT 0,
    fired INTEGER DEFAULT 0
);

CREATE TABLE notification_history (
    id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL,
    rule_id INTEGER,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

`notification_history.rule_id` is nullable — no foreign key constraint. If a rule is deleted, history rows retain a dangling `rule_id`. This is acceptable for debug/display purposes; callers handle missing rules gracefully.

### Migration

Old `notification_settings` table is dropped (`DROP TABLE IF EXISTS notification_settings`). Old `notification_history` table is also dropped and recreated with the new schema (adds `rule_id` column). This is acceptable — notification history is debug data, not critical. Migration runs at `Storage.init()` startup.

### Evaluation Logic

On every `state_changed` event from HA WebSocket:

1. Update state in DeviceRegistry (existing behavior)
2. Load all rules for the changed entity_id
3. For each rule:
   - Evaluate condition against new state
   - If condition is FALSE: set `fired = 0`, cancel hold timer if any
   - If condition is TRUE and `fired = 1`: skip (already notified)
   - If condition is TRUE and `fired = 0`:
     - If `hold_minutes = 0`: send notification, set `fired = 1`
     - If `hold_minutes > 0`: start hold timer (asyncio.Task with sleep)
       - After sleep, re-check condition against `DeviceRegistry.get_device(entity_id).state`
       - If still true: send notification, set `fired = 1`
       - If no longer true: do nothing (timer naturally expires)

### Value Comparison

- If `new_state` is `unavailable` or `unknown`: skip all rule evaluation for this entity, cancel any running hold timers (treat as condition-false)
- For `>`, `<`, `>=`, `<=`: cast both state and value to `float`, compare numerically
- For `=`: string comparison ("on", "off", "23.5")
- If cast to float fails for numeric operators: skip rule (log warning)

### In-Memory Timer State

```python
# rule_id -> asyncio.Task
_hold_timers: dict[int, asyncio.Task] = {}
```

- Timer cancelled when condition becomes false (`task.cancel()`)
- Timer cancelled when rule is deleted via UI (`task.cancel()`, remove from dict)
- All timers lost on bot restart; `fired` reset to 0 on startup via `UPDATE notification_rules SET fired = 0`
- On startup, after registry load, run a one-time evaluation pass for all rules against current states in DeviceRegistry. This handles: (a) re-arming hold timers for conditions that are still true, (b) avoiding spurious re-fire by immediately setting `fired = 1` for conditions that are true with `hold_minutes = 0`. This startup pass behaves identically to a `state_changed` event for every entity that has rules.
- Maximum `hold_minutes` cap: 1440 (24 hours)

### Repeat Behavior

One notification per trigger cycle. `fired` resets to 0 only when condition stops being true. Next notification only after condition false -> true transition.

## Settings UI Navigation

### Entry Point

```
/settings
-> [Visibility] [Notifications]
```

### Visibility Flow

```
[Visibility]
-> Room selection: [Kitchen] [Bedroom] [Living Room] ...
-> Device selection: [Temp Sensor] [Light Relay] ...
-> Entity list with toggles:
   [x] Temperature
   [x] Humidity
   [ ] Supply Voltage
   [ ] Zigbee Signal
   (tap toggles visibility)
-> [<- Back]
```

### Notifications Flow

```
[Notifications]
-> Room selection: [Kitchen] [Bedroom] ...
-> Device selection: [Temp Sensor] ...
-> Entity selection: [Temperature] [Humidity] ...
-> Rules for entity:
   1. > 35, hold 10 min  [Delete]
   2. < 5, hold 0 min    [Delete]
   [+ Add Rule]
-> [<- Back]
```

### Add Rule Flow (FSM)

```
[+ Add Rule]
-> Operator: [>] [<] [>=] [<=] [=]
-> Bot: "Enter value (number or on/off):"
-> User: "35"
-> Bot: "Hold time (minutes, 0 = immediate):"
-> User: "10"
-> Done: "> 35, hold 10 min"
```

Uses aiogram FSM (finite state machine) for multi-step text input. FSM state is scoped to `(user_id, chat_id)` — aiogram's default for group chats. Multiple users can create rules simultaneously without conflicts.

**Input validation:**
- Value step: must be parseable as float for numeric operators (`>`, `<`, `>=`, `<=`), any non-empty string for `=`. On invalid input, re-prompt with error message.
- Hold time step: must be a non-negative integer, max 1440 (24h). On invalid input, re-prompt with error message.

## Navigation Details

- Back buttons at every level: entity list -> device list -> room list -> `/settings` root
- Old `/notifications` command is removed, replaced by `/settings -> Notifications`
- All notifications are sent to the group chat (`chat_id` from config) — unchanged from base design
- Single chat scope: `entity_visibility` and `notification_rules` have no `chat_id` column (single-chat bot by design)
- Orphaned rules (entity removed from HA): rules remain in DB, invisible in UI (no state_changed events arrive). Acceptable — no garbage collection needed for v1.

## New Files

| File | Responsibility |
|------|---------------|
| `bot/notifications/__init__.py` | Package marker |
| `bot/notifications/engine.py` | Rule evaluation, timer management, notification dispatch |

## Modified Files

| File | Changes |
|------|---------|
| `bot/storage/db.py` | Remove `notification_settings` table. Add `entity_visibility` and `notification_rules` tables. CRUD methods for both. |
| `bot/devices/registry.py` | Filter hidden entities in `get_devices()`. New methods: `get_all_devices()`, `get_ha_devices_in_room()`. Store entity->device_name mapping. |
| `bot/telegram/handlers.py` | Add `/settings` command, visibility/notification callback handlers, FSM states for rule creation. |
| `bot/main.py` | Replace simple notification logic with NotificationEngine. Wire engine to state_changed events. |
| `bot/homeassistant/client.py` | No changes (device_registry already available). |

## Supported Device Types for Rules

All entity types can have rules. Numeric operators (`>`, `<`, `>=`, `<=`) make sense for sensors. Equality (`=`) works for all types (binary sensors: "on"/"off", switches, etc.).
