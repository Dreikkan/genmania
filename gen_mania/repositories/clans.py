"""Clan repository: clan reads, capacity, level and log."""
from __future__ import annotations

import logging
from typing import Any, Callable


class ClanRuntime:
    """Адаптер между bot.py и репозиторием кланов."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self.base_capacity = 10
        self.capacity_step = 5
        self.capacity_cost = 1000
        self.max_level = 21
        self.xp_per_level = 100
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        base_capacity: int,
        capacity_step: int,
        capacity_cost: int,
        max_level: int,
        xp_per_level: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self.base_capacity = base_capacity
        self.capacity_step = capacity_step
        self.capacity_cost = capacity_cost
        self.max_level = max_level
        self.xp_per_level = xp_per_level
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()


def make_clan_layer(runtime: ClanRuntime):
    """Возвращает clan-функции, привязанные к runtime."""

    async def get_clan(user_id: int):
        async with runtime.db.execute(
            "SELECT c.* FROM clans c JOIN clan_members cm "
            "ON c.id = cm.clan_id WHERE cm.user_id = ?",
            (user_id,),
        ) as c:
            return await c.fetchone()

    async def get_clan_members(clan_id: int):
        async with runtime.db.execute(
            "SELECT user_id, role FROM clan_members WHERE clan_id = ?",
            (clan_id,),
        ) as c:
            return await c.fetchall()

    async def get_clan_capacity(clan_id: int) -> int:
        async with runtime.db.execute(
            "SELECT capacity FROM clans WHERE id = ?", (clan_id,)
        ) as c:
            row = await c.fetchone()
        return (row[0] if row else None) or runtime.base_capacity

    async def get_clan_member_count(clan_id: int) -> int:
        async with runtime.db.execute(
            "SELECT COUNT(*) FROM clan_members WHERE clan_id = ?",
            (clan_id,),
        ) as c:
            return (await c.fetchone())[0] or 0

    def clan_capacity_cost(current_capacity: int) -> int:
        """Квадратичная цена расширения: 1k, 4k, 9k, ... за шаг."""
        steps = max(
            0,
            (current_capacity - runtime.base_capacity)
            // runtime.capacity_step,
        )
        return runtime.capacity_cost * (steps + 1) ** 2

    async def get_clan_power(clan_id: int):
        async with runtime.db.execute(
            """
            SELECT SUM(power) FROM (
                SELECT SUM(i.price * (1 + inv.stars * 0.5)) as power
                FROM inventory inv
                JOIN items i ON inv.item_id = i.id
                JOIN clan_members cm ON cm.user_id = inv.user_id
                WHERE cm.clan_id = ? AND inv.location = 'profile'
                GROUP BY inv.user_id
            )
            """,
            (clan_id,),
        ) as c:
            members_power = (await c.fetchone())[0] or 0
        async with runtime.db.execute(
            """
            SELECT SUM(i.price * (1 + ci.stars * 0.5))
            FROM clan_inventory ci
            JOIN items i ON ci.item_id = i.id
            WHERE ci.clan_id = ?
            """,
            (clan_id,),
        ) as c:
            clan_power = (await c.fetchone())[0] or 0
        return int(members_power + clan_power)

    async def get_clan_role(user_id: int, clan_id: int) -> str:
        async with runtime.db.execute(
            "SELECT role FROM clan_members "
            "WHERE user_id = ? AND clan_id = ?",
            (user_id, clan_id),
        ) as c:
            row = await c.fetchone()
        return row[0] if row else "none"

    async def log_clan(clan_id: int, action: str, details: str = ""):
        async with runtime.transaction():
            await runtime.db.execute(
                "INSERT INTO clan_log (clan_id, action, details) "
                "VALUES (?, ?, ?)",
                (clan_id, action, details),
            )

    async def get_clan_level_info(clan_id: int) -> tuple[int, int, float]:
        async with runtime.db.execute(
            "SELECT level, xp, bonus FROM clans WHERE id = ?", (clan_id,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return 1, 0, 0.0
        level, xp, bonus = row
        return (level or 1), (xp or 0), (bonus or 0.0)

    async def add_clan_xp(clan_id: int, amount: int) -> tuple[int, int, float]:
        """Добавляет XP клану, повышает уровень и пересчитывает бонус."""
        if amount <= 0:
            return await get_clan_level_info(clan_id)

        old_level = 1
        new_level = 1
        async with runtime.transaction():
            async with runtime.db.execute(
                "SELECT level, xp FROM clans WHERE id = ?", (clan_id,)
            ) as c:
                row = await c.fetchone()
            if not row:
                raise ValueError("Клан не найден.")

            old_level = row[0] or 1
            level = old_level
            xp = (row[1] or 0) + amount

            while (
                level < runtime.max_level
                and xp >= runtime.xp_per_level * level
            ):
                xp -= runtime.xp_per_level * level
                level += 1

            if level >= runtime.max_level:
                xp = min(xp, runtime.xp_per_level * level)

            bonus = min(0.20, (level - 1) * 0.01)
            new_level = level
            await runtime.db.execute(
                "UPDATE clans SET level = ?, xp = ?, bonus = ? WHERE id = ?",
                (level, xp, bonus, clan_id),
            )

        if new_level > old_level:
            await log_clan(clan_id, "level_up", f"{old_level} → {new_level}")
        return await get_clan_level_info(clan_id)

    async def get_active_clan_war(clan_id: int):
        async with runtime.db.execute(
            """
            SELECT id, clan1_id, clan2_id, start_time,
                   clan1_hp, clan2_hp, clan1_max_hp, clan2_max_hp,
                   clan1_damage, clan2_damage
            FROM clan_wars
            WHERE status = 'active' AND (clan1_id = ? OR clan2_id = ?)
            ORDER BY id DESC
            LIMIT 1
            """,
            (clan_id, clan_id),
        ) as c:
            return await c.fetchone()

    return (
        get_clan,
        get_clan_members,
        get_clan_capacity,
        get_clan_member_count,
        clan_capacity_cost,
        get_clan_power,
        get_clan_role,
        log_clan,
        get_clan_level_info,
        add_clan_xp,
        get_active_clan_war,
    )
