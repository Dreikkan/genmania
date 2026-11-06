import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_prestige_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

SCHEMA = """
CREATE TABLE players (
    user_id INTEGER PRIMARY KEY,
    coins INTEGER DEFAULT 20,
    gems INTEGER DEFAULT 0,
    total_coins_earned INTEGER DEFAULT 0,
    lifetime_production INTEGER DEFAULT 0,
    prestige_points INTEGER DEFAULT 0,
    grid_size INTEGER DEFAULT 9,
    storage_size INTEGER DEFAULT 36,
    income_bonus REAL DEFAULT 0,
    catalysts INTEGER DEFAULT 0,
    title TEXT DEFAULT 'Новичок',
    daily_quest_date TEXT,
    daily_quest_progress TEXT DEFAULT '{}',
    daily_quest_claimed TEXT DEFAULT '[]',
    last_collected TIMESTAMP,
    last_gem_collected TIMESTAMP,
    last_tax_time TIMESTAMP
);
CREATE TABLE auctions (
    id INTEGER PRIMARY KEY,
    seller_id INTEGER,
    status TEXT,
    current_bidder INTEGER,
    current_bid INTEGER,
    start_price INTEGER
);
CREATE TABLE auction_bids (auction_id INTEGER);
CREATE TABLE inventory (
    user_id INTEGER,
    slot INTEGER,
    item_id TEXT,
    location TEXT,
    stars INTEGER
);
CREATE TABLE market_orders (
    user_id INTEGER,
    status TEXT DEFAULT 'active'
);
CREATE TABLE player_upgrades (
    user_id INTEGER,
    upgrade_id TEXT
);
CREATE TABLE bank_deposits (user_id INTEGER);
CREATE TABLE bank_loans (
    user_id INTEGER,
    status TEXT DEFAULT 'active'
);
"""

USER_ID = 1001
BIDDER_ID = 1002


async def run_checks(db):
    await db.executescript(SCHEMA)
    await db.execute(
        "INSERT INTO players (user_id, coins, total_coins_earned, "
        "lifetime_production, prestige_points, "
        "grid_size, storage_size, income_bonus, catalysts, title) "
        "VALUES (?, 999, 250000, 500000, 0, 36, 100, 0.5, 7, 'Богач')",
        (USER_ID,),
    )
    await db.execute(
        "INSERT INTO players (user_id, coins) VALUES (?, 0)", (BIDDER_ID,)
    )
    await db.execute(
        "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
        "VALUES (?, 0, 'basic_gen', 'profile', 0)",
        (USER_ID,),
    )
    await db.execute("INSERT INTO market_orders (user_id) VALUES (?)", (USER_ID,))
    await db.execute("INSERT INTO player_upgrades (user_id) VALUES (?)", (USER_ID,))
    await db.execute("INSERT INTO bank_deposits (user_id) VALUES (?)", (USER_ID,))
    await db.execute("INSERT INTO bank_loans (user_id) VALUES (?)", (USER_ID,))
    await db.execute(
        "INSERT INTO auctions (id, seller_id, status, current_bidder, current_bid) "
        "VALUES (1, ?, 'active', ?, 500)",
        (USER_ID, BIDDER_ID),
    )
    await db.execute("INSERT INTO auction_bids (auction_id) VALUES (1)")
    await db.commit()
    m.bot.db = db

    original_add_season_xp = m.add_season_xp

    async def fake_add_season_xp(
        user_id: int, amount: int, guild_id=None, action=None
    ):
        return None

    m.add_season_xp = fake_add_season_xp
    try:
        # Активные вклад/кредит/ордера блокируют перерождение.
        ok, message, gain, points = await m.do_prestige(USER_ID)
        assert ok is False and "закрой" in message.lower(), (ok, message)

        await db.execute("DELETE FROM bank_deposits")
        await db.execute("DELETE FROM bank_loans")
        await db.execute("DELETE FROM market_orders")
        await db.commit()

        ok, message, gain, points = await m.do_prestige(USER_ID)
    finally:
        m.add_season_xp = original_add_season_xp

    assert ok is True, message
    assert gain == 2
    assert points == 2
    assert "2" in message

    async with db.execute(
        "SELECT coins, grid_size, storage_size, income_bonus, catalysts, title, "
        "prestige_points, total_coins_earned FROM players WHERE user_id = ?",
        (USER_ID,),
    ) as c:
        row = await c.fetchone()
    assert row == (
        m.DEFAULT_START_COINS,
        9,
        36,
        0,
        0,
        "Богач",
        2,
        250000,
    ), row

    for table in (
        "inventory",
        "market_orders",
        "player_upgrades",
        "bank_deposits",
        "bank_loans",
        "auctions",
        "auction_bids",
    ):
        async with db.execute(f"SELECT COUNT(*) FROM {table}") as c:
            count = (await c.fetchone())[0]
        assert count == 0, (table, count)

    async with db.execute(
        "SELECT coins FROM players WHERE user_id = ?", (BIDDER_ID,)
    ) as c:
        assert (await c.fetchone())[0] == 500

    class FakeInteraction:
        user = type("User", (), {"id": USER_ID})()

    embed = await m.build_prestige_embed(FakeInteraction())
    assert "Перерождение" in embed.title
    values = "\n".join(field.value for field in embed.fields)
    assert "**2**" in values
    assert "+10%" in values

    print("PRESTIGE TEST: OK")


async def main():
    db = await aiosqlite.connect(":memory:")
    try:
        await run_checks(db)
    finally:
        await db.close()
        m.bot.db = None


def test_prestige():
    asyncio.run(main())
