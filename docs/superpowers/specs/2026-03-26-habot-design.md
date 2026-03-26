# habot — Telegram-бот для управления умным домом

## Обзор

Telegram-бот для управления умным домом через два бэкенда:
- **Home Assistant** — REST API + WebSocket (основной источник устройств и событий)
- **Wirenboard** — MQTT (устройства, которых нет в HA)

Бот работает в групповом чате Telegram. Все участники чата могут управлять устройствами без разграничения прав. Авторизация по chat_id группы.

## Стек

- Python 3.12
- aiogram 3.x — Telegram Bot API
- aiomqtt 2.x — MQTT-клиент для Wirenboard
- aiohttp 3.x — HTTP/WebSocket-клиент для Home Assistant
- aiosqlite 0.20+ — async SQLite
- pydantic 2.x — валидация конфига и моделей
- pyyaml 6.x — парсинг конфигурации

## Архитектура

Async-монолит с единым event loop. Один процесс, один Docker-контейнер.

### Компоненты

```
Telegram handler -> DeviceRegistry -> HA Client (REST) или WB Client (MQTT publish)
HA WebSocket / MQTT subscribe -> DeviceRegistry (обновляет state) -> Notification -> Telegram
```

- **Telegram handlers** — обработка команд и inline-кнопок, делегирует всё в DeviceRegistry
- **DeviceRegistry** — единый реестр устройств из обоих источников, Telegram-хендлеры не знают деталей протоколов
- **HA Client** — REST API для чтения устройств и отправки команд (`POST /api/services/<domain>/<service>`)
- **HA WebSocket** — подписка на `state_changed` события, обновление состояний в реестре + пересылка уведомлений в Telegram. Переподключение с exponential backoff при обрыве связи. После переподключения — полный рефетч состояний через REST API для синхронизации реестра
- **WB Client** — MQTT-подписка на топики устройств из конфига, публикация команд. Переподключение с exponential backoff при обрыве связи. Изменения состояний WB-устройств обновляют реестр, но уведомления в Telegram — только от HA (WB-устройства, для которых нужны уведомления, должны быть добавлены в HA)
- **Storage** — SQLite для настроек уведомлений и истории

### Структура проекта

```
habot/
├── bot/
│   ├── __init__.py
│   ├── main.py              # точка входа, запуск всех компонентов
│   ├── config.py            # загрузка YAML-конфига + валидация
│   ├── telegram/
│   │   ├── handlers.py      # обработчики команд и callback-кнопок
│   │   ├── keyboards.py     # генерация inline-клавиатур
│   │   └── formatters.py    # форматирование сводок/статусов в текст
│   ├── homeassistant/
│   │   ├── client.py        # REST API клиент (устройства, команды)
│   │   └── websocket.py     # WebSocket подписка на события (уведомления)
│   ├── wirenboard/
│   │   └── client.py        # MQTT клиент (подписка + публикация)
│   ├── devices/
│   │   ├── registry.py      # единый реестр устройств (HA + WB)
│   │   └── models.py        # модели: Device, Room, DeviceState
│   └── storage/
│       └── db.py            # SQLite: настройки уведомлений, история
├── config.example.yaml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
└── tests/
```

## Конфигурация

Один YAML-файл. Секреты можно переопределить через env-переменные (`TELEGRAM_TOKEN`, `HA_TOKEN`) — приоритет над YAML.

```yaml
telegram:
  token: "BOT_TOKEN"
  chat_id: -1001234567890

homeassistant:
  url: "http://192.168.1.10:8123"
  token: "HA_LONG_LIVED_TOKEN"

mqtt:
  host: "192.168.1.20"
  port: 1883

wirenboard:
  devices:
    - id: "wb-mr6c_1"
      name: "Реле коридор"
      room: "Коридор"
      type: "switch"
      topic: "/devices/wb-mr6c_1/controls/K1"
    - id: "wb-msw3_temp"
      name: "Температура серверная"
      room: "Серверная"
      type: "sensor"
      topic: "/devices/wb-msw-v3_1/controls/Temperature"
      unit: "°C"

database:
  path: "./data/habot.db"
  history_retention_days: 30   # автоочистка истории уведомлений
```

HA-устройства и комнаты (areas) подтягиваются автоматически через API, в конфиге не дублируются. WB-устройства описываются вручную: id, имя, комната, тип, MQTT-топик.

## Модели данных

```python
@dataclass
class Device:
    id: str                    # уникальный ID (ha:light.kitchen или wb:wb-mr6c_1)
    name: str
    room: str
    type: str                  # switch, dimmer, sensor, cover, climate...
    source: str                # "ha" или "wb"
    state: str | None          # "on", "off", "23.5", ...
    unit: str | None           # "°C", "%", "W", ...
    attributes: dict           # доп. данные (яркость, цвет и т.д.)
```

### DeviceRegistry

- При старте загружает устройства из HA API (rooms/areas + devices + states) и из конфига (WB-устройства)
- Объединяет в единый список, группирует по комнатам
- Методы:
  - `get_rooms() -> list[str]`
  - `get_devices(room: str) -> list[Device]`
  - `get_device(id: str) -> Device`
  - `set_state(id: str, state: str, **attrs) -> None` — для switch: `"on"/"off"`, для dimmer: `"0".."100"` (процент яркости как строка), для climate: `"23.5"` (целевая температура). Дополнительные атрибуты передаются через `**attrs`
- `set_state()` делегирует в HA Client или WB MQTT Client в зависимости от `source`
- Состояния обновляются в реальном времени через HA WebSocket и MQTT-подписку

## UI в Telegram

### Inline-кнопки (основная навигация)

```
/start или /rooms
-> [Кухня] [Спальня] [Коридор] [Серверная]

Нажал "Кухня"
-> Кухня
  Свет потолок — ВКЛ
  Температура — 23.5°C
  Влажность — 45%
  [Свет потолок] [Свет подсветка] [<- Назад]

Нажал "Свет потолок"
-> Свет потолок: ВКЛ
  [Выкл] [Вкл]
  [<- Назад к Кухня]

Для диммера:
-> Диммер коридор: 70%
  [Выкл] [25%] [50%] [75%] [100%]
  [<- Назад]
```

### Быстрые команды

| Команда | Описание |
|---------|----------|
| `/help` | Список всех команд с описанием |
| `/rooms` | Список комнат (кнопки) |
| `/room <имя>` | Сводка по комнате |
| `/on <имя>` | Включить (поиск по подстроке имени, при неоднозначности — список кнопок) |
| `/off <имя>` | Выключить (аналогично) |
| `/set <имя> <значение>` | Установить значение (диммер: 0-100, аналогичный поиск) |
| `/status` | Общая сводка по всем комнатам |
| `/notifications` | Управление уведомлениями (вкл/выкл) |

## Уведомления

### Источник событий

Бот подключается к HA WebSocket API и подписывается на событие `state_changed`. Когда HA отправляет событие, бот:

1. Получает payload с `entity_id`, `old_state`, `new_state`
2. Проверяет в SQLite, не отключено ли уведомление для этого `entity_id`
3. Если включено — форматирует сообщение и отправляет в групповой чат

Бот **не** определяет пороги и не фильтрует события по значениям — это ответственность автоматизаций Home Assistant. HA решает, какие события генерировать, бот только доставляет. Примеры сообщений в чат (текст формируется из `new_state` и `friendly_name`):

```
Протечка — Ванная
Дверь открыта — Входная
Температура серверная: 38°C
```

### Управление уведомлениями

`/notifications` показывает список entity_id, для которых приходили уведомления, с inline-кнопками вкл/выкл для каждого. Гранулярность — per-entity (по конкретному устройству/сенсору). Это позволяет отключить "шумные" устройства, не затрагивая остальные.

## Storage (SQLite)

```sql
-- Настройки уведомлений per-entity
CREATE TABLE notification_settings (
    id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL UNIQUE,  -- "ha:binary_sensor.door_front" и т.д.
    enabled INTEGER DEFAULT 1        -- 1 = вкл, 0 = выкл
);

-- История уведомлений для дебага и /notifications UI
CREATE TABLE notification_history (
    id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- По умолчанию все уведомления включены (если записи нет в таблице — считаем enabled)
- `/notifications` собирает список entity_id из `notification_history` + `notification_settings` и показывает toggle-кнопки
- Автоочистка истории старше N дней (настраивается в конфиге, см. `database.history_retention_days`, по умолчанию 30)

## Docker

```yaml
# docker-compose.yml
services:
  habot:
    build: .
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/app/data
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - HA_TOKEN=${HA_TOKEN}
```

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot/ bot/
CMD ["python", "-m", "bot.main"]
```

## README

README.md должен содержать:

1. **Описание проекта** — что делает бот, краткий список возможностей
2. **Быстрый старт** — как запустить standalone (`docker compose up`)
3. **Интеграция в существующий стек** — пошаговая инструкция:
   - Как добавить сервис `habot` в существующий `docker-compose.yml` рядом с Home Assistant и Wirenboard
   - Настройка сети: подключение к той же Docker-сети, где работают HA и WB (пример с `networks:`)
   - Настройка volumes для конфига и SQLite
   - Пример `.env` файла с секретами
4. **Конфигурация** — описание полей `config.yaml`
5. **Команды бота** — таблица доступных команд

### Поддерживаемые типы устройств (v1)

В первой версии поддерживаются: `switch` (вкл/выкл), `dimmer` (яркость 0-100%), `sensor` (только чтение). Типы `cover` и `climate` — вне скоупа v1, могут быть добавлены позже.
