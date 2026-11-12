import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_market_matching_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "UPDATE items SET price = 15 WHERE id = 'basic_gen'"
    )
    await db.execute(
        "UPDATE market_prices SET base_price = 15, current_price = 15 "
        "WHERE item_id = 'basic_gen'"
    )
    await db.execute(
        "INSERT INTO players (user_id, coins) VALUES "
        "(1, 100), (2, 10000), (3, 100), (4, 10000)"
    )
    await db.execute(
        "INSERT INTO inventory (user_id, slot, item_id, location, stars) VALUES "
        "(1, 0, 'basic_gen', 'storage', 0), "
        "(1, 1, 'basic_gen', 'storage', 0), "
        "(1, 2, 'basic_gen', 'storage', 0), "
        "(3, 0, 'basic_gen', 'storage', 0), "
        "(3, 1, 'basic_gen', 'storage', 0)"
    )
    await db.commit()
    return db


async def _order(db, order_id):
    async with db.execute(
        "SELECT user_id, side, price, quantity, filled, status "
        "FROM market_orders WHERE id = ?",
        (order_id,),
    ) as c:
        return await c.fetchone()


async def _coins(db, user_id):
    async with db.execute(
        "SELECT coins FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        return (await c.fetchone())[0]


async def _inventory_count(db, user_id, item_id="basic_gen"):
    async with db.execute(
        "SELECT COUNT(*) FROM inventory WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    ) as c:
        return (await c.fetchone())[0]


def test_buy_order_matches_resting_sell_at_sell_price():
    async def run():
        db = await _init()
        try:
            ok, _ = await m.create_market_order(1, "sell", "basic_gen", 3, 12)
            assert ok
            ok, message = await m.create_market_order(
                2, "buy", "basic_gen", 5, 15
            )
            assert ok
            assert "Сразу исполнено: **3**" in message

            async with db.execute(
                "SELECT id FROM market_orders ORDER BY id"
            ) as c:
                sell_id, buy_id = [row[0] for row in await c.fetchall()]
            assert await _order(db, sell_id) == (1, "sell", 12, 3, 3, "filled")
            assert await _order(db, buy_id) == (2, "buy", 15, 5, 3, "active")

            assert await _coins(db, 1) == 136
            assert await _coins(db, 2) == 9934
            assert await _inventory_count(db, 2) == 3
            assert await _inventory_count(db, 1) == 0
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_sell_order_matches_resting_buy_at_buy_price():
    async def run():
        db = await _init()
        try:
            ok, _ = await m.create_market_order(2, "buy", "basic_gen", 4, 15)
            assert ok
            assert await _coins(db, 2) == 9940

            ok, message = await m.create_market_order(
                1, "sell", "basic_gen", 2, 12
            )
            assert ok
            assert "Сразу исполнено: **2**" in message

            async with db.execute(
                "SELECT id FROM market_orders ORDER BY id"
            ) as c:
                buy_id, sell_id = [row[0] for row in await c.fetchall()]
            assert await _order(db, buy_id) == (2, "buy", 15, 4, 2, "active")
            assert await _order(db, sell_id) == (1, "sell", 12, 2, 2, "filled")
            assert await _coins(db, 1) == 130
            assert await _coins(db, 2) == 9940
            assert await _inventory_count(db, 2) == 2
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_price_priority_matches_lowest_sell_first():
    async def run():
        db = await _init()
        try:
            assert (await m.create_market_order(
                1, "sell", "basic_gen", 1, 12
            ))[0]
            assert (await m.create_market_order(
                3, "sell", "basic_gen", 1, 13
            ))[0]

            ok, message = await m.create_market_order(
                2, "buy", "basic_gen", 2, 15
            )
            assert ok
            assert "Сразу исполнено: **2**" in message

            assert await _coins(db, 1) == 112
            assert await _coins(db, 3) == 113
            assert await _coins(db, 2) == 9975
            assert await _inventory_count(db, 2) == 2
            async with db.execute(
                "SELECT price FROM market_history WHERE item_id = 'basic_gen' "
                "ORDER BY id DESC LIMIT 2"
            ) as c:
                prices = [row[0] for row in await c.fetchall()]
            assert prices == [13, 12], prices
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_self_match_is_skipped():
    async def run():
        db = await _init()
        try:
            await db.execute("UPDATE players SET coins = 10000 WHERE user_id = 1")
            await db.commit()
            assert (await m.create_market_order(
                1, "sell", "basic_gen", 2, 12
            ))[0]
            assert (await m.create_market_order(
                1, "buy", "basic_gen", 2, 15
            ))[0]

            async with db.execute(
                "SELECT side, filled, status FROM market_orders ORDER BY id"
            ) as c:
                rows = await c.fetchall()
            assert rows == [("sell", 0, "active"), ("buy", 0, "active")]
            assert await _inventory_count(db, 1) == 1
            assert await _coins(db, 1) == 9970
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_no_space_buyer_does_not_move_money_and_can_retry():
    async def run():
        db = await _init()
        original_place_items = m.place_items

        async def fail_for_buyer(user_id, item_id, quantity, **kwargs):
            if user_id == 2:
                raise ValueError("нет места")
            return await original_place_items(
                user_id, item_id, quantity, **kwargs
            )

        try:
            assert (await m.create_market_order(
                1, "sell", "basic_gen", 1, 12
            ))[0]
            m.place_items = fail_for_buyer
            ok, _ = await m.create_market_order(2, "buy", "basic_gen", 1, 15)
            assert ok
            assert await _coins(db, 1) == 100
            assert await _coins(db, 2) == 9985
            assert await _inventory_count(db, 2) == 0

            async with db.execute(
                "SELECT filled, status FROM market_orders WHERE side = 'sell'"
            ) as c:
                assert await c.fetchone() == (0, "active")

            m.place_items = original_place_items
            trades = await m.match_market_orders("basic_gen")
            assert len(trades) == 1
            assert await _coins(db, 1) == 112
            assert await _coins(db, 2) == 9988
            assert await _inventory_count(db, 2) == 1
        finally:
            m.place_items = original_place_items
            await db.close()
            m.bot.db = None

    asyncio.run(run())
