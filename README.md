# habot

Telegram-бот для управления умным домом через Home Assistant и Wirenboard.

## Возможности

- 🏠 Просмотр устройств по комнатам с inline-кнопками
- 💡 Управление выключателями и диммерами
- ⚡ Быстрые команды: /on, /off, /set, /status
- 🔔 Правила уведомлений с порогами (>, <, >=, <=, =) и таймерами удержания
- 👁 Настройки видимости (скрытие шумных сенсоров из статуса)
- 📊 Группировка сущностей по устройствам в выводе статуса
- 📋 Главное меню с inline-навигацией (/menu, /start)
- Wirenboard MQTT-устройства наравне с HA

## Быстрый старт

1. Создайте `config.yaml`:
   ```bash
   cp config.example.yaml config.yaml
   ```

2. Отредактируйте `config.yaml` (токен Telegram, URL/токен HA, хост MQTT).

3. Создайте `.env` файл:
   ```
   TELEGRAM_TOKEN=your_bot_token
   HA_TOKEN=your_ha_long_lived_token
   ```

4. Запуск:
   ```bash
   docker compose up -d
   ```

## Docker-образ

Готовый образ публикуется в GitHub Container Registry при каждом пуше в master.

```
ghcr.io/ilyalaletin/habot:latest
```

### Использование в docker-compose.yml

```yaml
services:
  habot:
    image: ghcr.io/ilyalaletin/habot:latest
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - habot-data:/app/data
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - HA_TOKEN=${HA_TOKEN}

volumes:
  habot-data:
```

### Обновление

```bash
docker compose pull && docker compose up -d
```

### Интеграция с существующим стеком

Если Home Assistant и Wirenboard уже работают в Docker, подключите habot к той же сети:

```yaml
services:
  habot:
    image: ghcr.io/ilyalaletin/habot:latest
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
    name: homeassistant_default  # имя сети HA (проверьте: docker network ls)
```

В `config.yaml` используйте имена Docker-сервисов:

```yaml
homeassistant:
  url: "http://homeassistant:8123"
mqtt:
  host: "wirenboard"
```

## Получение токенов

### Telegram Bot Token

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`
3. Задайте имя и username бота
4. Скопируйте токен вида `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

**Chat ID** — ID чата, в котором бот будет работать. Чтобы узнать:
1. Добавьте бота в нужный групповой чат
2. Отправьте любое сообщение в чат
3. Откройте `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Найдите `"chat":{"id":-100...}` — это ваш `chat_id`

### Home Assistant Token

1. Откройте Home Assistant → профиль пользователя (иконка внизу боковой панели)
2. Прокрутите вниз до раздела **Долгосрочные токены доступа**
3. Нажмите **Создать токен**, задайте имя (например, `habot`)
4. Скопируйте токен — он показывается только один раз

## Конфигурация

См. `config.example.yaml` для всех параметров. Переменные окружения `TELEGRAM_TOKEN`, `HA_TOKEN` и `NOTIFICATION_DEDUP_MINUTES` переопределяют значения из YAML.

## Команды

| Команда | Описание |
|---------|----------|
| /menu | 📋 Главное меню |
| /help | ❓ Список всех команд |
| /rooms | 🏠 Список комнат |
| /room <имя> | Статус комнаты |
| /on <имя> | Включить устройство |
| /off <имя> | Выключить устройство |
| /set <имя> <значение> | Установить значение (диммер: 0-100) |
| /status | 📊 Полный статус всех комнат |
| /rules | 📋 Правила уведомлений |
| /settings | ⚙️ Видимость и правила уведомлений |
| /cancel | Отменить текущую операцию |

## Поддерживаемые типы устройств

- **switch** — вкл/выкл
- **dimmer** — яркость 0-100%
- **sensor** — только чтение (температура, влажность и т.д.)
