import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_market_order_edges_extra", BOT_PATH
)
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
        "(1, 1000), (2, 1000), (3, 0)"
    )
    await db.execute(
        "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
        "VALUES (1, 0, 'basic_gen', 'storage', 0), "
        "(1, 1, 'basic_gen', 'storage', 0)"
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


async def _insert_order(
    db,
    user_id,
    side,
    price,
    quantity=1,
    filled=0,
    status="active",
):
    expires = (
        datetime.datetime.now() + datetime.timedelta(hours=1)
    ).isoformat()
    await db.execute(
        "INSERT INTO market_orders "
        "(user_id, side, item_id, stars, price, quantity, filled, "
        "status, created_at, expires_at) "
        "VALUES (?, ?, 'basic_gen', 0, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            side,
            price,
            quantity,
            filled,
            status,
            datetime.datetime.now().isoformat(),
            expires,
        ),
    )
    await db.commit()
    async with db.execute("SELECT last_insert_rowid()") as c:
        return (await c.fetchone())[0]


async def _order_state(db, order_id):
    async with db.execute(
        "SELECT filled, status FROM market_orders WHERE id = ?",
        (order_id,),
    ) as c:
        return await c.fetchone()


def test_craft_cost_for_missing_item():
    assert m.craft_cost_for_item("missing") == m.CRAFT_COST_LATE


def test_match_skips_sell_outside_corridor():
    async def run():
        db = await _init()
        try:
            sell_id = await _insert_order(db, 1, "sell", 10)
            buy_id = await _insert_order(db, 2, "buy", 15)
            await m.match_market_orders("basic_gen")
            assert await _order_state(db, sell_id) == (0, "active")
            assert await _order_state(db, buy_id) == (0, "active")
        finally:
            await _close(db)

    asyncio.run(run())


def test_match_stops_when_buy_price_below_sell():
    async def run():
        db = await _init()
        try:
            buy_id = await _insert_order(db, 2, "buy", 13)
            sell_id = await _insert_order(db, 1, "sell", 14)
            await m.match_market_orders("basic_gen")
            assert await _order_state(db, buy_id) == (0, "active")
            assert await _order_state(db, sell_id) == (0, "active")
        finally:
            await _close(db)

    asyncio.run(run())


def test_buy_order_reserve_failure():
    async def run():
        db = await _init()
        try:
            ok, message = await m.create_market_order(
                3, "buy", "basic_gen", 2, 15
            )
            assert not ok
            assert "Нужно" in message
        finally:
            await _close(db)

    asyncio.run(run())


def test_market_match_failure_message():
    async def run():
        db = await _init()
        try:
            runtime = m.MARKET_ORDER_RUNTIME
            original = runtime.match_market_orders

            async def fail(*args, **kwargs):
                raise RuntimeError("probe")

            runtime.match_market_orders = fail
            try:
                ok, message = await m.create_market_order(
                    1, "sell", "basic_gen", 1, 15
                )
            finally:
                runtime.match_market_orders = original
            assert ok
            assert "Автосопоставление" in message
        finally:
            await _close(db)

    asyncio.run(run())


def test_fill_already_filled_order():
    async def run():
        db = await _init()
        try:
            order_id = await _insert_order(
                db, 1, "sell", 15, quantity=1, filled=1
            )
            ok, message = await m.fill_market_order(order_id, 2)
            assert not ok
            assert "уже исполнен" in message
        finally:
            await _close(db)

    asyncio.run(run())


def test_fill_sell_order_without_coins():
    async def run():
        db = await _init()
        try:
            order_id = await _insert_order(db, 1, "sell", 15)
            ok, message = await m.fill_market_order(order_id, 3)
            assert not ok
            assert "Недостаточно монет" in message
        finally:
            await _close(db)

    asyncio.run(run())


class _DeletedCursor:
    rowcount = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def __await__(self):
        async def _inner():
            return self

        return _inner().__await__()


class _RaceDB:
    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def execute(self, sql, params=()):
        if sql.lstrip().startswith("DELETE FROM inventory"):
            return _DeletedCursor()
        return self._db.execute(sql, params)


def test_fill_buy_order_inventory_race():
    async def run():
        db = await _init()
        real_db = db
        try:
            order_id = await _insert_order(db, 2, "buy", 15)
            m.bot.db = _RaceDB(real_db)
            ok, message = await m.fill_market_order(order_id, 1)
            assert not ok
            assert "уже продан" in message
        finally:
            m.bot.db = real_db
            await _close(real_db)

    asyncio.run(run())


def test_fill_buy_order_without_items():
    async def run():
        db = await _init()
        try:
            order_id = await _insert_order(db, 2, "buy", 15)
            ok, message = await m.fill_market_order(order_id, 3)
            assert not ok
            assert "В хранилище только" in message
        finally:
            await _close(db)

    asyncio.run(run())
