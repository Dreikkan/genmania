import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_titles_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_unlocked_titles_thresholds():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, total_crafts, "
                "grid_size, prestige_points) VALUES (1, 10000, 100, 10, 100, 1)"
            )
            for slot in range(10):
                await db.execute(
                    "INSERT INTO inventory "
                    "(user_id, slot, item_id, location, stars) "
                    "VALUES (1, ?, 'basic_gen', 'profile', ?)",
                    (slot, 5 if slot == 0 else 0),
                )
            await db.commit()

            unlocked = await m.get_unlocked_titles(1)
            assert {
                "novice",
                "builder",
                "alchemist",
                "star_lord",
                "rich",
                "gem_master",
                "grid_master",
                "ascended",
            } <= unlocked
            assert "collector" not in unlocked
            assert "banker" not in unlocked
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
