# Gen Mania

Discord-бот **Gen Mania** — incremental idle/management игра: генераторы,
синтез, звёзды, коллекция, биржа, аукцион, банк, кланы, PvP, питомцы,
статусы, сезон/battle pass, квесты, дейли, адвент, престиж и розыгрыши.

## Что внутри

- `bot.py` — основной монолит бота (discord.py 2.x + aiosqlite).
- `gen_mania/` — вынесенные модули: `config.py` (runtime-константы),
  `metrics.py` (in-process метрики), `db/transaction.py`
  (managed SQLite-транзакции), `repositories/audit.py`
  (журнал админ-действий), `repositories/settings.py`
  (настройки гильдий), `repositories/players.py`
  (аккаунты игроков и разблокировка титулов),
  `repositories/inventory.py` (инвентарь, слоты, размещение и почта),
  `repositories/market.py` (история цен), `services/market.py`
  (чистые функции цен), `services/market_orders.py` (ордера и
  buy/sell), `services/seasons.py` (сезон и battle pass), `services/pets.py`
  (питомцы и автоколлектор), `services/statuses.py` (статусы),
  `services/clan_applications.py` (заявки в клан),
  `services/notifications.py` (уведомления),
  `services/content.py` (контент-редактор),
  `services/profile_ui.py` (статистика синтеза, профиль, энергостанция
  и публичная карточка),
  `services/shop_ui.py` (магазин, достижения, коллекция),
  `services/upgrades_ui.py` (улучшения, питомцы, автосборщик),
  `services/analytics_ui.py` (аналитика профиля),
  `services/admin_ui.py` (админ-карточки), `services/auction.py` (ставки, выкуп,
  история), `services/bank.py` (кредиты и вклады), `services/pvp.py`
  (дуэли и кулдауны), `repositories/clans.py` (кланы и войны), `repositories/raids.py`
  (отряды и кулдауны), `services/giveaways.py` (награды и участие),
  `services/progress.py` (квесты, достижения, дейлики),
  `services/leaderboards.py` (топы и кэш),
  `services/raid_combat.py` (бой и завершение рейдов),
  `services/top_exclusion.py` (исключение из топов),
  `services/prestige.py` (престиж), `services/clan_wars.py`
  (клановые войны) и `services/taxes.py` (налоговые ставки).
  `bot.py` реэкспортирует их для обратной совместимости.
- `tests/` — pytest-набор: экономика, банк, биржа, аукцион, PvP,
  кланы, сезоны, розыгрыши, миграции, транзакции, UI-смоуки.
- `dev/` — локальный dev-стенд: запуск отдельного тестового бота с
  изолированной папкой `data`, проверка токена, БД и live-smoke.
- `CHANGELOG.md` — краткая история изменений.
- `.github/workflows/ci.yml` — pytest + обязательный ruff-профиль.

## Требования

- Python **3.10+** (проверялось на 3.14).
- `discord.py>=2.4`
- `aiosqlite>=0.20`
- В Discord Developer Portal включён **Server Members Intent**
  (нужен для локальных топов, налогов и состава участников).

## Быстрый старт

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:DISCORD_BOT_TOKEN="your_token"
$env:DATA_DIR="$PWD\data"
python bot.py
```

`DATA_DIR` — постоянная папка для `castle.db`, бэкапов и `bot.log`.
Не коммить `.env`, базу и бэкапы.

## Деплой на Bothost

Загружать нужно **и `bot.py`, и пакет `gen_mania/`**.
В корне лежит `bothost.json`:

```json
{
  "main": "bot.py",
  "language": "python",
  "python_version": "3.11"
}
```

Для Git-деплоя подключите репозиторий к Bothost и выберите ветку `main`.
Для загрузки архивом положите в `.zip`/`.tar.gz`:

- `bot.py`;
- `gen_mania/`;
- `requirements.txt`;
- `bothost.json`.

Не включайте в архив `.git/`, `tests/`, `dev/data/`, `__pycache__/`,
`bot_backup_*.py` и `bot_changes_*.diff`.
В Bothost задайте `DATA_DIR=/app/data` и `DISCORD_BOT_TOKEN`.
База и бэкапы должны оставаться в `/app/data`, иначе они потеряются
при перезапуске.

## Dev-стенд

Инструкция: [`dev/README_DEV.md`](dev/README_DEV.md).

Коротко:

```powershell
python dev\run_dev.py --check --probe
python dev\start_dev.py      # detached-фон
python dev\status_dev.py
python dev\stop_dev.py
```

Dev-стенд использует отдельный токен и `DATA_DIR=dev/data`,
поэтому production-бота и production-базу не затрагивает.
`dev/.env` и `dev/data/` исключены через `.gitignore`.

## Тесты

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
python -m pytest -q --cov=. --cov-report=term:skip-covered --cov-fail-under=50
ruff check --select F821,F811,F401 bot.py tests gen_mania
```

Текущий статус: **245 passed**, 67 test files.  
Coverage `bot.py`: **57.82%**, минимальный порог — **50%**.

Для мониторинга: `data/health.json` обновляется раз в 60 секунд,
owner-only команда `/health` показывает метрики и состояние задач.

## CI

GitHub Actions запускает на Windows:

- `python -m py_compile bot.py`;
- `pytest -q`;
- `ruff check --select F821,F811,F401 bot.py tests gen_mania`.

## Безопасность

- Никогда не коммить `DISCORD_BOT_TOKEN`, `.env`, `castle.db`,
  `*.db-wal`, `dev/data/` и `bot_backup_*.py`.
- Для dev-стенда используй отдельное тестовое Discord-приложение.
- Не запускай два процесса с одним токеном одновременно.
