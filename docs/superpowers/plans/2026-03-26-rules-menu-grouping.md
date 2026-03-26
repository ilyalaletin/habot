# Rules, Menu & Device Grouping Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/rules` command for listing/deleting notification rules, `/menu`+`/start` main menu, and group entities by device in `/status`/`/rooms` output.

**Architecture:** Three independent features touching handlers, formatters, keyboards, and registry. No DB changes needed — `get_all_rules()` and `get_device` already exist.

**Tech Stack:** Python 3.14, aiogram 3.x, aiosqlite, pytest-asyncio

---

## Chunk 1: Device Grouping in Status/Rooms

### Task 1: Add `get_device_groups()` to registry (visible-only version)

**Files:**
- Modify: `bot/devices/registry.py:118-141`
- Test: `tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_registry.py`, add:

```python
@pytest.mark.asyncio
async def test_get_device_groups_filters_hidden(ha_client, wb_devices, wb_publish):
    reg = DeviceRegistry(ha_client, wb_devices, wb_publish=wb_publish, hidden={"ha:sensor.kitchen_temp"})
    await reg.load()
    groups = reg.get_device_groups("Kitchen")
    # dev1 group should have only 1 entity (light), temp is hidden
    ha_groups = [g for g in groups if g[0] == "dev1"]
    assert len(ha_groups) == 1
    _, _, entities = ha_groups[0]
    assert len(entities) == 1
    assert entities[0].id == "ha:light.kitchen"


@pytest.mark.asyncio
async def test_get_device_groups_skips_fully_hidden_group(ha_client, wb_devices, wb_publish):
    reg = DeviceRegistry(ha_client, wb_devices, wb_publish=wb_publish, hidden={"ha:light.kitchen", "ha:sensor.kitchen_temp"})
    await reg.load()
    groups = reg.get_device_groups("Kitchen")
    assert groups == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_registry.py::test_get_device_groups_filters_hidden tests/test_registry.py::test_get_device_groups_skips_fully_hidden_group -v`
Expected: FAIL — `AttributeError: 'DeviceRegistry' object has no attribute 'get_device_groups'`

- [ ] **Step 3: Implement `get_device_groups()`**

In `bot/devices/registry.py`, add after `get_all_device_groups`:

```python
def get_device_groups(self, room: str) -> list[tuple[str, str, list[Device]]]:
    """Like get_all_device_groups but filters out hidden entities."""
    all_groups = self.get_all_device_groups(room)
    result = []
    for gid, gname, entities in all_groups:
        visible = [e for e in entities if e.id not in self._hidden]
        if visible:
            result.append((gid, gname, visible))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_registry.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/devices/registry.py tests/test_registry.py
git commit -m "feat: add get_device_groups() with hidden filtering"
```

### Task 2: Update `format_room_summary()` to accept groups

**Files:**
- Modify: `bot/telegram/formatters.py:23-27`
- Test: `tests/test_formatters.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_formatters.py`, update imports and add:

```python
def test_format_room_summary_with_groups():
    groups = [
        ("dev1", "Climate Sensor", [_sensor(name="Temperature"), _sensor(name="Humidity", state="45", unit="%")]),
        ("dev2", "Ceiling Light", [_switch(name="Light")]),
    ]
    text = format_room_summary("Kitchen", groups=groups)
    assert "<b>Kitchen</b>" in text
    assert "<b>Climate Sensor</b>" in text
    assert "<b>Ceiling Light</b>" in text
    assert "Temperature" in text
    assert "Humidity" in text
    assert "Light" in text


def test_format_room_summary_solo_no_header():
    groups = [
        ("_solo:ha:sensor.z", "Temperature", [_sensor(name="Temperature")]),
    ]
    text = format_room_summary("Kitchen", groups=groups)
    assert "<b>Kitchen</b>" in text
    assert "Temperature" in text
    # Solo entities should NOT have a bold device header
    lines = text.split("\n")
    bold_lines = [l for l in lines if "<b>" in l]
    assert len(bold_lines) == 1  # only room name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_formatters.py::test_format_room_summary_with_groups tests/test_formatters.py::test_format_room_summary_solo_no_header -v`
Expected: FAIL

- [ ] **Step 3: Update `format_room_summary()`**

Replace the function in `bot/telegram/formatters.py`:

```python
def format_room_summary(
    room: str,
    devices: list[Device] | None = None,
    groups: list[tuple[str, str, list[Device]]] | None = None,
) -> str:
    lines = [f"<b>{room}</b>"]
    if groups is not None:
        for gid, gname, entities in groups:
            lines.append("")
            if not gid.startswith("_solo:"):
                lines.append(f"<b>{gname}</b>")
            for d in entities:
                lines.append(f"  {format_device_state(d)}" if not gid.startswith("_solo:") else format_device_state(d))
    elif devices is not None:
        lines.append("")
        for d in devices:
            lines.append(format_device_state(d))
    return "\n".join(lines)
```

- [ ] **Step 4: Run all formatter tests**

Run: `.venv/bin/pytest tests/test_formatters.py -v`
Expected: All PASS (old `test_format_room_summary` still passes via `devices=` param)

- [ ] **Step 5: Commit**

```bash
git add bot/telegram/formatters.py tests/test_formatters.py
git commit -m "feat: format_room_summary supports device groups"
```

### Task 3: Wire grouping into handlers

**Files:**
- Modify: `bot/telegram/handlers.py` (cmd_status, cb_room, cmd_room)

- [ ] **Step 1: Update `cmd_status` to use groups**

In `bot/telegram/handlers.py`, change `cmd_status` body:

```python
    @router.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if not _check_chat(message):
            return
        rooms = registry.get_rooms()
        chunk = []
        chunk_len = 0
        for room in rooms:
            groups = registry.get_device_groups(room)
            part = format_room_summary(room, groups=groups)
            if chunk and chunk_len + len(part) + 2 > 4000:
                await message.answer("\n\n".join(chunk), parse_mode="HTML")
                chunk = []
                chunk_len = 0
            chunk.append(part)
            chunk_len += len(part) + 2
        if chunk:
            await message.answer("\n\n".join(chunk), parse_mode="HTML")
```

- [ ] **Step 2: Update `cb_room` callback to use groups**

```python
    @router.callback_query(F.data.startswith("room:"))
    async def cb_room(callback: CallbackQuery) -> None:
        room_name = callback.data.removeprefix("room:")
        devices = registry.get_devices(room_name)
        groups = registry.get_device_groups(room_name)
        text = format_room_summary(room_name, groups=groups)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=room_devices_keyboard(room_name, devices))
        await callback.answer()
```

- [ ] **Step 3: Update `cmd_room` to use groups**

```python
    @router.message(Command("room"))
    async def cmd_room(message: Message) -> None:
        if not _check_chat(message):
            return
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer("Usage: /room <name>")
            return
        room_name = args[1]
        devices = registry.get_devices(room_name)
        if not devices:
            for r in registry.get_rooms():
                if r.lower() == room_name.lower():
                    devices = registry.get_devices(r)
                    room_name = r
                    break
        if not devices:
            await message.answer(f"Room '{room_name}' not found.")
            return
        groups = registry.get_device_groups(room_name)
        text = format_room_summary(room_name, groups=groups)
        await message.answer(text, parse_mode="HTML", reply_markup=room_devices_keyboard(room_name, devices))
```

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/telegram/handlers.py
git commit -m "feat: use device groups in status/rooms display"
```

---

## Chunk 2: /rules Command

### Task 4: Add `rules_keyboard()` to keyboards

**Files:**
- Modify: `bot/telegram/keyboards.py`
- Test: `tests/test_keyboards.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_keyboards.py`, add import and test:

```python
from bot.telegram.keyboards import rules_list_keyboard

def test_rules_list_keyboard():
    rules = [
        {"id": 1, "entity_id": "ha:sensor.temp", "operator": ">", "value": "30", "hold_minutes": 5},
        {"id": 2, "entity_id": "ha:sensor.hum", "operator": "<", "value": "20", "hold_minutes": 0},
    ]
    names = {"ha:sensor.temp": "Temperature", "ha:sensor.hum": "Humidity"}
    kb = rules_list_keyboard(rules, names)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "rl:x:1" in callbacks
    assert "rl:x:2" in callbacks
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Temperature" in t and ">" in t and "30" in t for t in texts)


def test_rules_list_keyboard_empty():
    kb = rules_list_keyboard([], {})
    assert kb is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_keyboards.py::test_rules_list_keyboard tests/test_keyboards.py::test_rules_list_keyboard_empty -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement `rules_list_keyboard()`**

In `bot/telegram/keyboards.py`, add:

```python
def rules_list_keyboard(
    rules: list[dict], entity_names: dict[str, str]
) -> InlineKeyboardMarkup | None:
    if not rules:
        return None
    builder = InlineKeyboardBuilder()
    for rule in rules:
        name = entity_names.get(rule["entity_id"], rule["entity_id"])
        hold = f", hold {rule['hold_minutes']}m" if rule["hold_minutes"] > 0 else ""
        label = f"[x] {name} {rule['operator']} {rule['value']}{hold}"
        builder.button(text=label, callback_data=f"rl:x:{rule['id']}")
    builder.adjust(1)
    return builder.as_markup()
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_keyboards.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/telegram/keyboards.py tests/test_keyboards.py
git commit -m "feat: add rules_list_keyboard for /rules command"
```

### Task 5: Add `/rules` handler and `rl:x:` callback

**Files:**
- Modify: `bot/telegram/handlers.py`

- [ ] **Step 1: Add import**

Add `rules_list_keyboard` to the import from `bot.telegram.keyboards`.

- [ ] **Step 2: Add `/rules` command handler**

After the `cmd_status` handler, add:

```python
    @router.message(Command("rules"))
    async def cmd_rules(message: Message) -> None:
        if not _check_chat(message):
            return
        await _show_all_rules(message)
```

- [ ] **Step 3: Add `rl:x:` delete callback**

```python
    @router.callback_query(F.data.startswith("rl:x:"))
    async def cb_rules_delete(callback: CallbackQuery) -> None:
        rule_id = int(callback.data.removeprefix("rl:x:"))
        await storage.delete_rule(rule_id)
        if engine:
            engine.on_rule_deleted(rule_id)
        await callback.answer("Rule deleted")
        await _show_all_rules(callback.message, edit=True)
```

- [ ] **Step 4: Add `_show_all_rules` helper**

```python
    async def _show_all_rules(target, edit: bool = False) -> None:
        rules = await storage.get_all_rules()
        entity_names = {}
        for r in rules:
            device = registry.get_device(r["entity_id"])
            entity_names[r["entity_id"]] = device.name if device else r["entity_id"]
        kb = rules_list_keyboard(rules, entity_names)
        text = "<b>Notification rules:</b>" if rules else "No notification rules."
        if edit:
            await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
        else:
            await target.answer(text, parse_mode="HTML", reply_markup=kb)
```

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add bot/telegram/handlers.py
git commit -m "feat: add /rules command with delete via inline buttons"
```

---

## Chunk 3: /menu and /start

### Task 6: Add `menu_keyboard()` and wire /menu + /start

**Files:**
- Modify: `bot/telegram/keyboards.py`
- Modify: `bot/telegram/handlers.py`
- Test: `tests/test_keyboards.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_keyboards.py`:

```python
from bot.telegram.keyboards import menu_keyboard

def test_menu_keyboard():
    kb = menu_keyboard()
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "menu:rooms" in callbacks
    assert "menu:status" in callbacks
    assert "menu:rules" in callbacks
    assert "menu:settings" in callbacks
    assert "menu:help" in callbacks
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_keyboards.py::test_menu_keyboard -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement `menu_keyboard()`**

In `bot/telegram/keyboards.py`:

```python
def menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    items = [
        ("Rooms", "menu:rooms"),
        ("Status", "menu:status"),
        ("Rules", "menu:rules"),
        ("Settings", "menu:settings"),
        ("Help", "menu:help"),
    ]
    for text, cb in items:
        builder.button(text=text, callback_data=cb)
    builder.adjust(2)
    return builder.as_markup()
```

- [ ] **Step 4: Run keyboard tests**

Run: `.venv/bin/pytest tests/test_keyboards.py -v`
Expected: All PASS

- [ ] **Step 5: Update handlers — replace `/start`, add `/menu`, add callbacks**

In `bot/telegram/handlers.py`:

Replace the existing `cmd_rooms` handler (which handles both `/start` and `/rooms`):

```python
    @router.message(CommandStart())
    @router.message(Command("menu"))
    async def cmd_menu(message: Message) -> None:
        if not _check_chat(message):
            return
        await message.answer("Menu:", reply_markup=menu_keyboard())

    @router.message(Command("rooms"))
    async def cmd_rooms(message: Message) -> None:
        if not _check_chat(message):
            return
        rooms = registry.get_rooms()
        await message.answer("Rooms:", reply_markup=rooms_keyboard(rooms))
```

Add menu callback handler:

```python
    @router.callback_query(F.data.startswith("menu:"))
    async def cb_menu(callback: CallbackQuery) -> None:
        cmd = callback.data.removeprefix("menu:")
        if cmd == "rooms":
            rooms = registry.get_rooms()
            await callback.message.edit_text("Rooms:", reply_markup=rooms_keyboard(rooms))
        elif cmd == "status":
            await callback.message.delete()
            rooms = registry.get_rooms()
            chunk = []
            chunk_len = 0
            for room in rooms:
                groups = registry.get_device_groups(room)
                part = format_room_summary(room, groups=groups)
                if chunk and chunk_len + len(part) + 2 > 4000:
                    await callback.message.answer("\n\n".join(chunk), parse_mode="HTML")
                    chunk = []
                    chunk_len = 0
                chunk.append(part)
                chunk_len += len(part) + 2
            if chunk:
                await callback.message.answer("\n\n".join(chunk), parse_mode="HTML")
        elif cmd == "rules":
            await _show_all_rules(callback.message, edit=True)
        elif cmd == "settings":
            await callback.message.edit_text("Settings:", reply_markup=settings_root_keyboard())
        elif cmd == "help":
            await callback.message.edit_text(format_help(), parse_mode="HTML")
        await callback.answer()
```

Add `menu_keyboard` to imports from `bot.telegram.keyboards`.

- [ ] **Step 6: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add bot/telegram/keyboards.py bot/telegram/handlers.py tests/test_keyboards.py
git commit -m "feat: add /menu and /start as main menu with inline buttons"
```

### Task 7: Update `/help` and CLAUDE.md

**Files:**
- Modify: `bot/telegram/formatters.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update `format_help()` to include new commands**

In `bot/telegram/formatters.py`, update the `commands` list in `format_help()`:

```python
def format_help() -> str:
    commands = [
        ("/menu", "Main menu"),
        ("/help", "List of all commands"),
        ("/rooms", "List rooms"),
        ("/room &lt;name&gt;", "Room summary"),
        ("/on &lt;name&gt;", "Turn on device"),
        ("/off &lt;name&gt;", "Turn off device"),
        ("/set &lt;name&gt; &lt;value&gt;", "Set value (dimmer: 0-100)"),
        ("/status", "Full summary of all rooms"),
        ("/rules", "Notification rules"),
        ("/settings", "Visibility and notification rules"),
        ("/cancel", "Cancel current operation"),
    ]
    lines = ["<b>Available commands:</b>", ""]
    for cmd, desc in commands:
        lines.append(f"<code>{cmd}</code> — {desc}")
    return "\n".join(lines)
```

- [ ] **Step 2: Update test**

In `tests/test_formatters.py`, update `test_format_help`:

```python
def test_format_help():
    text = format_help()
    assert "/rooms" in text
    assert "/help" in text
    assert "/on" in text
    assert "/off" in text
    assert "/settings" in text
    assert "/cancel" in text
    assert "/menu" in text
    assert "/rules" in text
    assert "/notifications" not in text
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_formatters.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add bot/telegram/formatters.py tests/test_formatters.py CLAUDE.md
git commit -m "feat: update help text with /menu and /rules commands"
```

### Task 8: Final integration test

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Verify no regressions**

Check that no existing test was broken by the changes.
