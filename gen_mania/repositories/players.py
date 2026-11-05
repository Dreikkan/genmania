"""Player account repository.

Only account-level reads/writes live here. Domain services such as
combat, income and statuses stay in ``bot.py`` for now; they are reached
through runtime callbacks so monkeypatching on the imported bot module
keeps working.
"""
from __future__ import annotations

import logging
from typing import Any, Callable


class PlayerRuntime:
    """Адаптер между bot.py и репозиторием игроков."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self._settings_getter: Callable[[], Callable] = lambda: None
        self._status_bonus_getter: Callable[[], Callable] = lambda: None
        self.start_grid = 9
        self.storage_size = 36
        self.default_start_coins = 20
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        commit_getter: Callable[[], Callable],
        settings_getter: Callable[[], Callable],
        status_bonus_getter: Callable[[], Callable],
        start_grid: int,
        storage_size: int,
        default_start_coins: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._commit_getter = commit_getter
        self._settings_getter = settings_getter
        self._status_bonus_getter = status_bonus_getter
        self.start_grid = start_grid
        self.storage_size = storage_size
        self.default_start_coins = default_start_coins
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    async def commit(self) -> None:
        commit = self._commit_getter()
        if commit is not None:
            await commit()

    async def get_settings(self, guild_id: int) -> dict:
        getter = self._settings_getter()
        return await getter(guild_id)

    async def get_status_bonus(self, user_id: int) -> float:
        getter = self._status_bonus_getter()
        return await getter(user_id)


def make_player_layer(runtime: PlayerRuntime):
    """Возвращает account-функции игрока, привязанные к runtime."""

    async def is_accessibility_mode(user_id: int) -> bool:
        async with runtime.db.execute(
            "SELECT COALESCE(accessibility_mode, 0) "
            "FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        return bool(row[0]) if row else False

    async def toggle_accessibility_mode(user_id: int) -> bool:
        async with runtime.transaction():
            async with runtime.db.execute(
                "SELECT COALESCE(accessibility_mode, 0) "
                "FROM players WHERE user_id = ?",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            new_value = 0 if (row and row[0]) else 1
            await runtime.db.execute(
                "UPDATE players SET accessibility_mode = ? WHERE user_id = ?",
                (new_value, user_id),
            )
        return bool(new_value)

    async def get_player_stats(user_id: int, guild_id: int = None):
        async with runtime.db.execute(
            "SELECT grid_size, gems, coins FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()

        if not row:
            start = runtime.default_start_coins
            if guild_id:
                settings = await runtime.get_settings(guild_id)
                start = settings["start_coins"]
            await runtime.db.execute(
                "INSERT OR IGNORE INTO players "
                "(user_id, coins, grid_size, storage_size, "
                "last_gem_collected, last_tax_time) "
                "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (user_id, start, runtime.start_grid, runtime.storage_size),
            )
            await runtime.commit()
            return runtime.start_grid, 0.0, 0, start

        return (
            row[0] or runtime.start_grid,
            await runtime.get_status_bonus(user_id),
            row[1] or 0,
            row[2] or 0,
        )

    async def get_prestige_points(user_id: int) -> int:
        async with runtime.db.execute(
            "SELECT prestige_points FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        return (row[0] if row else 0) or 0

    return (
        is_accessibility_mode,
        toggle_accessibility_mode,
        get_player_stats,
        get_prestige_points,
    )
