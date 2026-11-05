# Gen Mania — локальный dev-стенд

Цель: запускать бота для live-проверок, не трогая production-бота и
production-базу.

## Что изолировано

- **Токен** — только в `dev/.env`, не в коде и не в git.
- **База** — `dev/data/castle.db` (локальная копия; не коммитится).
- **Логи и бэкапы** — `dev/data/bot.log`, `dev/data/backups/`.
- `run_dev.py` принудительно выставляет `DATA_DIR=dev/data`, поэтому
  бот не откроет `/app/data` и не запишет в production.

## Шаг 1. Тестовое приложение

1. Открой https://discord.com/developers/applications
2. Создай отдельное приложение, например `Gen Mania Dev`.
3. `Bot` -> `Reset Token` -> скопируй токен.
4. В `Privileged Gateway Intents` включи **Server Members Intent**.
5. `OAuth2` -> `URL Generator`:
   - scopes: `bot`, `applications.commands`;
   - permissions: `Administrator` (только для тестового сервера).
6. Пригласи тестового бота на отдельный тестовый сервер.

## Шаг 2. Токен

Открой `dev/.env` и замени:

```env
DISCORD_BOT_TOKEN=your_dev_bot_token
```

на токен тестового приложения. Не отправляй токен в чат и не коммить.

## Шаг 3. Проверка

```powershell
# из корня репозитория
python dev\run_dev.py --check --probe
```

`--probe` покажет имя бота, список серверов и глобальные
slash-команды. Сам токен не выводится.

## Шаг 4. Запуск

В отдельном терминале (foreground):

```powershell
python dev\run_dev.py
```

Или в detached-фоне (процесс переживает закрытие терминала):

```powershell
python dev\start_dev.py
```

Остановка — `Ctrl+C` для foreground или:

```powershell
python dev\status_dev.py
python dev\stop_dev.py
```

`status_dev.py` показывает PID, хвост `bot.log` и состояние базы.
`stop_dev.py` останавливает только dev-бота по PID из
`dev/data/dev_bot.pid`.

## Шаг 5. Live smoke-тест

```powershell
python dev\live_smoke.py
```

Отправляет одно тестовое сообщение в первый текстовый канал
тестового сервера. Это проверяет, что бот видит каналы и имеет
право писать.

## Шаг 6. Кастомные эмодзи

Один раз после создания тестового приложения:

```powershell
python dev\upload_emojis.py
```

Скрипт скачивает эмодзи по ID из production-кода с CDN и
загружает их в тестовое приложение. После этого перезапусти
бота — он подхватит эмодзи по именам.

## Важно

- **Не запускай два процесса с одним токеном.** Если использовать
  production-токен, сначала останови production-бота.
- Лучше отдельное тестовое приложение: тогда production продолжает
  работать, а dev-бот живёт на тестовом сервере.
- Если нужна свежая копия production-базы, положи её в
  `dev/data/castle.db` при остановленном боте.
- Для проверки базы:

```powershell
python dev\check_db.py
```
