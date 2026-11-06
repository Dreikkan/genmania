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
        self._clan_getter: Callable[[], Callable] = lambda: None
        self._collection_count_getter: Callable[[], Callable] = lambda: None
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
        clan_getter: Callable[[], Callable],
        collection_count_getter: Callable[[], Callable],
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
        self._clan_getter = clan_getter
        self._collection_count_getter = collection_count_getter
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

    async def get_clan(self, user_id: int):
        getter = self._clan_getter()
        return await getter(user_id)

    async def get_collection_count(self, user_id: int) -> int:
        getter = self._collection_count_getter()
        return await getter(user_id)

    async def get_prestige_points(self, user_id: int) -> int:
        async with self.db.execute(
            "SELECT prestige_points FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        return (row[0] if row else 0) or 0


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

    async def get_unlocked_titles(user_id: int) -> set:
        async with runtime.db.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM inventory
                 WHERE user_id = ? AND location = 'profile') AS gens,
                (SELECT COUNT(*) FROM inventory
                 WHERE user_id = ? AND location = 'profile'
                 AND stars >= 5) AS five_star,
                (SELECT COUNT(DISTINCT item_id) FROM inventory
                 WHERE user_id = ? AND location = 'profile')
                 AS distinct_gens,
                (SELECT total_crafts FROM players
                 WHERE user_id = ?) AS crafts,
                (SELECT coins FROM players
                 WHERE user_id = ?) AS coins,
                (SELECT gems FROM players
                 WHERE user_id = ?) AS gems,
                (SELECT grid_size FROM players
                 WHERE user_id = ?) AS grid_size
            """,
            (user_id,) * 7,
        ) as c:
            row = await c.fetchone()
        (
            gens,
            five_star,
            _distinct_gens,
            crafts,
            coins,
            gems,
            grid_size,
        ) = row or (0,) * 7

        async with runtime.db.execute(
            "SELECT raid_wins FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            raid_row = await c.fetchone()
        raid_wins = (raid_row[0] if raid_row else 0) or 0

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM duel_history WHERE winner_id = ?",
            (user_id,),
        ) as c:
            duel_wins = (await c.fetchone())[0] or 0

        async with runtime.db.execute(
            "SELECT COUNT(*), MAX(level) FROM user_pets_v2 "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            pet_count, pet_max_level = await c.fetchone()
        pet_count = pet_count or 0
        pet_max_level = pet_max_level or 0

        clan = await runtime.get_clan(user_id)
        is_clan_leader = bool(clan and clan[2] == user_id)
        async with runtime.db.execute(
            "SELECT COUNT(*) FROM clan_wars WHERE winner_id = ?",
            (clan[0] if clan else -1,),
        ) as c:
            clan_wars_won = (await c.fetchone())[0] or 0

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM bank_history WHERE user_id = ? "
            "AND COALESCE(kind, 'deposit') = 'deposit'",
            (user_id,),
        ) as c:
            bank_deposits = (await c.fetchone())[0] or 0

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM tax_log WHERE user_id = ?",
            (user_id,),
        ) as c:
            tax_count = (await c.fetchone())[0] or 0

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM auctions WHERE seller_id = ?",
            (user_id,),
        ) as c:
            auction_sold = (await c.fetchone())[0] or 0
        async with runtime.db.execute(
            "SELECT COUNT(*) FROM auctions "
            "WHERE current_bidder = ? AND status = 'finished'",
            (user_id,),
        ) as c:
            auction_bought = (await c.fetchone())[0] or 0

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM player_quests "
            "WHERE user_id = ? AND completed = 1",
            (user_id,),
        ) as c:
            story_done = (await c.fetchone())[0] or 0

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM player_achievements "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            ach_count = (await c.fetchone())[0] or 0

        prestige_points = await runtime.get_prestige_points(user_id)
        collection_count = await runtime.get_collection_count(user_id)

        unlocked = {"novice"}
        if gens >= 10:
            unlocked.add("builder")
        if crafts >= 10:
            unlocked.add("alchemist")
        if five_star >= 1:
            unlocked.add("star_lord")
        if coins >= 10000:
            unlocked.add("rich")
        if raid_wins >= 5:
            unlocked.add("raider")
        if duel_wins >= 10:
            unlocked.add("duelist")
        if collection_count >= 20:
            unlocked.add("collector")
        if pet_count >= 3:
            unlocked.add("pet_lover")
        if pet_max_level >= 10:
            unlocked.add("pet_master")
        if is_clan_leader:
            unlocked.add("clan_leader")
        if clan_wars_won >= 1:
            unlocked.add("clan_warrior")
        if bank_deposits >= 1:
            unlocked.add("banker")
        if tax_count >= 3:
            unlocked.add("taxpayer")
        if auction_sold >= 1:
            unlocked.add("auctioneer")
        if auction_bought >= 1:
            unlocked.add("trader")
        if gems >= 100:
            unlocked.add("gem_master")
        if story_done >= 5:
            unlocked.add("quest_hero")
        if ach_count >= 10:
            unlocked.add("ach_hunter")
        if grid_size >= 100:
            unlocked.add("grid_master")
        if prestige_points >= 1:
            unlocked.add("ascended")

        return unlocked

    return (
        is_accessibility_mode,
        toggle_accessibility_mode,
        get_player_stats,
        get_prestige_points,
        get_unlocked_titles,
    )
