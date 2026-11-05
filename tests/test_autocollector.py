import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_autocollector_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_full_income_has_no_offline_penalty():
    async def run():
        db = await _init()
        try:
            three_hours_ago = (
                datetime.datetime.now() - datetime.timedelta(hours=3)
            ).isoformat()
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 0)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (1, 0, 'basic_gen', 'profile')"
            )
            await db.execute(
                "UPDATE players SET last_collected = ?, last_gem_collected = ? "
                "WHERE user_id = 1",
                (three_hours_ago, three_hours_ago),
            )
            await db.commit()

            per_sec_coins, per_sec_gems = await m.get_per_second_income(1)
            full_coins, full_gems = await m.calculate_full_passive_income(1)
            manual_coins, manual_gems = await m.calculate_passive_income(1)

            expected = int(3 * 3600 * per_sec_coins)
            assert abs(full_coins - expected) <= 5, (full_coins, expected)
            assert full_coins > manual_coins, (full_coins, manual_coins)
            assert full_gems >= manual_gems
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_offline_cap_removed():
    assert m.cap_passive_income(1_000_000, 7201, 100_000) == 1_000_000
    assert m.cap_passive_income(1_000_000, 999_999, 1) == 1_000_000


def test_placing_generator_resets_retroactive_income():
    async def run():
        db = await _init()
        try:
            three_hours_ago = (
                datetime.datetime.now() - datetime.timedelta(hours=3)
            ).isoformat()
            await db.execute(
                "INSERT INTO players (user_id, coins, last_collected, "
                "last_gem_collected) VALUES (1, 0, ?, ?)",
                (three_hours_ago, three_hours_ago),
            )
            await db.commit()

            await m.place_items(1, "basic_gen", 1)
            per_sec_coins, _ = await m.get_per_second_income(1)
            coins, _ = await m.calculate_full_passive_income(1)
            assert coins <= per_sec_coins * 5 + 1, coins
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
