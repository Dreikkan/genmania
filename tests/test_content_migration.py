import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_content_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

SCHEMA = """
CREATE TABLE items (
    id TEXT PRIMARY KEY,
    name TEXT,
    price INTEGER,
    income_per_hour REAL DEFAULT 0,
    income_gems_per_hour REAL DEFAULT 0,
    emoji TEXT,
    rarity TEXT,
    buyable INTEGER DEFAULT 1,
    emoji_by_star TEXT DEFAULT '{}'
);
CREATE TABLE achievements (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    reward_gems INTEGER,
    emoji TEXT
);
CREATE TABLE gem_shop (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    price_gems INTEGER,
    emoji TEXT,
    category TEXT,
    max_level INTEGER
);
CREATE TABLE grid_shop (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    price_coins INTEGER,
    size INTEGER,
    emoji TEXT
);
CREATE TABLE market_prices (
    item_id TEXT PRIMARY KEY,
    base_price INTEGER,
    current_price INTEGER,
    demand INTEGER DEFAULT 0,
    supply INTEGER DEFAULT 0,
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE guild_settings (
    guild_id INTEGER PRIMARY KEY,
    start_coins INTEGER DEFAULT 20
);
"""


async def main():
    db = await aiosqlite.connect(":memory:")
    try:
        await run_checks(db)
    finally:
        await db.close()


async def run_checks(db):
    await db.executescript(SCHEMA)
    await db.execute(
        "INSERT INTO items (id, name, price, income_per_hour, emoji, rarity, buyable) "
        "VALUES ('basic_gen', 'Старое', 10, 0.001, '<:custom:123>', 'common', 0)"
    )
    await db.execute(
        "INSERT INTO achievements (id, name, description, reward_gems, emoji) "
        "VALUES ('first_craft', 'Старое', 'Старое', 1, '<:ach:123>')"
    )
    await db.execute(
        "INSERT INTO gem_shop (id, name, description, price_gems, emoji, category, max_level) "
        "VALUES ('vip', 'Старое', 'Старое', 1, '<:vip:123>', 'upgrade', 1)"
    )
    await db.execute(
        "INSERT INTO grid_shop (id, name, description, price_coins, size, emoji) "
        "VALUES ('grid_4x4', 'Старое', 'Старое', 1, 9, '<:grid:123>')"
    )
    await db.execute(
        "INSERT INTO market_prices (item_id, base_price, current_price) "
        "VALUES ('basic_gen', 10, 15)"
    )
    await db.execute(
        "INSERT INTO guild_settings (guild_id, start_coins) VALUES (1, 3)"
    )
    await db.execute(
        "INSERT INTO guild_settings (guild_id, start_coins) VALUES (2, 50)"
    )
    await db.commit()
    m.bot.db = db

    items = [("basic_gen", "Новое", 100, 0.01, "<:new:999>", "rare", 1, 0)]
    achievements = [("first_craft", "Новое", "Новое описание", 50, "<:new:999>")]
    gems = [("vip", "VIP", "Новое", 100, "<:new:999>", "status", 1)]
    grids = [("grid_4x4", "Сетка", "Новое", 500, 16, "<:new:999>")]
    daily = [("daily_common", "Лист", "🍃", "common", 0)]

    old_version = m.CONTENT_VERSION
    m.CONTENT_VERSION = 1
    try:
        await m.bot.apply_content_migrations(items, achievements, gems, grids, daily)

        async with db.execute(
            "SELECT name, price, income_per_hour, rarity, emoji, buyable "
            "FROM items WHERE id = 'basic_gen'"
        ) as c:
            name, price, income, rarity, emoji, buyable = await c.fetchone()
        assert name == "Новое" and price == 100 and rarity == "rare"
        assert emoji == "<:custom:123>" and buyable == 0

        async with db.execute(
            "SELECT name, reward_gems, emoji FROM achievements WHERE id = 'first_craft'"
        ) as c:
            assert await c.fetchone() == ("Новое", 50, "<:ach:123>")

        async with db.execute(
            "SELECT base_price, current_price FROM market_prices WHERE item_id = 'basic_gen'"
        ) as c:
            assert await c.fetchone() == (100, 100)

        async with db.execute(
            "SELECT value FROM content_meta WHERE key = 'content_version'"
        ) as c:
            assert (await c.fetchone())[0] == "1"

        async with db.execute(
            "SELECT start_coins FROM guild_settings WHERE guild_id = 1"
        ) as c:
            assert (await c.fetchone())[0] == m.DEFAULT_START_COINS
        async with db.execute(
            "SELECT start_coins FROM guild_settings WHERE guild_id = 2"
        ) as c:
            assert (await c.fetchone())[0] == 50

        # Без повышения версии значения не перезаписываются.
        items2 = [("basic_gen", "Ещё новее", 200, 0.02, "<:x:1>", "epic", 1, 0)]
        await m.bot.apply_content_migrations(items2, achievements, gems, grids, daily)
        async with db.execute("SELECT price FROM items WHERE id = 'basic_gen'") as c:
            assert (await c.fetchone())[0] == 100

        # Новая версия применяет изменения.
        m.CONTENT_VERSION = 2
        await m.bot.apply_content_migrations(items2, achievements, gems, grids, daily)
        async with db.execute("SELECT price FROM items WHERE id = 'basic_gen'") as c:
            assert (await c.fetchone())[0] == 200
    finally:
        m.CONTENT_VERSION = old_version

    print("CONTENT MIGRATION TEST: OK")


def test_content_migration():
    asyncio.run(main())
