import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_order_book_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute("INSERT INTO players (user_id, coins) VALUES (1, 1000)")
    await db.commit()
    return db


def test_order_book_levels_and_spread():
    async def run():
        db = await _init()
        try:
            now = datetime.datetime.now()
            expires = (now + datetime.timedelta(hours=1)).isoformat()
            created = now.isoformat()
            rows = [
                (1, "sell", "basic_gen", 0, 18, 5, 0, "active", created, expires),
                (2, "sell", "basic_gen", 0, 20, 3, 0, "active", created, expires),
                (1, "buy", "basic_gen", 0, 15, 4, 0, "active", created, expires),
                (2, "buy", "basic_gen", 0, 12, 6, 0, "active", created, expires),
            ]
            await db.executemany(
                "INSERT INTO market_orders "
                "(user_id, side, item_id, stars, price, quantity, filled, "
                "status, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            await db.commit()

            embed = await m.build_order_book_embed("basic_gen")
            assert "Стакан" in embed.title
            values = "\n".join(field.value for field in embed.fields)
            assert "18" in values and "20" in values
            assert "15" in values and "12" in values
            assert values.index("18") < values.index("20")
            assert values.index("15") < values.index("12")
            assert "Спред" in embed.description

            synthesis_only = await m.build_order_book_embed("space_gen")
            assert "только через синтез" in synthesis_only.description.lower()
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_order_limits_quantity_value_and_active_orders():
    async def run():
        db = await _init()
        try:
            old_qty = m.MARKET_MAX_ORDER_QTY
            old_value = m.MARKET_MAX_ORDER_VALUE
            old_active = m.MARKET_MAX_ACTIVE_ORDERS
            old_daily = m.MARKET_MAX_DAILY_VOLUME
            try:
                m.MARKET_MAX_ORDER_QTY = 100
                m.MARKET_MAX_ORDER_VALUE = 10_000_000
                m.MARKET_MAX_ACTIVE_ORDERS = 1
                m.MARKET_MAX_DAILY_VOLUME = 50_000_000

                ok, message = await m.create_market_order(
                    1, "buy", "basic_gen", 101, 15
                )
                assert ok is False and "Максимум" in message, message

                m.MARKET_MAX_ORDER_VALUE = 10
                ok, message = await m.create_market_order(
                    1, "buy", "basic_gen", 1, 15
                )
                assert ok is False and "лимита" in message.lower(), message

                m.MARKET_MAX_ORDER_VALUE = 10_000_000
                m.MARKET_MAX_ACTIVE_ORDERS = 1
                ok, message = await m.create_market_order(
                    1, "buy", "basic_gen", 1, 15
                )
                assert ok is True, message
                ok, message = await m.create_market_order(
                    1, "buy", "basic_gen", 1, 15
                )
                assert ok is False and "активных ордеров" in message, message
            finally:
                m.MARKET_MAX_ORDER_QTY = old_qty
                m.MARKET_MAX_ORDER_VALUE = old_value
                m.MARKET_MAX_ACTIVE_ORDERS = old_active
                m.MARKET_MAX_DAILY_VOLUME = old_daily
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_daily_order_volume_limit():
    async def run():
        db = await _init()
        try:
            old_daily = m.MARKET_MAX_DAILY_VOLUME
            old_active = m.MARKET_MAX_ACTIVE_ORDERS
            try:
                m.MARKET_MAX_DAILY_VOLUME = 20
                m.MARKET_MAX_ACTIVE_ORDERS = 10
                ok, message = await m.create_market_order(
                    1, "buy", "basic_gen", 1, 15
                )
                assert ok is True, message
                ok, message = await m.create_market_order(
                    1, "buy", "basic_gen", 1, 15
                )
                assert ok is False and "Дневной лимит" in message, message
            finally:
                m.MARKET_MAX_DAILY_VOLUME = old_daily
                m.MARKET_MAX_ACTIVE_ORDERS = old_active
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_order_book_buttons_exist():
    market = m.MarketView(1, total_pages=1)
    market_labels = [
        child.label
        for child in market.children
        if isinstance(child, m.discord.ui.Button)
    ]
    assert "Стакан" in market_labels, market_labels

    hub = m.TradingHubView(1, None, "change", 0)
    hub_labels = [
        child.label
        for child in hub.children
        if isinstance(child, m.discord.ui.Button)
    ]
    assert "Стакан" in hub_labels, hub_labels
