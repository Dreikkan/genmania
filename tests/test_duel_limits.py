import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_duel_limits_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_duel_bet_cap_and_cooldown():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 10000), (2, 10000)"
            )
            await db.commit()

            ok, message = await m.resolve_duel(1, 2, 2000, "dice")
            assert ok is False and "Ставка" in message, message

            ok, message = await m.resolve_duel(1, 2, 1000, "dice")
            assert ok is True, message
            assert await m.get_duel_cooldown_seconds(1) > 250
            assert await m.get_duel_cooldown_seconds(2) > 250

            ok, message = await m.resolve_duel(1, 2, 100, "dice")
            assert ok is False and "Кулдаун" in message, message
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_power_duel_blocks_much_weaker_target():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour) "
                "VALUES ('strong_relic', 'Сильный', 10000, 0), "
                "('weak_relic', 'Слабый', 100, 0)"
            )
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000), (2, 1000)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (1, 0, 'strong_relic', 'profile'), "
                "(2, 0, 'weak_relic', 'profile')"
            )
            await db.commit()
            allowed, reason = await m.validate_power_duel(1, 2)
            assert allowed is False and "диапазоне" in reason.lower(), (allowed, reason)

            allowed, reason = await m.validate_power_duel(2, 1)
            assert allowed is False and "диапазоне" in reason.lower(), (allowed, reason)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_power_duel_has_variance():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 10000), (2, 10000)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (1, 0, 'basic_gen', 'profile'), "
                "(2, 0, 'basic_gen', 'profile')"
            )
            await db.commit()

            calls = iter((0.85, 1.15))
            original_uniform = m.random.uniform
            m.random.uniform = lambda a, b: next(calls)
            try:
                ok, message = await m.resolve_duel(1, 2, 100, "power")
            finally:
                m.random.uniform = original_uniform

            assert ok is True, message
            assert "→" in message, message
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
