"""Guild settings repository.

The module is deliberately decoupled from ``bot.py``. ``bot.py`` creates a
``SettingsRuntime``, binds getters to its own globals and receives bound
functions back. This keeps tests that replace ``bot.db``, caches or
``get_settings`` working exactly as before.
"""
from __future__ import annotations

import copy
import datetime
import json
import logging
from typing import Any, Callable

SETTING_COLUMNS = {
    "bot_name": "bot_name",
    "custom_emojis": "custom_emojis",
    "currency_coins": "currency_coins",
    "currency_gems": "currency_gems",
    "prefix": "prefix",
    "start_coins": "start_coins",
    "disabled_commands": "disabled_commands",
    "status_roles": "status_roles",
    "battlepass_enabled": "battlepass_enabled",
    "admin_role_id": "admin_role_id",
    "tax_rate": "tax_rate",
}


class SettingsRuntime:
    """Адаптер между bot.py и репозиторием настроек."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self._actor_id_getter: Callable[[], Any] = lambda: None
        self._audit_getter: Callable[[], Callable] = lambda: None
        self._settings_cache_getter: Callable[[], dict] = lambda: {}
        self._tax_cache_getter: Callable[[], dict] = lambda: {}
        self.settings_ttl = 30.0
        self.defaults: dict[str, Any] = {}
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        commit_getter: Callable[[], Callable],
        actor_id_getter: Callable[[], Any],
        audit_getter: Callable[[], Callable],
        settings_cache_getter: Callable[[], dict],
        tax_cache_getter: Callable[[], dict],
        settings_ttl: float,
        defaults: dict,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._commit_getter = commit_getter
        self._actor_id_getter = actor_id_getter
        self._audit_getter = audit_getter
        self._settings_cache_getter = settings_cache_getter
        self._tax_cache_getter = tax_cache_getter
        self.settings_ttl = settings_ttl
        self.defaults = defaults
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    @property
    def settings_cache(self) -> dict:
        return self._settings_cache_getter()

    @property
    def tax_cache(self) -> dict:
        return self._tax_cache_getter()

    async def commit(self) -> None:
        commit = self._commit_getter()
        if commit is not None:
            await commit()

    def actor_id(self):
        return self._actor_id_getter()

    async def log_admin_action(self, *args, **kwargs) -> None:
        audit = self._audit_getter()
        if audit is not None:
            await audit(*args, **kwargs)


def make_settings_layer(runtime: SettingsRuntime):
    """Возвращает пару ``get_settings`` / ``save_setting``."""

    def _json_load(raw, fallback):
        if not raw:
            return copy.deepcopy(fallback)
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            runtime.logger.warning("Повреждён JSON настройки: %r", raw)
            return copy.deepcopy(fallback)

    async def get_settings(guild_id: int) -> dict:
        defaults = runtime.defaults
        if not guild_id:
            return copy.deepcopy(defaults)

        now_ts = datetime.datetime.now().timestamp()
        cached = runtime.settings_cache.get(guild_id)
        if cached and (now_ts - cached[0]) < runtime.settings_ttl:
            return copy.deepcopy(cached[1])

        async with runtime.db.execute(
            """
            SELECT bot_name, custom_emojis, currency_coins, currency_gems,
                   prefix, start_coins, disabled_commands, status_roles,
                   battlepass_enabled, admin_role_id, tax_rate
            FROM guild_settings WHERE guild_id = ?
            """,
            (guild_id,),
        ) as c:
            row = await c.fetchone()

        if not row:
            return copy.deepcopy(defaults)

        result = {
            "bot_name": row[0] or defaults["bot_name"],
            "custom_emojis": _json_load(row[1], {}),
            "currency_coins": row[2] or defaults["currency_coins"],
            "currency_gems": row[3] or defaults["currency_gems"],
            "prefix": row[4] or "/",
            "start_coins": (
                row[5] if row[5] is not None else defaults["start_coins"]
            ),
            "disabled_commands": _json_load(row[6], []),
            "status_roles": _json_load(row[7], {}),
            "battlepass_enabled": bool(row[8]) if row[8] is not None else True,
            "admin_role_id": row[9],
            "tax_rate": row[10] if row[10] is not None else defaults["tax_rate"],
        }
        runtime.settings_cache[guild_id] = (now_ts, result)
        return copy.deepcopy(result)

    async def save_setting(
        guild_id: int,
        key: str,
        value,
        actor_id: int | None = None,
    ):
        column = SETTING_COLUMNS.get(key)
        if not column:
            runtime.logger.warning("Неизвестный ключ настройки: %s", key)
            return
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        await runtime.db.execute(
            "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
            (guild_id,),
        )
        await runtime.db.execute(
            f"UPDATE guild_settings SET {column} = ? WHERE guild_id = ?",
            (value, guild_id),
        )
        await runtime.commit()
        runtime.settings_cache.pop(guild_id, None)
        if key == "tax_rate":
            runtime.tax_cache.clear()

        actor_id = actor_id or runtime.actor_id()
        if actor_id:
            rendered = str(value)
            if len(rendered) > 200:
                rendered = rendered[:197] + "..."
            await runtime.log_admin_action(
                actor_id,
                0,
                "setting_change",
                f"{key}={rendered}",
                guild_id=guild_id,
            )

    return get_settings, save_setting
