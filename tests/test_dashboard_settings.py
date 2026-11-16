"""Tests for applying dashboard settings to guild_settings."""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_dashboard_settings_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeRole:
    def __init__(self, role_id: int, name: str):
        self.id = role_id
        self.name = name


class FakePermissions:
    administrator = True


class FakeMember:
    def __init__(self, user_id: int, name: str):
        self.id = user_id
        self.name = name
        self.display_name = name
        self.guild_permissions = FakePermissions()
        self.roles = [FakeRole(777, "Администратор")]
        self.bot = False


class FakeChannel:
    def __init__(self, channel_id: int, name: str):
        self.id = channel_id
        self.name = name
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))
        return None


class FakeJoinMember:
    def __init__(self, guild):
        self.id = 3
        self.guild = guild
        self.mention = "<@3>"
        self.display_name = "Newbie"
        self.name = "newbie"
        self.display_avatar = type("Avatar", (), {"url": "https://example.test/a.png"})()


class FakeGuild:
    def __init__(self):
        self.id = 42
        self.name = "420 SQUAD"
        self.owner_id = 1
        self.roles = [FakeRole(777, "Администратор")]
        self.members = [FakeMember(1, "Vortex"), FakeMember(2, "Kira")]
        self.text_channels = [FakeChannel(500, "welcome")]

    def get_member(self, user_id: int):
        return next((member for member in self.members if member.id == user_id), None)

    def get_channel(self, channel_id: int):
        return next(
            (channel for channel in self.text_channels if channel.id == channel_id),
            None,
        )


async def _prepare():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await db.execute(
        "CREATE TABLE guild_settings (guild_id INTEGER PRIMARY KEY, "
        "bot_name TEXT, custom_emojis TEXT, currency_coins TEXT, currency_gems TEXT, "
        "prefix TEXT, start_coins INTEGER, disabled_commands TEXT, status_roles TEXT, "
        "battlepass_enabled INTEGER, admin_role_id INTEGER, tax_rate REAL, "
        "welcome_channel_id INTEGER, welcome_text_ru TEXT, welcome_text_en TEXT, "
        "max_grid INTEGER, maintenance INTEGER)"
    )
    await db.execute(
        "CREATE TABLE admin_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "admin_id INTEGER, target_id INTEGER, guild_id INTEGER, action TEXT, "
        "details TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    await db.execute(
        "CREATE TABLE global_settings (key TEXT PRIMARY KEY, value TEXT)"
    )
    await db.execute("INSERT INTO guild_settings (guild_id) VALUES (42)")
    await db.commit()
    guild = FakeGuild()
    m.bot.get_guild = lambda guild_id: guild if guild_id == 42 else None
    m._settings_cache.clear()
    m._tax_rate_cache.clear()
    return db


def test_apply_global_settings_owner_only():
    async def run():
        db = await _prepare()
        original_is_owner = m.bot.is_owner

        async def fake_is_owner(user):
            return getattr(user, "id", None) == 1

        m.bot.is_owner = fake_is_owner
        try:
            denied = await m.bot.apply_dashboard_settings(
                {
                    "scope": "global",
                    "guild_id": 0,
                    "requested_by": "2",
                    "settings": {"public_stats": False},
                }
            )
            assert denied["ok"] is False

            result = await m.bot.apply_dashboard_settings(
                {
                    "scope": "global",
                    "guild_id": 0,
                    "requested_by": "1",
                    "settings": {
                        "public_stats": False,
                        "weekly_report": True,
                        "backup_interval_hours": 6,
                    },
                }
            )
            assert result["ok"] is True
            assert {
                "public_stats",
                "weekly_report",
                "backup_interval_hours",
            } <= set(result["applied"])
            settings = await m.get_global_settings()
            assert settings["public_stats"] is False
            assert settings["weekly_report"] is True
            assert settings["backup_interval_hours"] == 6

            invalid = await m.bot.apply_dashboard_settings(
                {
                    "scope": "global",
                    "guild_id": 0,
                    "requested_by": "1",
                    "settings": {"backup_interval_hours": 3},
                }
            )
            assert invalid["ok"] is False
            assert any(
                "backup_interval_hours" in warning
                for warning in invalid["warnings"]
            )
        finally:
            m.bot.is_owner = original_is_owner
            await db.close()

    asyncio.run(run())


def test_apply_dashboard_settings_valid():
    async def run():
        db = await _prepare()
        try:
            result = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "1",
                    "settings": {
                        "start_coins": 500,
                        "currency_name": "кредиты",
                        "premium_name": "кристаллы",
                        "tax_rate": 7.5,
                        "admin_role": "Администратор",
                    },
                }
            )
            assert result["ok"] is True
            assert "start_coins" in result["applied"]
            assert result["warnings"]
            async with db.execute(
                "SELECT start_coins, currency_coins, currency_gems, tax_rate, "
                "admin_role_id FROM guild_settings WHERE guild_id = 42"
            ) as cursor:
                row = await cursor.fetchone()
            assert row == (100, "кредиты", "кристаллы", 0.075, 777)
        finally:
            await db.close()

    asyncio.run(run())


def test_apply_dashboard_settings_grid_and_maintenance():
    async def run():
        db = await _prepare()
        try:
            result = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "1",
                    "settings": {"max_grid": 7, "maintenance": True},
                }
            )
            assert result["ok"] is True
            assert {"max_grid", "maintenance"} <= set(result["applied"])
            async with db.execute(
                "SELECT max_grid, maintenance FROM guild_settings "
                "WHERE guild_id = 42"
            ) as cursor:
                assert await cursor.fetchone() == (7, 1)

            m._settings_cache.clear()
            settings = await m.get_settings(42)
            assert settings["max_grid"] == 7
            assert settings["maintenance"] is True
            assert await m.get_guild_max_grid(42) == 7
            assert await m.is_guild_maintenance(42) is True

            clamped = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "1",
                    "settings": {"max_grid": 20},
                }
            )
            assert clamped["ok"] is True
            assert any("max_grid" in warning for warning in clamped["warnings"])
            m._settings_cache.clear()
            assert await m.get_guild_max_grid(42) == 10
        finally:
            await db.close()

    asyncio.run(run())


def test_apply_dashboard_settings_welcome_channel():
    async def run():
        db = await _prepare()
        try:
            result = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "1",
                    "settings": {"welcome_channel": "#welcome"},
                }
            )
            assert result["ok"] is True
            assert "welcome_channel" in result["applied"]
            async with db.execute(
                "SELECT welcome_channel_id FROM guild_settings WHERE guild_id = 42"
            ) as cursor:
                assert (await cursor.fetchone())[0] == 500

            by_id = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "1",
                    "settings": {"welcome_channel": "<#500>"},
                }
            )
            assert by_id["ok"] is True

            texts = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "1",
                    "settings": {
                        "welcome_text_ru": "Привет, {member}!",
                        "welcome_text_en": "Hello, {member}!",
                    },
                }
            )
            assert texts["ok"] is True
            assert "welcome_text_ru" in texts["applied"]
            assert "welcome_text_en" in texts["applied"]
            async with db.execute(
                "SELECT welcome_text_ru, welcome_text_en "
                "FROM guild_settings WHERE guild_id = 42"
            ) as cursor:
                assert (await cursor.fetchone()) == (
                    "Привет, {member}!",
                    "Hello, {member}!",
                )

            missing = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "1",
                    "settings": {"welcome_channel": "missing"},
                }
            )
            assert missing["ok"] is False
            assert any("welcome_channel" in warning for warning in missing["warnings"])

            cleared = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "1",
                    "settings": {"welcome_channel": ""},
                }
            )
            assert cleared["ok"] is True
            async with db.execute(
                "SELECT welcome_channel_id FROM guild_settings WHERE guild_id = 42"
            ) as cursor:
                assert (await cursor.fetchone())[0] is None
        finally:
            await db.close()

    asyncio.run(run())


def test_on_member_join_sends_welcome():
    async def run():
        db = await _prepare()
        try:
            await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "1",
                    "settings": {
                        "welcome_channel": "#welcome",
                        "welcome_text_ru": "RU: {member} · {start_coins} {currency}",
                        "welcome_text_en": "EN: {member} · {server}",
                    },
                }
            )
            guild = m.bot.get_guild(42)
            member = FakeJoinMember(guild)
            await m.on_member_join(member)
            channel = guild.text_channels[0]
            assert channel.sent
            embed = channel.sent[0][1].get("embed")
            assert embed is not None
            assert "RU: <@3> · 8 монеты" in embed.description
            assert "EN: <@3> · 420 SQUAD" in embed.description
        finally:
            await db.close()

    asyncio.run(run())


def test_apply_dashboard_settings_edges():
    async def run():
        db = await _prepare()
        try:
            assert (await m.bot.apply_dashboard_settings(None))["ok"] is False
            assert (
                await m.bot.apply_dashboard_settings(
                    {"guild_id": "bad", "settings": {}}
                )
            )["ok"] is False
            assert (
                await m.bot.apply_dashboard_settings(
                    {"guild_id": 999, "settings": {"start_coins": 1}}
                )
            )["ok"] is False
            assert (
                await m.bot.apply_dashboard_settings(
                    {"guild_id": 42, "settings": {}}
                )
            )["ok"] is False
            assert (
                await m.bot.apply_dashboard_settings(
                    {
                        "guild_id": 42,
                        "requested_by": "2",
                        "settings": {"start_coins": 1},
                    }
                )
            )["ok"] is True

            result = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "1",
                    "settings": {
                        "start_coins": "bad",
                        "currency_name": "",
                        "premium_name": "кристаллы",
                        "tax_rate": "bad",
                        "admin_role": "Нет такой роли",
                    },
                }
            )
            assert result["ok"] is True
            assert any("start_coins" in warning for warning in result["warnings"])
            assert any("tax_rate" in warning for warning in result["warnings"])
            assert any("admin_role" in warning for warning in result["warnings"])

            cleared = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "1",
                    "settings": {"admin_role": "0"},
                }
            )
            assert cleared["ok"] is True
            async with db.execute(
                "SELECT admin_role_id FROM guild_settings WHERE guild_id = 42"
            ) as cursor:
                assert (await cursor.fetchone())[0] is None
        finally:
            await db.close()

    asyncio.run(run())
