from html import escape

from bot.devices.models import Device


def _state_emoji(state: str | None) -> str:
    if state in ("on",):
        return "🟢"
    if state in ("off",):
        return "🔴"
    return "⚪"


def format_device_state(device: Device) -> str:
    if device.type == "sensor":
        unit = f" {device.unit}" if device.unit else ""
        return f"📊 {device.name} — {device.state}{unit}"
    elif device.type == "dimmer":
        if device.state == "off":
            return f"🔴 {device.name} — выкл"
        brightness = device.attributes.get("brightness")
        if brightness is not None:
            pct = round(brightness / 255 * 100)
            return f"🟢 {device.name} — вкл ({pct}%)"
        return f"🟢 {device.name} — вкл"
    else:
        if device.state == "on":
            return f"🟢 {device.name} — вкл"
        elif device.state == "off":
            return f"🔴 {device.name} — выкл"
        return f"⚪ {device.name} — {device.state or '?'}"


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
