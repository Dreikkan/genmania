"""Shop, achievements and collection embeds."""
from __future__ import annotations

import logging
from typing import Any, Callable

from .market import clamp_market_price


class ShopUiRuntime:
    """Адаптер между bot.py и UI магазина/коллекции."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._settings_getter: Callable[[], Callable] = lambda: None
        self._accessibility_getter: Callable[[], Callable] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self._price_formatter: Callable[[int], str] = str
        self._reward_scale_getter: Callable[[], Callable] = (
            lambda: lambda points: 1.0
        )
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self.button_emojis: dict = {}
        self.page_size = 10
        self.income_hint = ""
        self.synthesis_only = set()
        self.rarity_names: dict = {}
        self.collection_bonus = 0.005
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        settings_getter: Callable[[], Callable],
        accessibility_getter: Callable[[], Callable],
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        price_formatter: Callable[[int], str],
        reward_scale_getter: Callable[[], Callable],
        emoji_getter: Callable[[], Callable],
        button_emojis: dict,
        page_size: int,
        income_hint: str,
        synthesis_only,
        rarity_names: dict,
        collection_bonus: float,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._settings_getter = settings_getter
        self._accessibility_getter = accessibility_getter
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self._price_formatter = price_formatter
        self._reward_scale_getter = reward_scale_getter
        self._emoji_getter = emoji_getter
        self.button_emojis = button_emojis
        self.page_size = page_size
        self.income_hint = income_hint
        self.synthesis_only = synthesis_only
        self.rarity_names = rarity_names
        self.collection_bonus = collection_bonus
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    async def get_settings(self, guild_id: int):
        return await self._settings_getter()(guild_id)

    async def is_accessibility_mode(self, user_id: int):
        return await self._accessibility_getter()(user_id)

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    async def fix_emojis(self, embed):
        return await self._emoji_fixer(embed)

    def format_price(self, value: int) -> str:
        return self._price_formatter(value)

    def reward_scale(self, prestige_points: int) -> float:
        return self._reward_scale_getter()(prestige_points)

    def emoji(self, key: str):
        return self._emoji_getter()(key)


def make_shop_ui_layer(runtime: ShopUiRuntime):
    """Возвращает shop/collection embeds, привязанные к runtime."""

    async def build_shop_page(interaction, page: int):
        guild_id = interaction.guild_id
        settings = await runtime.get_settings(guild_id)
        compact = await runtime.is_accessibility_mode(
            interaction.user.id
        )
        custom = settings["custom_emojis"]
        coin = str(runtime.button_emojis.get("_coin", "🪙"))
        gem = str(runtime.button_emojis.get("_gem", "💎"))
        shop_emoji = str(
            runtime.button_emojis.get("_generators", "🏭")
        )

        async with runtime.db.execute(
            "SELECT id, name, price, income_per_hour, emoji, "
            "rarity, income_gems_per_hour, buyable "
            "FROM items WHERE id LIKE '%_gen' ORDER BY price ASC"
        ) as c:
            rows = await c.fetchall()

        async with runtime.db.execute(
            "SELECT item_id, current_price FROM market_prices"
        ) as c:
            market_current = dict(await c.fetchall())

        total = len(rows)
        total_pages = max(
            1, (total + runtime.page_size - 1) // runtime.page_size
        )
        page = max(0, min(page, total_pages - 1))
        chunk = rows[
            page * runtime.page_size:
            page * runtime.page_size + runtime.page_size
        ]
        page_total = sum(
            price
            for (
                _id,
                _name,
                price,
                _inc,
                _emoji,
                _rarity,
                _gems,
                buyable,
            ) in chunk
            if buyable
        )
        async with runtime.db.execute(
            "SELECT coins, gems FROM players WHERE user_id = ?",
            (interaction.user.id,),
        ) as c:
            player_row = await c.fetchone()
        balance_coins = (
            player_row[0] if player_row else 0
        ) or 0
        balance_gems = (
            player_row[1] if player_row else 0
        ) or 0

        embed = runtime.embed(
            title=f"{shop_emoji} Магазин",
            description=(
                f"Страница {page + 1}/{total_pages}\n"
                f"Баланс: {coin} "
                f"**{runtime.format_price(balance_coins)}** | "
                f"{gem} "
                f"**{runtime.format_price(balance_gems)}**\n"
                f"Стоимость всей страницы: {coin} "
                f"**{runtime.format_price(page_total)}**\n"
                "Магазин — фиксированная цена, биржа — "
                "вторичный рынок."
                + (
                    ""
                    if compact
                    else f"\n-# {runtime.income_hint}"
                )
            ),
            color=0xf1c40f,
        )

        for (
            item_id,
            name,
            price,
            income_coins,
            default_emoji,
            rarity,
            income_gems,
            buyable,
        ) in chunk:
            emoji = custom.get(item_id, default_emoji)
            inc = []
            if income_coins > 0:
                inc.append(
                    f"{coin} {runtime.format_price(income_coins * 3600)}/час"
                )
            if income_gems > 0:
                inc.append(
                    f"{gem} {runtime.format_price(income_gems * 3600)}/час"
                )
            inc_str = " ".join(inc) if inc else "без дохода"

            if buyable:
                price_str = (
                    f"Цена: {coin} {runtime.format_price(price)}"
                )
            elif item_id in runtime.synthesis_only:
                price_str = "Цена: `Только синтез`"
            else:
                price_str = "Покупка на бирже/аукционе"

            market_str = ""
            if (
                item_id not in runtime.synthesis_only
                and item_id in market_current
            ):
                market_price = clamp_market_price(
                    market_current[item_id] or price,
                    price,
                    bool(buyable),
                )
                market_str = (
                    f"Биржа: {coin} "
                    f"{runtime.format_price(market_price)}"
                )

            value_parts = [price_str]
            if market_str:
                value_parts.append(market_str)
            if buyable and income_coins > 0 and price > 0:
                payback_hours = price / (income_coins * 3600)
                if payback_hours < 48:
                    payback = f"Окупаемость: {payback_hours:.1f} ч"
                else:
                    payback = f"Окупаемость: {payback_hours / 24:.1f} дн"
                if payback_hours > 24 * 30:
                    payback = "⚠️ " + payback
                value_parts.append(payback)
            value_parts.extend(
                [
                    inc_str,
                    runtime.rarity_names.get(rarity, rarity),
                ]
            )

            embed.add_field(
                name=f"{emoji} {name}",
                value=" | ".join(value_parts),
                inline=False,
            )

        return await runtime.fix_emojis(embed), total_pages

    async def build_achievements_page(interaction, page: int):
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        custom = (await runtime.get_settings(guild_id))[
            "custom_emojis"
        ]
        ach_emoji = custom.get("_achievements", "🏆")
        gem = str(runtime.button_emojis.get("_gem", "💎"))

        async with runtime.db.execute(
            "SELECT id, name, description, reward_gems, emoji "
            "FROM achievements ORDER BY reward_gems ASC"
        ) as c:
            all_ach = await c.fetchall()

        async with runtime.db.execute(
            "SELECT achievement_id FROM player_achievements "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            unlocked = {r[0] for r in await c.fetchall()}

        async with runtime.db.execute(
            "SELECT prestige_points FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        scale = runtime.reward_scale((row[0] if row else 0) or 0)

        total = len(all_ach)
        total_pages = max(
            1, (total + runtime.page_size - 1) // runtime.page_size
        )
        page = max(0, min(page, total_pages - 1))
        chunk = all_ach[
            page * runtime.page_size:
            page * runtime.page_size + runtime.page_size
        ]

        embed = runtime.embed(
            title=(
                f"{ach_emoji} Достижения — {interaction.user.name}"
            ),
            description=(
                f"Страница {page + 1}/{total_pages} | "
                f"Открыто: {len(unlocked)}/{total}"
            ),
            color=0xf1c40f,
        )
        for ach_id, name, desc, reward, emoji in chunk:
            status = (
                "✅ Открыто"
                if ach_id in unlocked
                else "🔒 Закрыто"
            )
            embed.add_field(
                name=f"{emoji} {name}",
                value=(
                    f"{desc}\nНаграда: {gem} {int(reward * scale)} — "
                    f"{status}"
                ),
                inline=False,
            )
        embed.set_footer(text=f"Множитель престижа: ×{scale:g}")
        return await runtime.fix_emojis(embed), total_pages

    async def build_collection_embed(interaction, page: int = 0):
        user_id = interaction.user.id
        async with runtime.db.execute(
            "SELECT id, name, emoji, rarity, price FROM items "
            "WHERE id LIKE '%\\_gen' ESCAPE '\\' ORDER BY price ASC"
        ) as c:
            all_items = await c.fetchall()

        async with runtime.db.execute(
            "SELECT item_id FROM player_collection "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            unlocked = {r[0] for r in await c.fetchall()}

        async with runtime.db.execute(
            "SELECT item_id, stars FROM player_star_collection "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            star_rows = await c.fetchall()
        star_map: dict[str, set[int]] = {}
        for item_id, stars in star_rows:
            star_map.setdefault(item_id, set()).add(stars)
        for item_id in unlocked:
            star_map.setdefault(item_id, set()).add(0)

        total = len(all_items)
        total_pages = max(
            1, (total + runtime.page_size - 1) // runtime.page_size
        )
        page = max(0, min(page, total_pages - 1))
        chunk = all_items[
            page * runtime.page_size:
            page * runtime.page_size + runtime.page_size
        ]
        discovered = sum(
            1 for item_id, *_ in all_items if item_id in unlocked
        )
        bonus_pct = (
            discovered * runtime.collection_bonus * 100
        )
        stars_found = sum(len(stars) for stars in star_map.values())
        stars_total = total * 6

        embed = runtime.embed(
            title=f"{runtime.emoji('_collection')} "
            "Коллекция генераторов",
            description=(
                f"Генераторов: **{discovered}/{total}** · "
                f"звёзд: **{stars_found}/{stars_total}**\n"
                f"Бонус к доходу: **+{bonus_pct:.1f}%**\n"
                f"Страница {page + 1}/{total_pages}"
            ),
            color=0x3498db,
        )
        for item_id, name, emoji, rarity, price in chunk:
            is_open = item_id in unlocked
            stars = star_map.get(item_id, set())
            if is_open:
                marks = " ".join(
                    f"{star}★{'✅' if star in stars else '⬜'}"
                    for star in range(6)
                )
                field_name = f"✅ {emoji} {name}"
            else:
                marks = "0★⬜ 1★⬜ 2★⬜ 3★⬜ 4★⬜ 5★⬜"
                field_name = f"🔒 {emoji} ???"
            embed.add_field(
                name=field_name[:100],
                value=(
                    f"{runtime.rarity_names.get(rarity, rarity)}\n"
                    f"{marks}"
                ),
                inline=False,
            )
        embed.set_footer(
            text=(
                "Каждый новый генератор даёт +0.5% к доходу; "
                "звёзды отмечаются отдельно"
            )
        )
        return await runtime.fix_emojis(embed), total_pages

    return (
        build_shop_page,
        build_achievements_page,
        build_collection_embed,
    )
