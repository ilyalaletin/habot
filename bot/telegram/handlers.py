from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery

from bot.devices.registry import DeviceRegistry
from bot.storage.db import Storage
from bot.telegram.formatters import (
    format_room_summary, format_device_state, format_help,
)
from bot.telegram.keyboards import (
    rooms_keyboard, room_devices_keyboard, switch_control_keyboard, dimmer_control_keyboard,
)


def make_router(registry: DeviceRegistry, storage: Storage, chat_id: int) -> Router:
    router = Router()

    def _check_chat(msg_or_cb) -> bool:
        chat = msg_or_cb.chat if hasattr(msg_or_cb, "chat") else msg_or_cb.message.chat
        return chat.id == chat_id

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
        parts = []
        for room in rooms:
            devices = registry.get_devices(room)
            parts.append(format_room_summary(room, devices))
        await message.answer("\n\n".join(parts), parse_mode="HTML")

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

    @router.message(Command("notifications"))
    async def cmd_notifications(message: Message) -> None:
        if not _check_chat(message):
            return
        await _send_notification_settings(message)

    async def _send_notification_settings(message: Message) -> None:
        settings = await storage.get_notification_settings()
        if not settings:
            await message.answer("No notification history yet.")
            return
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        for entity_id, enabled in sorted(settings.items()):
            builder.button(
                text=f"{'[x]' if enabled else '[ ]'} {entity_id}",
                callback_data=f"notif:{entity_id}:{'off' if enabled else 'on'}",
            )
        builder.adjust(1)
        await message.answer("Notifications:", reply_markup=builder.as_markup())

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

    @router.callback_query(F.data.startswith("notif:"))
    async def cb_notif_toggle(callback: CallbackQuery) -> None:
        _, entity_id, action = callback.data.split(":", 2)
        enabled = action == "on"
        await storage.set_notification_enabled(entity_id, enabled)
        await callback.answer(f"{'Enabled' if enabled else 'Disabled'}: {entity_id}")
        await _send_notification_settings(callback.message)

    @router.callback_query(F.data == "back:rooms")
    async def cb_back_rooms(callback: CallbackQuery) -> None:
        rooms = registry.get_rooms()
        await callback.message.edit_text("Rooms:", reply_markup=rooms_keyboard(rooms))
        await callback.answer()

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
