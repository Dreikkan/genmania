"""Tests for web game command execution in CastleBot."""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import tempfile
from unittest import mock

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("genmania_web_game_handler_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakePermissions:
    def __init__(self, administrator: bool):
        self.administrator = administrator


class FakeAvatar:
    url = "https://example.test/avatar.png"


class FakeRole:
    def __init__(self, role_id: int, name: str):
        self.id = role_id
        self.name = name


class FakeMember:
    def __init__(self, user_id: int, name: str, admin: bool = False):
        self.id = user_id
        self.name = name
        self.display_name = name
        self.display_avatar = FakeAvatar()
        self.guild_permissions = FakePermissions(admin)
        self.roles = [FakeRole(777, "Администратор")] if admin else []
        self.bot = False


class FakeTextChannel:
    def __init__(self, channel_id: int, name: str, position: int = 0):
        self.id = channel_id
        self.name = name
        self.position = position


class FakeGuild:
    def __init__(self):
        self.id = 42
        self.name = "420 SQUAD"
        self.owner_id = 1
        self.member_count = 3
        self.members = [
            FakeMember(1, "Vortex", admin=True),
            FakeMember(2, "Kira"),
            FakeMember(3, "Guest"),
        ]
        self.roles = [FakeRole(777, "Администратор")]
        self.icon = None
        self.text_channels = [FakeTextChannel(500, "general")]

    def get_member(self, user_id: int):
        return next((member for member in self.members if member.id == user_id), None)


def _guild():
    guild = FakeGuild()
    m.bot.get_guild = lambda guild_id: guild if guild_id == 42 else None
    m.bot._connection._guilds = {42: guild}
    return guild


def test_web_game_state_collect_and_admin():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()

        async def fake_is_owner(user):
            return getattr(user, "id", None) == 1

        m.bot.is_owner = fake_is_owner
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES "
            "(1, 5000, 10), (2, 0, 5)"
        )
        await db.commit()
        try:
            state = await m.bot.handle_web_game_command(
                {
                    "id": "s1",
                    "action": "state",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert state["ok"] is True
            assert state["guild_name"] == "420 SQUAD"
            assert state["player"]["name"] == "Vortex"
            assert state["player"]["is_admin"] is True
            assert state["player"]["grid_side"] == 3
            assert state["is_owner"] is True
            assert len(state["guilds"]) == 1
            assert len(state["admin_guilds"]) == 1
            assert state["admin_guilds"][0]["channels"] == [
                {"id": "500", "name": "general", "position": 0}
            ]
            assert state["admin_guilds"][0]["local_top"][0]["discord_id"] == "1"
            assert state["admin_guilds"][0]["local_top"][0]["coins"] == 5000
            assert state["giveaway_rewards"]

            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "income_gems_per_hour, rarity) VALUES "
                "('gen_test', 'Тестовый генератор', 1000, 3600, 0, 'common')"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 1, 'gen_test', 'profile', 0)"
            )
            await db.execute(
                "UPDATE players SET last_collected = datetime('now', '-1 hour') "
                "WHERE user_id = 1"
            )
            await db.commit()

            collected = await m.bot.handle_web_game_command(
                {
                    "id": "c1",
                    "action": "collect",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert collected["ok"] is True
            assert collected["coins"] >= 3000
            assert "state" in collected

            grant = {
                "id": "g1",
                "action": "admin_grant",
                "user_id": "1",
                "guild_id": "42",
                "payload": {
                    "target_id": "2",
                    "currency": "coins",
                    "amount": 1000,
                },
            }
            granted = await m.bot.handle_web_game_command(grant)
            assert granted["ok"] is True
            assert granted["coins"] == 1000
            again = await m.bot.handle_web_game_command(grant)
            assert again == granted
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as cursor:
                assert (await cursor.fetchone())[0] == 1000

            reset = await m.bot.handle_web_game_command(
                {
                    "id": "r1",
                    "action": "admin_reset",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {"target_id": "2"},
                }
            )
            assert reset["ok"] is True
            assert "removed" in reset
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_giveaway_permissions_and_dispatch():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        guild = _guild()
        guild.members.append(FakeMember(4, "LocalAdmin", admin=True))

        async def fake_is_owner(user):
            return getattr(user, "id", None) == 1

        calls = {}

        async def fake_create(
            creator_id,
            guild_id,
            channel,
            reward_type,
            reward_id,
            amount,
            winners,
            duration_hours,
        ):
            calls["local"] = (channel, guild_id, reward_type, amount, winners)
            return True, "✅ Локальный розыгрыш создан"

        async def fake_global(
            creator_id,
            reward_type,
            reward_id,
            amount,
            winners,
            duration_hours,
        ):
            calls["global"] = (reward_type, amount, winners)
            return True, "✅ Глобальный розыгрыш создан"

        original_create = m.create_giveaway
        original_global = m.create_global_giveaway
        original_channel = m.select_giveaway_channel
        original_resolver = m.bot._web_game_giveaway_channel
        selected_channel = object()
        m.bot.is_owner = fake_is_owner
        m.create_giveaway = fake_create
        m.create_global_giveaway = fake_global
        m.select_giveaway_channel = lambda _guild: selected_channel
        m.bot._web_game_giveaway_channel = (
            lambda _guild, _raw_channel_id: selected_channel
        )
        try:
            local = await m.bot.handle_web_game_command(
                {
                    "id": "giveaway-local",
                    "action": "admin_giveaway",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {
                        "scope": "server",
                        "channel_id": "500",
                        "reward_type": "coins",
                        "amount": 100,
                        "winners": 2,
                        "duration_hours": 24,
                    },
                }
            )
            assert local["ok"] is True
            assert local["scope"] == "server"
            assert calls["local"] == (
                selected_channel,
                42,
                "coins",
                100,
                2,
            )

            global_result = await m.bot.handle_web_game_command(
                {
                    "id": "giveaway-global",
                    "action": "admin_giveaway",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {
                        "scope": "global",
                        "reward_type": "gems",
                        "amount": 25,
                        "winners": 1,
                        "duration_hours": 6,
                    },
                }
            )
            assert global_result["ok"] is True
            assert global_result["scope"] == "global"
            assert calls["global"] == ("gems", 25, 1)

            try:
                await m.bot.handle_web_game_command(
                    {
                        "id": "giveaway-global-local-admin",
                        "action": "admin_giveaway",
                        "user_id": "4",
                        "guild_id": "42",
                        "payload": {
                            "scope": "global",
                            "reward_type": "coins",
                            "amount": 10,
                            "winners": 1,
                            "duration_hours": 1,
                        },
                    }
                )
            except PermissionError:
                pass
            else:
                raise AssertionError(
                    "локальный админ не должен создавать глобальный розыгрыш"
                )
        finally:
            m.create_giveaway = original_create
            m.create_global_giveaway = original_global
            m.select_giveaway_channel = original_channel
            m.bot._web_game_giveaway_channel = original_resolver
            await db.close()

    asyncio.run(run())


def test_web_game_top_exclusions_local_and_global():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        m._top_cache.clear()
        await db.execute("INSERT INTO players (user_id) VALUES (2)")
        await db.commit()
        guild = _guild()
        guild.members.append(FakeMember(4, "LocalAdmin", admin=True))

        async def fake_is_owner(user):
            return getattr(user, "id", None) == 1

        m.bot.is_owner = fake_is_owner
        try:
            local = await m.bot.handle_web_game_command(
                {
                    "id": "top-local-exclude",
                    "action": "admin_top_exclude",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {
                        "target_id": "2",
                        "scope": "server",
                        "exclude": True,
                    },
                }
            )
            assert local["ok"] is True
            assert local["scope"] == "server"
            assert local["changed"] is True
            exclusions = await m.bot._web_game_guild_top_exclusions(guild)
            assert exclusions == [
                {"id": "2", "name": "Kira", "handle": "Kira"}
            ]
            assert await m.bot._web_game_global_top_exclusions(guild) == []

            again = await m.bot.handle_web_game_command(
                {
                    "id": "top-local-exclude-again",
                    "action": "admin_top_exclude",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {
                        "target_id": "2",
                        "scope": "server",
                        "exclude": True,
                    },
                }
            )
            assert again["changed"] is False

            local_admin = await m.bot.handle_web_game_command(
                {
                    "id": "top-local-admin",
                    "action": "admin_top_exclude",
                    "user_id": "4",
                    "guild_id": "42",
                    "payload": {
                        "target_id": "2",
                        "scope": "server",
                        "exclude": False,
                    },
                }
            )
            assert local_admin["ok"] is True
            assert local_admin["changed"] is True
            assert await m.bot._web_game_guild_top_exclusions(guild) == []

            try:
                await m.bot.handle_web_game_command(
                    {
                        "id": "top-global-denied",
                        "action": "admin_top_exclude",
                        "user_id": "4",
                        "guild_id": "42",
                        "payload": {
                            "target_id": "2",
                            "scope": "global",
                            "exclude": True,
                        },
                    }
                )
            except PermissionError:
                pass
            else:
                raise AssertionError(
                    "локальный админ не должен исключать из глобального топа"
                )

            global_exclude = await m.bot.handle_web_game_command(
                {
                    "id": "top-global-exclude",
                    "action": "admin_top_exclude",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {
                        "target_id": "2",
                        "scope": "global",
                        "exclude": True,
                    },
                }
            )
            assert global_exclude["ok"] is True
            assert global_exclude["changed"] is True
            global_exclusions = await m.bot._web_game_global_top_exclusions(
                guild
            )
            assert global_exclusions == [
                {"id": "2", "name": "Kira", "handle": "Kira"}
            ]

            global_include = await m.bot.handle_web_game_command(
                {
                    "id": "top-global-include",
                    "action": "admin_top_exclude",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {
                        "target_id": "2",
                        "scope": "global",
                        "exclude": False,
                    },
                }
            )
            assert global_include["changed"] is True
            assert await m.bot._web_game_global_top_exclusions(guild) == []
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_giveaway_list_and_cancel():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        guild = _guild()
        guild.members.append(FakeMember(4, "LocalAdmin", admin=True))

        async def fake_is_owner(user):
            return getattr(user, "id", None) == 1

        m.bot.is_owner = fake_is_owner
        await db.execute(
            "INSERT INTO giveaways (guild_id, channel_id, message_id, "
            "creator_id, title, reward_type, reward_id, amount, "
            "winners_count, status, ends_at, scope) VALUES "
            "(42, 500, 900, 1, 'Локальный', 'coins', '', 10, 1, "
            "'active', '2099-01-01T00:00:00', 'server')"
        )
        await db.execute(
            "INSERT INTO giveaways (guild_id, channel_id, message_id, "
            "creator_id, title, reward_type, reward_id, amount, "
            "winners_count, status, ends_at, scope) VALUES "
            "(NULL, NULL, NULL, 1, 'Глобальный', 'gems', '', 10, 1, "
            "'active', '2099-01-01T00:00:00', 'global')"
        )
        await db.commit()

        updates = []
        original_update = m.update_giveaway_message

        async def fake_update(giveaway_id):
            updates.append(giveaway_id)

        m.update_giveaway_message = fake_update
        try:
            local_list = await m.bot._web_game_guild_giveaways(guild)
            assert local_list[0]["title"] == "Локальный"
            assert local_list[0]["status"] == "active"
            global_list = await m.bot._web_game_global_giveaways()
            assert global_list[0]["title"] == "Глобальный"

            cancelled = await m.bot.handle_web_game_command(
                {
                    "id": "giveaway-cancel",
                    "action": "admin_giveaway_cancel",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {"giveaway_id": "1"},
                }
            )
            assert cancelled["ok"] is True
            assert cancelled["status"] == "cancelled"
            assert updates == [1]

            again = await m.bot.handle_web_game_command(
                {
                    "id": "giveaway-cancel-again",
                    "action": "admin_giveaway_cancel",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {"giveaway_id": "1"},
                }
            )
            assert again["changed"] is False

            try:
                await m.bot.handle_web_game_command(
                    {
                        "id": "giveaway-cancel-global-denied",
                        "action": "admin_giveaway_cancel",
                        "user_id": "4",
                        "guild_id": "42",
                        "payload": {"giveaway_id": "2"},
                    }
                )
            except PermissionError:
                pass
            else:
                raise AssertionError(
                    "локальный админ не должен отменять глобальный розыгрыш"
                )

            global_cancelled = await m.bot.handle_web_game_command(
                {
                    "id": "giveaway-cancel-global",
                    "action": "admin_giveaway_cancel",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {"giveaway_id": "2"},
                }
            )
            assert global_cancelled["scope"] == "global"
            assert updates == [1, 2]
        finally:
            m.update_giveaway_message = original_update
            await db.close()

    asyncio.run(run())


def test_web_game_buy_move_sell_generator():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems, grid_size, "
            "storage_size) VALUES (1, 10000, 0, 9, 36)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO items (id, name, price, income_per_hour, "
            "income_gems_per_hour, rarity, buyable) VALUES "
            "('basic_gen', 'Базовый генератор', 1000, 1, 0, "
            "'common', 1)"
        )
        await db.commit()

        async def noop(*_args, **_kwargs):
            return None

        async def noop_achievements(*_args, **_kwargs):
            return []

        originals = {
            name: getattr(m, name)
            for name in (
                "update_quest_progress",
                "check_achievements",
                "complete_onboarding_step",
                "get_clan",
                "update_clan_quest",
                "update_story_quests",
            )
        }
        m.update_quest_progress = noop
        m.check_achievements = noop_achievements
        m.complete_onboarding_step = noop
        m.get_clan = noop
        m.update_clan_quest = noop
        m.update_story_quests = noop
        try:
            bought = await m.bot.handle_web_game_command(
                {
                    "id": "buy-1",
                    "action": "buy_generator",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {"item_id": "basic_gen", "quantity": 2},
                }
            )
            assert bought["ok"] is True
            assert bought["cost"] == 1500
            assert bought["discount"] == 500
            assert bought["placement"] == {
                "profile": 2,
                "storage": 0,
                "temp": 0,
            }
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 1"
            ) as cursor:
                assert (await cursor.fetchone())[0] == 8500
            assert len(bought["state"]["inventory"]) == 2
            assert all(
                item["income_hour"] == 3600
                for item in bought["state"]["inventory"]
            )

            moved = await m.bot.handle_web_game_command(
                {
                    "id": "move-1",
                    "action": "move_generator",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {"location": "profile", "slot": 0},
                }
            )
            assert moved["ok"] is True
            assert moved["target"] == "storage"
            storage_items = [
                item for item in moved["state"]["inventory"]
                if item["location"] == "storage"
            ]
            assert len(storage_items) == 1
            assert storage_items[0]["can_sell"] is True

            sold = await m.bot.handle_web_game_command(
                {
                    "id": "sell-1",
                    "action": "sell_generator",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {"slot": storage_items[0]["slot"]},
                }
            )
            assert sold["ok"] is True
            assert sold["sell_price"] == 100
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 1"
            ) as cursor:
                assert (await cursor.fetchone())[0] == 8600
        finally:
            for name, value in originals.items():
                setattr(m, name, value)
            await db.close()

    asyncio.run(run())


def test_web_game_star_upgrade():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems, grid_size, "
            "storage_size) VALUES (1, 1000, 10, 9, 36)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO items (id, name, price, income_per_hour, "
            "income_gems_per_hour, rarity, buyable) VALUES "
            "('basic_gen', 'Базовый генератор', 1000, 1, 0, "
            "'common', 1)"
        )
        await db.executemany(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
            "VALUES (1, ?, 'basic_gen', 'profile', 0)",
            [(0,), (1,)],
        )
        await db.commit()
        try:
            result = await m.bot.handle_web_game_command(
                {
                    "id": "star-1",
                    "action": "upgrade_star",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {"location": "profile", "slot": 0},
                }
            )
            assert result["ok"] is True
            assert result["success"] is True
            assert result["next_star"] == 1
            async with db.execute(
                "SELECT slot, stars FROM inventory "
                "WHERE user_id = 1 ORDER BY slot"
            ) as cursor:
                rows = await cursor.fetchall()
            assert len(rows) == 1
            assert rows[0][1] == 1
            state_items = result["state"]["inventory"]
            assert len(state_items) == 1
            assert state_items[0]["stars"] == 1
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_craft_generator():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems, catalysts, "
            "grid_size, storage_size) VALUES (1, 1000, 10, 1, 9, 36)"
        )
        await db.executemany(
            "INSERT OR REPLACE INTO items (id, name, price, "
            "income_per_hour, income_gems_per_hour, rarity, buyable) "
            "VALUES (?, ?, ?, ?, 0, 'common', 1)",
            [
                ("basic_gen", "Базовый генератор", 1000, 1),
                ("copper_gen", "Медный генератор", 2000, 2),
            ],
        )
        await db.executemany(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
            "VALUES (1, ?, 'basic_gen', 'profile', 0)",
            [(0,), (1,)],
        )
        await db.commit()
        try:
            result = await m.bot.handle_web_game_command(
                {
                    "id": "craft-1",
                    "action": "craft_generator",
                    "user_id": "1",
                    "guild_id": "42",
                    "payload": {"item_id": "basic_gen"},
                }
            )
            assert result["ok"] is True
            assert result["success"] is True
            assert result["dst_id"] == "copper_gen"
            assert result["state"]["inventory"][0]["item_id"] == "copper_gen"
            assert len(result["state"]["inventory"]) == 1
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_bank_deposit_and_withdraw():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES (2, 10000, 0)"
        )
        await db.commit()
        try:
            result = await m.bot.handle_web_game_command(
                {
                    "id": "bank-deposit-1",
                    "action": "bank_deposit",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"amount": 1000, "days": 7},
                }
            )
            assert result["ok"] is True
            assert result["amount"] == 1000
            assert result["payout"] > 1000
            assert result["state"]["bank"]["deposit"]["amount"] == 1000
            assert result["state"]["player"]["coins"] == 9000

            withdraw = await m.bot.handle_web_game_command(
                {
                    "id": "bank-withdraw-1",
                    "action": "bank_withdraw",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert withdraw["ok"] is True
            assert withdraw["matured"] is False
            assert withdraw["payout"] == 1000
            assert withdraw["state"]["bank"]["deposit"] is None
            assert withdraw["state"]["player"]["coins"] == 10000
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_bank_loan_and_repay():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES (2, 1000, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO items (id, name, price, "
            "income_per_hour, income_gems_per_hour, rarity, buyable) "
            "VALUES ('basic_gen', 'Базовый генератор', 1000, 1, 0, "
            "'common', 1)"
        )
        await db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
            "VALUES (2, 0, 'basic_gen', 'profile', 0)"
        )
        await db.commit()
        try:
            result = await m.bot.handle_web_game_command(
                {
                    "id": "bank-loan-1",
                    "action": "bank_take_loan",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {
                        "item_id": "basic_gen",
                        "stars": 0,
                        "amount": 500,
                    },
                }
            )
            assert result["ok"] is True
            assert result["amount"] == 500
            assert result["total_due"] == 625
            assert result["state"]["player"]["coins"] == 1500
            assert result["state"]["bank"]["loan"]["amount"] == 500
            assert result["state"]["bank"]["loan"]["total_due"] == 625
            assert not any(
                item["item_id"] == "basic_gen"
                for item in result["state"]["inventory"]
            )

            repay = await m.bot.handle_web_game_command(
                {
                    "id": "bank-repay-1",
                    "action": "bank_repay_loan",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert repay["ok"] is True
            assert repay["total_due"] == 625
            assert repay["state"]["player"]["coins"] == 875
            assert repay["state"]["bank"]["loan"] is None
            assert any(
                item["item_id"] == "basic_gen"
                for item in repay["state"]["inventory"]
            )
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_clan_create_apply_and_approve():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES "
            "(2, 1000, 0), (3, 0, 0)"
        )
        await db.commit()
        try:
            created = await m.bot.handle_web_game_command(
                {
                    "id": "clan-create-1",
                    "action": "clan_create",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"name": "Ночной дозор"},
                }
            )
            assert created["ok"] is True
            assert created["state"]["player"]["coins"] == 500
            details = created["state"]["clan"]["details"]
            assert details["role"] == "leader"
            assert details["name"] == "Ночной дозор"
            clan_id = created["clan_id"]

            browser = await m.bot.handle_web_game_command(
                {
                    "id": "clan-state-1",
                    "action": "state",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            entry = next(
                row
                for row in browser["clan"]["browser"]
                if row["id"] == clan_id
            )
            assert entry["can_apply"] is True

            applied = await m.bot.handle_web_game_command(
                {
                    "id": "clan-apply-1",
                    "action": "clan_apply",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {"clan_id": clan_id},
                }
            )
            assert applied["ok"] is True
            assert applied["state"]["clan"]["in_clan"] is False
            pending = applied["state"]["clan"]["pending_application"]
            assert pending["clan_name"] == "Ночной дозор"

            leader_state = await m.bot.handle_web_game_command(
                {
                    "id": "clan-state-2",
                    "action": "state",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            applications = leader_state["clan"]["details"]["applications"]
            assert len(applications) == 1

            decided = await m.bot.handle_web_game_command(
                {
                    "id": "clan-app-decide-1",
                    "action": "clan_application_decide",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {
                        "application_id": applications[0]["id"],
                        "approve": True,
                    },
                }
            )
            assert decided["ok"] is True
            assert decided["approved"] is True
            assert decided["state"]["clan"]["details"]["members_count"] == 2
            assert decided["state"]["clan"]["details"]["applications"] == []

            member_state = await m.bot.handle_web_game_command(
                {
                    "id": "clan-state-3",
                    "action": "state",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert member_state["clan"]["in_clan"] is True
            assert member_state["clan"]["details"]["role"] == "member"
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_clan_donate_and_expand():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES (2, 5000, 0)"
        )
        await db.commit()
        try:
            created = await m.bot.handle_web_game_command(
                {
                    "id": "clan-create-2",
                    "action": "clan_create",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"name": "Складской союз"},
                }
            )
            donated = await m.bot.handle_web_game_command(
                {
                    "id": "clan-donate-1",
                    "action": "clan_donate",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"amount": 1000},
                }
            )
            assert donated["state"]["player"]["coins"] == 3500
            assert donated["state"]["clan"]["details"]["treasury"] == 1000

            expanded = await m.bot.handle_web_game_command(
                {
                    "id": "clan-expand-1",
                    "action": "clan_expand",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert expanded["ok"] is True
            assert expanded["old_capacity"] == 10
            assert expanded["new_capacity"] == 15
            assert expanded["state"]["clan"]["details"]["capacity"] == 15
            assert expanded["state"]["clan"]["details"]["treasury"] == 0
            assert created["clan_id"] == expanded["state"]["clan"]["details"]["id"]
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_clan_leave_returns_treasury():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES (2, 1000, 0)"
        )
        await db.commit()
        try:
            await m.bot.handle_web_game_command(
                {
                    "id": "clan-create-3",
                    "action": "clan_create",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"name": "Одинокий замок"},
                }
            )
            await m.bot.handle_web_game_command(
                {
                    "id": "clan-donate-2",
                    "action": "clan_donate",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"amount": 300},
                }
            )
            left = await m.bot.handle_web_game_command(
                {
                    "id": "clan-leave-1",
                    "action": "clan_leave",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert left["ok"] is True
            assert left["disbanded"] is True
            assert left["treasury_returned"] == 300
            assert left["state"]["player"]["coins"] == 500
            assert left["state"]["clan"]["in_clan"] is False
            assert left["state"]["clan"]["browser"] == []
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_clan_invite_accept():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES "
            "(2, 1000, 0), (3, 0, 0)"
        )
        await db.commit()
        try:
            created = await m.bot.handle_web_game_command(
                {
                    "id": "clan-create-4",
                    "action": "clan_create",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"name": "Приглашённые"},
                }
            )
            clan_id = int(created["clan_id"])
            cursor = await db.execute(
                "INSERT INTO clan_invites (clan_id, inviter_id, target_id) "
                "VALUES (?, 2, 3)",
                (clan_id,),
            )
            invite_id = cursor.lastrowid
            await db.commit()

            accepted = await m.bot.handle_web_game_command(
                {
                    "id": "clan-invite-1",
                    "action": "clan_invite_accept",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {"invite_id": invite_id},
                }
            )
            assert accepted["ok"] is True
            assert accepted["state"]["clan"]["in_clan"] is True
            assert accepted["state"]["clan"]["details"]["role"] == "member"
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_market_buy_and_sell():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES (2, 10000, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO items (id, name, price, "
            "income_per_hour, income_gems_per_hour, rarity, buyable) "
            "VALUES ('basic_gen', 'Базовый генератор', 1000, 1, 0, "
            "'common', 1)"
        )
        await db.execute(
            "INSERT INTO market_prices (item_id, base_price, "
            "current_price, demand, supply) "
            "VALUES ('basic_gen', 1000, 1000, 0, 0) "
            "ON CONFLICT(item_id) DO UPDATE SET "
            "base_price = 1000, current_price = 1000, "
            "demand = 0, supply = 0"
        )
        await db.commit()
        try:
            bought = await m.bot.handle_web_game_command(
                {
                    "id": "market-buy-1",
                    "action": "market_buy",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {
                        "item_id": "basic_gen",
                        "quantity": 2,
                    },
                }
            )
            assert bought["ok"] is True
            assert bought["state"]["player"]["coins"] < 10000
            assert len(bought["state"]["inventory"]) == 2

            await db.execute(
                "UPDATE inventory SET location = 'storage' "
                "WHERE user_id = 2 AND item_id = 'basic_gen'"
            )
            await db.commit()
            coins_before = bought["state"]["player"]["coins"]
            sold = await m.bot.handle_web_game_command(
                {
                    "id": "market-sell-1",
                    "action": "market_sell",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {
                        "item_id": "basic_gen",
                        "quantity": 1,
                    },
                }
            )
            assert sold["ok"] is True
            assert sold["state"]["player"]["coins"] > coins_before
            assert len(sold["state"]["inventory"]) == 1
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_market_order_create_and_fill():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES "
            "(2, 10000, 0), (3, 10000, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO items (id, name, price, "
            "income_per_hour, income_gems_per_hour, rarity, buyable) "
            "VALUES ('basic_gen', 'Базовый генератор', 1000, 1, 0, "
            "'common', 1)"
        )
        await db.execute(
            "INSERT INTO market_prices (item_id, base_price, "
            "current_price, demand, supply) "
            "VALUES ('basic_gen', 1000, 1000, 0, 0) "
            "ON CONFLICT(item_id) DO UPDATE SET "
            "base_price = 1000, current_price = 1000, "
            "demand = 0, supply = 0"
        )
        await db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
            "VALUES (2, 0, 'basic_gen', 'storage', 0)"
        )
        await db.commit()
        try:
            created = await m.bot.handle_web_game_command(
                {
                    "id": "market-order-create-1",
                    "action": "market_order_create",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {
                        "side": "sell",
                        "item_id": "basic_gen",
                        "quantity": 1,
                        "price": 1000,
                    },
                }
            )
            assert created["ok"] is True
            assert len(created["state"]["market"]["my_orders"]) == 1
            assert created["state"]["inventory"] == []
            order_id = created["state"]["market"]["my_orders"][0]["id"]

            filled = await m.bot.handle_web_game_command(
                {
                    "id": "market-order-fill-1",
                    "action": "market_order_fill",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {"order_id": order_id},
                }
            )
            assert filled["ok"] is True
            assert any(
                item["item_id"] == "basic_gen"
                for item in filled["state"]["inventory"]
            )
            assert filled["state"]["market"]["my_orders"] == []

            seller_state = await m.bot.handle_web_game_command(
                {
                    "id": "market-state-1",
                    "action": "state",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert seller_state["market"]["my_orders"] == []
            assert seller_state["player"]["coins"] > 10000
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_pvp_raid():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES "
            "(2, 1000, 0), (3, 10000, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO items (id, name, price, "
            "income_per_hour, income_gems_per_hour, rarity, buyable) "
            "VALUES ('basic_gen', 'Базовый генератор', 1000, 1, 0, "
            "'common', 1)"
        )
        await db.executemany(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
            "VALUES (?, 0, 'basic_gen', 'profile', 0)",
            [(2,), (3,)],
        )
        await db.commit()
        try:
            with mock.patch.object(
                m.random, "randint", side_effect=[1000, 1]
            ):
                raided = await m.bot.handle_web_game_command(
                    {
                        "id": "pvp-raid-1",
                        "action": "pvp_raid",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"target_id": "3"},
                    }
                )
            assert raided["ok"] is True
            assert raided["success"] is True
            assert raided["loot"] > 0
            assert raided["state"]["player"]["coins"] > 1000
            assert raided["state"]["pvp"]["stats"]["raid_cd"] > 0
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_pvp_espionage():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES "
            "(2, 1000, 0), (3, 10000, 5)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO items (id, name, price, "
            "income_per_hour, income_gems_per_hour, rarity, buyable) "
            "VALUES ('basic_gen', 'Базовый генератор', 1000, 1, 0, "
            "'common', 1)"
        )
        await db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
            "VALUES (3, 0, 'basic_gen', 'profile', 0)"
        )
        await db.commit()
        try:
            intel = await m.bot.handle_web_game_command(
                {
                    "id": "pvp-espionage-1",
                    "action": "pvp_espionage",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"target_id": "3"},
                }
            )
            assert intel["ok"] is True
            assert intel["intel"]["power"] == 1000
            assert intel["intel"]["generators"] == 1
            assert intel["state"]["pvp"]["stats"]["espionage_cd"] > 0
            try:
                await m.bot.handle_web_game_command(
                    {
                        "id": "pvp-espionage-2",
                        "action": "pvp_espionage",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"target_id": "3"},
                    }
                )
            except ValueError as exc:
                assert "Шпионаж" in str(exc)
            else:
                raise AssertionError("Повторный шпионаж должен быть отклонён")
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_auction_create_bid_and_buyout():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES "
            "(2, 10000, 0), (3, 10000, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO items (id, name, price, "
            "income_per_hour, income_gems_per_hour, rarity, buyable) "
            "VALUES ('epic_gen', 'Эпический генератор', 5000, 5, 0, "
            "'epic', 0)"
        )
        await db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
            "VALUES (2, 0, 'epic_gen', 'profile', 0)"
        )
        await db.commit()
        try:
            created = await m.bot.handle_web_game_command(
                {
                    "id": "auction-create-1",
                    "action": "auction_create",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {
                        "slot": 0,
                        "item_id": "epic_gen",
                        "stars": 0,
                        "start_price": 1000,
                        "buyout_price": 2000,
                        "hours": 24,
                    },
                }
            )
            assert created["ok"] is True
            assert len(created["state"]["auction"]["my_lots"]) == 1
            assert created["state"]["inventory"] == []
            lot_id = created["state"]["auction"]["my_lots"][0]["id"]

            bid = await m.bot.handle_web_game_command(
                {
                    "id": "auction-bid-1",
                    "action": "auction_bid",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {
                        "auction_id": lot_id,
                        "amount": 1200,
                    },
                }
            )
            assert bid["ok"] is True
            lot = next(
                item
                for item in bid["state"]["auction"]["lots"]
                if item["id"] == lot_id
            )
            assert lot["current_bid"] == 1200
            assert lot["current_bidder"] == "3"

            bought = await m.bot.handle_web_game_command(
                {
                    "id": "auction-buyout-1",
                    "action": "auction_buyout",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {"auction_id": lot_id},
                }
            )
            assert bought["ok"] is True
            assert bought["state"]["auction"]["my_lots"] == []
            assert any(
                item["item_id"] == "epic_gen"
                for item in bought["state"]["inventory"]
            )

            seller_state = await m.bot.handle_web_game_command(
                {
                    "id": "auction-state-1",
                    "action": "state",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert seller_state["player"]["coins"] > 10000
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_auction_cancel_refunds_bidder():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES "
            "(2, 10000, 0), (3, 10000, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO items (id, name, price, "
            "income_per_hour, income_gems_per_hour, rarity, buyable) "
            "VALUES ('epic_gen', 'Эпический генератор', 5000, 5, 0, "
            "'epic', 0)"
        )
        await db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
            "VALUES (2, 0, 'epic_gen', 'profile', 0)"
        )
        await db.commit()
        try:
            created = await m.bot.handle_web_game_command(
                {
                    "id": "auction-create-2",
                    "action": "auction_create",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {
                        "slot": 0,
                        "item_id": "epic_gen",
                        "stars": 0,
                        "start_price": 1000,
                        "buyout_price": 0,
                        "hours": 12,
                    },
                }
            )
            lot_id = created["state"]["auction"]["my_lots"][0]["id"]
            await m.bot.handle_web_game_command(
                {
                    "id": "auction-bid-2",
                    "action": "auction_bid",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {
                        "auction_id": lot_id,
                        "amount": 1100,
                    },
                }
            )
            cancelled = await m.bot.handle_web_game_command(
                {
                    "id": "auction-cancel-1",
                    "action": "auction_cancel",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"auction_id": lot_id},
                }
            )
            assert cancelled["ok"] is True
            assert cancelled["state"]["auction"]["my_lots"] == []
            assert any(
                item["item_id"] == "epic_gen"
                for item in cancelled["state"]["inventory"]
            )

            bidder_state = await m.bot.handle_web_game_command(
                {
                    "id": "auction-state-2",
                    "action": "state",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert bidder_state["player"]["coins"] == 10000
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_clan_roles_transfer_and_kick():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES "
            "(2, 1000, 0), (3, 1000, 0)"
        )
        await db.commit()
        try:
            created = await m.bot.handle_web_game_command(
                {
                    "id": "clan-roles-create",
                    "action": "clan_create",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"name": "Ролевой клан"},
                }
            )
            clan_id = created["clan_id"]
            applied = await m.bot.handle_web_game_command(
                {
                    "id": "clan-roles-apply",
                    "action": "clan_apply",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {"clan_id": clan_id},
                }
            )
            app_id = applied["state"]["clan"]["pending_application"]
            leader_state = await m.bot.handle_web_game_command(
                {
                    "id": "clan-roles-state",
                    "action": "state",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            application_id = leader_state["clan"]["details"]["applications"][0]["id"]
            await m.bot.handle_web_game_command(
                {
                    "id": "clan-roles-approve",
                    "action": "clan_application_decide",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {
                        "application_id": application_id,
                        "approve": True,
                    },
                }
            )

            promoted = await m.bot.handle_web_game_command(
                {
                    "id": "clan-roles-promote",
                    "action": "clan_promote",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"target_id": "3"},
                }
            )
            member = next(
                item
                for item in promoted["state"]["clan"]["details"]["members"]
                if item["user_id"] == "3"
            )
            assert member["role"] == "veteran"

            demoted = await m.bot.handle_web_game_command(
                {
                    "id": "clan-roles-demote",
                    "action": "clan_demote",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"target_id": "3"},
                }
            )
            member = next(
                item
                for item in demoted["state"]["clan"]["details"]["members"]
                if item["user_id"] == "3"
            )
            assert member["role"] == "member"

            transferred = await m.bot.handle_web_game_command(
                {
                    "id": "clan-roles-transfer",
                    "action": "clan_transfer",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"target_id": "3"},
                }
            )
            assert transferred["state"]["clan"]["details"]["role"] == "member"

            kicked = await m.bot.handle_web_game_command(
                {
                    "id": "clan-roles-kick",
                    "action": "clan_kick",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {"target_id": "2"},
                }
            )
            assert kicked["state"]["clan"]["details"]["members_count"] == 1
            assert app_id is not None
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_raid_party_invite_and_start():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        await db.execute(
            "INSERT INTO players (user_id, coins, gems) VALUES "
            "(1, 10000, 0), (2, 1000, 0), (3, 1000, 0)"
        )
        await db.executemany(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
            "VALUES (?, 0, 'basic_gen', 'profile', 0)",
            [(1,), (2,), (3,)],
        )
        await db.execute(
            "INSERT OR REPLACE INTO items (id, name, price, "
            "income_per_hour, income_gems_per_hour, rarity, buyable) "
            "VALUES ('basic_gen', 'Базовый генератор', 1000, 1, 0, "
            "'common', 1)"
        )
        await db.commit()
        try:
            created = await m.bot.handle_web_game_command(
                {
                    "id": "party-create-1",
                    "action": "raid_party_create",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert created["ok"] is True
            party_id = created["party_id"]
            invited = await m.bot.handle_web_game_command(
                {
                    "id": "party-invite-1",
                    "action": "raid_party_invite",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"target_id": "3"},
                }
            )
            assert invited["ok"] is True
            target_state = await m.bot.handle_web_game_command(
                {
                    "id": "party-state-1",
                    "action": "state",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            invites = target_state["raid_party"]["invites"]
            assert len(invites) == 1
            invite_id = invites[0]["id"]

            accepted = await m.bot.handle_web_game_command(
                {
                    "id": "party-accept-1",
                    "action": "raid_party_accept",
                    "user_id": "3",
                    "guild_id": "42",
                    "payload": {"invite_id": invite_id},
                }
            )
            assert accepted["ok"] is True
            assert accepted["state"]["raid_party"]["party"]["members_count"] == 2

            with mock.patch.object(
                m.random, "randint", side_effect=[1000, 1]
            ):
                raided = await m.bot.handle_web_game_command(
                    {
                        "id": "party-raid-1",
                        "action": "raid_party_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"target_id": "1"},
                    }
                )
            assert raided["ok"] is True
            assert raided["success"] is True
            assert raided["total_loot"] > 0
            assert raided["state"]["raid_party"]["party"]["members_count"] == 2
            assert party_id == raided["state"]["raid_party"]["party"]["id"]
        finally:
            await db.close()

    asyncio.run(run())


def test_web_game_rejects_non_admin_and_unknown_guild():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
        m.bot._web_game_table_ready = False
        await m.bot.init_db()
        m._settings_cache.clear()
        m._tax_rate_cache.clear()
        _guild()
        try:
            try:
                await m.bot.handle_web_game_command(
                    {
                        "id": "g2",
                        "action": "admin_grant",
                        "user_id": "3",
                        "guild_id": "42",
                        "payload": {
                            "target_id": "2",
                            "currency": "coins",
                            "amount": 10,
                        },
                    }
                )
            except PermissionError:
                pass
            else:
                raise AssertionError("не-админ не должен начислять валюту")

            try:
                await m.bot.handle_web_game_command(
                    {"id": "s2", "action": "state", "user_id": "1", "guild_id": "999"}
                )
            except ValueError:
                raise AssertionError("состояние должно вернуть список гильдий")
        finally:
            await db.close()

    asyncio.run(run())
