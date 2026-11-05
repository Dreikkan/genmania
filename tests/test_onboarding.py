import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_onboarding_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_onboarding_steps_and_rewards():
    async def run():
        db = await _init()
        try:
            await db.execute("INSERT INTO players (user_id, coins, gems) VALUES (1, 0, 0)")
            await db.commit()

            first = await m.complete_onboarding_step(1, "buy_generator")
            assert first and first["coins"] == 50, first
            assert await m.complete_onboarding_step(1, "buy_generator") is None

            for step in ("claim_daily", "open_quests", "craft", "social"):
                assert await m.complete_onboarding_step(1, step), step

            done = await m.get_onboarding_progress(1)
            assert done == set(m.ONBOARDING_STEPS), done

            async with db.execute(
                "SELECT coins, gems FROM players WHERE user_id = 1"
            ) as c:
                coins, gems = await c.fetchone()
            assert coins == 275, coins
            assert gems == 2, gems
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_onboarding_next_step():
    done = {"buy_generator"}
    step, data = m.get_next_onboarding_step(done)
    assert step == "claim_daily", (step, data)
    assert data[0] == "Забери ежедневную награду"
