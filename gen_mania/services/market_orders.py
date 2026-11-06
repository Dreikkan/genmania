"""Market buy/sell and order-book service."""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable

from .market import (
    calculate_market_buy_prices,
    clamp_market_price,
    market_order_price_bounds,
    parse_market_datetime,
)


class MarketOrderRuntime:
    """Адаптер между bot.py и сервисом рыночных ордеров."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._place_items_getter: Callable[[], Callable] = lambda: None
        self._compensation_getter: Callable[[], Callable] = lambda: None
        self._record_price_getter: Callable[[], Callable] = lambda: None
        self._quest_getter: Callable[[], Callable] = lambda: None
        self._achievements_getter: Callable[[], Callable] = lambda: None
        self._synthesis_only_getter: Callable[[], Callable] = lambda: None
        self._price_formatter: Callable[[int], str] = str
        self._max_order_qty_getter: Callable[[], int] = lambda: 100
        self._max_order_value_getter: Callable[[], int] = lambda: 10_000_000
        self._max_active_orders_getter: Callable[[], int] = lambda: 10
        self._max_daily_volume_getter: Callable[[], int] = lambda: 50_000_000
        self.sell_rate = 0.70
        self.sell_allowed_rarities = {"common", "uncommon", "rare"}
        self.order_rarities = {
            "common",
            "uncommon",
            "rare",
            "epic",
            "legendary",
            "mythic",
        }
        self.order_duration_hours = 72
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        place_items_getter: Callable[[], Callable],
        compensation_getter: Callable[[], Callable],
        record_price_getter: Callable[[], Callable],
        quest_getter: Callable[[], Callable],
        achievements_getter: Callable[[], Callable],
        synthesis_only_getter: Callable[[], Callable],
        price_formatter: Callable[[int], str],
        sell_rate: float,
        sell_allowed_rarities,
        order_rarities,
        max_order_qty_getter: Callable[[], int],
        max_order_value_getter: Callable[[], int],
        max_active_orders_getter: Callable[[], int],
        max_daily_volume_getter: Callable[[], int],
        order_duration_hours: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._place_items_getter = place_items_getter
        self._compensation_getter = compensation_getter
        self._record_price_getter = record_price_getter
        self._quest_getter = quest_getter
        self._achievements_getter = achievements_getter
        self._synthesis_only_getter = synthesis_only_getter
        self._price_formatter = price_formatter
        self.sell_rate = sell_rate
        self.sell_allowed_rarities = sell_allowed_rarities
        self.order_rarities = order_rarities
        self._max_order_qty_getter = max_order_qty_getter
        self._max_order_value_getter = max_order_value_getter
        self._max_active_orders_getter = max_active_orders_getter
        self._max_daily_volume_getter = max_daily_volume_getter
        self.order_duration_hours = order_duration_hours
        self.logger = logger

    @property
    def max_order_qty(self) -> int:
        return self._max_order_qty_getter()

    @property
    def max_order_value(self) -> int:
        return self._max_order_value_getter()

    @property
    def max_active_orders(self) -> int:
        return self._max_active_orders_getter()

    @property
    def max_daily_volume(self) -> int:
        return self._max_daily_volume_getter()

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    async def place_items(self, *args, **kwargs):
        return await self._place_items_getter()(*args, **kwargs)

    async def grant_compensation(self, *args, **kwargs):
        return await self._compensation_getter()(*args, **kwargs)

    async def record_market_price(self, *args, **kwargs):
        return await self._record_price_getter()(*args, **kwargs)

    async def update_quest_progress(self, *args, **kwargs) -> None:
        await self._quest_getter()(*args, **kwargs)

    async def check_achievements(self, *args, **kwargs):
        return await self._achievements_getter()(*args, **kwargs)

    def is_synthesis_only(self, item_id: str) -> bool:
        return self._synthesis_only_getter()(item_id)

    def format_price(self, value: int) -> str:
        return self._price_formatter(value)


def make_market_order_layer(runtime: MarketOrderRuntime):
    """Возвращает market-функции, привязанные к runtime."""

    async def buy_market_item(
        user_id: int, item_id: str, qty: int
    ) -> tuple[bool, str]:
        if qty <= 0:
            return False, "❌ Количество должно быть больше нуля."
        if runtime.is_synthesis_only(item_id):
            return False, "❌ Этот генератор нельзя купить: только синтез."

        async with runtime.db.execute(
            """
            SELECT i.name, i.price, i.buyable, mp.current_price,
                   mp.base_price, mp.demand, mp.supply
            FROM items i
            JOIN market_prices mp ON mp.item_id = i.id
            WHERE i.id = ?
            """,
            (item_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            return False, "❌ Предмет не найден на бирже."
        (
            name,
            item_price,
            buyable,
            current_price,
            base_price,
            demand0,
            supply0,
        ) = row
        price = clamp_market_price(
            current_price or item_price or base_price or 1,
            item_price or base_price or 1,
            bool(buyable),
        )
        avg_price, new_price = calculate_market_buy_prices(
            price, item_price or base_price or price, qty
        )
        new_price = clamp_market_price(
            new_price,
            item_price or base_price or price,
            bool(buyable),
        )
        avg_price = min(new_price, max(price, avg_price))
        total = avg_price * qty

        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT coins FROM players WHERE user_id = ?",
                    (user_id,),
                ) as c:
                    coins_row = await c.fetchone()
                coins = (coins_row[0] if coins_row else 0) or 0
                if coins < total:
                    raise ValueError(
                        f"Нужно 🪙 {total}, у тебя {coins}."
                    )

                cur = await runtime.db.execute(
                    "UPDATE players SET coins = coins - ? "
                    "WHERE user_id = ? AND coins >= ?",
                    (total, user_id, total),
                )
                if cur.rowcount == 0:
                    raise ValueError(
                        "Недостаточно монет (баланс изменился)."
                    )

                await runtime.place_items(
                    user_id, item_id, qty, commit=False
                )

                await runtime.db.execute(
                    "UPDATE market_prices SET demand = demand + ?, "
                    "current_price = ?, last_update = ? "
                    "WHERE item_id = ?",
                    (
                        qty,
                        new_price,
                        datetime.datetime.now().isoformat(),
                        item_id,
                    ),
                )
                await runtime.record_market_price(
                    item_id,
                    new_price,
                    (demand0 or 0) + qty,
                    supply0 or 0,
                    commit=False,
                )
        except ValueError as e:
            return False, f"❌ {e}"

        await runtime.update_quest_progress(user_id, "buy_3", qty)
        await runtime.update_quest_progress(user_id, "buy_10", qty)
        await runtime.update_quest_progress(user_id, "buy_25", qty)
        await runtime.check_achievements(user_id)
        return True, f"✅ Куплено **{name}** ×{qty} за 🪙 {total}."

    async def sell_market_item(
        user_id: int, item_id: str, qty: int
    ) -> tuple[bool, str]:
        if qty <= 0:
            return False, "❌ Количество должно быть больше нуля."
        if runtime.is_synthesis_only(item_id):
            return False, "❌ Этот генератор нельзя продать: только синтез."

        async with runtime.db.execute(
            """
            SELECT i.name, i.price, i.rarity, i.buyable, mp.current_price,
                   mp.base_price, mp.demand, mp.supply
            FROM items i
            JOIN market_prices mp ON mp.item_id = i.id
            WHERE i.id = ?
            """,
            (item_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            return False, "❌ Предмет не найден на бирже."
        (
            name,
            item_price,
            rarity,
            buyable,
            current_price,
            base_price,
            demand0,
            supply0,
        ) = row
        if rarity not in runtime.sell_allowed_rarities:
            return (
                False,
                "❌ Предметы этой редкости продаются только через аукцион.",
            )

        price = clamp_market_price(
            current_price or item_price or base_price or 1,
            item_price or base_price or 1,
            bool(buyable),
        )
        proceeds = max(1, int(price * runtime.sell_rate)) * qty

        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT slot FROM inventory "
                    "WHERE user_id = ? AND location = 'storage' "
                    "AND item_id = ? AND stars = 0 "
                    "AND COALESCE(is_locked, 0) = 0 "
                    "ORDER BY slot ASC LIMIT ?",
                    (user_id, item_id, qty),
                ) as c:
                    slots = [r[0] for r in await c.fetchall()]
                if len(slots) < qty:
                    raise ValueError(
                        f"В хранилище только {len(slots)} шт. "
                        f"**{name}**, нужно {qty}."
                    )

                for slot in slots:
                    cur = await runtime.db.execute(
                        "DELETE FROM inventory "
                        "WHERE user_id = ? AND location = 'storage' "
                        "AND slot = ? AND item_id = ? AND stars = 0 "
                        "AND COALESCE(is_locked, 0) = 0",
                        (user_id, slot, item_id),
                    )
                    if cur.rowcount == 0:
                        raise ValueError(
                            "Предмет уже продан или перемещён."
                        )

                await runtime.db.execute(
                    "UPDATE players SET coins = coins + ?, "
                    "total_coins_earned = total_coins_earned + ? "
                    "WHERE user_id = ?",
                    (proceeds, proceeds, user_id),
                )

                new_price = clamp_market_price(
                    int(price * (1 - 0.01 * qty)),
                    item_price or base_price or price,
                    bool(buyable),
                )
                await runtime.db.execute(
                    "UPDATE market_prices SET supply = supply + ?, "
                    "current_price = ?, last_update = ? "
                    "WHERE item_id = ?",
                    (
                        qty,
                        new_price,
                        datetime.datetime.now().isoformat(),
                        item_id,
                    ),
                )
                await runtime.record_market_price(
                    item_id,
                    new_price,
                    demand0 or 0,
                    (supply0 or 0) + qty,
                    commit=False,
                )
        except ValueError as e:
            return False, f"❌ {e}"

        await runtime.update_quest_progress(user_id, "sell_3", qty)
        await runtime.check_achievements(user_id)
        return True, f"✅ Продано **{name}** ×{qty} за 🪙 {proceeds}."

    async def match_market_orders(
        item_id: str | None = None,
    ) -> list[dict]:
        """Автоматически сопоставляет встречные активные ордера."""
        trades: list[dict] = []
        async with runtime.transaction():
            if item_id:
                query = (
                    "SELECT id, user_id, side, item_id, price, quantity, "
                    "filled, created_at, expires_at FROM market_orders "
                    "WHERE status = 'active' AND item_id = ?"
                )
                params = (item_id,)
            else:
                query = (
                    "SELECT id, user_id, side, item_id, price, quantity, "
                    "filled, created_at, expires_at FROM market_orders "
                    "WHERE status = 'active'"
                )
                params = ()
            async with runtime.db.execute(query, params) as c:
                rows = await c.fetchall()

            now = datetime.datetime.now()
            books: dict[str, dict] = {}
            for (
                oid,
                uid,
                side,
                iid,
                price,
                qty,
                filled,
                created,
                expires,
            ) in rows:
                expires_at = parse_market_datetime(expires)
                if expires_at and expires_at < now:
                    continue
                remaining = (qty or 0) - (filled or 0)
                if remaining <= 0:
                    continue
                books.setdefault(
                    iid, {"buy": [], "sell": []}
                )[side].append(
                    {
                        "id": oid,
                        "user_id": uid,
                        "side": side,
                        "price": int(price or 0),
                        "remaining": remaining,
                        "created_at": created or "",
                    }
                )

            for iid, book in books.items():
                async with runtime.db.execute(
                    "SELECT price, buyable FROM items WHERE id = ?",
                    (iid,),
                ) as c:
                    item_row = await c.fetchone()
                if not item_row:
                    continue
                low, high = market_order_price_bounds(
                    item_row[0], bool(item_row[1])
                )
                buys = sorted(
                    book["buy"],
                    key=lambda o: (
                        -o["price"],
                        o["created_at"],
                        o["id"],
                    ),
                )
                sells = sorted(
                    book["sell"],
                    key=lambda o: (
                        o["price"],
                        o["created_at"],
                        o["id"],
                    ),
                )
                blocked_buyers: set[int] = set()

                while True:
                    pair = None
                    for buy in buys:
                        if buy["remaining"] <= 0:
                            continue
                        if buy["user_id"] in blocked_buyers:
                            continue
                        if not (low <= buy["price"] <= high):
                            continue
                        for sell in sells:
                            if sell["remaining"] <= 0:
                                continue
                            if sell["user_id"] == buy["user_id"]:
                                continue
                            if not (low <= sell["price"] <= high):
                                continue
                            if buy["price"] < sell["price"]:
                                break
                            pair = (buy, sell)
                            break
                        if pair:
                            break
                    if not pair:
                        break

                    buy, sell = pair
                    quantity = min(
                        buy["remaining"], sell["remaining"]
                    )
                    if quantity <= 0:
                        break
                    buy_age = (buy["created_at"], buy["id"])
                    sell_age = (
                        sell["created_at"],
                        sell["id"],
                    )
                    execution_price = (
                        buy["price"]
                        if buy_age <= sell_age
                        else sell["price"]
                    )
                    buyer_id = buy["user_id"]
                    seller_id = sell["user_id"]
                    try:
                        async with runtime.transaction():
                            await runtime.place_items(
                                buyer_id,
                                iid,
                                quantity,
                                commit=False,
                                stars=0,
                            )
                            total = execution_price * quantity
                            await runtime.db.execute(
                                "UPDATE players SET coins = coins + ?, "
                                "total_coins_earned = "
                                "total_coins_earned + ? "
                                "WHERE user_id = ?",
                                (total, total, seller_id),
                            )
                            refund = (
                                buy["price"] - execution_price
                            ) * quantity
                            if refund > 0:
                                await runtime.db.execute(
                                    "UPDATE players SET coins = coins + ? "
                                    "WHERE user_id = ?",
                                    (refund, buyer_id),
                                )
                            await runtime.db.execute(
                                "UPDATE market_orders "
                                "SET filled = filled + ?, "
                                "status = CASE WHEN filled + ? >= quantity "
                                "THEN 'filled' ELSE 'active' END "
                                "WHERE id = ?",
                                (quantity, quantity, buy["id"]),
                            )
                            await runtime.db.execute(
                                "UPDATE market_orders "
                                "SET filled = filled + ?, "
                                "status = CASE WHEN filled + ? >= quantity "
                                "THEN 'filled' ELSE 'active' END "
                                "WHERE id = ?",
                                (quantity, quantity, sell["id"]),
                            )
                            async with runtime.db.execute(
                                "SELECT demand, supply FROM market_prices "
                                "WHERE item_id = ?",
                                (iid,),
                            ) as c:
                                market_row = await c.fetchone()
                            demand, supply = market_row or (0, 0)
                            await runtime.record_market_price(
                                iid,
                                execution_price,
                                demand,
                                supply,
                                commit=False,
                            )
                    except ValueError as exc:
                        blocked_buyers.add(buyer_id)
                        runtime.logger.warning(
                            "MARKET_MATCH: пропуск пары buy#%s/sell#%s: %s",
                            buy["id"],
                            sell["id"],
                            exc,
                        )
                        continue

                    buy["remaining"] -= quantity
                    sell["remaining"] -= quantity
                    trades.append(
                        {
                            "item_id": iid,
                            "buyer_id": buyer_id,
                            "seller_id": seller_id,
                            "buy_order_id": buy["id"],
                            "sell_order_id": sell["id"],
                            "quantity": quantity,
                            "price": execution_price,
                        }
                    )

        for trade in trades:
            await runtime.update_quest_progress(
                trade["buyer_id"], "buy_3", trade["quantity"]
            )
            await runtime.update_quest_progress(
                trade["seller_id"], "sell_3", trade["quantity"]
            )
            await runtime.check_achievements(trade["buyer_id"])
            await runtime.check_achievements(trade["seller_id"])
        return trades

    async def create_market_order(
        user_id: int,
        side: str,
        item_id: str,
        quantity: int,
        price: int,
    ) -> tuple[bool, str]:
        if side not in ("buy", "sell"):
            return False, "❌ Неверная сторона ордера."
        if quantity <= 0 or price <= 0:
            return (
                False,
                "❌ Количество и цена должны быть больше нуля.",
            )

        async with runtime.db.execute(
            "SELECT name, rarity, price, buyable FROM items WHERE id = ?",
            (item_id,),
        ) as c:
            item = await c.fetchone()
        if not item:
            return False, "❌ Предмет не найден."
        name, rarity, item_price, buyable = item
        if runtime.is_synthesis_only(item_id):
            return (
                False,
                "❌ Этот генератор нельзя торговать: только синтез.",
            )
        if rarity not in runtime.order_rarities:
            return False, "❌ Ордера недоступны для этой редкости."
        low, high = market_order_price_bounds(
            item_price, bool(buyable)
        )
        if not (low <= price <= high):
            return (
                False,
                f"❌ Цена ордера вне коридора: 🪙 {low}–{high}.",
            )
        if quantity > runtime.max_order_qty:
            return (
                False,
                f"❌ Максимум {runtime.max_order_qty} предметов "
                "в одном ордере.",
            )
        order_value = price * quantity
        if order_value > runtime.max_order_value:
            return (
                False,
                f"❌ Стоимость ордера больше лимита "
                f"🪙 {runtime.format_price(runtime.max_order_value)}.",
            )
        async with runtime.db.execute(
            "SELECT COUNT(*) FROM market_orders "
            "WHERE user_id = ? AND status = 'active'",
            (user_id,),
        ) as c:
            active_orders = (await c.fetchone())[0] or 0
        if active_orders >= runtime.max_active_orders:
            return (
                False,
                f"❌ У тебя уже {active_orders} активных ордеров. "
                f"Максимум — {runtime.max_active_orders}.",
            )
        async with runtime.db.execute(
            "SELECT COALESCE(SUM(price * quantity), 0) FROM market_orders "
            "WHERE user_id = ? AND date(created_at) = date('now')",
            (user_id,),
        ) as c:
            daily_volume = (await c.fetchone())[0] or 0
        if (
            daily_volume + order_value
            > runtime.max_daily_volume
        ):
            return (
                False,
                f"❌ Дневной лимит ордеров: "
                f"🪙 {runtime.format_price(runtime.max_daily_volume)}.",
            )

        expires = (
            datetime.datetime.now()
            + datetime.timedelta(hours=runtime.order_duration_hours)
        ).isoformat()
        order_id = None
        try:
            async with runtime.transaction():
                if side == "sell":
                    async with runtime.db.execute(
                        "SELECT slot FROM inventory "
                        "WHERE user_id = ? AND location = 'storage' "
                        "AND item_id = ? AND stars = 0 "
                        "AND COALESCE(is_locked, 0) = 0 "
                        "ORDER BY slot ASC LIMIT ?",
                        (user_id, item_id, quantity),
                    ) as c:
                        slots = [r[0] for r in await c.fetchall()]
                    if len(slots) < quantity:
                        raise ValueError(
                            f"В хранилище только {len(slots)} шт. "
                            f"**{name}**."
                        )
                    for slot in slots:
                        await runtime.db.execute(
                            "DELETE FROM inventory "
                            "WHERE user_id = ? AND location = 'storage' "
                            "AND slot = ? AND item_id = ?",
                            (user_id, slot, item_id),
                        )
                else:
                    total = price * quantity
                    cur = await runtime.db.execute(
                        "UPDATE players SET coins = coins - ? "
                        "WHERE user_id = ? AND coins >= ?",
                        (total, user_id, total),
                    )
                    if cur.rowcount == 0:
                        raise ValueError(
                            f"Нужно 🪙 {total} для резерва."
                        )

                cursor = await runtime.db.execute(
                    "INSERT INTO market_orders "
                    "(user_id, side, item_id, stars, price, quantity, "
                    "filled, status, expires_at) "
                    "VALUES (?, ?, ?, 0, ?, ?, 0, 'active', ?)",
                    (
                        user_id,
                        side,
                        item_id,
                        price,
                        quantity,
                        expires,
                    ),
                )
                order_id = cursor.lastrowid
        except ValueError as e:
            return False, f"❌ {e}"

        match_failed = False
        try:
            await match_market_orders(item_id)
        except Exception:
            runtime.logger.exception(
                "MARKET_MATCH: не удалось сопоставить ордера"
            )
            match_failed = True

        async with runtime.db.execute(
            "SELECT filled, status FROM market_orders WHERE id = ?",
            (order_id,),
        ) as c:
            order_state = await c.fetchone()
        filled, status = order_state or (0, "active")
        remaining = max(0, quantity - (filled or 0))

        if side == "sell":
            message = (
                f"✅ Ордер на продажу **{name}** ×{quantity} "
                f"по 🪙 {price} создан."
            )
        else:
            message = (
                f"✅ Ордер на покупку **{name}** ×{quantity} "
                f"по 🪙 {price} создан. "
                f"Резерв: 🪙 {price * remaining}."
            )
        if filled:
            if status == "filled":
                message += f"\n⚡ Сразу исполнено: **{filled}** шт."
            else:
                message += (
                    f"\n⚡ Сразу исполнено: **{filled}** шт., "
                    f"осталось **{remaining}**."
                )
        elif match_failed:
            message += "\n⚠️ Автосопоставление временно недоступно."
        return True, message

    async def fill_market_order(
        order_id: int, user_id: int
    ) -> tuple[bool, str]:
        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT user_id, side, item_id, stars, price, quantity, "
                    "filled, status, expires_at "
                    "FROM market_orders WHERE id = ?",
                    (order_id,),
                ) as c:
                    order = await c.fetchone()
                if not order:
                    raise ValueError("Ордер не найден.")
                (
                    owner_id,
                    side,
                    item_id,
                    stars,
                    price,
                    quantity,
                    filled,
                    status,
                    expires_at,
                ) = order
                if status != "active":
                    raise ValueError("Ордер уже закрыт.")
                if (
                    datetime.datetime.fromisoformat(expires_at)
                    < datetime.datetime.now()
                ):
                    raise ValueError("Ордер истёк.")
                if owner_id == user_id:
                    raise ValueError("Нельзя исполнить свой ордер.")

                async with runtime.db.execute(
                    "SELECT price, buyable FROM items WHERE id = ?",
                    (item_id,),
                ) as c:
                    item_row = await c.fetchone()
                if not item_row:
                    raise ValueError("Предмет не найден.")
                item_price, item_buyable = item_row
                low, high = market_order_price_bounds(
                    item_price, bool(item_buyable)
                )
                if not (low <= price <= high):
                    raise ValueError(
                        "Цена ордера устарела и вышла за коридор. "
                        "Попроси продавца создать новый ордер."
                    )

                remaining = quantity - filled
                if remaining <= 0:
                    raise ValueError("Ордер уже исполнен.")
                total = price * remaining

                if side == "sell":
                    cur = await runtime.db.execute(
                        "UPDATE players SET coins = coins - ? "
                        "WHERE user_id = ? AND coins >= ?",
                        (total, user_id, total),
                    )
                    if cur.rowcount == 0:
                        raise ValueError("Недостаточно монет.")
                    await runtime.db.execute(
                        "UPDATE players SET coins = coins + ?, "
                        "total_coins_earned = total_coins_earned + ? "
                        "WHERE user_id = ?",
                        (total, total, owner_id),
                    )
                    await runtime.place_items(
                        user_id,
                        item_id,
                        remaining,
                        commit=False,
                        stars=stars or 0,
                    )
                    buyer_id, seller_id = user_id, owner_id
                else:
                    async with runtime.db.execute(
                        "SELECT slot FROM inventory "
                        "WHERE user_id = ? AND location = 'storage' "
                        "AND item_id = ? AND stars = 0 "
                        "AND COALESCE(is_locked, 0) = 0 "
                        "ORDER BY slot ASC LIMIT ?",
                        (user_id, item_id, remaining),
                    ) as c:
                        slots = [r[0] for r in await c.fetchall()]
                    if len(slots) < remaining:
                        raise ValueError(
                            f"В хранилище только {len(slots)} шт., "
                            f"нужно {remaining}."
                        )
                    for slot in slots:
                        cur = await runtime.db.execute(
                            "DELETE FROM inventory "
                            "WHERE user_id = ? AND location = 'storage' "
                            "AND slot = ? AND item_id = ?",
                            (user_id, slot, item_id),
                        )
                        if cur.rowcount == 0:
                            raise ValueError(
                                "Предмет уже продан или перемещён."
                            )
                    await runtime.place_items(
                        owner_id,
                        item_id,
                        remaining,
                        commit=False,
                        stars=stars or 0,
                    )
                    await runtime.db.execute(
                        "UPDATE players SET coins = coins + ?, "
                        "total_coins_earned = total_coins_earned + ? "
                        "WHERE user_id = ?",
                        (total, total, user_id),
                    )
                    buyer_id, seller_id = owner_id, user_id

                new_filled = filled + remaining
                await runtime.db.execute(
                    "UPDATE market_orders SET filled = ?, status = ? "
                    "WHERE id = ?",
                    (
                        new_filled,
                        (
                            "filled"
                            if new_filled >= quantity
                            else "active"
                        ),
                        order_id,
                    ),
                )
                async with runtime.db.execute(
                    "SELECT demand, supply FROM market_prices "
                    "WHERE item_id = ?",
                    (item_id,),
                ) as c:
                    market_row = await c.fetchone()
                demand, supply = market_row or (0, 0)
                await runtime.record_market_price(
                    item_id, price, demand, supply, commit=False
                )
        except ValueError as e:
            return False, f"❌ {e}"

        await runtime.update_quest_progress(
            buyer_id, "buy_3", remaining
        )
        await runtime.update_quest_progress(
            seller_id, "sell_3", remaining
        )
        await runtime.check_achievements(buyer_id)
        await runtime.check_achievements(seller_id)
        return True, (
            f"✅ Ордер #{order_id} исполнен: **{remaining}** шт. "
            f"по 🪙 {price} (всего 🪙 {price * remaining})."
        )

    async def cancel_market_order(
        order_id: int, user_id: int
    ) -> tuple[bool, str]:
        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT user_id, side, item_id, price, quantity, "
                    "filled, status FROM market_orders WHERE id = ?",
                    (order_id,),
                ) as c:
                    order = await c.fetchone()
                if not order:
                    raise ValueError("Ордер не найден.")
                (
                    owner_id,
                    side,
                    item_id,
                    price,
                    quantity,
                    filled,
                    status,
                ) = order
                if owner_id != user_id:
                    raise ValueError("Это не твой ордер.")
                if status != "active":
                    raise ValueError("Ордер уже закрыт.")
                remaining = quantity - filled
                if remaining <= 0:
                    raise ValueError("Ордер уже исполнен.")

                if side == "sell":
                    await runtime.place_items(
                        user_id,
                        item_id,
                        remaining,
                        commit=False,
                        stars=0,
                    )
                else:
                    refund = price * remaining
                    await runtime.db.execute(
                        "UPDATE players SET coins = coins + ?, "
                        "total_coins_earned = total_coins_earned + ? "
                        "WHERE user_id = ?",
                        (refund, refund, user_id),
                    )

                await runtime.db.execute(
                    "UPDATE market_orders SET status = 'cancelled' "
                    "WHERE id = ?",
                    (order_id,),
                )
        except ValueError as e:
            return False, f"❌ {e}"
        return True, f"✅ Ордер #{order_id} отменён."

    async def expire_market_orders():
        now = datetime.datetime.now().isoformat()
        async with runtime.transaction():
            async with runtime.db.execute(
                "SELECT id, user_id, side, item_id, price, quantity, filled "
                "FROM market_orders "
                "WHERE status = 'active' AND expires_at < ?",
                (now,),
            ) as c:
                orders = await c.fetchall()

            for (
                order_id,
                user_id,
                side,
                item_id,
                price,
                quantity,
                filled,
            ) in orders:
                remaining = max(
                    0, (quantity or 0) - (filled or 0)
                )
                if remaining <= 0:
                    await runtime.db.execute(
                        "UPDATE market_orders SET status = 'expired' "
                        "WHERE id = ?",
                        (order_id,),
                    )
                    continue
                if side == "buy":
                    refund = (price or 0) * remaining
                    await runtime.db.execute(
                        "UPDATE players SET coins = coins + ?, "
                        "total_coins_earned = total_coins_earned + ? "
                        "WHERE user_id = ?",
                        (refund, refund, user_id),
                    )
                else:
                    try:
                        await runtime.place_items(
                            user_id,
                            item_id,
                            remaining,
                            commit=False,
                            stars=0,
                        )
                    except ValueError:
                        await runtime.grant_compensation(
                            user_id, item_id, remaining
                        )
                await runtime.db.execute(
                    "UPDATE market_orders SET status = 'expired' "
                    "WHERE id = ?",
                    (order_id,),
                )

    return (
        buy_market_item,
        sell_market_item,
        match_market_orders,
        create_market_order,
        fill_market_order,
        cancel_market_order,
        expire_market_orders,
    )
