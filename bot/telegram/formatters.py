from html import escape

from bot.devices.models import Device


def _state_emoji(state: str | None) -> str:
    if state in ("on",):
        return "🟢"
    if state in ("off",):
        return "🔴"
    return "⚪"


def _short_name(device: Device, group_name: str | None) -> str:
    """Strip group/device name prefix from entity name to avoid duplication."""
    name = device.name
    if group_name and name.startswith(group_name):
        short = name[len(group_name):].lstrip(" -–—")
        if short:
            return short
    return name


def format_device_state(device: Device, group_name: str | None = None) -> str:
    name = _short_name(device, group_name) if group_name else device.name
    if device.type == "sensor":
        unit = f" {device.unit}" if device.unit else ""
        state = device.state
        if state == "on":
            state = "вкл"
        elif state == "off":
            state = "выкл"
        return f"📊 {name} — {state}{unit}"
    elif device.type == "dimmer":
        if device.state == "off":
            return f"🔴 {name} — выкл"
        brightness = device.attributes.get("brightness")
        if brightness is not None:
            pct = round(brightness / 255 * 100)
            return f"🟢 {name} — вкл ({pct}%)"
        return f"🟢 {name} — вкл"
    else:
        if device.state == "on":
            return f"🟢 {name} — вкл"
        elif device.state == "off":
            return f"🔴 {name} — выкл"
        return f"⚪ {name} — {device.state or '?'}"


def format_room_summary(
    room: str,
    devices: list[Device] | None = None,
    groups: list[tuple[str, str, list[Device]]] | None = None,
) -> str:
    lines = [f"<b>{room}</b>"]
    if groups is not None:
        for gid, gname, entities in groups:
            lines.append("")
            is_solo = gid.startswith("_solo:")
            if not is_solo:
                lines.append(f"<b>{gname}</b>")
            for d in entities:
                text = format_device_state(d, group_name=gname if not is_solo else None)
                lines.append(f"  {text}" if not is_solo else text)
    elif devices is not None:
        lines.append("")
        for d in devices:
            lines.append(format_device_state(d))
    return "\n".join(lines)


def format_notification(entity_id: str, friendly_name: str, old_state: str, new_state: str) -> str:
    return f"🔔 {friendly_name}: {old_state} → {new_state}"


def format_help() -> str:
    commands = [
        ("/menu", "Главное меню"),
        ("/help", "Список всех команд"),
        ("/rooms", "Список комнат"),
        ("/room &lt;имя&gt;", "Статус комнаты"),
        ("/on &lt;имя&gt;", "Включить устройство"),
        ("/off &lt;имя&gt;", "Выключить устройство"),
        ("/set &lt;имя&gt; &lt;значение&gt;", "Установить значение (диммер: 0-100)"),
        ("/status", "Полный статус всех комнат"),
        ("/rules", "Правила уведомлений"),
        ("/settings", "Видимость и правила уведомлений"),
        ("/cancel", "Отменить текущую операцию"),
    ]
    lines = ["<b>📋 Доступные команды:</b>", ""]
    for cmd, desc in commands:
        lines.append(f"<code>{cmd}</code> — {desc}")
    return "\n".join(lines)
