import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_market_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

SCHEMA = """
CREATE TABLE players (
    user_id INTEGER PRIMARY KEY,
    coins INTEGER DEFAULT 0,
    gems INTEGER DEFAULT 0,
    total_coins_earned INTEGER DEFAULT 0,
    total_gems_earned INTEGER DEFAULT 0,
    grid_size INTEGER DEFAULT 9,
    storage_size INTEGER DEFAULT 36,
    income_bonus REAL DEFAULT 0,
    daily_quest_date TEXT DEFAULT NULL,
    daily_quest_progress TEXT DEFAULT '{}',
    daily_quest_claimed TEXT DEFAULT '[]'
);
CREATE TABLE items (
    id TEXT PRIMARY KEY,
    name TEXT,
    price INTEGER DEFAULT 100,
    emoji TEXT DEFAULT '📦',
    rarity TEXT DEFAULT 'common',
    buyable INTEGER DEFAULT 1
);
CREATE TABLE inventory (
    user_id INTEGER,
    slot INTEGER,
    item_id TEXT,
    location TEXT DEFAULT 'profile',
    stars INTEGER DEFAULT 0,
    is_locked INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, location, slot)
);
CREATE TABLE player_collection (
    user_id INTEGER,
    item_id TEXT,
    PRIMARY KEY (user_id, item_id)
);
CREATE TABLE market_prices (
    item_id TEXT PRIMARY KEY,
    base_price INTEGER,
    current_price INTEGER,
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    demand INTEGER DEFAULT 0,
    supply INTEGER DEFAULT 0
);
CREATE TABLE market_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT,
    price INTEGER,
    demand INTEGER DEFAULT 0,
    supply INTEGER DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE market_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    side TEXT,
    item_id TEXT,
    stars INTEGER DEFAULT 0,
    price INTEGER,
    quantity INTEGER,
    filled INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);
"""


class FakeInteraction:
    pass


async def main():
    db = await aiosqlite.connect(":memory:")
    try:
        await run_checks(db)
    finally:
        await db.close()


async def run_checks(db):
    await db.executescript(SCHEMA)
    await db.execute(
        "INSERT INTO items (id, name, price, rarity) "
        "VALUES ('basic_gen', 'Базовый', 100, 'common')"
    )
    await db.execute(
        "INSERT INTO market_prices (item_id, base_price, current_price) "
        "VALUES ('basic_gen', 100, 100)"
    )
    await db.execute(
        "INSERT INTO market_history (item_id, price) VALUES ('basic_gen', 100)"
    )
    await db.execute(
        "INSERT INTO players (user_id, coins) VALUES (1, 1000), (2, 1000)"
    )
    await db.commit()
    m.bot.db = db

    async def noop(*args, **kwargs):
        return None

    m.update_quest_progress = noop
    m.check_achievements = noop

    # Продажа: 3 предмета уходят в эскроу.
    for slot in range(5):
        await db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location) "
            "VALUES (1, ?, 'basic_gen', 'storage')",
            (slot,),
        )
    await db.commit()

    ok, msg = await m.create_market_order(1, "sell", "basic_gen", 3, 100)
    assert ok, msg
    async with db.execute(
        "SELECT COUNT(*) FROM inventory WHERE user_id = 1 AND location = 'storage'"
    ) as c:
        assert (await c.fetchone())[0] == 2

    # Покупатель исполняет sell-ордер.
    ok, msg = await m.fill_market_order(1, 2)
    assert ok, msg
    async with db.execute("SELECT coins FROM players WHERE user_id = 1") as c:
        assert (await c.fetchone())[0] == 1294
    async with db.execute(
        "SELECT COUNT(*) FROM inventory WHERE user_id = 2 AND item_id = 'basic_gen'"
    ) as c:
        assert (await c.fetchone())[0] == 3
    async with db.execute(
        "SELECT status FROM market_orders WHERE id = 1"
    ) as c:
        assert (await c.fetchone())[0] == "filled"

    # Buy-ордер: резерв монет, затем исполнение продавцом.
    for slot in range(2):
        await db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location) "
            "VALUES (1, ?, 'basic_gen', 'storage')",
            (10 + slot,),
        )
    await db.commit()
    ok, msg = await m.create_market_order(2, "buy", "basic_gen", 2, 100)
    assert ok, msg
    async with db.execute("SELECT coins FROM players WHERE user_id = 2") as c:
        assert (await c.fetchone())[0] == 500
    ok, msg = await m.fill_market_order(2, 1)
    assert ok, msg
    async with db.execute("SELECT coins FROM players WHERE user_id = 1") as c:
        assert (await c.fetchone())[0] == 1490
    async with db.execute(
        "SELECT COUNT(*) FROM inventory WHERE user_id = 2 AND item_id = 'basic_gen'"
    ) as c:
        assert (await c.fetchone())[0] == 5

    # Отмена sell-ордера возвращает предмет.
    await db.execute(
        "INSERT INTO inventory (user_id, slot, item_id, location) "
        "VALUES (1, 20, 'basic_gen', 'storage')"
    )
    await db.commit()
    ok, msg = await m.create_market_order(1, "sell", "basic_gen", 1, 100)
    assert ok, msg
    async with db.execute(
        "SELECT id FROM market_orders WHERE user_id = 1 AND status = 'active'"
    ) as c:
        order_id = (await c.fetchone())[0]
    ok, msg = await m.cancel_market_order(order_id, 1)
    assert ok, msg
    async with db.execute(
        "SELECT COUNT(*) FROM inventory WHERE user_id = 1 AND item_id = 'basic_gen'"
    ) as c:
        assert (await c.fetchone())[0] == 3

    # Отмена buy-ордера возвращает резерв.
    ok, msg = await m.create_market_order(2, "buy", "basic_gen", 1, 100)
    assert ok, msg
    async with db.execute(
        "SELECT id FROM market_orders WHERE user_id = 2 AND status = 'active'"
    ) as c:
        order_id = (await c.fetchone())[0]
    ok, msg = await m.cancel_market_order(order_id, 2)
    assert ok, msg
    async with db.execute("SELECT coins FROM players WHERE user_id = 2") as c:
        assert (await c.fetchone())[0] == 500

    # Просроченный buy-ордер возвращает резерв.
    ok, msg = await m.create_market_order(2, "buy", "basic_gen", 1, 80)
    assert ok, msg
    async with db.execute(
        "SELECT id FROM market_orders WHERE user_id = 2 AND status = 'active'"
    ) as c:
        expired_id = (await c.fetchone())[0]
    await db.execute(
        "UPDATE market_orders SET expires_at = ? WHERE id = ?",
        ((datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat(), expired_id),
    )
    await db.commit()
    await m.expire_market_orders()
    async with db.execute(
        "SELECT status FROM market_orders WHERE id = ?", (expired_id,)
    ) as c:
        assert (await c.fetchone())[0] == "expired"
    async with db.execute("SELECT coins FROM players WHERE user_id = 2") as c:
        assert (await c.fetchone())[0] == 500

    # История и экран биржи.
    await m.record_market_price("basic_gen", 110, 2, 1)
    history = await m.build_market_history_embed("basic_gen")
    assert "История цен" in history.title
    market_embed, _market_pages = await m.build_market_embed(
        FakeInteraction(), "common", "price_desc"
    )
    assert "Биржа" in market_embed.title

    missing = await m.build_market_history_embed("missing_item")
    assert "не найден" in missing.description

    hub = await m.build_trading_hub_embed()
    assert "Трейд-хаб" in hub.title

    print("MARKET SMOKE TEST: OK")


def test_smoke():
    asyncio.run(main())
