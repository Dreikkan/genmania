import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_service_branches2_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    m._top_cache.clear()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._top_cache.clear()


def test_content_price_generator_and_achievement_branches():
    async def run():
        db = await _init()
        try:
            ok, message = await m.set_item_price(1, "Bad ID", 10)
            assert not ok and "ID" in message
            ok, message = await m.set_item_price(1, "basic_gen", "bad")
            assert not ok and "Цена" in message
            ok, message = await m.set_item_price(1, "missing_gen", 10)
            assert not ok and "не найден" in message
            ok, message = await m.set_item_price(1, "basic_gen", 123)
            assert ok and "123" in message

            ok, _ = await m.add_generator_content(
                1, "Bad ID", "Name", 10, 1, 0, "⚙️", "common"
            )
            assert not ok
            ok, _ = await m.add_generator_content(
                1, "new_gen", "", 10, 1, 0, "⚙️", "common"
            )
            assert not ok
            ok, _ = await m.add_generator_content(
                1, "new_gen", "Name", "bad", 1, 0, "⚙️", "common"
            )
            assert not ok
            ok, _ = await m.add_generator_content(
                1, "new_gen", "Name", 10, "bad", 0, "⚙️", "common"
            )
            assert not ok
            ok, _ = await m.add_generator_content(
                1, "new_gen", "Name", 10, 1, "bad", "⚙️", "common"
            )
            assert not ok
            ok, _ = await m.add_generator_content(
                1, "new_gen", "Name", 10, 1, 0, "", "common"
            )
            assert not ok
            ok, _ = await m.add_generator_content(
                1, "new_gen", "Name", 10, 1, 0, "⚙️", "impossible"
            )
            assert not ok
            ok, _ = await m.add_generator_content(
                1, "basic_gen", "Name", 10, 1, 0, "⚙️", "common"
            )
            assert not ok
            ok, message = await m.add_generator_content(
                1, "new_gen", "Новый", 10, 1, 0, "⚙️", "common"
            )
            assert ok and "new_gen" in message

            await db.execute(
                "INSERT INTO achievements "
                "(id, name, description, reward_gems, emoji) "
                "VALUES ('ach1', 'Ach', 'Desc', 1, '🏆')"
            )
            await db.commit()

            ok, _ = await m.update_achievement_content(
                1, "Bad ID", "Name", "Desc", 1, "🏆"
            )
            assert not ok
            ok, _ = await m.update_achievement_content(
                1, "ach1", "", "Desc", 1, "🏆"
            )
            assert not ok
            ok, _ = await m.update_achievement_content(
                1, "ach1", "Name", "", 1, "🏆"
            )
            assert not ok
            ok, _ = await m.update_achievement_content(
                1, "ach1", "Name", "Desc", "bad", "🏆"
            )
            assert not ok
            ok, _ = await m.update_achievement_content(
                1, "ach1", "Name", "Desc", 1, ""
            )
            assert not ok
            ok, _ = await m.update_achievement_content(
                1, "missing_ach", "Name", "Desc", 1, "🏆"
            )
            assert not ok
            ok, message = await m.update_achievement_content(
                1, "ach1", "New", "New desc", 5, "⭐"
            )
            assert ok and "ach1" in message
        finally:
            await _close(db)

    asyncio.run(run())


def test_clan_application_decisions():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id) VALUES (?)",
                [(1,), (2,), (3,), (4,)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (3, 1, 'member')"
            )
            await db.execute(
                "INSERT INTO clan_applications (id, clan_id, user_id) "
                "VALUES (10, 1, 2), (11, 1, 4)"
            )
            await db.commit()

            ok, message = await m.decide_clan_application(99, True, 1)
            assert not ok and "не найдена" in message
            ok, message = await m.decide_clan_application(10, True, 3)
            assert not ok and "прав" in message
            ok, message = await m.decide_clan_application(10, True, 1)
            assert ok and "принят" in message
            ok, message = await m.decide_clan_application(11, False, 1)
            assert ok and "отклонена" in message
        finally:
            await _close(db)

    asyncio.run(run())


def test_unlocked_titles_all_thresholds():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, total_crafts, "
                "grid_size, raid_wins) VALUES (1, 10000, 100, 10, 9, 5)"
            )
            await db.executemany(
                "INSERT INTO duel_history (winner_id) VALUES (?)",
                [(1,)] * 10,
            )
            await db.executemany(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (1, ?, 'basic_gen', 'profile', ?)",
                [(slot, 5 if slot == 0 else 0) for slot in range(10)],
            )
            await db.executemany(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "emoji, rarity, buyable) "
                "VALUES (?, 'Collection', 10, 0, '⚙️', 'common', 1)",
                [(f"col{i}_gen",) for i in range(20)],
            )
            await db.executemany(
                "INSERT INTO player_collection (user_id, item_id) "
                "VALUES (1, ?)",
                [(f"col{i}_gen",) for i in range(20)],
            )
            await db.executemany(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level) "
                "VALUES (1, ?, ?)",
                [("cat", 10), ("dog", 1), ("dragon", 1)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader')"
            )
            await db.execute(
                "INSERT INTO clan_wars "
                "(clan1_id, clan2_id, winner_id, start_time, status) "
                "VALUES (1, 2, 1, '2026-01-01', 'finished')"
            )
            await db.execute(
                "INSERT INTO bank_history (user_id, amount) VALUES (1, 100)"
            )
            await db.executemany(
                "INSERT INTO tax_log (user_id, amount) VALUES (1, ?)",
                [(1,), (1,), (1,)],
            )
            await db.execute(
                "INSERT INTO auctions (seller_id, item_id, status) "
                "VALUES (1, 'basic_gen', 'finished')"
            )
            await db.execute(
                "INSERT INTO auctions "
                "(seller_id, item_id, current_bidder, status) "
                "VALUES (2, 'basic_gen', 1, 'finished')"
            )
            await db.executemany(
                "INSERT INTO player_quests (user_id, quest_id, completed) "
                "VALUES (1, ?, 1)",
                [(f"q{i}",) for i in range(5)],
            )
            await db.executemany(
                "INSERT INTO player_achievements (user_id, achievement_id) "
                "VALUES (1, ?)",
                [(f"a{i}",) for i in range(10)],
            )
            await db.commit()

            unlocked = await m.get_unlocked_titles(1)
            for title in (
                "builder",
                "alchemist",
                "rich",
                "raider",
                "duelist",
                "collector",
                "pet_lover",
                "pet_master",
                "clan_leader",
                "clan_warrior",
                "banker",
                "taxpayer",
                "auctioneer",
                "trader",
                "gem_master",
                "quest_hero",
                "ach_hunter",
            ):
                assert title in unlocked, title
        finally:
            await _close(db)

    asyncio.run(run())


def test_leaderboards_clans_empty_guild_and_fetch_fallback():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, ?)",
                [(1, 100), (2, 200)],
            )
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "emoji, rarity, buyable) "
                "VALUES ('clan_gen', 'Clan gen', 100, 1, '⚙️', 'rare', 1)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 0), (2, 'Beta', 2, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 2, 'leader')"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (1, 0, 'clan_gen', 'profile')"
            )
            await db.commit()

            original_get_guild = m.bot.get_guild
            m.bot.get_guild = lambda guild_id: SimpleNamespace(members=[])
            try:
                assert await m.get_top_players("coins", guild_id=1) == []
                assert await m.get_top_players("clans", guild_id=1) == []
            finally:
                m.bot.get_guild = original_get_guild

            rows = await m.get_top_players("clans", limit=10)
            assert rows and rows[0][1] == "Alpha"

            original_get_user = m.bot.get_user
            original_fetch_user = m.bot.fetch_user
            m.bot.get_user = lambda user_id: None

            async def fetch_user(user_id):
                return SimpleNamespace(id=user_id, name=f"Fetched{user_id}")

            m.bot.fetch_user = fetch_user
            try:
                embed = await m.build_top_embed(
                    FakeInteraction(1), "coins", limit=10, scope="global"
                )
                assert "Fetched1" in "\n".join(
                    field.value for field in embed.fields
                )
                clan_embed = await m.build_top_embed(
                    FakeInteraction(1), "clans", limit=10, scope="global"
                )
                assert "Alpha" in "\n".join(
                    field.value for field in clan_embed.fields
                )
                fallback = await m.build_top_embed(
                    FakeInteraction(1), "unknown", limit=10, scope="global"
                )
                assert "Топ — По монетам" in fallback.title
            finally:
                m.bot.get_user = original_get_user
                m.bot.fetch_user = original_fetch_user
        finally:
            await _close(db)

    asyncio.run(run())
