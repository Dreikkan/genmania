"""Тесты кейсов казино: недельный пул, списание, выдача, лимит."""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import tempfile
from unittest import mock

import aiosqlite
import pytest

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("genmania_casino_test", BOT_PATH)
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
        return next(
            (member for member in self.members if member.id == user_id),
            None,
        )


def _guild():
    guild = FakeGuild()
    m.bot.get_guild = lambda guild_id: guild if guild_id == 42 else None
    m.bot._connection._guilds = {42: guild}
    return guild


async def _setup(coins: int = 0, gems: int = 0):
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
    m.bot._web_game_table_ready = False
    await m.bot.init_db()
    m._settings_cache.clear()
    _guild()
    await db.execute(
        "INSERT OR REPLACE INTO players (user_id, coins, gems) "
        "VALUES (2, ?, ?)",
        (coins, gems),
    )
    await db.commit()
    return db


def test_casino_pool_is_weekly_and_unique():
    async def run():
        db = await _setup()
        try:
            pool = await m.bot._casino_pool()
            assert len(pool) == 15
            assert [entry["position"] for entry in pool] == list(
                range(1, 16)
            )
            ids = [entry["item_id"] for entry in pool]
            assert len(set(ids)) == 15
            assert all(entry["item_id"].endswith("_gen") for entry in pool)
            assert all("_emoji_by_star" in entry for entry in pool)

            start = m.datetime.datetime(
                2026, 11, 16, tzinfo=m.datetime.timezone.utc
            )
            end = start + m.datetime.timedelta(days=7)
            with mock.patch.object(
                m.CastleBot,
                "_casino_week_bounds",
                return_value=(2026, 47, start, end),
            ):
                week47 = [
                    entry["item_id"] for entry in await m.bot._casino_pool()
                ]
            with mock.patch.object(
                m.CastleBot,
                "_casino_week_bounds",
                return_value=(2026, 48, end, end),
            ):
                week48 = [
                    entry["item_id"] for entry in await m.bot._casino_pool()
                ]
            assert week47 != week48
            assert len(set(week47) & set(week48)) == 10
        finally:
            await db.close()

    asyncio.run(run())


def test_casino_state_cases_and_odds():
    async def run():
        db = await _setup(coins=100_000, gems=200)
        try:
            casino = await m.bot._web_game_casino_state(2)
            assert casino["week"]["week"] > 0
            assert len(casino["pool"]) == 15
            assert len(casino["cases"]) == 3
            assert casino["opened_today"] == 0
            assert casino["day_limit"] == m.CASINO_DAY_LIMIT
            bronze = casino["cases"][0]
            assert bronze["id"] == "bronze_case"
            assert bronze["currency"] == "coins"
            assert bronze["price"] == 500
            assert bronze["odds"]
            assert abs(sum(item["chance"] for item in bronze["stars"]) - 100) < 0.2
            golden = casino["cases"][2]
            assert golden["currency"] == "gems"
            assert golden["price"] == 20
            assert casino["history"] == []
        finally:
            await db.close()

    asyncio.run(run())


def test_casino_case_open_spends_coins_and_grants_item():
    async def run():
        db = await _setup(coins=10_000)
        try:
            result = await m.bot.handle_web_game_command(
                {
                    "id": "case-open-1",
                    "action": "case_open",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"case_id": "bronze_case"},
                }
            )
            assert result["ok"] is True
            assert result["action"] == "case_open"
            assert result["price"] == 500
            assert result["currency"] == "coins"
            assert result["item"]["item_id"].endswith("_gen")
            assert 0 <= result["item"]["stars"] <= 2
            state = result["state"]
            assert state["casino"]["opened_today"] == 1
            assert state["casino"]["history"][0]["case_id"] == "bronze_case"

            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as cursor:
                coins = int((await cursor.fetchone())[0])
            assert coins == 9_500
            async with db.execute(
                "SELECT COUNT(*) FROM casino_case_opens WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 1
            async with db.execute(
                "SELECT COUNT(*) FROM inventory WHERE user_id = 2"
            ) as cursor:
                inventory = int((await cursor.fetchone())[0])
            async with db.execute(
                "SELECT COUNT(*) FROM mailbox WHERE user_id = 2"
            ) as cursor:
                mailbox = int((await cursor.fetchone())[0])
            assert inventory + mailbox == 1
        finally:
            await db.close()

    asyncio.run(run())


def test_casino_case_open_uses_gems():
    async def run():
        db = await _setup(gems=20)
        try:
            result = await m.bot.handle_web_game_command(
                {
                    "id": "case-open-2",
                    "action": "case_open",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {"case_id": "golden_case"},
                }
            )
            assert result["ok"] is True
            assert result["currency"] == "gems"
            assert result["price"] == 20
            async with db.execute(
                "SELECT gems FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 0
        finally:
            await db.close()

    asyncio.run(run())


def test_casino_case_open_rejects_bad_input_and_limits():
    async def run():
        db = await _setup(coins=0, gems=0)
        try:
            with pytest.raises(ValueError, match="Неизвестный кейс"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "case-bad",
                        "action": "case_open",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"case_id": "nope"},
                    }
                )
            with pytest.raises(ValueError, match="Не хватает средств"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "case-poor",
                        "action": "case_open",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"case_id": "bronze_case"},
                    }
                )

            await db.executemany(
                "INSERT INTO casino_case_opens "
                "(user_id, guild_id, case_id, item_id, stars, currency, "
                "price) VALUES (2, 42, 'bronze_case', 'basic_gen', 0, "
                "'coins', 500)",
                [()] * m.CASINO_DAY_LIMIT,
            )
            await db.execute(
                "UPDATE players SET coins = 100000 WHERE user_id = 2"
            )
            await db.commit()
            with pytest.raises(ValueError, match="Дневной лимит"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "case-limit",
                        "action": "case_open",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"case_id": "bronze_case"},
                    }
                )
        finally:
            await db.close()

    asyncio.run(run())
