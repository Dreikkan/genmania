"""Clan overview and browser embeds."""
from __future__ import annotations

import logging
from typing import Any, Callable


class ClanUiRuntime:
    """Адаптер между bot.py и клановыми embed'ами."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self._price_formatter: Callable[[int], str] = str
        self._members_getter: Callable[[], Callable] = lambda: None
        self._capacity_getter: Callable[[], Callable] = lambda: None
        self._power_getter: Callable[[], Callable] = lambda: None
        self._level_getter: Callable[[], Callable] = lambda: None
        self.xp_per_level = 1000
        self.max_level = 20
        self.coin = "🪙"
        self.page_size = 10
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        embed_factory: Callable[..., Any],
        emoji_getter: Callable[[], Callable],
        emoji_fixer: Callable[[Any], Any],
        price_formatter: Callable[[int], str],
        members_getter: Callable[[], Callable],
        capacity_getter: Callable[[], Callable],
        power_getter: Callable[[], Callable],
        level_getter: Callable[[], Callable],
        xp_per_level: int,
        max_level: int,
        coin: str,
        page_size: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._embed_factory = embed_factory
        self._emoji_getter = emoji_getter
        self._emoji_fixer = emoji_fixer
        self._price_formatter = price_formatter
        self._members_getter = members_getter
        self._capacity_getter = capacity_getter
        self._power_getter = power_getter
        self._level_getter = level_getter
        self.xp_per_level = xp_per_level
        self.max_level = max_level
        self.coin = coin
        self.page_size = page_size
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    def emoji(self, key: str):
        return self._emoji_getter()(key)

    async def fix_emojis(self, embed):
        return await self._emoji_fixer(embed)

    def format_price(self, value: int) -> str:
        return self._price_formatter(value)

    async def get_members(self, clan_id: int):
        return await self._members_getter()(clan_id)

    async def get_capacity(self, clan_id: int):
        return await self._capacity_getter()(clan_id)

    async def get_power(self, clan_id: int):
        return await self._power_getter()(clan_id)

    async def get_level_info(self, clan_id: int):
        return await self._level_getter()(clan_id)


def make_clan_ui_layer(runtime: ClanUiRuntime):
    """Возвращает клановые embed-функции, привязанные к runtime."""

    async def build_clan_embed(interaction, clan):
        c_id = clan[0]
        name = clan[1]
        leader_id = clan[2]
        treasury = clan[3]
        bonus = clan[4] if len(clan) > 4 else 0.0

        members = await runtime.get_members(c_id)
        capacity = await runtime.get_capacity(c_id)
        power = await runtime.get_power(c_id)
        level, xp, bonus = await runtime.get_level_info(c_id)
        xp_need = runtime.xp_per_level * level

        embed = runtime.embed(
            title=f"{runtime.emoji('_clan')} Клан «{name}»",
            color=0x9B59B6,
        )
        embed.add_field(
            name="Лидер", value=f"<@{leader_id}>", inline=True
        )
        embed.add_field(
            name="Участников",
            value=f"{len(members)}/{capacity}",
            inline=True,
        )
        embed.add_field(
            name="Мощь клана", value=str(power), inline=True
        )
        embed.add_field(
            name="Сундук",
            value=f"{runtime.coin} {treasury}",
            inline=True,
        )
        embed.add_field(
            name="Уровень",
            value=(
                f"**{level}/{runtime.max_level}** "
                f"(XP {xp}/{xp_need})"
            ),
            inline=True,
        )
        embed.add_field(
            name="Бонус к доходу",
            value=f"+{int(bonus * 100)}%",
            inline=True,
        )
        return await runtime.fix_emojis(embed)

    async def build_clan_browser_embed(
        page: int = 0, query: str | None = None
    ):
        where = ""
        params: list = []
        if query:
            where = "WHERE c.name LIKE ?"
            params.append(f"%{query}%")
        async with runtime.db.execute(
            f"SELECT c.id, c.name, c.leader_id, c.treasury, c.bonus, "
            f"COUNT(cm.user_id) FROM clans c "
            f"LEFT JOIN clan_members cm ON cm.clan_id = c.id "
            f"{where} GROUP BY c.id "
            f"ORDER BY COUNT(cm.user_id) DESC, c.name ASC",
            params,
        ) as c:
            rows = await c.fetchall()

        page_size = runtime.page_size
        total_pages = max(
            1, (len(rows) + page_size - 1) // page_size
        )
        page = max(0, min(page, total_pages - 1))
        chunk = rows[
            page * page_size:page * page_size + page_size
        ]

        embed = runtime.embed(
            title="🏰 Браузер кланов",
            description=(
                f"Страница {page + 1}/{total_pages}"
                + (f" · поиск: `{query}`" if query else "")
                + "\nВыбери клан в списке и подай заявку."
                if rows
                else "Кланов пока нет. Создай первый!"
            ),
            color=0x3498DB,
        )
        for (
            clan_id,
            name,
            leader_id,
            treasury,
            bonus,
            members,
        ) in chunk:
            embed.add_field(
                name=f"🏰 {name}",
                value=(
                    f"Лидер: <@{leader_id}> · "
                    f"Участников: **{members}**\n"
                    f"Сундук: 🪙 "
                    f"{runtime.format_price(treasury or 0)} · "
                    f"Бонус: **+{int((bonus or 0) * 100)}%**"
                ),
                inline=False,
            )
        return embed, total_pages, chunk

    return build_clan_embed, build_clan_browser_embed
