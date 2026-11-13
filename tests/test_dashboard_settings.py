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


class FakeGuild:
    def __init__(self):
        self.id = 42
        self.name = "420 SQUAD"
        self.roles = [FakeRole(777, "Администратор")]


async def _prepare():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await db.execute(
        "CREATE TABLE guild_settings (guild_id INTEGER PRIMARY KEY, "
        "bot_name TEXT, custom_emojis TEXT, currency_coins TEXT, currency_gems TEXT, "
        "prefix TEXT, start_coins INTEGER, disabled_commands TEXT, status_roles TEXT, "
        "battlepass_enabled INTEGER, admin_role_id INTEGER, tax_rate REAL)"
    )
    await db.execute("INSERT INTO guild_settings (guild_id) VALUES (42)")
    await db.commit()
    guild = FakeGuild()
    m.bot.get_guild = lambda guild_id: guild if guild_id == 42 else None
    m._settings_cache.clear()
    m._tax_rate_cache.clear()
    return db


def test_apply_dashboard_settings_valid():
    async def run():
        db = await _prepare()
        try:
            result = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "",
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

            result = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
                    "requested_by": "",
                    "settings": {
                        "start_coins": "bad",
                        "currency_name": "",
                        "premium_name": "кристаллы",
                        "tax_rate": "bad",
                        "admin_role": "Нет такой роли",
                    },
                }
            )
            assert result["ok"] is True  # premium_name всё равно применился
            assert any("start_coins" in warning for warning in result["warnings"])
            assert any("tax_rate" in warning for warning in result["warnings"])
            assert any("admin_role" in warning for warning in result["warnings"])

            cleared = await m.bot.apply_dashboard_settings(
                {
                    "guild_id": 42,
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
