"""Leaderboard queries and short-lived cache."""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable


class LeaderboardRuntime:
    """Адаптер между bot.py и сервисом топов."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._bot_getter: Callable[[], Any] = lambda: None
        self._combat_power_many_getter: Callable[[], Callable] = lambda: None
        self._cache_getter: Callable[[], dict] = lambda: {}
        self.cache_ttl = 300
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        bot_getter: Callable[[], Any],
        combat_power_many_getter: Callable[[], Callable],
        cache_getter: Callable[[], dict],
        cache_ttl: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._bot_getter = bot_getter
        self._combat_power_many_getter = combat_power_many_getter
        self._cache_getter = cache_getter
        self.cache_ttl = cache_ttl
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    @property
    def bot(self):
        return self._bot_getter()

    @property
    def cache(self) -> dict:
        return self._cache_getter()

    async def combat_power_many(self, user_ids):
        getter = self._combat_power_many_getter()
        return await getter(user_ids)


def make_leaderboard_layer(runtime: LeaderboardRuntime):
    """Возвращает функции топов, привязанные к runtime."""

    async def get_top_players(
        top_type: str, limit: int = 10, guild_id: int | None = None
    ) -> list:
        """Возвращает список (user_id, value) для указанного топа.

        guild_id=None — глобальный топ; иначе только участники сервера.
        """
        member_ids = None
        if guild_id:
            guild = (
                runtime.bot.get_guild(guild_id)
                if hasattr(runtime.bot, "get_guild")
                else None
            )
            if guild is None:
                return []
            member_ids = [member.id for member in guild.members]

        def user_filter(column: str = "user_id") -> tuple[str, list]:
            if member_ids is None:
                return "", []
            if not member_ids:
                return " AND 0", []
            placeholders = ",".join("?" for _ in member_ids)
            return (
                f" AND {column} IN ({placeholders})",
                list(member_ids),
            )

        if top_type == "coins":
            where, params = user_filter()
            async with runtime.db.execute(
                f"SELECT user_id, coins FROM players WHERE 1=1 {where} "
                f"AND COALESCE(top_excluded, 0) = 0 "
                f"ORDER BY coins DESC LIMIT ?",
                (*params, limit),
            ) as c:
                return await c.fetchall()

        elif top_type == "gems":
            where, params = user_filter()
            async with runtime.db.execute(
                f"SELECT user_id, gems FROM players WHERE 1=1 {where} "
                f"AND COALESCE(top_excluded, 0) = 0 "
                f"ORDER BY gems DESC LIMIT ?",
                (*params, limit),
            ) as c:
                return await c.fetchall()

        elif top_type == "crafts":
            where, params = user_filter()
            async with runtime.db.execute(
                f"SELECT user_id, total_crafts FROM players WHERE 1=1 {where} "
                f"AND COALESCE(top_excluded, 0) = 0 "
                f"ORDER BY total_crafts DESC LIMIT ?",
                (*params, limit),
            ) as c:
                return await c.fetchall()

        elif top_type == "pets":
            where, params = user_filter("up.user_id")
            async with runtime.db.execute(
                f"SELECT up.user_id, COUNT(*) AS cnt FROM user_pets_v2 up "
                f"JOIN players p ON p.user_id = up.user_id "
                f"WHERE 1=1 {where} AND COALESCE(p.top_excluded, 0) = 0 "
                f"GROUP BY up.user_id ORDER BY cnt DESC LIMIT ?",
                (*params, limit),
            ) as c:
                return await c.fetchall()

        elif top_type == "power":
            where, params = user_filter("inv.user_id")
            candidate_limit = max(limit * 10, 100)
            async with runtime.db.execute(
                f"SELECT inv.user_id, "
                f"SUM(i.price * (1 + inv.stars * 0.5)) AS power "
                f"FROM inventory inv JOIN items i ON inv.item_id = i.id "
                f"JOIN players p ON p.user_id = inv.user_id "
                f"WHERE inv.location = 'profile' "
                f"AND COALESCE(p.top_excluded, 0) = 0 "
                f"{where} GROUP BY inv.user_id "
                f"ORDER BY power DESC LIMIT ?",
                (*params, candidate_limit),
            ) as c:
                raw_rows = await c.fetchall()
            powers = await runtime.combat_power_many(
                [user_id for user_id, _raw_power in raw_rows]
            )
            scored = [
                (user_id, powers.get(user_id, 0))
                for user_id, _raw in raw_rows
            ]
            scored.sort(key=lambda row: row[1], reverse=True)
            return scored[:limit]

        elif top_type == "clans":
            clan_where = ""
            clan_params: list = []
            if member_ids is not None:
                if not member_ids:
                    return []
                placeholders = ",".join("?" for _ in member_ids)
                clan_where = (
                    " WHERE EXISTS (SELECT 1 FROM clan_members cm2 "
                    f"WHERE cm2.clan_id = c.id AND cm2.user_id IN "
                    f"({placeholders}))"
                )
                clan_params = list(member_ids)
            clan_where = (clan_where or " WHERE 1=1") + (
                " AND (c.leader_id IS NULL OR c.leader_id NOT IN "
                "(SELECT user_id FROM players "
                "WHERE COALESCE(top_excluded, 0) = 1))"
            )
            async with runtime.db.execute(
                f"""
                SELECT c.id, c.name,
                    COALESCE((
                        SELECT SUM(i.price * (1 + ci.stars * 0.5))
                        FROM clan_inventory ci
                        JOIN items i ON ci.item_id = i.id
                        WHERE ci.clan_id = c.id
                    ), 0)
                    + COALESCE((
                        SELECT SUM(mp.power) FROM (
                            SELECT SUM(i2.price * (1 + inv.stars * 0.5))
                                AS power
                            FROM inventory inv
                            JOIN items i2 ON inv.item_id = i2.id
                            JOIN clan_members cm ON cm.user_id = inv.user_id
                            WHERE cm.clan_id = c.id
                            AND inv.location = 'profile'
                            GROUP BY inv.user_id
                        ) mp
                    ), 0) AS power
                FROM clans c
                {clan_where}
                ORDER BY power DESC
                LIMIT ?
                """,
                (*clan_params, limit),
            ) as c:
                return await c.fetchall()

        elif top_type == "prestige":
            where, params = user_filter()
            async with runtime.db.execute(
                f"SELECT user_id, prestige_points FROM players "
                f"WHERE 1=1 {where} "
                f"AND COALESCE(top_excluded, 0) = 0 "
                f"ORDER BY prestige_points DESC LIMIT ?",
                (*params, limit),
            ) as c:
                return await c.fetchall()

        elif top_type == "collection":
            where, params = user_filter("pc.user_id")
            async with runtime.db.execute(
                f"SELECT pc.user_id, COUNT(*) AS cnt FROM player_collection pc "
                f"JOIN players p ON p.user_id = pc.user_id "
                f"WHERE 1=1 {where} AND COALESCE(p.top_excluded, 0) = 0 "
                f"GROUP BY pc.user_id ORDER BY cnt DESC LIMIT ?",
                (*params, limit),
            ) as c:
                return await c.fetchall()

        elif top_type == "duels":
            where, params = user_filter("dh.winner_id")
            async with runtime.db.execute(
                f"SELECT dh.winner_id AS user_id, COUNT(*) AS wins "
                f"FROM duel_history dh "
                f"JOIN players p ON p.user_id = dh.winner_id "
                f"WHERE 1=1 {where} AND COALESCE(p.top_excluded, 0) = 0 "
                f"GROUP BY dh.winner_id ORDER BY wins DESC LIMIT ?",
                (*params, limit),
            ) as c:
                return await c.fetchall()

        return []

    async def get_top_players_cached(
        top_type: str, limit: int = 10, guild_id: int | None = None
    ) -> list:
        """Кэширует результаты топов на 5 минут."""
        now = datetime.datetime.now().timestamp()
        cache_key = f"{top_type}:{limit}:{guild_id or 'global'}"
        if cache_key in runtime.cache:
            ts, rows = runtime.cache[cache_key]
            if now - ts < runtime.cache_ttl:
                return rows

        rows = await get_top_players(top_type, limit, guild_id)
        runtime.cache[cache_key] = (now, rows)
        return rows

    return get_top_players, get_top_players_cached
