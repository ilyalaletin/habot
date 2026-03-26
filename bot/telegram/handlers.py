from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.devices.registry import DeviceRegistry
from bot.storage.db import Storage
from bot.telegram.formatters import format_room_summary, format_device_state, format_help
from bot.telegram.keyboards import (
    rooms_keyboard,
    room_devices_keyboard,
    switch_control_keyboard,
    dimmer_control_keyboard,
    settings_root_keyboard,
    settings_rooms_keyboard,
    settings_devices_keyboard,
    visibility_entities_keyboard,
    notification_entities_keyboard,
    notification_rules_keyboard,
    operator_keyboard,
)


class AddRuleStates(StatesGroup):
    waiting_for_value = State()
    waiting_for_hold = State()


def make_router(
    registry: DeviceRegistry, storage: Storage, chat_id: int, *, engine=None
) -> Router:
    router = Router()

    def _check_chat(msg_or_cb) -> bool:
        chat = msg_or_cb.chat if hasattr(msg_or_cb, "chat") else msg_or_cb.message.chat
        return chat.id == chat_id

    def _resolve(ri: int, gi: int, ei: int):
        """Resolve room/group/entity indices to actual objects."""
        rooms = registry.get_all_rooms()
        if ri >= len(rooms):
            return None, None, None, None
        room = rooms[ri]
        groups = registry.get_all_device_groups(room)
        if gi >= len(groups):
            return None, None, None, None
        _, group_name, entities = groups[gi]
        if ei >= len(entities):
            return None, None, None, None
        return entities[ei], room, group_name, entities

    def _resolve_visible(ri: int, gi: int, ei: int):
        """Like _resolve but filters out hidden entities (for notifications)."""
        rooms = registry.get_all_rooms()
        if ri >= len(rooms):
            return None, None, None, None
        room = rooms[ri]
        groups = registry.get_all_device_groups(room)
        if gi >= len(groups):
            return None, None, None, None
        _, group_name, all_entities = groups[gi]
        visible = [e for e in all_entities if not registry.is_hidden(e.id)]
        if ei >= len(visible):
            return None, None, None, None
        return visible[ei], room, group_name, visible

    # ==================== Device commands ====================

    @router.message(CommandStart())
    @router.message(Command("rooms"))
    async def cmd_rooms(message: Message) -> None:
        if not _check_chat(message):
            return
        rooms = registry.get_rooms()
        await message.answer("Rooms:", reply_markup=rooms_keyboard(rooms))

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        if not _check_chat(message):
            return
        await message.answer(format_help(), parse_mode="HTML")

    @router.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if not _check_chat(message):
            return
        rooms = registry.get_rooms()
        chunk = []
        chunk_len = 0
        for room in rooms:
            devices = registry.get_devices(room)
            part = format_room_summary(room, devices)
            if chunk and chunk_len + len(part) + 2 > 4000:
                await message.answer("\n\n".join(chunk), parse_mode="HTML")
                chunk = []
                chunk_len = 0
            chunk.append(part)
            chunk_len += len(part) + 2
        if chunk:
            await message.answer("\n\n".join(chunk), parse_mode="HTML")

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
        text = format_room_summary(room_name, devices)
        await message.answer(text, parse_mode="HTML", reply_markup=room_devices_keyboard(room_name, devices))

    @router.message(Command("on"))
    async def cmd_on(message: Message) -> None:
        if not _check_chat(message):
            return
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer("Usage: /on <device name>")
            return
        await _handle_device_command(message, args[1], "on")

    @router.message(Command("off"))
    async def cmd_off(message: Message) -> None:
        if not _check_chat(message):
            return
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer("Usage: /off <device name>")
            return
        await _handle_device_command(message, args[1], "off")

    @router.message(Command("set"))
    async def cmd_set(message: Message) -> None:
        if not _check_chat(message):
            return
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            await message.answer("Usage: /set <device name> <value>")
            return
        name, value = args[1], args[2]
        matches = registry.find_devices(name)
        controllable = [d for d in matches if d.is_controllable]
        if not controllable:
            await message.answer(f"Device '{name}' not found.")
            return
        if len(controllable) == 1:
            device = controllable[0]
            if device.type == "dimmer":
                brightness = int(round(int(value) / 100 * 255))
                await registry.set_state(device.id, "on", brightness=brightness)
            else:
                await registry.set_state(device.id, value)
            await message.answer(f"{device.name}: set to {value}")
        else:
            await _send_disambiguation(message, controllable)

    # ==================== Device callbacks ====================

    @router.callback_query(F.data.startswith("room:"))
    async def cb_room(callback: CallbackQuery) -> None:
        room_name = callback.data.removeprefix("room:")
        devices = registry.get_devices(room_name)
        text = format_room_summary(room_name, devices)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=room_devices_keyboard(room_name, devices))
        await callback.answer()

    @router.callback_query(F.data.startswith("device:"))
    async def cb_device(callback: CallbackQuery) -> None:
        device_id = callback.data.removeprefix("device:")
        device = registry.get_device(device_id)
        if not device:
            await callback.answer("Device not found")
            return
        text = format_device_state(device)
        if device.type == "dimmer":
            kb = dimmer_control_keyboard(device_id, device.room)
        else:
            kb = switch_control_keyboard(device_id, device.room)
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("set:"))
    async def cb_set(callback: CallbackQuery) -> None:
        _, device_id, state = callback.data.split(":", 2)
        await registry.set_state(device_id, state)
        device = registry.get_device(device_id)
        await callback.answer(f"{device.name}: {state}")
        text = format_device_state(device)
        if device.type == "dimmer":
            kb = dimmer_control_keyboard(device_id, device.room)
        else:
            kb = switch_control_keyboard(device_id, device.room)
        await callback.message.edit_text(text, reply_markup=kb)

    @router.callback_query(F.data.startswith("dim:"))
    async def cb_dim(callback: CallbackQuery) -> None:
        _, device_id, pct_str = callback.data.split(":", 2)
        pct = int(pct_str)
        brightness = int(round(pct / 100 * 255))
        await registry.set_state(device_id, "on", brightness=brightness)
        device = registry.get_device(device_id)
        await callback.answer(f"{device.name}: {pct}%")
        text = format_device_state(device)
        kb = dimmer_control_keyboard(device_id, device.room)
        await callback.message.edit_text(text, reply_markup=kb)

    @router.callback_query(F.data == "back:rooms")
    async def cb_back_rooms(callback: CallbackQuery) -> None:
        rooms = registry.get_rooms()
        await callback.message.edit_text("Rooms:", reply_markup=rooms_keyboard(rooms))
        await callback.answer()

    # ==================== Settings command ====================

    @router.message(Command("settings"))
    async def cmd_settings(message: Message) -> None:
        if not _check_chat(message):
            return
        await message.answer("Settings:", reply_markup=settings_root_keyboard())

    @router.callback_query(F.data == "bk:s")
    async def cb_back_settings(callback: CallbackQuery) -> None:
        await callback.message.edit_text("Settings:", reply_markup=settings_root_keyboard())
        await callback.answer()

    # ==================== Visibility ====================

    @router.callback_query(F.data == "s:vis")
    async def cb_vis_rooms(callback: CallbackQuery) -> None:
        rooms = registry.get_all_rooms()
        await callback.message.edit_text(
            "Visibility — select room:",
            reply_markup=settings_rooms_keyboard(rooms, prefix="sv"),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("sv:r:"))
    async def cb_vis_devices(callback: CallbackQuery) -> None:
        ri = int(callback.data.removeprefix("sv:r:"))
        rooms = registry.get_all_rooms()
        if ri >= len(rooms):
            await callback.answer("Room not found")
            return
        room = rooms[ri]
        groups = registry.get_all_device_groups(room)
        if not groups:
            await callback.answer("No devices in this room")
            return
        await callback.message.edit_text(
            f"<b>{room}</b> — select device:",
            parse_mode="HTML",
            reply_markup=settings_devices_keyboard(groups, ri, prefix="sv"),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("sv:d:"))
    async def cb_vis_entities(callback: CallbackQuery) -> None:
        rest = callback.data.removeprefix("sv:d:")
        ri_str, gi_str = rest.split(":")
        ri, gi = int(ri_str), int(gi_str)
        rooms = registry.get_all_rooms()
        if ri >= len(rooms):
            await callback.answer("Room not found")
            return
        room = rooms[ri]
        groups = registry.get_all_device_groups(room)
        if gi >= len(groups):
            await callback.answer("Device not found")
            return
        _, group_name, entities = groups[gi]
        hidden = await storage.get_hidden_entities()
        await callback.message.edit_text(
            f"<b>{group_name}</b>\nToggle visibility:",
            parse_mode="HTML",
            reply_markup=visibility_entities_keyboard(entities, hidden, ri, gi),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("sv:t:"))
    async def cb_vis_toggle(callback: CallbackQuery) -> None:
        rest = callback.data.removeprefix("sv:t:")
        parts = rest.split(":")
        if len(parts) != 3:
            await callback.answer("Error")
            return
        ri, gi, ei = int(parts[0]), int(parts[1]), int(parts[2])
        entity, room, group_name, entities = _resolve(ri, gi, ei)
        if not entity:
            await callback.answer("Entity not found")
            return
        is_hidden = await storage.is_entity_hidden(entity.id)
        new_hidden = not is_hidden
        await storage.set_entity_hidden(entity.id, new_hidden)
        registry.set_hidden(entity.id, new_hidden)

        hidden_set = await storage.get_hidden_entities()
        status = "hidden" if new_hidden else "visible"
        await callback.answer(f"{entity.name}: {status}")
        await callback.message.edit_text(
            f"<b>{group_name}</b>\nToggle visibility:",
            parse_mode="HTML",
            reply_markup=visibility_entities_keyboard(entities, hidden_set, ri, gi),
        )

    # ==================== Notifications ====================

    @router.callback_query(F.data == "s:ntf")
    async def cb_ntf_rooms(callback: CallbackQuery) -> None:
        rooms = registry.get_all_rooms()
        await callback.message.edit_text(
            "Notification rules — select room:",
            reply_markup=settings_rooms_keyboard(rooms, prefix="sn"),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("sn:r:"))
    async def cb_ntf_devices(callback: CallbackQuery) -> None:
        ri = int(callback.data.removeprefix("sn:r:"))
        rooms = registry.get_all_rooms()
        if ri >= len(rooms):
            await callback.answer("Room not found")
            return
        room = rooms[ri]
        groups = registry.get_all_device_groups(room)
        if not groups:
            await callback.answer("No devices in this room")
            return
        await callback.message.edit_text(
            f"<b>{room}</b> — select device:",
            parse_mode="HTML",
            reply_markup=settings_devices_keyboard(groups, ri, prefix="sn"),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("sn:d:"))
    async def cb_ntf_entities(callback: CallbackQuery) -> None:
        rest = callback.data.removeprefix("sn:d:")
        ri_str, gi_str = rest.split(":")
        ri, gi = int(ri_str), int(gi_str)
        rooms = registry.get_all_rooms()
        if ri >= len(rooms):
            await callback.answer("Room not found")
            return
        room = rooms[ri]
        groups = registry.get_all_device_groups(room)
        if gi >= len(groups):
            await callback.answer("Device not found")
            return
        _, group_name, all_entities = groups[gi]
        visible = [e for e in all_entities if not registry.is_hidden(e.id)]
        if not visible:
            await callback.answer("All entities in this group are hidden")
            return
        await callback.message.edit_text(
            f"<b>{group_name}</b>\nSelect entity for rules:",
            parse_mode="HTML",
            reply_markup=notification_entities_keyboard(visible, ri, gi),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("sn:e:"))
    async def cb_ntf_rules(callback: CallbackQuery) -> None:
        rest = callback.data.removeprefix("sn:e:")
        parts = rest.split(":")
        ri, gi, ei = int(parts[0]), int(parts[1]), int(parts[2])
        await _show_rules(callback, ri, gi, ei)

    @router.callback_query(F.data.startswith("sn:x:"))
    async def cb_ntf_delete_rule(callback: CallbackQuery) -> None:
        rest = callback.data.removeprefix("sn:x:")
        # Format: sn:x:<rule_id>:<ri>:<gi>:<ei>
        parts = rest.split(":")
        rule_id = int(parts[0])
        ri, gi, ei = int(parts[1]), int(parts[2]), int(parts[3])
        await storage.delete_rule(rule_id)
        if engine:
            engine.on_rule_deleted(rule_id)
        await callback.answer("Rule deleted")
        await _show_rules(callback, ri, gi, ei)

    @router.callback_query(F.data.startswith("sn:a:"))
    async def cb_ntf_add_rule(callback: CallbackQuery, state: FSMContext) -> None:
        rest = callback.data.removeprefix("sn:a:")
        parts = rest.split(":")
        ri, gi, ei = int(parts[0]), int(parts[1]), int(parts[2])
        entity, room, group_name, entities = _resolve_visible(ri, gi, ei)
        if not entity:
            await callback.answer("Entity not found")
            return
        await state.update_data(rule_entity_id=entity.id, rule_ri=ri, rule_gi=gi, rule_ei=ei)
        await callback.message.edit_text(
            "Select operator:", reply_markup=operator_keyboard()
        )
        await callback.answer()

    @router.callback_query(F.data == "sn:cancel")
    async def cb_ntf_cancel_fsm(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        await state.clear()
        ri = data.get("rule_ri")
        if ri is not None:
            await _show_rules(callback, data["rule_ri"], data["rule_gi"], data["rule_ei"])
        else:
            await callback.answer("Cancelled")

    @router.message(Command("cancel"))
    async def cmd_cancel(message: Message, state: FSMContext) -> None:
        if not _check_chat(message):
            return
        current = await state.get_state()
        if current is None:
            await message.answer("Nothing to cancel.")
            return
        await state.clear()
        await message.answer("Cancelled.")

    @router.callback_query(F.data.startswith("sn:o:"))
    async def cb_ntf_select_op(callback: CallbackQuery, state: FSMContext) -> None:
        op = callback.data.removeprefix("sn:o:")
        await state.update_data(rule_operator=op)
        await state.set_state(AddRuleStates.waiting_for_value)
        if op in (">", "<", ">=", "<="):
            prompt = "Enter threshold value (number, or /cancel):"
        else:
            prompt = "Enter value (number, on, off, etc. — or /cancel):"
        await callback.message.edit_text(prompt)
        await callback.answer()

    @router.message(AddRuleStates.waiting_for_value)
    async def fsm_rule_value(message: Message, state: FSMContext) -> None:
        if not _check_chat(message):
            return
        data = await state.get_data()
        value = message.text.strip()
        op = data.get("rule_operator", "=")

        # Validate: numeric operators require a float-parseable value
        if op in (">", "<", ">=", "<="):
            try:
                float(value)
            except ValueError:
                await message.answer(f"Invalid number: '{value}'. Enter a numeric value:")
                return

        if not value:
            await message.answer("Value cannot be empty. Try again:")
            return

        await state.update_data(rule_value=value)
        await state.set_state(AddRuleStates.waiting_for_hold)
        await message.answer("Hold time in minutes (0 = immediate, max 1440, or /cancel):")

    @router.message(AddRuleStates.waiting_for_hold)
    async def fsm_rule_hold(message: Message, state: FSMContext) -> None:
        if not _check_chat(message):
            return
        text = message.text.strip()
        try:
            hold = int(text)
        except ValueError:
            await message.answer(f"Invalid number: '{text}'. Enter minutes (0-1440):")
            return
        if hold < 0 or hold > 1440:
            await message.answer("Hold time must be 0-1440 minutes. Try again:")
            return

        data = await state.get_data()
        entity_id = data["rule_entity_id"]
        operator = data["rule_operator"]
        value = data["rule_value"]
        ri, gi, ei = data["rule_ri"], data["rule_gi"], data["rule_ei"]

        await storage.add_rule(entity_id, operator, value, hold_minutes=hold)
        await state.clear()

        hold_text = f", hold {hold}m" if hold > 0 else ""
        await message.answer(f"Rule added: {operator} {value}{hold_text}")

        # Show updated rules list
        entity, room, group_name, entities = _resolve_visible(ri, gi, ei)
        name = entity.name if entity else entity_id
        rules = await storage.get_rules_for_entity(entity_id)
        lines = [f"<b>{name}</b>", ""]
        for i, r in enumerate(rules, 1):
            h = f", hold {r['hold_minutes']}m" if r["hold_minutes"] > 0 else ""
            lines.append(f"{i}. {r['operator']} {r['value']}{h}")
        if not rules:
            lines.append("No rules.")
        await message.answer(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=notification_rules_keyboard(rules, ri, gi, ei),
        )

    # ==================== Helpers ====================

    async def _show_rules(callback: CallbackQuery, ri: int, gi: int, ei: int) -> None:
        entity, room, group_name, entities = _resolve_visible(ri, gi, ei)
        if not entity:
            await callback.answer("Entity not found")
            return
        rules = await storage.get_rules_for_entity(entity.id)
        lines = [f"<b>{entity.name}</b>", ""]
        for i, r in enumerate(rules, 1):
            h = f", hold {r['hold_minutes']}m" if r["hold_minutes"] > 0 else ""
            lines.append(f"{i}. {r['operator']} {r['value']}{h}")
        if not rules:
            lines.append("No rules.")
        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=notification_rules_keyboard(rules, ri, gi, ei),
        )

    async def _handle_device_command(message: Message, name: str, state: str) -> None:
        matches = registry.find_devices(name)
        controllable = [d for d in matches if d.is_controllable]
        if not controllable:
            await message.answer(f"Device '{name}' not found.")
            return
        if len(controllable) == 1:
            device = controllable[0]
            await registry.set_state(device.id, state)
            await message.answer(f"{device.name}: {state}")
        else:
            await _send_disambiguation(message, controllable)

    async def _send_disambiguation(message: Message, devices: list) -> None:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        for d in devices:
            builder.button(text=d.name, callback_data=f"device:{d.id}")
        builder.adjust(1)
        await message.answer("Multiple devices found. Choose one:", reply_markup=builder.as_markup())

    return router
