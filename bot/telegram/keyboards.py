from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.devices.models import Device


def rooms_keyboard(rooms: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for room in rooms:
        builder.button(text=room, callback_data=f"room:{room}")
    builder.adjust(2)
    return builder.as_markup()


def room_devices_keyboard(room: str, devices: list[Device]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    controllable = [d for d in devices if d.is_controllable]
    for d in controllable:
        builder.button(text=d.name, callback_data=f"device:{d.id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="<- Back", callback_data="back:rooms"))
    return builder.as_markup()


def switch_control_keyboard(device_id: str, room: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Vykl", callback_data=f"set:{device_id}:off")
    builder.button(text="Vkl", callback_data=f"set:{device_id}:on")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text=f"<- Back to {room}", callback_data=f"room:{room}"))
    return builder.as_markup()


def dimmer_control_keyboard(device_id: str, room: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Vykl", callback_data=f"set:{device_id}:off")
    for pct in (25, 50, 75, 100):
        builder.button(text=f"{pct}%", callback_data=f"dim:{device_id}:{pct}")
    builder.adjust(5)
    builder.row(InlineKeyboardButton(text=f"<- Back to {room}", callback_data=f"room:{room}"))
    return builder.as_markup()


def back_keyboard(callback_data: str, label: str = "<- Back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=callback_data)]])
