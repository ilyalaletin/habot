# habot

Telegram bot for smart home control via Home Assistant and Wirenboard.

## Features

- Browse devices by room with inline buttons
- Control switches and dimmers
- Quick commands: /on, /off, /set, /status
- Real-time notifications from Home Assistant events
- Per-entity notification management (enable/disable)
- Wirenboard MQTT devices alongside HA devices

## Quick Start

1. Copy config:
   ```bash
   cp config.example.yaml config.yaml
   ```

2. Edit `config.yaml` with your settings (Telegram token, HA URL/token, MQTT host).

3. Create `.env` file:
   ```
   TELEGRAM_TOKEN=your_bot_token
   HA_TOKEN=your_ha_long_lived_token
   ```

4. Run:
   ```bash
   docker compose up -d
   ```

## Integration with Existing Docker Compose

If you already have Home Assistant and Wirenboard running in Docker, add habot to the same stack.

### Option A: Add to existing docker-compose.yml

Add the `habot` service to your existing `docker-compose.yml`:

```yaml
services:
  # ... your existing services (homeassistant, etc.)

  habot:
    build: /path/to/habot
    restart: unless-stopped
    volumes:
      - /path/to/habot/config.yaml:/app/config.yaml:ro
      - habot-data:/app/data
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - HA_TOKEN=${HA_TOKEN}
    networks:
      - default  # same network as HA and WB

volumes:
  habot-data:
```

In `config.yaml`, use Docker service names as hosts:

```yaml
homeassistant:
  url: "http://homeassistant:8123"  # Docker service name
mqtt:
  host: "wirenboard"  # or your MQTT broker service name
```

### Option B: Separate compose with shared network

If habot has its own `docker-compose.yml`, connect it to the existing network:

```yaml
services:
  habot:
    build: .
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - habot-data:/app/data
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - HA_TOKEN=${HA_TOKEN}
    networks:
      - ha-network

volumes:
  habot-data:

networks:
  ha-network:
    external: true
    name: homeassistant_default  # name of your HA network (check with: docker network ls)
```

Find your HA network name:
```bash
docker network ls | grep home
```

## Configuration

See `config.example.yaml` for all options. Environment variables `TELEGRAM_TOKEN` and `HA_TOKEN` override YAML values.

## Commands

| Command | Description |
|---------|-------------|
| /help | List all commands |
| /rooms | Browse rooms |
| /room <name> | Room summary |
| /on <name> | Turn on device |
| /off <name> | Turn off device |
| /set <name> <value> | Set value (dimmer: 0-100) |
| /status | Full summary |
| /notifications | Manage notifications |

## Supported Device Types (v1)

- **switch** -- on/off control
- **dimmer** -- brightness 0-100%
- **sensor** -- read-only (temperature, humidity, etc.)
