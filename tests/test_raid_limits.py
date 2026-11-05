import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_raid_limits_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_target_daily_loss_cap():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000), (2, 10000)"
            )
            for uid in (1, 2):
                await db.execute(
                    "INSERT INTO inventory (user_id, slot, item_id, location) "
                    "VALUES (?, 0, 'basic_gen', 'profile')",
                    (uid,),
                )
            await db.execute(
                "INSERT INTO raid_loot_log (user_id, target_id, amount, date) "
                "VALUES (99, 2, 2400, ?)",
                (m.today_str(),),
            )
            await db.commit()

            original_randint = m.random.randint
            calls = iter((100000, 1))
            m.random.randint = lambda a, b: next(calls)
            try:
                result, error = await m.perform_raid([1], 2)
            finally:
                m.random.randint = original_randint

            assert error is None, error
            assert result["success"] is True
            assert result["loot"] == {1: 100}, result["loot"]
            assert result["target_capped"] is True, result
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_raid_blocks_farming_much_weaker_target():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour) "
                "VALUES ('strong_relic', 'Сильный', 10000, 0), "
                "('weak_relic', 'Слабый', 100, 0)"
            )
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000), (2, 10000)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (1, 0, 'strong_relic', 'profile'), "
                "(2, 0, 'weak_relic', 'profile')"
            )
            await db.commit()

            result, error = await m.perform_raid([1], 2)
            assert result is None
            assert error and "слабая" in error.lower(), error
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
