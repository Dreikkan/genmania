"""Runtime configuration and stable constants for Gen Mania."""
from __future__ import annotations

import datetime
import os

DEFAULT_BOT_NAME = "Gen Mania"
DEFAULT_CURRENCY_COINS = "монеты"
DEFAULT_CURRENCY_GEMS = "гемы"
DEFAULT_START_COINS = 20
DEFAULT_TAX_RATE = 0.02
INCOME_HINT = (
    "Доход начисляется каждую секунду, в интерфейсе показан за час."
)

# Backups
BACKUP_INTERVAL_HOURS = float(os.getenv("BACKUP_INTERVAL_HOURS", "6"))
BACKUP_KEEP = int(os.getenv("BACKUP_KEEP", "10"))

# Schema / content migrations
SCHEMA_VERSION = 18
CONTENT_VERSION = 8

# Metrics / health
SLOW_DB_TX_MS = 100.0
HEALTH_WRITE_INTERVAL_SECONDS = 60
UTC = datetime.timezone.utc  # noqa: UP017 - совместимость с Python 3.10
