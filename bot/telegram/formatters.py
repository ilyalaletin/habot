from html import escape

from bot.devices.models import Device


def format_device_state(device: Device) -> str:
    if device.type == "sensor":
        unit = f" {device.unit}" if device.unit else ""
        return f"{device.name} -- {device.state}{unit}"
    elif device.type == "dimmer":
        if device.state == "off":
            return f"{device.name} -- VYKL"
        brightness = device.attributes.get("brightness")
        if brightness is not None:
            pct = round(brightness / 255 * 100)
            return f"{device.name} -- VKL ({pct}%)"
        return f"{device.name} -- VKL"
    else:
        state_text = "VKL" if device.state == "on" else "VYKL"
        return f"{device.name} -- {state_text}"


def format_room_summary(room: str, devices: list[Device]) -> str:
    lines = [f"<b>{room}</b>", ""]
    for d in devices:
        lines.append(format_device_state(d))
    return "\n".join(lines)


def format_notification(entity_id: str, friendly_name: str, old_state: str, new_state: str) -> str:
    return f"{friendly_name}: {old_state} -> {new_state}"


def format_help() -> str:
    commands = [
        ("/help", "List of all commands"),
        ("/rooms", "List rooms"),
        ("/room &lt;name&gt;", "Room summary"),
        ("/on &lt;name&gt;", "Turn on device"),
        ("/off &lt;name&gt;", "Turn off device"),
        ("/set &lt;name&gt; &lt;value&gt;", "Set value (dimmer: 0-100)"),
        ("/status", "Full summary of all rooms"),
        ("/notifications", "Manage notifications (on/off)"),
    ]
    lines = ["<b>Available commands:</b>", ""]
    for cmd, desc in commands:
        lines.append(f"<code>{cmd}</code> — {desc}")
    return "\n".join(lines)
