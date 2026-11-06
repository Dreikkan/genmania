import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

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

            async with db.execute(
                "SELECT id, name, leader_id, treasury, bonus "
                "FROM clans WHERE id = 1"
            ) as c:
                clan = await c.fetchone()
            clan_embed = await m.build_clan_embed(
                SimpleNamespace(), clan
            )
            assert "Клан «Alpha»" in clan_embed.title
            clan_text = "\n".join(
                field.value for field in clan_embed.fields
            )
            assert "1000" in clan_text

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


def test_clan_war_embed_sides():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury, bonus) "
                "VALUES (1, 'Alpha', 1, 1000, 0.2), "
                "(2, 'Beta', 2, 500, 0.1)"
            )
            await db.commit()
            started = (
                datetime.datetime.now() - datetime.timedelta(hours=1)
            ).isoformat()
            war = (
                7,
                1,
                2,
                started,
                900,
                700,
                1000,
                1000,
                50,
                40,
            )
            own = await m.build_clan_war_embed(
                SimpleNamespace(), war, 1
            )
            assert "Клановая война #7" in own.title
            assert "Alpha" in own.description
            assert "Beta" in own.description
            own_text = "\n".join(field.value for field in own.fields)
            assert "900/1000" in own_text

            enemy_view = await m.build_clan_war_embed(
                SimpleNamespace(), war, 2
            )
            enemy_text = "\n".join(
                field.value for field in enemy_view.fields
            )
            assert "700/1000" in enemy_text
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
