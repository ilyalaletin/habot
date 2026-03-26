from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.devices.models import Device


def rooms_keyboard(rooms: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for room in rooms:
        builder.button(text=room, callback_data=f"room:{room}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Menu", callback_data="bk:menu"))
    return builder.as_markup()


def room_devices_keyboard(room: str, devices: list[Device]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    controllable = [d for d in devices if d.is_controllable]
    for d in controllable:
        builder.button(text=d.name, callback_data=f"device:{d.id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="back:rooms"))
    return builder.as_markup()


def switch_control_keyboard(device_id: str, room: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔴 Выкл", callback_data=f"set:{device_id}:off")
    builder.button(text="🟢 Вкл", callback_data=f"set:{device_id}:on")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text=f"◀️ {room}", callback_data=f"room:{room}"))
    return builder.as_markup()


def dimmer_control_keyboard(device_id: str, room: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔴 Выкл", callback_data=f"set:{device_id}:off")
    for pct in (25, 50, 75, 100):
        builder.button(text=f"{pct}%", callback_data=f"dim:{device_id}:{pct}")
    builder.adjust(5)
    builder.row(InlineKeyboardButton(text=f"◀️ {room}", callback_data=f"room:{room}"))
    return builder.as_markup()


def back_keyboard(callback_data: str, label: str = "◀️ Back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=callback_data)]])


def settings_root_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👁 Visibility", callback_data="s:vis")
    builder.button(text="🔔 Notifications", callback_data="s:ntf")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Menu", callback_data="bk:menu"))
    return builder.as_markup()


def settings_rooms_keyboard(rooms: list[str], prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for idx, room in enumerate(rooms):
        builder.button(text=room, callback_data=f"{prefix}:r:{idx}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="bk:s"))
    return builder.as_markup()


def settings_devices_keyboard(
    groups: list[tuple[str, str, list]], room_idx: int, prefix: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for idx, (group_id, group_name, entities) in enumerate(groups):
        builder.button(text=group_name, callback_data=f"{prefix}:d:{room_idx}:{idx}")
    builder.adjust(2)
    back_target = "s:vis" if prefix == "sv" else "s:ntf"
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=back_target))
    return builder.as_markup()


def visibility_entities_keyboard(
    entities: list[Device], hidden: set[str], room_idx: int, group_idx: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ei, d in enumerate(entities):
        mark = "⬜" if d.id in hidden else "✅"
        builder.button(text=f"{mark} {d.name}", callback_data=f"sv:t:{room_idx}:{group_idx}:{ei}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"sv:r:{room_idx}"))
    return builder.as_markup()


def notification_entities_keyboard(
    entities: list[Device], room_idx: int, group_idx: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ei, d in enumerate(entities):
        builder.button(text=d.name, callback_data=f"sn:e:{room_idx}:{group_idx}:{ei}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"sn:r:{room_idx}"))
    return builder.as_markup()


def notification_rules_keyboard(
    rules: list[dict], room_idx: int, group_idx: int, ent_idx: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for rule in rules:
        hold = f", hold {rule['hold_minutes']}m" if rule["hold_minutes"] > 0 else ""
        label = f"❌ {rule['operator']} {rule['value']}{hold}"
        builder.button(text=label, callback_data=f"sn:x:{rule['id']}:{room_idx}:{group_idx}:{ent_idx}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="➕ Добавить правило", callback_data=f"sn:a:{room_idx}:{group_idx}:{ent_idx}"))
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"sn:d:{room_idx}:{group_idx}"))
    return builder.as_markup()


def menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    items = [
        ("🏠 Комнаты", "menu:rooms"),
        ("📊 Статус", "menu:status"),
        ("📋 Правила", "menu:rules"),
        ("⚙️ Настройки", "menu:settings"),
        ("❓ Помощь", "menu:help"),
    ]
    for text, cb in items:
        builder.button(text=text, callback_data=cb)
    builder.adjust(2)
    return builder.as_markup()


def rules_list_keyboard(
    rules: list[dict], entity_names: dict[str, str]
) -> InlineKeyboardMarkup | None:
    if not rules:
        return None
    builder = InlineKeyboardBuilder()
    for rule in rules:
        name = entity_names.get(rule["entity_id"], rule["entity_id"])
        hold = f", hold {rule['hold_minutes']}m" if rule["hold_minutes"] > 0 else ""
        label = f"❌ {name} {rule['operator']} {rule['value']}{hold}"
        builder.button(text=label, callback_data=f"rl:x:{rule['id']}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="◀️ Menu", callback_data="bk:menu"))
    return builder.as_markup()


def operator_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for op in (">", "<", ">=", "<=", "="):
        builder.button(text=op, callback_data=f"sn:o:{op}")
    builder.adjust(5)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="sn:cancel"))
    return builder.as_markup()
