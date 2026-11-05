import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_clan_browser_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_clan_browser_and_applications():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 0), (2, 0), (3, 0)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury, bonus) "
                "VALUES (1, 'Alpha', 1, 1000, 0.2), (2, 'Beta', 3, 500, 0.1)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (3, 2, 'leader')"
            )
            await db.commit()

            embed, total_pages, chunk = await m.build_clan_browser_embed(0)
            assert total_pages == 1
            assert len(chunk) == 2
            assert "Браузер кланов" in embed.title

            embed2, _, chunk2 = await m.build_clan_browser_embed(0, "Alpha")
            assert len(chunk2) == 1

            ok, message = await m.apply_to_clan(2, 1)
            assert ok, message
            ok, message = await m.apply_to_clan(2, 1)
            assert not ok and "уже" in message.lower(), message

            async with db.execute(
                "SELECT id FROM clan_applications WHERE user_id = 2"
            ) as c:
                app_id = (await c.fetchone())[0]
            ok, message = await m.decide_clan_application(app_id, True, 1)
            assert ok, message
            async with db.execute(
                "SELECT clan_id, role FROM clan_members WHERE user_id = 2"
            ) as c:
                assert await c.fetchone() == (1, "member")

            ok, message = await m.decide_clan_application(app_id, True, 1)
            assert not ok and "обработана" in message.lower(), message
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
