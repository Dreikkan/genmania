"""Auction lifecycle service.

Keeps bid/buyout rules and DB writes in one place. Discord objects,
achievements, quests and item delivery are injected through runtime
getters so existing monkeypatches on ``bot.py`` keep working.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable

import discord


class AuctionRuntime:
    """Адаптер между bot.py и аукционным сервисом."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._bot_getter: Callable[[], Any] = lambda: None
        self._quest_getter: Callable[[], Callable] = lambda: None
        self._achievements_getter: Callable[[], Callable] = lambda: None
        self._place_items_getter: Callable[[], Callable] = lambda: None
        self._compensation_getter: Callable[[], Callable] = lambda: None
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self.anti_snipe_seconds = 120
        self.fee_rate = 0.05
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        bot_getter: Callable[[], Any],
        quest_getter: Callable[[], Callable],
        achievements_getter: Callable[[], Callable],
        place_items_getter: Callable[[], Callable],
        compensation_getter: Callable[[], Callable],
        emoji_getter: Callable[[], Callable],
        embed_factory: Callable[..., Any],
        anti_snipe_seconds: int,
        fee_rate: float,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._bot_getter = bot_getter
        self._quest_getter = quest_getter
        self._achievements_getter = achievements_getter
        self._place_items_getter = place_items_getter
        self._compensation_getter = compensation_getter
        self._emoji_getter = emoji_getter
        self._embed_factory = embed_factory
        self.anti_snipe_seconds = anti_snipe_seconds
        self.fee_rate = fee_rate
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    @property
    def bot(self):
        return self._bot_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    def emoji(self, key: str):
        return self._emoji_getter()(key)

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    async def update_quest_progress(self, *args, **kwargs) -> None:
        await self._quest_getter()(*args, **kwargs)

    async def check_achievements(self, *args, **kwargs) -> None:
        await self._achievements_getter()(*args, **kwargs)

    async def place_items(self, *args, **kwargs):
        return await self._place_items_getter()(*args, **kwargs)

    async def grant_compensation(self, *args, **kwargs):
        return await self._compensation_getter()(*args, **kwargs)


def make_auction_layer(runtime: AuctionRuntime):
    """Возвращает auction-функции, привязанные к runtime."""

    async def release_active_auction_bids(user_id: int) -> tuple[int, int]:
        """Снимает активные ставки игрока на чужих лотах.

        Возвращает (количество лотов, сумма возврата). Вызывать только
        внутри db_transaction. Лот возвращается к стартовой цене и снова
        доступен для ставок.
        """
        async with runtime.db.execute(
            "SELECT id, current_bid, start_price FROM auctions "
            "WHERE current_bidder = ? AND status = 'active' "
            "AND COALESCE(seller_id, 0) != ?",
            (user_id, user_id),
        ) as c:
            lots = await c.fetchall()

        total_refund = 0
        for auction_id, current_bid, start_price in lots:
            refund = max(0, int(current_bid or 0))
            if refund:
                await runtime.db.execute(
                    "UPDATE players SET coins = coins + ? WHERE user_id = ?",
                    (refund, user_id),
                )
                total_refund += refund
            await runtime.db.execute(
                "UPDATE auctions SET current_bid = ?, current_bidder = NULL "
                "WHERE id = ? AND status = 'active' AND current_bidder = ?",
                (max(0, int(start_price or 0)), auction_id, user_id),
            )
            if refund:
                await runtime.db.execute(
                    "INSERT INTO auction_bids "
                    "(auction_id, bidder_id, amount, kind) "
                    "VALUES (?, ?, ?, 'refund')",
                    (auction_id, user_id, refund),
                )
        return len(lots), total_refund

    async def place_auction_bid(
        user_id: int, auction_id: int, amount: int
    ) -> tuple[bool, str, int | None, bool]:
        """Ставит ставку. Возвращает (ok, message, previous_bidder, extended)."""
        previous_bidder = None
        extended = False
        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT seller_id, current_bid, current_bidder, buyout_price, "
                    "end_time, status FROM auctions WHERE id = ?",
                    (auction_id,),
                ) as c:
                    lot = await c.fetchone()
                if not lot:
                    raise ValueError("Лот не найден.")

                (
                    seller_id,
                    current_bid,
                    current_bidder,
                    buyout_price,
                    end_time,
                    status,
                ) = lot
                if status != "active":
                    raise ValueError("Лот уже закрыт.")
                end_dt = datetime.datetime.fromisoformat(end_time)
                if end_dt < datetime.datetime.now():
                    raise ValueError("Время лота истекло.")
                if user_id == seller_id:
                    raise ValueError("Нельзя ставить на свой лот.")
                if amount <= (current_bid or 0):
                    raise ValueError(f"Ставка должна быть > {current_bid}.")
                if buyout_price and amount >= buyout_price:
                    raise ValueError(
                        "Ставка должна быть ниже Buyout. "
                        "Используй «Купить сразу»."
                    )

                async with runtime.db.execute(
                    "SELECT coins FROM players WHERE user_id = ?", (user_id,)
                ) as c:
                    coins_row = await c.fetchone()
                coins = (coins_row[0] if coins_row else 0) or 0
                if coins < amount:
                    raise ValueError("Недостаточно монет.")

                if current_bidder:
                    await runtime.db.execute(
                        "UPDATE players SET coins = coins + ? WHERE user_id = ?",
                        (current_bid, current_bidder),
                    )

                cur = await runtime.db.execute(
                    "UPDATE players SET coins = coins - ? "
                    "WHERE user_id = ? AND coins >= ?",
                    (amount, user_id, amount),
                )
                if cur.rowcount == 0:
                    raise ValueError("Недостаточно монет (баланс изменился).")

                await runtime.db.execute(
                    "UPDATE auctions SET current_bid = ?, current_bidder = ? "
                    "WHERE id = ?",
                    (amount, user_id, auction_id),
                )

                if (
                    end_dt - datetime.datetime.now()
                ).total_seconds() < runtime.anti_snipe_seconds:
                    new_end = (
                        datetime.datetime.now() + datetime.timedelta(minutes=2)
                    ).isoformat()
                    await runtime.db.execute(
                        "UPDATE auctions SET end_time = ? WHERE id = ?",
                        (new_end, auction_id),
                    )
                    extended = True

                await runtime.db.execute(
                    "INSERT INTO auction_bids "
                    "(auction_id, bidder_id, amount, kind) "
                    "VALUES (?, ?, ?, 'bid')",
                    (auction_id, user_id, amount),
                )
                previous_bidder = current_bidder
        except ValueError as e:
            return False, f"❌ {e}", None, False

        await runtime.update_quest_progress(user_id, "bid_auction")

        if previous_bidder and previous_bidder != user_id:
            prev_user = runtime.bot.get_user(previous_bidder)
            if prev_user:
                try:
                    await prev_user.send(
                        f"🏛️ Твою ставку на лоте #{auction_id} перебили: "
                        f"🪙 {amount}."
                    )
                except (
                    discord.Forbidden,
                    discord.NotFound,
                    discord.HTTPException,
                ):
                    pass

        message = (
            f"{runtime.emoji('_approve')} Ставка 🪙 {amount} принята. "
            "Ты лидер лота!"
        )
        if extended:
            message += "\n⏱ Лот продлён на 2 минуты."
        return True, message, previous_bidder, extended

    async def buyout_auction(
        user_id: int, auction_id: int
    ) -> tuple[bool, str, int]:
        """Выкупает лот по buyout-цене. Возвращает (ok, message, compensation)."""
        compensation = 0
        mailbox_sent = False
        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT seller_id, item_id, stars, current_bid, "
                    "current_bidder, buyout_price, end_time, status "
                    "FROM auctions WHERE id = ?",
                    (auction_id,),
                ) as c:
                    lot = await c.fetchone()
                if not lot:
                    raise ValueError("Лот не найден.")

                (
                    seller_id,
                    item_id,
                    stars,
                    current_bid,
                    current_bidder,
                    buyout_price,
                    end_time,
                    status,
                ) = lot
                if status != "active":
                    raise ValueError("Лот уже закрыт.")
                if (
                    datetime.datetime.fromisoformat(end_time)
                    < datetime.datetime.now()
                ):
                    raise ValueError("Время лота истекло.")
                if user_id == seller_id:
                    raise ValueError("Нельзя купить свой лот.")
                if not buyout_price:
                    raise ValueError("У этого лота нет Buyout.")
                if buyout_price <= (current_bid or 0):
                    raise ValueError("Buyout уже перекрыт текущей ставкой.")

                async with runtime.db.execute(
                    "SELECT coins FROM players WHERE user_id = ?", (user_id,)
                ) as c:
                    coins_row = await c.fetchone()
                coins = (coins_row[0] if coins_row else 0) or 0
                if coins < buyout_price:
                    raise ValueError("Недостаточно монет для выкупа.")

                if current_bidder:
                    await runtime.db.execute(
                        "UPDATE players SET coins = coins + ? WHERE user_id = ?",
                        (current_bid, current_bidder),
                    )

                cur = await runtime.db.execute(
                    "UPDATE players SET coins = coins - ? "
                    "WHERE user_id = ? AND coins >= ?",
                    (buyout_price, user_id, buyout_price),
                )
                if cur.rowcount == 0:
                    raise ValueError("Недостаточно монет (баланс изменился).")

                fee = int(buyout_price * runtime.fee_rate)
                seller_net = buyout_price - fee
                await runtime.db.execute(
                    "UPDATE players SET coins = coins + ?, "
                    "total_coins_earned = total_coins_earned + ? "
                    "WHERE user_id = ?",
                    (seller_net, seller_net, seller_id),
                )

                try:
                    await runtime.place_items(
                        user_id, item_id, 1, commit=False, stars=stars or 0
                    )
                except ValueError:
                    await runtime.grant_compensation(
                        user_id, item_id, 1, stars or 0
                    )
                    mailbox_sent = True

                await runtime.db.execute(
                    "UPDATE auctions SET status = 'finished', current_bid = ?, "
                    "current_bidder = ?, end_time = ? WHERE id = ?",
                    (
                        buyout_price,
                        user_id,
                        datetime.datetime.now().isoformat(),
                        auction_id,
                    ),
                )
                await runtime.db.execute(
                    "INSERT INTO auction_bids "
                    "(auction_id, bidder_id, amount, kind) "
                    "VALUES (?, ?, ?, 'buyout')",
                    (auction_id, user_id, buyout_price),
                )
        except ValueError as e:
            return False, f"❌ {e}", 0

        await runtime.update_quest_progress(user_id, "bid_auction")
        await runtime.check_achievements(user_id)
        message = (
            f"{runtime.emoji('_approve')} Лот #{auction_id} куплен за "
            f"🪙 {buyout_price}!"
        )
        if mailbox_sent:
            message += "\nНет места — предмет отправлен в почту."
        return True, message, compensation

    async def build_auction_history_embed(auction_id: int):
        async with runtime.db.execute(
            "SELECT a.seller_id, a.item_id, a.stars, a.current_bid, "
            "a.current_bidder, a.buyout_price, a.end_time, a.status, "
            "i.name, i.emoji "
            "FROM auctions a LEFT JOIN items i ON i.id = a.item_id "
            "WHERE a.id = ?",
            (auction_id,),
        ) as c:
            lot = await c.fetchone()

        embed = runtime.embed(
            title=f"{runtime.emoji('_history')} История лота #{auction_id}",
            color=0xf1c40f,
        )
        if not lot:
            embed.description = "Лот не найден."
            return embed

        (
            seller_id,
            item_id,
            stars,
            current_bid,
            current_bidder,
            buyout_price,
            end_time,
            status,
            name,
            item_emoji,
        ) = lot
        embed.description = (
            f"{item_emoji or '📦'} **{name or item_id}** ({stars}★)\n"
            f"Продавец: <@{seller_id}> · Статус: **{status}**"
        )

        async with runtime.db.execute(
            "SELECT bidder_id, amount, COALESCE(kind, 'bid'), timestamp "
            "FROM auction_bids WHERE auction_id = ? ORDER BY id DESC LIMIT 10",
            (auction_id,),
        ) as c:
            bids = await c.fetchall()

        if bids:
            lines = []
            for bidder_id, amount, kind, timestamp in bids:
                if kind == "buyout":
                    icon = runtime.emoji("_approve")
                    kind_name = "выкуп"
                elif kind == "refund":
                    icon = runtime.emoji("_back")
                    kind_name = "возврат"
                else:
                    icon = runtime.emoji("_coin")
                    kind_name = "ставка"
                lines.append(
                    f"{icon} <@{bidder_id}> — 🪙 **{amount}** ({kind_name})\n"
                    f"`{str(timestamp)[:16]}`"
                )
            embed.add_field(
                name="Последние ставки",
                value="\n".join(lines),
                inline=False,
            )
        else:
            embed.add_field(
                name="Последние ставки",
                value="Ставок пока нет.",
                inline=False,
            )

        embed.add_field(
            name="Итог",
            value=(
                f"Текущая ставка: 🪙 **{current_bid}**\n"
                f"Лидер: "
                f"{f'<@{current_bidder}>' if current_bidder else 'нет'}\n"
                f"Buyout: "
                f"{f'🪙 **{buyout_price}**' if buyout_price else 'нет'}\n"
                f"До: `{str(end_time)[:16]}`"
            ),
            inline=False,
        )
        return embed

    return (
        release_active_auction_bids,
        place_auction_bid,
        buyout_auction,
        build_auction_history_embed,
    )
