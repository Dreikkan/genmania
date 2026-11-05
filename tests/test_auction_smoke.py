import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_auction_test", BOT_PATH)
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
    PRIMARY KEY (user_id, location, slot)
);
CREATE TABLE player_collection (
    user_id INTEGER,
    item_id TEXT,
    PRIMARY KEY (user_id, item_id)
);
CREATE TABLE auctions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER,
    item_id TEXT,
    stars INTEGER DEFAULT 0,
    start_price INTEGER,
    current_bid INTEGER DEFAULT 0,
    current_bidder INTEGER DEFAULT NULL,
    buyout_price INTEGER DEFAULT NULL,
    end_time TIMESTAMP,
    status TEXT DEFAULT 'active'
);
CREATE TABLE auction_bids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    auction_id INTEGER,
    bidder_id INTEGER,
    amount INTEGER,
    kind TEXT DEFAULT 'bid',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class FakeInteraction:
    def __init__(self):
        self.kwargs = None

    async def edit_original_response(self, **kwargs):
        self.kwargs = kwargs


async def main():
    db = await aiosqlite.connect(":memory:")
    try:
        await run_checks(db)
    finally:
        await db.close()


async def run_checks(db):
    await db.executescript(SCHEMA)
    await db.execute(
        "INSERT INTO items (id, name, price) VALUES ('basic_gen', 'Базовый', 100)"
    )
    await db.execute(
        "INSERT INTO players (user_id, coins) VALUES (1, 0), (2, 1000), (3, 1000)"
    )
    end = (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat()
    await db.execute(
        "INSERT INTO auctions "
        "(id, seller_id, item_id, stars, start_price, current_bid, "
        "buyout_price, end_time, status) "
        "VALUES (1, 1, 'basic_gen', 0, 100, 100, 500, ?, 'active')",
        (end,),
    )
    await db.commit()
    m.bot.db = db

    async def noop(*args, **kwargs):
        return None

    m.update_quest_progress = noop
    m.check_achievements = noop

    # Экран активных лотов.
    fake = FakeInteraction()
    await m.open_auction_view(fake, 2)
    assert "Аукцион" in fake.kwargs["embed"].title
    assert isinstance(fake.kwargs["view"], m.AuctionView)

    # Ставка 1.
    ok, msg, _prev, extended = await m.place_auction_bid(2, 1, 150)
    assert ok, msg
    async with db.execute("SELECT coins FROM players WHERE user_id = 2") as c:
        assert (await c.fetchone())[0] == 850
    async with db.execute(
        "SELECT current_bid, current_bidder FROM auctions WHERE id = 1"
    ) as c:
        assert await c.fetchone() == (150, 2)

    # Перебивание: предыдущий лидер получает возврат.
    ok, msg, prev, _ = await m.place_auction_bid(3, 1, 200)
    assert ok and prev == 2, (ok, msg, prev)
    async with db.execute("SELECT coins FROM players WHERE user_id = 2") as c:
        assert (await c.fetchone())[0] == 1000
    async with db.execute("SELECT coins FROM players WHERE user_id = 3") as c:
        assert (await c.fetchone())[0] == 800

    # Нельзя перебить Buyout ставкой.
    ok, msg, _, _ = await m.place_auction_bid(3, 1, 500)
    assert not ok and "Buyout" in msg, (ok, msg)

    # Нельзя ставить на свой лот.
    ok, msg, _, _ = await m.place_auction_bid(1, 1, 300)
    assert not ok and "свой лот" in msg, (ok, msg)

    # Buyout: возврат ставки, списание, передача предмета, комиссия.
    ok, msg, compensation = await m.buyout_auction(3, 1)
    assert ok and compensation == 0, (ok, msg, compensation)
    async with db.execute(
        "SELECT coins FROM players WHERE user_id = 3"
    ) as c:
        assert (await c.fetchone())[0] == 500
    async with db.execute(
        "SELECT coins FROM players WHERE user_id = 1"
    ) as c:
        assert (await c.fetchone())[0] == 475  # 500 - 5%
    async with db.execute(
        "SELECT status, current_bidder FROM auctions WHERE id = 1"
    ) as c:
        assert await c.fetchone() == ("finished", 3)
    async with db.execute(
        "SELECT COUNT(*) FROM inventory WHERE user_id = 3 AND item_id = 'basic_gen'"
    ) as c:
        assert (await c.fetchone())[0] == 1
    async with db.execute(
        "SELECT COUNT(*) FROM auction_bids WHERE auction_id = 1 AND kind = 'buyout'"
    ) as c:
        assert (await c.fetchone())[0] == 1

    # Повторный buyout невозможен.
    ok, msg, _ = await m.buyout_auction(2, 1)
    assert not ok and "закрыт" in msg, (ok, msg)

    # История собирается.
    history = await m.build_auction_history_embed(1)
    assert "История лота #1" in history.title
    assert "Последние ставки" in [field.name for field in history.fields]

    print("AUCTION SMOKE TEST: OK")


def test_smoke():
    asyncio.run(main())
