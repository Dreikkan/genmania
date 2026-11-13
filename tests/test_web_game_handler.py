"""Tests for web game command execution in CastleBot."""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import tempfile

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
            assert len(state["guilds"]) == 1

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
