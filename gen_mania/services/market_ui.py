"""Market, trading hub and order-book embeds."""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable

from .market import clamp_market_price, market_sparkline


class MarketUiRuntime:
    """Адаптер между bot.py и рыночными embed'ами."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self._price_formatter: Callable[[int], str] = str
        self._synthesis_only_getter: Callable[[], Callable] = lambda: None
        self.gen_synthesis_only: set = set()
        self.market_sell_rate = 0.7
        self.rarity_names: dict = {}
        self.shop_market_min_ratio = 0.8
        self.shop_market_max_ratio = 1.2
        self.market_history_limit = 20
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        embed_factory: Callable[..., Any],
        emoji_getter: Callable[[], Callable],
        emoji_fixer: Callable[[Any], Any],
        price_formatter: Callable[[int], str],
        synthesis_only_getter: Callable[[], Callable],
        gen_synthesis_only: set,
        market_sell_rate: float,
        rarity_names: dict,
        shop_market_min_ratio: float,
        shop_market_max_ratio: float,
        market_history_limit: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._embed_factory = embed_factory
        self._emoji_getter = emoji_getter
        self._emoji_fixer = emoji_fixer
        self._price_formatter = price_formatter
        self._synthesis_only_getter = synthesis_only_getter
        self.gen_synthesis_only = gen_synthesis_only
        self.market_sell_rate = market_sell_rate
        self.rarity_names = rarity_names
        self.shop_market_min_ratio = shop_market_min_ratio
        self.shop_market_max_ratio = shop_market_max_ratio
        self.market_history_limit = market_history_limit
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

    def is_synthesis_only(self, item_id: str) -> bool:
        return self._synthesis_only_getter()(item_id)


def make_market_ui_layer(runtime: MarketUiRuntime):
    """Возвращает рыночные embed-функции, привязанные к runtime."""

    async def build_market_history_embed(item_id: str):
        async with runtime.db.execute(
            "SELECT i.name, i.emoji, mp.base_price, mp.current_price, "
            "mp.demand, mp.supply FROM items i "
            "JOIN market_prices mp ON mp.item_id = i.id WHERE i.id = ?",
            (item_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            return runtime.embed(
                title="История цен",
                description="Предмет не найден на бирже.",
                color=0xE74C3C,
            )

        name, emoji, base, current, demand, supply = row
        async with runtime.db.execute(
            "SELECT price FROM market_history WHERE item_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (item_id, runtime.market_history_limit),
        ) as c:
            history = [r[0] for r in await c.fetchall()]
        history.reverse()
        if not history:
            history = [current]

        change = history[-1] - history[0]
        change_pct = (change / history[0] * 100) if history[0] else 0
        spark = market_sparkline(history)
        embed = runtime.embed(
            title=f"{runtime.emoji('_history')} История цен: {name}",
            description=(
                f"{emoji or '📦'} База: 🪙 **{base}** · "
                f"Сейчас: 🪙 **{current}**\n"
                f"`{spark}`\n"
                f"Изменение: **{change:+d}** ({change_pct:+.1f}%)"
            ),
            color=0x9B59B6,
        )
        embed.add_field(
            name="Диапазон",
            value=(
                f"Мин: 🪙 **{min(history)}**\n"
                f"Макс: 🪙 **{max(history)}**\n"
                f"Точек: **{len(history)}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Спрос / предложение",
            value=(
                f"Спрос: **{demand or 0}**\n"
                f"Предложение: **{supply or 0}**"
            ),
            inline=True,
        )
        embed.set_footer(
            text=(
                "История обновляется при покупках, продажах "
                "и рыночных циклах."
            )
        )
        return embed

    async def build_market_embed(
        interaction,
        rarity: str | None = None,
        sort: str = "change",
        page: int = 0,
    ):
        sort_map = {
            "change": "ABS(mp.current_price - mp.base_price) DESC",
            "price_desc": "mp.current_price DESC",
            "price_asc": "mp.current_price ASC",
            "demand": "mp.demand DESC, mp.supply ASC",
            "name": "i.name ASC",
        }
        sort = sort if sort in sort_map else "change"
        hidden = tuple(sorted(runtime.gen_synthesis_only))
        hidden_ph = ",".join("?" for _ in hidden)
        conditions = [f"mp.item_id NOT IN ({hidden_ph})"]
        params: list = list(hidden)
        if rarity:
            conditions.append("i.rarity = ?")
            params.append(rarity)
        where = "WHERE " + " AND ".join(conditions)

        async with runtime.db.execute(
            f"SELECT COUNT(*) FROM market_prices mp "
            f"JOIN items i ON i.id = mp.item_id {where}",
            params,
        ) as c:
            total = (await c.fetchone())[0] or 0
        page_size = 10
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))

        async with runtime.db.execute(
            f"""
            SELECT mp.item_id, i.name, i.emoji, mp.base_price,
                   mp.current_price, mp.demand, mp.supply, i.price,
                   i.buyable,
                   (SELECT GROUP_CONCAT(price, ',') FROM (
                        SELECT price FROM market_history mh
                        WHERE mh.item_id = mp.item_id
                        ORDER BY mh.id DESC LIMIT 6
                   )) AS recent
            FROM market_prices mp
            JOIN items i ON i.id = mp.item_id
            {where}
            ORDER BY {sort_map[sort]}
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, page * page_size),
        ) as c:
            rows = await c.fetchall()

        rarity_label = (
            runtime.rarity_names.get(rarity, "Все") if rarity else "Все"
        )
        sort_names = {
            "change": "по изменению",
            "price_desc": "дорогие",
            "price_asc": "дешёвые",
            "demand": "по спросу",
            "name": "по названию",
        }
        embed = runtime.embed(
            title=f"{runtime.emoji('_market')} Биржа",
            description=(
                f"Страница {page + 1}/{total_pages}\n"
                "Покупка — по средней цене пачки. Продажа — "
                f"**{int(runtime.market_sell_rate * 100)}%** "
                "от текущей цены.\n"
                "Для магазинных генераторов цена ограничена "
                f"**{int(runtime.shop_market_min_ratio * 100)}–"
                f"{int(runtime.shop_market_max_ratio * 100)}%** "
                "цены магазина.\n"
                f"Фильтр: **{rarity_label}** · "
                f"Сортировка: **{sort_names[sort]}**"
            ),
            color=0x9B59B6,
        )
        if not rows:
            embed.add_field(
                name="Пусто", value="На бирже пока нет товаров."
            )
            return await runtime.fix_emojis(embed), total_pages

        for (
            item_id,
            name,
            emoji,
            base,
            current,
            demand,
            supply,
            item_price,
            buyable,
            recent,
        ) in rows:
            current = clamp_market_price(
                current or item_price or base or 1,
                item_price or base or 1,
                bool(buyable),
            )
            base = item_price or base
            trend = (
                "🟢"
                if current > base
                else ("🔴" if current < base else "⚪")
            )
            prices = [
                int(value)
                for value in (recent or "").split(",")
                if value
            ]
            spark = market_sparkline(prices) if prices else "—"
            embed.add_field(
                name=f"{trend} {emoji} {name}",
                value=(
                    f"Цена: 🪙 **{current}** (база {base})\n"
                    f"Спрос: **{demand}** | Предложение: **{supply}**\n"
                    f"`{spark}`"
                ),
                inline=False,
            )
        embed.set_footer(text="Обновление цен — раз в 6 часов")
        return await runtime.fix_emojis(embed), total_pages

    async def build_trading_hub_embed():
        hidden = tuple(sorted(runtime.gen_synthesis_only))
        hidden_ph = ",".join("?" for _ in hidden)
        async with runtime.db.execute(
            "SELECT mp.item_id, i.name, i.emoji, mp.current_price, "
            "mp.base_price, mp.demand, mp.supply, i.price, i.buyable "
            "FROM market_prices mp "
            f"JOIN items i ON i.id = mp.item_id "
            f"WHERE mp.item_id NOT IN ({hidden_ph}) "
            "ORDER BY i.price ASC",
            hidden,
        ) as c:
            rows = await c.fetchall()

        embed = runtime.embed(
            title=f"{runtime.emoji('_market')} Трейд-хаб",
            description="Лучшие цены и активные ордера по предметам.",
            color=0x2ECC71,
        )
        shown = 0
        for (
            item_id,
            name,
            emoji,
            current,
            base,
            demand,
            supply,
            item_price,
            buyable,
        ) in rows:
            current = clamp_market_price(
                current or item_price or base or 1,
                item_price or base or 1,
                bool(buyable),
            )
            base = item_price or base
            async with runtime.db.execute(
                "SELECT COUNT(*), MIN(price) FROM market_orders "
                "WHERE item_id = ? AND side = 'sell' "
                "AND status = 'active'",
                (item_id,),
            ) as c:
                sell_count, sell_min = await c.fetchone()
            async with runtime.db.execute(
                "SELECT COUNT(*), MAX(price) FROM market_orders "
                "WHERE item_id = ? AND side = 'buy' "
                "AND status = 'active'",
                (item_id,),
            ) as c:
                buy_count, buy_max = await c.fetchone()
            change = 0.0
            if base:
                change = (current - base) / base * 100
            embed.add_field(
                name=f"{emoji} {name}"[:100],
                value=(
                    f"Цена: 🪙 **{runtime.format_price(current)}** "
                    f"({change:+.1f}% к базовой)\n"
                    f"Продажа: **{sell_count}** ордеров"
                    + (
                        f", мин. 🪙 {runtime.format_price(sell_min)}"
                        if sell_min
                        else ""
                    )
                    + f"\nПокупка: **{buy_count}** ордеров"
                    + (
                        f", макс. 🪙 {runtime.format_price(buy_max)}"
                        if buy_max
                        else ""
                    )
                ),
                inline=False,
            )
            shown += 1
            if shown >= 8:
                break
        if not shown:
            embed.description = "На бирже пока нет предметов."
        return await runtime.fix_emojis(embed)

    async def build_order_book_embed(item_id: str):
        async with runtime.db.execute(
            "SELECT i.name, i.emoji, i.price, i.buyable, "
            "mp.current_price FROM items i "
            "LEFT JOIN market_prices mp ON mp.item_id = i.id "
            "WHERE i.id = ?",
            (item_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            return runtime.embed(
                title="❌ Предмет не найден", color=0xE74C3C
            )
        name, emoji, item_price, buyable, current = row
        if runtime.is_synthesis_only(item_id):
            return runtime.embed(
                title=f"{runtime.emoji('_market')} {name}",
                description=(
                    "Этот генератор доступен только через синтез."
                ),
                color=0x9B59B6,
            )

        now = datetime.datetime.now().isoformat()
        async with runtime.db.execute(
            "SELECT side, price, SUM(quantity - filled) AS remaining, "
            "COUNT(*) FROM market_orders "
            "WHERE item_id = ? AND status = 'active' "
            "AND expires_at > ? GROUP BY side, price",
            (item_id, now),
        ) as c:
            levels = await c.fetchall()

        asks = sorted(
            (price, remaining, count)
            for side, price, remaining, count in levels
            if side == "sell" and remaining > 0
        )
        bids = sorted(
            (
                (price, remaining, count)
                for side, price, remaining, count in levels
                if side == "buy" and remaining > 0
            ),
            reverse=True,
        )
        current = clamp_market_price(
            current or item_price or 1,
            item_price or 1,
            bool(buyable),
        )
        best_ask = asks[0][0] if asks else None
        best_bid = bids[0][0] if bids else None
        if best_ask is not None and best_bid is not None:
            spread = best_ask - best_bid
            spread_pct = spread / best_ask * 100 if best_ask else 0
            spread_text = (
                f"🪙 {runtime.format_price(spread)} "
                f"({spread_pct:+.1f}%)"
            )
        else:
            spread_text = "нет встречных заявок"

        embed = runtime.embed(
            title=f"{runtime.emoji('_market')} Стакан — {name}",
            description=(
                f"Текущая цена биржи: "
                f"🪙 **{runtime.format_price(current)}**\n"
                f"Лучший bid: "
                f"**{runtime.format_price(best_bid) if best_bid else '—'}** "
                f"· Лучший ask: "
                f"**{runtime.format_price(best_ask) if best_ask else '—'}**\n"
                f"Спред: **{spread_text}**"
            ),
            color=0x9B59B6,
        )

        def level_lines(levels_data):
            if not levels_data:
                return "нет заявок"
            return "\n".join(
                f"🪙 **{runtime.format_price(price)}** × {remaining} "
                f"({count} заявк{'' if count == 1 else 'и'})"
                for price, remaining, count in levels_data[:5]
            )

        embed.add_field(
            name="📉 Продажа",
            value=level_lines(asks),
            inline=True,
        )
        embed.add_field(
            name="📈 Покупка",
            value=level_lines(bids),
            inline=True,
        )
        embed.set_footer(
            text="Исполнение заявок — в разделе «Ордера»."
        )
        return await runtime.fix_emojis(embed)

    return (
        build_market_history_embed,
        build_market_embed,
        build_trading_hub_embed,
        build_order_book_embed,
    )
