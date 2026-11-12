import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_upgrade_prices_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_grid_prices_scale_logically():
    async def run():
        db = await _init()
        try:
            async with db.execute(
                "SELECT id, price_coins, size FROM grid_shop "
                "UNION ALL "
                "SELECT id, price_gems, NULL FROM gem_shop "
                "WHERE id LIKE 'grid_%'"
            ) as c:
                rows = await c.fetchall()
            prices = {}
            for item_id, price, size in rows:
                prices[item_id] = price
            sizes = {
                "grid_4x4": 16,
                "grid_5x5": 25,
                "grid_6x6": 36,
                "grid_7x7": 49,
                "grid_8x8": 64,
                "grid_9x9": 81,
                "grid_10x10": 100,
            }

            expected = {
                "grid_4x4": 500,
                "grid_5x5": 1250,
                "grid_6x6": 2250,
                "grid_7x7": 400,
                "grid_8x8": 700,
                "grid_9x9": 1100,
                "grid_10x10": 1600,
            }
            assert prices == expected, prices

            order = [
                "grid_4x4", "grid_5x5", "grid_6x6",
                "grid_7x7", "grid_8x8", "grid_9x9", "grid_10x10",
            ]
            prev = 0.0
            for item_id in order:
                price = prices[item_id]
                if item_id in ("grid_4x4", "grid_5x5", "grid_6x6"):
                    coin_value = price
                else:
                    coin_value = price * m.COINS_PER_GEM
                per_slot = coin_value / sizes[item_id]
                assert per_slot > prev, (item_id, per_slot, prev)
                prev = per_slot
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_clan_capacity_prices_are_quadratic():
    capacities = [10, 15, 20, 25, 30, 35, 40, 45]
    costs = [m.clan_capacity_cost(c) for c in capacities]
    assert costs == [1000, 4000, 9000, 16000, 25000, 36000, 49000, 64000]
    assert m.clan_capacity_cost(m.CLAN_MAX_CAPACITY) == 81000


def test_clan_upgrade_embed_shows_next_quadratic_cost():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury, capacity) "
                "VALUES (1, 'Alpha', 1, 10000, 10)"
            )
            await db.commit()
            embed = await m.build_clan_upgrades_embed(1)
            text = "\n".join(field.value for field in embed.fields)
            assert "1 000" in text

            await db.execute("UPDATE clans SET capacity = 15 WHERE id = 1")
            await db.commit()
            embed = await m.build_clan_upgrades_embed(1)
            text = "\n".join(field.value for field in embed.fields)
            assert "4 000" in text
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_upgrade_prices_use_targeted_migration():
    assert m.CONTENT_VERSION == 8
    assert m.SCHEMA_VERSION == 18
