import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_economy_formatting_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_short_number_formatting():
    assert m.format_price(0) == "0"
    assert m.format_price(999) == "999"
    assert m.format_price(1_000) == "1K"
    assert m.format_price(1_500) == "1.5K"
    assert m.format_price(320_000) == "320K"
    assert m.format_price(1_000_000) == "1M"
    assert m.format_price(1_500_000) == "1.5M"
    assert m.format_price(1_000_000_000) == "1B"
    assert m.format_price(10**15) == "1Qa"
    assert m.format_price(10**18) == "1Qi"
    assert m.format_price(-1_500) == "-1.5K"

    assert m.format_content_number(1_500) == "1.5K"
    assert m.format_content_number(1_000.0) == "1K"
    assert m.format_content_number(5.0) == "5"
    assert m.format_content_number(1.5) == "1.5"
    assert m.format_short_number(1.5) == "1.5"
    assert m.format_short_number(float("inf")) == "inf"
    assert m.format_short_number("bad") == "bad"
    assert m.format_content_number("bad") == "bad"


def test_top_generators_have_meaningful_gem_income():
    async def run():
        m._DB_WRITE_LOCK = asyncio.Lock()
        m._DB_TX_OWNER = None
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        await m.bot.init_db()
        try:
            async with db.execute(
                "SELECT id, income_gems_per_hour FROM items "
                "WHERE id IN ('space_gen', 'divine_gen', 'legendary_gen') "
                "ORDER BY price"
            ) as c:
                rows = await c.fetchall()
            values = {item_id: value * 3600 for item_id, value in rows}
            assert values["space_gen"] >= 5
            assert values["divine_gen"] > values["space_gen"]
            assert values["legendary_gen"] > values["divine_gen"]
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
