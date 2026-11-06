import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_service_branches4_test", BOT_PATH
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
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


def test_auction_bid_and_buyout_errors():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, ?)",
                [(1, 1000), (2, 1000), (3, 1000), (4, 10)],
            )
            now = datetime.datetime.now()
            await db.executemany(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, current_bid, current_bidder, "
                "buyout_price, end_time, status) "
                "VALUES (?, ?, 'basic_gen', ?, ?, ?, ?, ?)",
                [
                    (11, 1, 0, None, 1000,
                     (now + datetime.timedelta(hours=1)).isoformat(),
                     "closed"),
                    (12, 1, 0, None, 1000,
                     (now - datetime.timedelta(hours=1)).isoformat(),
                     "active"),
                    (13, 1, 50, 1, 1000,
                     (now + datetime.timedelta(hours=1)).isoformat(),
                     "active"),
                    (14, 1, 50, 2, 1000,
                     (now + datetime.timedelta(seconds=10)).isoformat(),
                     "active"),
                    (21, 1, 0, None, 1000,
                     (now - datetime.timedelta(hours=1)).isoformat(),
                     "active"),
                    (22, 3, 0, None, 1000,
                     (now + datetime.timedelta(hours=1)).isoformat(),
                     "active"),
                    (23, 1, 0, None, None,
                     (now + datetime.timedelta(hours=1)).isoformat(),
                     "active"),
                    (24, 1, 100, None, 100,
                     (now + datetime.timedelta(hours=1)).isoformat(),
                     "active"),
                    (25, 1, 0, None, 5000,
                     (now + datetime.timedelta(hours=1)).isoformat(),
                     "active"),
                ],
            )
            await db.commit()

            ok, message, _, _ = await m.place_auction_bid(1, 999, 10)
            assert not ok and "не найден" in message
            ok, message, _, _ = await m.place_auction_bid(1, 11, 10)
            assert not ok and "закрыт" in message
            ok, message, _, _ = await m.place_auction_bid(1, 12, 10)
            assert not ok and "истекло" in message
            ok, message, _, _ = await m.place_auction_bid(4, 13, 100)
            assert not ok and "Недостаточно" in message

            class ForbiddenUser:
                async def send(self, *args, **kwargs):
                    raise m.discord.Forbidden.__new__(m.discord.Forbidden)

            original_get_user = m.bot.get_user
            m.bot.get_user = lambda user_id: ForbiddenUser()
            try:
                ok, message, previous, extended = (
                    await m.place_auction_bid(3, 14, 100)
                )
            finally:
                m.bot.get_user = original_get_user
            assert ok and previous == 2 and extended
            assert "продлён" in message

            ok, message, _ = await m.buyout_auction(1, 999)
            assert not ok and "не найден" in message
            ok, message, _ = await m.buyout_auction(1, 21)
            assert not ok and "истекло" in message
            ok, message, _ = await m.buyout_auction(3, 22)
            assert not ok and "свой" in message
            ok, message, _ = await m.buyout_auction(2, 23)
            assert not ok and "Buyout" in message
            ok, message, _ = await m.buyout_auction(2, 24)
            assert not ok and "перекрыт" in message
            ok, message, _ = await m.buyout_auction(2, 25)
            assert not ok and "Недостаточно" in message
        finally:
            await _close(db)

    asyncio.run(run())


def test_update_clan_quest_completes():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury, level) "
                "VALUES (1, 'Alpha', 1, 0, 1)"
            )
            await db.execute(
                "INSERT INTO clan_quests "
                "(id, clan_id, quest_type, progress, target, reward) "
                "VALUES (1, 1, 'raid', 0, 2, 100)"
            )
            await db.commit()
            await m.update_clan_quest(1, "raid", 1)
            row = await db.execute_fetchall(
                "SELECT progress, completed FROM clan_quests WHERE id = 1"
            )
            assert row[0] == (1, 0)
            await m.update_clan_quest(1, "raid", 1)
            row = await db.execute_fetchall(
                "SELECT progress, completed FROM clan_quests WHERE id = 1"
            )
            assert row[0] == (2, 1)
            treasury = await db.execute_fetchall(
                "SELECT treasury FROM clans WHERE id = 1"
            )
            assert treasury[0][0] >= 100
            await m.update_clan_quest(1, "missing", 1)
        finally:
            await _close(db)

    asyncio.run(run())


def test_analytics_embed_empty_and_deposit_pet():
    async def run():
        db = await _init()
        try:
            missing = await m.build_analytics_embed(FakeInteraction(99))
            assert "не найден" in missing.title

            await db.execute(
                "INSERT INTO players (user_id, coins, gems, grid_size, "
                "total_crafts, total_successes, active_pet) "
                "VALUES (1, 100, 10, 9, 2, 1, 'cat')"
            )
            await db.execute(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level) "
                "VALUES (1, 'cat', 3)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (1, 0, 'basic_gen', 'profile')"
            )
            now = datetime.datetime.now()
            await db.execute(
                "INSERT INTO bank_deposits "
                "(user_id, amount, interest_rate, start_time, end_time) "
                "VALUES (1, 500, 0.05, ?, ?)",
                (
                    now.isoformat(),
                    (now + datetime.timedelta(days=3)).isoformat(),
                ),
            )
            await db.commit()
            embed = await m.build_analytics_embed(FakeInteraction(1))
            text = "\n".join(field.value for field in embed.fields)
            assert "Кот" in text
            assert "500" in text
        finally:
            await _close(db)

    asyncio.run(run())


def test_notification_cycle_skip_edges():
    async def run():
        db = await _init()
        try:
            now = datetime.datetime.now()
            await db.executemany(
                "INSERT INTO players (user_id, active_pet) VALUES (?, 'cat')",
                [(1,), (2,), (3,)],
            )
            await db.executemany(
                "INSERT INTO user_pets_v2 "
                "(user_id, pet_id, level, last_fed) VALUES (?, 'cat', ?, ?)",
                [
                    (1, 10, None),
                    (2, 1, now.isoformat()),
                    (
                        3,
                        1,
                        (now - datetime.timedelta(hours=10)).isoformat(),
                    ),
                ],
            )
            await db.execute(
                "UPDATE players SET last_daily = ? WHERE user_id = 3",
                (now.isoformat(),),
            )
            await db.execute(
                "INSERT INTO user_notifications "
                "(user_id, notif_type, enabled) "
                "VALUES (3, 'pet_hungry', 0), (3, 'autocollect', 0)"
            )
            await db.execute(
                "INSERT INTO autocollectors (user_id, level, last_auto) "
                "VALUES (1, 1, NULL)"
            )
            await db.execute(
                "INSERT INTO auctions "
                "(seller_id, item_id, current_bid, end_time, status) "
                "VALUES (1, 'basic_gen', 10, ?, 'active')",
                ((now + datetime.timedelta(hours=5)).isoformat(),),
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
                "INSERT INTO clan_wars "
                "(clan1_id, clan2_id, start_time, status) "
                "VALUES (1, 2, ?, 'active')",
                (now.isoformat(),),
            )
            await db.commit()

            sent = []

            class User:
                def __init__(self, uid):
                    self.id = uid

                async def send(self, *args, **kwargs):
                    sent.append(self.id)

            original_get_user = m.bot.get_user
            m.bot.get_user = lambda uid: User(uid)
            original_max = m.NOTIFICATION_RUNTIME.max_sent_per_cycle
            m.NOTIFICATION_RUNTIME.max_sent_per_cycle = 100
            try:
                await m.run_notification_cycle()
            finally:
                m.bot.get_user = original_get_user
                m.NOTIFICATION_RUNTIME.max_sent_per_cycle = original_max
        finally:
            await _close(db)

    asyncio.run(run())


def test_guild_access_snapshot_edges():
    async def run():
        db = await _init()
        try:
            assert await m.sync_guild_access(SimpleNamespace(id=None)) is None

            class BadOwnerGuild:
                id = 100
                owner_id = 1
                owner = None
                roles = ()
                me = None
                member_count = 0

                async def fetch_member(self, user_id):
                    raise m.discord.NotFound.__new__(m.discord.NotFound)

            snapshot = await m.sync_guild_access(BadOwnerGuild())
            assert snapshot["guild_id"] == 100

            class BrokenDB:
                in_transaction = False

                async def execute(self, *args, **kwargs):
                    raise RuntimeError("db down")

                async def commit(self):
                    raise RuntimeError("db down")

            original_db = m.bot.db
            m.bot.db = BrokenDB()
            try:
                snapshot = await m.sync_guild_access(
                    SimpleNamespace(
                        id=101,
                        owner_id=1,
                        owner=None,
                        roles=(),
                        me=None,
                        member_count=0,
                    )
                )
                assert snapshot["guild_id"] == 101
            finally:
                m.bot.db = original_db
        finally:
            await _close(db)

    asyncio.run(run())


def test_tax_rate_member_fallback_paths():
    async def run():
        db = await _init()
        try:
            m._tax_rate_cache.clear()

            class FetchMemberGuild:
                id = 1

                def get_member(self, user_id):
                    return None

                async def fetch_member(self, user_id):
                    return SimpleNamespace(id=user_id)

            class BrokenGuild:
                id = 2

                def get_member(self, user_id):
                    raise RuntimeError("broken")

            class MissingGuild:
                id = 3

                def get_member(self, user_id):
                    return None

                async def fetch_member(self, user_id):
                    raise m.discord.NotFound.__new__(m.discord.NotFound)

            with patch.object(
                type(m.bot), "guilds", new_callable=PropertyMock
            ) as guilds:
                guilds.return_value = [
                    FetchMemberGuild(),
                    BrokenGuild(),
                    MissingGuild(),
                ]
                rate = await m.get_tax_rate_for_user(42)
            assert isinstance(rate, float)

            class MapGuild:
                def __init__(self, guild_id, members):
                    self.id = guild_id
                    self.members = members

            original_settings = m.get_settings

            async def settings_getter(guild_id):
                if guild_id == 99:
                    raise ValueError("bad settings")
                return await original_settings(guild_id)

            m.get_settings = settings_getter
            try:
                with patch.object(
                    type(m.bot), "guilds", new_callable=PropertyMock
                ) as guilds:
                    guilds.return_value = [
                        MapGuild(
                            1,
                            [
                                SimpleNamespace(id=None),
                                SimpleNamespace(id=42),
                            ],
                        ),
                        MapGuild(99, []),
                    ]
                    rates = await m.get_tax_rate_map()
                assert rates[42] >= 0.0
            finally:
                m.get_settings = original_settings
        finally:
            m._tax_rate_cache.clear()
            await _close(db)

    asyncio.run(run())


def test_content_misc_branches():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT OR REPLACE INTO content_meta (key, value) VALUES "
                "('content_version', 'bad'), ('manual_revision', 'bad'), "
                "('last_content_editor_id', 'bad'), ('last_content_edit_at', 'x')"
            )
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "income_gems_per_hour, rarity, buyable, emoji) "
                "VALUES ('Bad ID', '', -1, -1, -1, 'special', 2, '')"
            )
            await db.execute(
                "INSERT INTO achievements "
                "(id, name, description, reward_gems, emoji) "
                "VALUES ('Bad ID', '', '', -1, '')"
            )
            await db.commit()

            status = await m.get_content_status()
            assert status["content_version"] == 0
            assert status["last_editor_id"] is None

            issues = await m.validate_content_data()
            assert len(issues) >= 5

            ok, _ = await m.update_item_content(
                1, "Bad ID", "Name", 10, 1, 0, "common"
            )
            assert not ok
            ok, _ = await m.update_item_content(
                1, "basic_gen", "", 10, 1, 0, "common"
            )
            assert not ok
            ok, _ = await m.update_item_content(
                1, "basic_gen", "Name", 10, 1, 0, "special"
            )
            assert not ok
            ok, _ = await m.update_item_content(
                1, "missing_gen", "Name", 10, 1, 0, "common"
            )
            assert not ok
            ok, _ = await m.update_item_content(
                1, "basic_gen", "Name", 10, "bad", 0, "common"
            )
            assert not ok
            ok, _ = await m.update_item_content(
                1, "basic_gen", "Name", 10, 1, "bad", "common"
            )
            assert not ok
            ok, _ = await m.set_item_income(1, "basic_gen", "bad", 0)
            assert not ok
            ok, _ = await m.set_item_income(1, "missing_gen", 1, 0)
            assert not ok
            ok, message = await m.set_item_income(1, "basic_gen", "", "")
            assert ok and "Доход" in message

            ok, _ = await m.add_achievement_content(
                1, "Bad ID", "Name", "Desc", 1, "🏆"
            )
            assert not ok
            ok, _ = await m.add_achievement_content(
                1, "ach_new", "", "Desc", 1, "🏆"
            )
            assert not ok
            ok, _ = await m.add_achievement_content(
                1, "ach_new", "Name", "", 1, "🏆"
            )
            assert not ok
            ok, _ = await m.add_achievement_content(
                1, "ach_new", "Name", "Desc", 1, ""
            )
            assert not ok
            ok, _ = await m.add_achievement_content(
                1, "ach_new", "Name", "Desc", "bad", "🏆"
            )
            assert not ok
            ok, message = await m.add_achievement_content(
                1, "ach_new", "Name", "Desc", 1, "🏆"
            )
            assert ok and "добавлено" in message

            ok, message = await m.delete_achievement_content(
                1, "ach_new", False
            )
            assert not ok and "Отменено" in message
            ok, message = await m.delete_achievement_content(
                1, "Bad ID", True
            )
            assert not ok
            ok, message = await m.delete_achievement_content(
                1, "no_such_ach", True
            )
            assert not ok and "не найдено" in message.lower()
            ok, message = await m.delete_achievement_content(
                1, "ach_new", True
            )
            assert ok and "удалено" in message
        finally:
            await _close(db)

    asyncio.run(run())
