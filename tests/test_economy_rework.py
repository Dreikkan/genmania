import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_economy_rework_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_exchange_fee_is_fixed():
    assert m.EXCHANGE_FEE_RATE == 0.05
    assert m.exchange_fee_rate(12, "coins_to_gems") == 0.05
    assert m.exchange_fee_rate(10_000_000, "coins_to_gems") == 0.05


def test_prestige_cost_grows():
    assert m.prestige_required_total(1) == 150_000
    assert m.prestige_required_total(2) == 350_000
    assert m.prestige_required_total(3) == 600_000
    assert m.prestige_points_from_lifetime(500_000) == 2
    assert m.prestige_point_cost(2) == 250_000
    assert m.prestige_gain_from_lifetime(249_999, 2) == 0
    assert m.prestige_gain_from_lifetime(250_000, 2) == 1


def test_shop_policy_and_star_collection():
    async def run():
        db = await _init()
        try:
            async with db.execute(
                "SELECT id, buyable FROM items WHERE id IN ('basic_gen','ruby_gen')"
            ) as c:
                rows = dict(await c.fetchall())
            assert rows["basic_gen"] == 1
            assert rows["ruby_gen"] == 0

            await db.execute("INSERT INTO players (user_id) VALUES (1)")
            await m.place_items(1, "basic_gen", 1, stars=2)
            async with db.execute(
                "SELECT stars FROM player_star_collection "
                "WHERE user_id = 1 AND item_id = 'basic_gen'"
            ) as c:
                stars = {row[0] for row in await c.fetchall()}
            assert 2 in stars, stars

            embed, _pages = await m.build_collection_embed(FakeInteraction(1), 0)
            first_value = embed.fields[0].value
            assert "2★" in first_value
            assert "2★⬜" not in first_value
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
