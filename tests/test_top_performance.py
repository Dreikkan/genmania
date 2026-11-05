import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_top_perf_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._tax_rate_cache.clear()
    m._top_cache.clear()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems) VALUES "
        "(1, 1000, 1000), (2, 100, 100), (3, 100, 100)"
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._tax_rate_cache.clear()
    m._top_cache.clear()


def test_combat_power_many_matches_single():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (?, ?, 'basic_gen', 'profile', ?)",
                [(1, 0, 0), (2, 1, 1), (3, 2, 2)],
            )
            await db.execute(
                "UPDATE players SET active_pet = 'dragon' WHERE user_id = 2"
            )
            await db.execute(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level) "
                "VALUES (2, 'dragon', 3)"
            )
            await db.execute(
                "UPDATE players SET title = 'Звёздный лорд' WHERE user_id = 3"
            )
            await db.commit()

            single = {
                uid: await m.get_combat_power(uid) for uid in (1, 2, 3)
            }
            batch = await m.get_combat_power_many([1, 2, 3, 3, 999])
            assert batch[1] == single[1]
            assert batch[2] == single[2]
            assert batch[3] == single[3]
            assert batch[999] == 0
            assert await m.get_combat_power_many([]) == {}
        finally:
            await _close(db)

    asyncio.run(run())


def test_top_power_query_count_is_batched():
    async def run():
        db = await _init()
        try:
            users = list(range(100, 150))
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, ?, ?)",
                [(uid, 1000, 100) for uid in users],
            )
            await db.executemany(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (?, 0, 'basic_gen', 'profile', ?)",
                [(uid, uid % 5) for uid in users],
            )
            await db.commit()

            original_execute = db.execute
            query_count = 0

            def counted(*args, **kwargs):
                nonlocal query_count
                query_count += 1
                return original_execute(*args, **kwargs)

            db.execute = counted
            try:
                rows = await m.get_top_players("power", limit=10)
            finally:
                db.execute = original_execute

            assert len(rows) == 10
            # candidate SELECT + base power SELECT + pets/titles SELECT
            assert query_count <= 5, query_count
        finally:
            await _close(db)

    asyncio.run(run())


def test_tax_rate_map_uses_max_guild_rate():
    class FakeGuild:
        def __init__(self, guild_id: int, members):
            self.id = guild_id
            self.members = members
            self._by_id = {member.id: member for member in members}

        def get_member(self, user_id: int):
            return self._by_id.get(user_id)

    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings "
                "(guild_id, tax_rate) VALUES (?, ?)",
                (1001, 0.02),
            )
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings "
                "(guild_id, tax_rate) VALUES (?, ?)",
                (1002, 0.10),
            )
            await db.commit()

            user1 = SimpleNamespace(id=1)
            user2 = SimpleNamespace(id=2)
            user3 = SimpleNamespace(id=3)
            guild1 = FakeGuild(1001, [user1, user2])
            guild2 = FakeGuild(1002, [user1, user3])

            with patch.object(
                type(m.bot), "guilds", new_callable=PropertyMock
            ) as guilds_mock:
                guilds_mock.return_value = [guild1, guild2]
                m._settings_cache.clear()
                rates = await m.get_tax_rate_map()

            assert rates[1] == 0.10
            assert rates[2] == 0.02
            assert rates[3] == 0.10
            assert 999 not in rates
        finally:
            await _close(db)

    asyncio.run(run())


def test_tax_rate_cache_invalidated_by_setting_change():
    class FakeGuild:
        def __init__(self, guild_id: int, user_id: int):
            self.id = guild_id
            self._member = SimpleNamespace(id=user_id)

        def get_member(self, user_id: int):
            return self._member if user_id == self._member.id else None

    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings "
                "(guild_id, tax_rate) VALUES (?, ?)",
                (1001, 0.02),
            )
            await db.commit()
            guild = FakeGuild(1001, 1)

            with patch.object(
                type(m.bot), "guilds", new_callable=PropertyMock
            ) as guilds_mock:
                guilds_mock.return_value = [guild]
                m._settings_cache.clear()
                m._tax_rate_cache.clear()

                assert await m.get_tax_rate_for_user(1) == 0.02

                # Меняем БД в обход save_setting: кэш должен держать 0.02.
                await db.execute(
                    "UPDATE guild_settings SET tax_rate = 0.10 "
                    "WHERE guild_id = 1001"
                )
                await db.commit()
                m._settings_cache.clear()
                assert await m.get_tax_rate_for_user(1) == 0.02

                # save_setting сбрасывает кэш налога.
                await m.save_setting(1001, "tax_rate", 0.10)
                assert await m.get_tax_rate_for_user(1) == 0.10
        finally:
            await _close(db)

    asyncio.run(run())
