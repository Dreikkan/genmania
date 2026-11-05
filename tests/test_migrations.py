import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_migrations_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

USER = 501


async def run_checks(db):
    # Имитация старой БД: только старые колонки и строки.
    await db.executescript("""
        CREATE TABLE players (
            user_id INTEGER PRIMARY KEY,
            coins INTEGER,
            gems INTEGER,
            last_collected TIMESTAMP
        );
        CREATE TABLE bank_deposits (
            user_id INTEGER PRIMARY KEY,
            amount INTEGER,
            interest_rate REAL,
            end_time TIMESTAMP
        );
        CREATE TABLE clan_members (
            user_id INTEGER PRIMARY KEY,
            clan_id INTEGER,
            role TEXT DEFAULT 'member'
        );
        CREATE TABLE clans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            leader_id INTEGER,
            treasury INTEGER DEFAULT 0,
            bonus REAL DEFAULT 0.0
        );
    """)
    await db.execute(
        "INSERT INTO players (user_id, coins, gems, last_collected) "
        "VALUES (?, 100, 0, CURRENT_TIMESTAMP)",
        (USER,),
    )
    await db.execute(
        "INSERT INTO bank_deposits (user_id, amount, interest_rate, end_time) "
        "VALUES (?, 1000, 0.14, ?)",
        (USER, "2030-01-01T00:00:00"),
    )
    await db.execute(
        "INSERT INTO clan_members (user_id, clan_id, role) VALUES (?, 1, 'leader')",
        (USER,),
    )
    await db.execute(
        "INSERT INTO clans (name, leader_id) VALUES ('Old Clan', ?)", (USER,)
    )
    await db.commit()

    await m.bot.init_db()

    async with db.execute("PRAGMA table_info(players)") as c:
        player_cols = {r[1] for r in await c.fetchall()}
    assert "last_tax_time" in player_cols
    assert "last_gem_collected" in player_cols

    async with db.execute(
        "SELECT coins, last_tax_time, last_gem_collected FROM players WHERE user_id = ?",
        (USER,),
    ) as c:
        coins, last_tax, last_gem = await c.fetchone()
    assert coins == 100
    assert last_tax
    assert last_gem

    async with db.execute(
        "SELECT start_time, end_time FROM bank_deposits WHERE user_id = ?", (USER,)
    ) as c:
        start_time, end_time = await c.fetchone()
    assert start_time
    assert end_time

    async with db.execute(
        "SELECT joined_at FROM clan_members WHERE user_id = ?", (USER,)
    ) as c:
        assert (await c.fetchone())[0]

    async with db.execute(
        "SELECT created_at FROM clans WHERE name = 'Old Clan'"
    ) as c:
        assert (await c.fetchone())[0]

    async with db.execute("PRAGMA user_version") as c:
        assert (await c.fetchone())[0] == m.SCHEMA_VERSION

    async with db.execute(
        "SELECT COUNT(*) FROM schema_migrations WHERE name = ?",
        (f"schema_v{m.SCHEMA_VERSION}",),
    ) as c:
        assert (await c.fetchone())[0] == 1

    # do_prestige должен работать после миграции last_tax_time.
    await db.execute("DELETE FROM bank_deposits")
    await db.execute("DELETE FROM market_orders")
    await db.execute(
        "UPDATE players SET total_coins_earned = 500000, "
        "lifetime_production = 500000 WHERE user_id = ?",
        (USER,),
    )
    await db.commit()
    ok, message, gain, points = await m.do_prestige(USER)
    assert ok is True, message
    assert gain == 2
    assert points == 2

    print("MIGRATIONS TEST: OK")


async def main():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    try:
        await run_checks(db)
    finally:
        await db.close()
        m.bot.db = None


def test_old_db_migrations():
    asyncio.run(main())
