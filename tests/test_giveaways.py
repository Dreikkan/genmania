import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_giveaways_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeMessage:
    _next_id = 9000

    def __init__(self, channel_id):
        FakeMessage._next_id += 1
        self.id = FakeMessage._next_id
        self.channel_id = channel_id
        self.jump_url = f"https://discord.com/channels/1/{channel_id}/{self.id}"
        self.edited = None
        self.deleted = False

    async def edit(self, **kwargs):
        self.edited = kwargs

    async def delete(self):
        self.deleted = True


class FakeChannel:
    def __init__(self, channel_id, allow=True):
        self.id = channel_id
        self.allow = allow
        self.sent = []
        self.messages = {}

    def permissions_for(self, member):
        return SimpleNamespace(
            send_messages=self.allow, embed_links=self.allow
        )

    async def send(self, **kwargs):
        if not self.allow:
            raise RuntimeError("no permission")
        message = FakeMessage(self.id)
        self.sent.append(kwargs)
        self.messages[message.id] = message
        return message

    async def fetch_message(self, message_id):
        return self.messages[message_id]


class FakeGuild:
    def __init__(self, guild_id, channel):
        self.id = guild_id
        self.me = SimpleNamespace()
        self.system_channel = channel
        self.public_updates_channel = None
        self.text_channels = [channel]


async def _init(coins=100_000, gems=100_000, catalysts=1000):
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems, catalysts) VALUES "
        "(1, ?, ?, ?), (2, 100, 100, 10), (3, 100, 100, 10), "
        "(4, 100, 100, 10)",
        (coins, gems, catalysts),
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._DB_TX_OWNER = None
    m._settings_cache.clear()


def _future(hours=24):
    return (datetime.datetime.now() + datetime.timedelta(hours=hours)).isoformat()


async def _insert_giveaway(
    db,
    *,
    creator_id=1,
    guild_id=100,
    scope="server",
    reward_type="coins",
    reward_id="",
    amount=100,
    winners=2,
    ends_at=None,
    status="active",
    title="Тестовый розыгрыш",
    message_id=None,
    channel_id=500,
):
    cursor = await db.execute(
        "INSERT INTO giveaways "
        "(guild_id, channel_id, message_id, creator_id, title, reward_type, "
        "reward_id, amount, winners_count, status, ends_at, winner_ids, scope) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?)",
        (
            guild_id,
            channel_id,
            message_id,
            creator_id,
            title,
            reward_type,
            reward_id,
            amount,
            winners,
            status,
            ends_at or _future(),
            scope,
        ),
    )
    await db.commit()
    return cursor.lastrowid


async def _coins(db, user_id):
    async with db.execute(
        "SELECT coins FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        return (await c.fetchone())[0]


async def _gems(db, user_id):
    async with db.execute(
        "SELECT gems FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        return (await c.fetchone())[0]


async def _inventory_count(db, user_id, item_id="basic_gen"):
    async with db.execute(
        "SELECT COUNT(*) FROM inventory WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    ) as c:
        return (await c.fetchone())[0]


def test_giveaway_reward_validation_covers_all_mechanics():
    async def run():
        db = await _init()
        try:
            coins, error = await m.giveaway_validate_reward("coins", "", "500")
            assert not error
            assert "500" in coins["summary"]

            gems, error = await m.giveaway_validate_reward("gems", "", "250")
            assert not error
            assert "250" in gems["summary"]

            catalysts, error = await m.giveaway_validate_reward(
                "catalysts", "", "3"
            )
            assert not error
            assert "3" in catalysts["summary"]

            generator, error = await m.giveaway_validate_reward(
                "generator", "basic_gen", "2"
            )
            assert not error
            assert "Базовый генератор" in generator["summary"]

            pet, error = await m.giveaway_validate_reward("pet", "cat", "1")
            assert not error
            assert "Кот" in pet["summary"]

            pet_level, error = await m.giveaway_validate_reward(
                "pet_level", "dog", "3"
            )
            assert not error
            assert "+3 ур." in pet_level["summary"]

            status, error = await m.giveaway_validate_reward(
                "status", "vip", "7"
            )
            assert not error
            assert "VIP" in status["summary"]

            clan_level, error = await m.giveaway_validate_reward(
                "clan_level", "", "2"
            )
            assert not error
            assert "+2 ур. клана" in clan_level["summary"]

            for reward_type, reward_id, amount in (
                ("unknown", "", "1"),
                ("generator", "missing_gen", "1"),
                ("pet", "missing_pet", "1"),
                ("status", "vip", "2"),
                ("status", "unknown", "1"),
                ("coins", "", "0"),
                ("gems", "", str(m.GIVEAWAY_MAX_GEMS + 1)),
                ("clan_level", "", "0"),
            ):
                meta, error = await m.giveaway_validate_reward(
                    reward_type, reward_id, amount
                )
                assert meta is None and error, (reward_type, reward_id, amount)
        finally:
            await _close(db)

    asyncio.run(run())


def test_join_rules_for_server_and_global_giveaways():
    async def run():
        db = await _init()
        try:
            server_id = await _insert_giveaway(db, guild_id=100, ends_at=_future())
            ok, message = await m.join_giveaway(server_id, 1, 100)
            assert not ok and "своём" in message

            ok, message = await m.join_giveaway(server_id, 2, 100)
            assert ok, message
            ok, message = await m.join_giveaway(server_id, 2, 100)
            assert not ok and "уже участвуешь" in message

            ok, message = await m.join_giveaway(server_id, 3, 999)
            assert not ok and "другом сервере" in message

            global_id = await _insert_giveaway(
                db, guild_id=None, scope="global", ends_at=_future()
            )
            ok, message = await m.join_giveaway(global_id, 3, 999)
            assert ok, message

            expired_id = await _insert_giveaway(
                db,
                guild_id=100,
                ends_at=(datetime.datetime.now() - datetime.timedelta(minutes=1)).isoformat(),
            )
            ok, message = await m.join_giveaway(expired_id, 3, 100)
            assert not ok and "истекло" in message

            no_player_id = await _insert_giveaway(db, guild_id=100)
            ok, message = await m.join_giveaway(no_player_id, 999, 100)
            assert not ok and "зарегистрируйся" in message

            clan_giveaway = await _insert_giveaway(
                db, guild_id=100, reward_type="clan_level", amount=1
            )
            ok, message = await m.join_giveaway(clan_giveaway, 2, 100)
            assert not ok and "клане" in message
        finally:
            await _close(db)

    asyncio.run(run())


def test_finish_giveaway_pays_winners_without_creator_charge():
    async def run():
        db = await _init(coins=10_000)
        try:
            giveaway_id = await _insert_giveaway(
                db, reward_type="coins", amount=1000, winners=3
            )
            await db.executemany(
                "INSERT INTO giveaway_entries (giveaway_id, user_id) "
                "VALUES (?, ?)",
                [(giveaway_id, 2), (giveaway_id, 3)],
            )
            await db.commit()

            await m.finish_giveaway(giveaway_id)

            assert await _coins(db, 2) == 1_100
            assert await _coins(db, 3) == 1_100
            assert await _coins(db, 1) == 10_000

            async with db.execute(
                "SELECT status, winner_ids FROM giveaways WHERE id = ?",
                (giveaway_id,),
            ) as c:
                status, winner_ids = await c.fetchone()
            assert status == "finished"
            assert set(__import__("json").loads(winner_ids)) == {2, 3}
        finally:
            await _close(db)

    asyncio.run(run())


def test_finish_clan_level_giveaway_filters_members():
    async def run():
        db = await _init(gems=5_000)
        try:
            await db.execute(
                "INSERT INTO clans (name, leader_id, level, bonus) "
                "VALUES ('Test Clan', 2, 1, 0.0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (2, 1, 'leader')"
            )
            await db.commit()

            giveaway_id = await _insert_giveaway(
                db,
                reward_type="clan_level",
                amount=1,
                winners=2,
            )
            await db.executemany(
                "INSERT INTO giveaway_entries (giveaway_id, user_id) "
                "VALUES (?, ?)",
                [(giveaway_id, 2), (giveaway_id, 3)],
            )
            await db.commit()

            await m.finish_giveaway(giveaway_id)

            async with db.execute(
                "SELECT level FROM clans WHERE id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 2
            assert await _gems(db, 1) == 5_000
            async with db.execute(
                "SELECT winner_ids FROM giveaways WHERE id = ?",
                (giveaway_id,),
            ) as c:
                assert __import__("json").loads((await c.fetchone())[0]) == [2]

            await db.execute(
                "UPDATE clans SET level = ? WHERE id = 1",
                (m.CLAN_MAX_LEVEL,),
            )
            await db.commit()
            assert await m.grant_clan_levels(1, 1) is None
        finally:
            await _close(db)

    asyncio.run(run())


def test_pet_and_status_rewards_apply():
    async def run():
        db = await _init()
        try:
            assert await m.grant_pet_reward(2, "cat", 2) == 3
            assert await m.grant_pet_reward(2, "cat", 0) == 4
            async with db.execute(
                "SELECT level FROM user_pets_v2 "
                "WHERE user_id = 2 AND pet_id = 'cat'"
            ) as c:
                assert (await c.fetchone())[0] == 4

            await db.execute(
                "UPDATE user_pets_v2 SET level = ? "
                "WHERE user_id = 2 AND pet_id = 'cat'",
                (m.PET_MAX_LEVEL,),
            )
            await db.commit()
            assert await m.grant_pet_reward(2, "cat", 1) == 0

            assert await m.grant_status_reward(2, "vip", 3)
            async with db.execute(
                "SELECT expires_at FROM player_upgrades "
                "WHERE user_id = 2 AND upgrade_id = 'vip'"
            ) as c:
                expiry = datetime.datetime.fromisoformat((await c.fetchone())[0])
            assert expiry > datetime.datetime.now() + datetime.timedelta(days=2)
        finally:
            await _close(db)

    asyncio.run(run())


def test_create_server_giveaway_posts_message_without_charge():
    async def run():
        db = await _init(coins=10_000)
        try:
            channel = FakeChannel(500)
            ok, message = await m.create_giveaway(
                1, 100, channel, "coins", "", "1000", "2", "24"
            )
            assert ok, message
            assert channel.sent
            async with db.execute(
                "SELECT scope, message_id, channel_id, status "
                "FROM giveaways"
            ) as c:
                row = await c.fetchone()
            assert row[0] == "server"
            assert row[1] in channel.messages and row[2] == 500
            assert row[3] == "active"
            assert await _coins(db, 1) == 10_000
        finally:
            await _close(db)

    asyncio.run(run())


def test_create_global_giveaway_posts_to_all_servers():
    async def run():
        db = await _init(coins=10_000)
        original = m.global_giveaway_guilds
        original_get_channel = m.bot.get_channel
        try:
            channels = {500: FakeChannel(500), 501: FakeChannel(501)}
            guilds = [
                FakeGuild(100, channels[500]),
                FakeGuild(101, channels[501]),
            ]
            m.global_giveaway_guilds = lambda: guilds
            m.bot.get_channel = lambda channel_id: channels.get(channel_id)

            ok, message = await m.create_global_giveaway(
                1, "gems", "", "100", "2", "24"
            )
            assert ok, message
            assert "2" in message
            assert len(channels[500].sent) == 1
            assert len(channels[501].sent) == 1
            assert await _gems(db, 1) == 100_000

            async with db.execute(
                "SELECT scope, guild_id, channel_id, message_id "
                "FROM giveaways"
            ) as c:
                scope, guild_id, _channel_id, _message_id = await c.fetchone()
            assert scope == "global"
            assert guild_id is None
            async with db.execute(
                "SELECT COUNT(*) FROM giveaway_messages"
            ) as c:
                assert (await c.fetchone())[0] == 2

            ok, message = await m.join_giveaway(1, 1, 999)
            assert not ok and "своём" in message
            ok, message = await m.join_giveaway(1, 2, 999)
            assert ok, message
            ok, message = await m.join_giveaway(1, 3, 999)
            assert ok, message

            await m.finish_giveaway(1)
            for channel in channels.values():
                for sent in channel.sent:
                    assert sent["view"].__class__.__name__ == "GiveawayJoinView"
                for sent_message in channel.messages.values():
                    assert sent_message.edited is not None
                    assert (
                        sent_message.edited["view"].__class__.__name__
                        == "GiveawayFinishedView"
                    )
        finally:
            m.global_giveaway_guilds = original
            m.bot.get_channel = original_get_channel
            await _close(db)

    asyncio.run(run())


def test_giveaways_are_only_in_admin_panel():
    social = m.SocialView(1)
    labels = [
        getattr(child, "label", None) for child in social.children
    ]
    assert "Розыгрыши" not in labels
    assert hasattr(m, "AdminGiveawaysView")
    assert not hasattr(m, "GiveawaysView")


def test_select_giveaway_channel_skips_denied_channels():
    denied = FakeChannel(1, allow=False)
    allowed = FakeChannel(2, allow=True)
    guild = FakeGuild(100, denied)
    guild.text_channels = [denied, allowed]
    assert m.select_giveaway_channel(guild) is allowed


def test_send_giveaway_message_mentions_everyone():
    async def run():
        db = await _init()
        original_get = m.get_giveaway
        original_build = m.build_giveaway_embed
        original_view = m.GiveawayJoinView
        original_add = m.bot.add_view
        try:
            async def fake_get(_giveaway_id):
                return (1, 100, 500, 1, 1, "title", "coins", "", 10, 1)

            async def fake_build(_giveaway):
                return object()

            class FakeView:
                def __init__(self, giveaway_id):
                    self.giveaway_id = giveaway_id

            added = []

            def fake_add_view(view, message_id=None):
                added.append((view, message_id))

            m.get_giveaway = fake_get
            m.build_giveaway_embed = fake_build
            m.GiveawayJoinView = FakeView
            m.bot.add_view = fake_add_view
            channel = FakeChannel(500)
            message = await m.send_giveaway_message(channel, 1)
            assert message.id
            sent = channel.sent[-1]
            assert sent["content"] == "@everyone"
            assert sent["allowed_mentions"].everyone is True
            assert sent["allowed_mentions"].users is False
            assert sent["allowed_mentions"].roles is False
            assert added and added[0][1] == message.id
        finally:
            m.get_giveaway = original_get
            m.build_giveaway_embed = original_build
            m.GiveawayJoinView = original_view
            m.bot.add_view = original_add
            await _close(db)

    asyncio.run(run())


def test_old_giveaways_table_gets_scope_column():
    async def run():
        m._DB_WRITE_LOCK = asyncio.Lock()
        m._DB_TX_OWNER = None
        m._settings_cache.clear()
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await db.execute("""
                CREATE TABLE giveaways (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    channel_id INTEGER,
                    message_id INTEGER,
                    creator_id INTEGER,
                    title TEXT,
                    reward_type TEXT,
                    reward_id TEXT,
                    amount INTEGER,
                    winners_count INTEGER,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ends_at TIMESTAMP,
                    winner_ids TEXT DEFAULT '[]'
                )
            """)
            await db.execute(
                "INSERT INTO giveaways (guild_id, creator_id, title, "
                "reward_type, reward_id, amount, winners_count, ends_at) "
                "VALUES (100, 1, 'old', 'coins', '', 100, 1, ?)",
                (_future(),),
            )
            await db.commit()
            await m.bot.init_db()
            columns = await m.get_table_columns(db, "giveaways")
            assert "scope" in columns
            async with db.execute(
                "SELECT scope FROM giveaways WHERE title = 'old'"
            ) as c:
                assert (await c.fetchone())[0] == "server"
            columns = await m.get_table_columns(db, "giveaway_messages")
            assert {"giveaway_id", "guild_id", "channel_id", "message_id"} <= columns
        finally:
            await db.close()
            m.bot.db = None
            m._DB_TX_OWNER = None
            m._settings_cache.clear()

    asyncio.run(run())


def test_global_giveaway_send_concurrency_is_bounded():
    async def run():
        db = await _init(coins=10_000)
        original_guilds = m.global_giveaway_guilds
        original_send = m.send_giveaway_message
        try:
            channels = {
                500 + index: FakeChannel(500 + index) for index in range(12)
            }
            guilds = [
                FakeGuild(100 + index, channels[500 + index])
                for index in range(12)
            ]
            m.global_giveaway_guilds = lambda: guilds
            active = 0
            max_active = 0

            async def fake_send(channel, giveaway_id):
                nonlocal active, max_active
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.02)
                active -= 1
                return FakeMessage(channel.id)

            m.send_giveaway_message = fake_send
            ok, message = await m.create_global_giveaway(
                1, "gems", "", "100", "1", "24"
            )
            assert ok, message
            assert "12" in message
            assert max_active <= m.GIVEAWAY_GLOBAL_SEND_CONCURRENCY
            assert max_active >= 2
        finally:
            m.global_giveaway_guilds = original_guilds
            m.send_giveaway_message = original_send
            await _close(db)

    asyncio.run(run())
