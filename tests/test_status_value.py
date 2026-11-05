import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_status_value_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_status_ladder_values():
    assert m.best_status_bonus([]) == 0.0
    assert m.best_status_bonus(["vip"]) == 0.15
    assert m.best_status_bonus(["vip", "diamond"]) == 0.45
    assert m.best_status_bonus(["platinum", "gold"]) == 0.35
    assert m.status_rank("diamond") > m.status_rank("vip")


def test_cat_does_not_dominate_vip():
    cat_max = m.PET_TYPES["cat"]["per_level"] * m.PET_MAX_LEVEL
    assert abs(cat_max - m.STATUS_BONUSES["vip"]) < 1e-9, cat_max


def test_prestige_preserves_purchased_status():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, lifetime_production, "
                "prestige_points, title) VALUES (1, 1000, 500000, 0, 'Богач')"
            )
            await db.execute(
                "INSERT INTO player_upgrades (user_id, upgrade_id) "
                "VALUES (1, 'diamond'), (1, 'grid_10x10')"
            )
            await db.commit()

            original_add_season_xp = m.add_season_xp

            async def noop_add_season_xp(*args, **kwargs):
                return None

            m.add_season_xp = noop_add_season_xp
            try:
                ok, message, gain, points = await m.do_prestige(1)
            finally:
                m.add_season_xp = original_add_season_xp

            assert ok is True, message
            assert gain == 2 and points == 2

            async with db.execute(
                "SELECT income_bonus, title, prestige_points "
                "FROM players WHERE user_id = 1"
            ) as c:
                income_bonus, title, prestige_points = await c.fetchone()
            assert income_bonus == m.STATUS_BONUSES["diamond"], income_bonus
            assert title == "Богач"
            assert prestige_points == 2

            async with db.execute(
                "SELECT upgrade_id FROM player_upgrades WHERE user_id = 1"
            ) as c:
                upgrades = [row[0] for row in await c.fetchall()]
            assert upgrades == ["diamond"], upgrades
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
