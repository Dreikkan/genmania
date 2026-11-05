import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_leaderboard_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    m._top_cache.clear()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.executemany(
        "INSERT INTO players "
        "(user_id, coins, gems, total_crafts, prestige_points) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (1, 1000, 10, 5, 3),
            (2, 500, 50, 10, 1),
            (3, 100, 100, 1, 2),
        ],
    )
    await db.executemany(
        "INSERT INTO user_pets_v2 (user_id, pet_id, level) VALUES (?, ?, 1)",
        [(1, "cat"), (1, "dog"), (2, "cat")],
    )
    await db.executemany(
        "INSERT INTO player_collection (user_id, item_id) VALUES (?, ?)",
        [(1, "basic_gen"), (1, "copper_gen"), (2, "basic_gen")],
    )
    await db.executemany(
        "INSERT INTO duel_history (winner_id, loser_id, bet, type) "
        "VALUES (?, ?, 1, 'dice')",
        [(1, 2), (1, 3), (2, 1)],
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._DB_TX_OWNER = None
    m._top_cache.clear()


def test_all_leaderboard_types_and_cache():
    async def run():
        db = await _init()
        try:
            assert await m.get_top_players("coins") == [
                (1, 1000),
                (2, 500),
                (3, 100),
            ]
            assert await m.get_top_players("gems") == [
                (3, 100),
                (2, 50),
                (1, 10),
            ]
            assert await m.get_top_players("crafts") == [
                (2, 10),
                (1, 5),
                (3, 1),
            ]
            assert await m.get_top_players("pets") == [(1, 2), (2, 1)]
            assert await m.get_top_players("prestige") == [
                (1, 3),
                (3, 2),
                (2, 1),
            ]
            assert await m.get_top_players("collection") == [(1, 2), (2, 1)]
            assert await m.get_top_players("duels") == [(1, 2), (2, 1)]
            assert await m.get_top_players("unknown") == []

            m._top_cache.clear()
            first = await m.get_top_players_cached("coins", 2)
            second = await m.get_top_players_cached("coins", 2)
            assert first is second
            assert first == [(1, 1000), (2, 500)]

            original_get_guild = m.bot.get_guild
            m.bot.get_guild = lambda guild_id: SimpleNamespace(
                members=[SimpleNamespace(id=2)]
            )
            try:
                assert await m.get_top_players("coins", 10, guild_id=99) == [
                    (2, 500)
                ]
                m.bot.get_guild = lambda guild_id: None
                assert await m.get_top_players("coins", 10, guild_id=99) == []
            finally:
                m.bot.get_guild = original_get_guild
        finally:
            await _close(db)

    asyncio.run(run())
