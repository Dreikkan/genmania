"""Upgrades, pets and autocollector embeds."""
from __future__ import annotations

import logging
from typing import Any, Callable


class UpgradesUiRuntime:
    """Адаптер между bot.py и UI улучшений/питомцев."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._active_statuses_getter: Callable[[], Callable] = lambda: None
        self._pets_getter: Callable[[], Callable] = lambda: None
        self._active_pet_getter: Callable[[], Callable] = lambda: None
        self._autocollector_getter: Callable[[], Callable] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._price_formatter: Callable[[int], str] = str
        self._status_price: Callable[[str, int], int | None] = (
            lambda status_id, days: None
        )
        self._status_expiry: Callable[[Any], str] = str
        self._effect_summary: Callable[[dict, int], str] = (
            lambda ptype, level: ""
        )
        self.button_emojis: dict = {}
        self.upgrades_page_size = 10
        self.status_bonuses: dict = {}
        self.start_grid = 9
        self.pet_types: dict = {}
        self.pet_max_level = 10
        self.autocollect_levels: dict = {}
        self.autocollect_price = 0
        self.autocollect_max_level = 0
        self.gem = "💎"
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        active_statuses_getter: Callable[[], Callable],
        pets_getter: Callable[[], Callable],
        active_pet_getter: Callable[[], Callable],
        autocollector_getter: Callable[[], Callable],
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        emoji_getter: Callable[[], Callable],
        price_formatter: Callable[[int], str],
        status_price: Callable[[str, int], int | None],
        status_expiry: Callable[[Any], str],
        effect_summary: Callable[[dict, int], str],
        button_emojis: dict,
        upgrades_page_size: int,
        status_bonuses: dict,
        start_grid: int,
        pet_types: dict,
        pet_max_level: int,
        autocollect_levels: dict,
        autocollect_price: int,
        autocollect_max_level: int,
        gem: str,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._active_statuses_getter = active_statuses_getter
        self._pets_getter = pets_getter
        self._active_pet_getter = active_pet_getter
        self._autocollector_getter = autocollector_getter
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self._emoji_getter = emoji_getter
        self._price_formatter = price_formatter
        self._status_price = status_price
        self._status_expiry = status_expiry
        self._effect_summary = effect_summary
        self.button_emojis = button_emojis
        self.upgrades_page_size = upgrades_page_size
        self.status_bonuses = status_bonuses
        self.start_grid = start_grid
        self.pet_types = pet_types
        self.pet_max_level = pet_max_level
        self.autocollect_levels = autocollect_levels
        self.autocollect_price = autocollect_price
        self.autocollect_max_level = autocollect_max_level
        self.gem = gem
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    async def get_active_statuses(self, user_id: int):
        return await self._active_statuses_getter()(user_id)

    async def get_user_pets(self, user_id: int):
        return await self._pets_getter()(user_id)

    async def get_active_pet(self, user_id: int):
        return await self._active_pet_getter()(user_id)

    async def get_autocollector(self, user_id: int):
        return await self._autocollector_getter()(user_id)

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    async def fix_emojis(self, embed):
        return await self._emoji_fixer(embed)

    def emoji(self, key: str):
        return self._emoji_getter()(key)

    def format_price(self, value: int) -> str:
        return self._price_formatter(value)

    def status_price(self, status_id: str, days: int):
        return self._status_price(status_id, days)

    def format_status_expiry(self, value) -> str:
        return self._status_expiry(value)

    def effect_summary(self, ptype: dict, level: int) -> str:
        return self._effect_summary(ptype, level)


def make_upgrades_ui_layer(runtime: UpgradesUiRuntime):
    """Возвращает UI-функции улучшений и питомцев."""

    async def build_upgrades_page(interaction, page: int):
        guild_id = interaction.guild_id
        gem = str(runtime.button_emojis.get("_gem", "💎"))
        coin = str(runtime.button_emojis.get("_coin", "🪙"))
        up_emoji = str(
            runtime.button_emojis.get("_upgrades", "💎")
        )
        user_id = interaction.user.id

        async with runtime.db.execute(
            "SELECT grid_size FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        current_grid_size = (
            (row[0] if row else runtime.start_grid)
            or runtime.start_grid
        )

        async with runtime.db.execute(
            """
            SELECT id, name, description, price_coins as price,
                   emoji, 'coins' as currency, size FROM grid_shop
            UNION ALL
            SELECT id, name, description, price_gems as price,
                   emoji, 'gems' as currency, 0 as size FROM gem_shop
            """
        ) as c:
            rows = await c.fetchall()

        order = {
            "grid_4x4": 1,
            "grid_5x5": 2,
            "grid_6x6": 3,
            "grid_7x7": 4,
            "grid_8x8": 5,
            "grid_9x9": 6,
            "grid_10x10": 7,
            "vip": 10,
            "gold": 11,
            "platinum": 12,
            "diamond": 13,
        }
        rows = sorted(rows, key=lambda r: order.get(r[0], 99))

        async with runtime.db.execute(
            "SELECT upgrade_id FROM player_upgrades "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            owned = {r[0] for r in await c.fetchall()}
        active_statuses = await runtime.get_active_statuses(user_id)

        total = len(rows)
        total_pages = max(
            1,
            (total + runtime.upgrades_page_size - 1)
            // runtime.upgrades_page_size,
        )
        page = max(0, min(page, total_pages - 1))
        chunk = rows[
            page * runtime.upgrades_page_size:
            page * runtime.upgrades_page_size
            + runtime.upgrades_page_size
        ]
        page_coins = sum(
            price
            for _id, _name, _desc, price, _emoji, currency, _size
            in chunk
            if currency == "coins"
        )
        page_gems = sum(
            (
                runtime.status_price(item_id, 1) or price
            )
            if item_id in runtime.status_bonuses
            else price
            for (
                item_id,
                _name,
                _desc,
                price,
                _emoji,
                currency,
                _size,
            ) in chunk
            if currency == "gems"
        )
        async with runtime.db.execute(
            "SELECT coins, gems FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            balance_row = await c.fetchone()
        balance_coins = (
            balance_row[0] if balance_row else 0
        ) or 0
        balance_gems = (
            balance_row[1] if balance_row else 0
        ) or 0

        embed = runtime.embed(
            title=f"{up_emoji} Магазин улучшений",
            description=(
                f"Страница {page + 1}/{total_pages}\n"
                f"Баланс: {coin} "
                f"**{runtime.format_price(balance_coins)}** | "
                f"{gem} "
                f"**{runtime.format_price(balance_gems)}**\n"
                f"На странице: {coin} "
                f"**{runtime.format_price(page_coins)}** | "
                f"{gem} "
                f"**{runtime.format_price(page_gems)}**"
            ),
            color=0x9b59b6,
        )

        for gid, name, desc, price, emoji, currency, size in chunk:
            if gid in runtime.status_bonuses:
                min_price = runtime.status_price(gid, 1)
                max_price = runtime.status_price(gid, 30)
                price_str = (
                    f"{gem} {runtime.format_price(min_price)}–"
                    f"{runtime.format_price(max_price)} (1–30 дней)"
                )
            else:
                price_str = (
                    f"{coin} {runtime.format_price(price)}"
                    if currency == "coins"
                    else f"{gem} {runtime.format_price(price)}"
                )

            if gid == "vip":
                emoji = runtime.emoji("_vip")
            elif gid == "gold":
                emoji = runtime.emoji("_gold")
            elif gid == "platinum":
                emoji = runtime.emoji("_platinum")
            elif gid == "diamond":
                emoji = runtime.emoji("_diamond")

            if gid in runtime.status_bonuses:
                if gid in active_statuses:
                    status = (
                        "✅ Активен до "
                        f"`{runtime.format_status_expiry(active_statuses[gid])}`"
                    )
                else:
                    status = "🛒 Доступно (1–30 дней)"
            elif gid in owned:
                status = "✅ Куплено"
            elif size > 0 and size <= current_grid_size:
                status = (
                    f"🚫 Недоступно (у вас сетка {current_grid_size})"
                )
            else:
                status = "🛒 Доступно для покупки"

            embed.add_field(
                name=f"{emoji} {name} (`{gid}`)",
                value=f"{desc}\nЦена: {price_str}\n{status}",
                inline=False,
            )

        return await runtime.fix_emojis(embed), total_pages

    async def build_pets_embed(interaction):
        user_id = interaction.user.id
        pets = await runtime.get_user_pets(user_id)
        active = await runtime.get_active_pet(user_id)

        embed = runtime.embed(
            title="🐾 Питомцы",
            description=(
                "Купи питомца, корми его и получай бонусы. "
                "Активный питомец даёт эффект."
            ),
            color=0x9b59b6,
        )

        if not pets:
            embed.add_field(
                name="У тебя пока нет питомцев",
                value="Загляни в магазин питомцев!",
                inline=False,
            )
        else:
            for pet_id, level, last_fed in pets:
                ptype = runtime.pet_types.get(pet_id)
                if not ptype:
                    continue
                is_active = (
                    "✅ "
                    if active and active[0] == pet_id
                    else ""
                )
                embed.add_field(
                    name=(
                        f"{is_active}{ptype['emoji']} "
                        f"{ptype['name']} "
                        f"(ур. {level}/{runtime.pet_max_level})"
                    ),
                    value=runtime.effect_summary(ptype, level),
                    inline=False,
                )

        embed.set_footer(text="Купить питомца — кнопка ниже.")
        return await runtime.fix_emojis(embed)

    async def build_autocollector_embed(interaction):
        user_id = interaction.user.id
        existing = await runtime.get_autocollector(user_id)

        embed = runtime.embed(
            title="🤖 Автосборщик", color=0x3498db
        )

        if not existing:
            embed.description = (
                "Покупай автосборщик, чтобы доход собирался "
                "**автоматически** раз в "
                f"{runtime.autocollect_levels[1][1]} ч, "
                "даже когда ты офлайн.\n\n"
                f"Цена: {runtime.gem} {runtime.autocollect_price}"
            )
        else:
            level, last_auto = existing
            interval = runtime.autocollect_levels[level][1]
            next_level = level + 1
            if next_level <= runtime.autocollect_max_level:
                next_price, next_interval = (
                    runtime.autocollect_levels[next_level]
                )
                upgrade_str = (
                    f"\nУлучшение до {next_level} ур.: "
                    f"💎 {next_price} → раз в {next_interval} ч"
                )
            else:
                upgrade_str = "\nМаксимальный уровень."
            embed.description = (
                f"Уровень: **{level}/"
                f"{runtime.autocollect_max_level}**\n"
                f"Интервал: раз в **{interval} ч**\n"
                f"Последний сбор: `{last_auto or '—'}`"
                f"{upgrade_str}"
            )
        return await runtime.fix_emojis(embed)

    return (
        build_upgrades_page,
        build_pets_embed,
        build_autocollector_embed,
    )
