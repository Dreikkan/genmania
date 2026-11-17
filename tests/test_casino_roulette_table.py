"""Тесты общего стола рулетки: ставки, спин, выплаты, раунды."""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import tempfile
import time
from unittest import mock

import aiosqlite
import pytest

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "genmania_roulette_table_test", BOT_PATH
)
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


async def _setup(coins_a: int = 1000, coins_b: int = 1000):
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
    m.bot._web_game_table_ready = False
    await m.bot.init_db()
    m._settings_cache.clear()
    _guild()
    m.bot._roulette_tables.clear()
    await db.execute(
        "INSERT OR REPLACE INTO players (user_id, coins, gems) "
        "VALUES (2, ?, 0), (3, ?, 0)",
        (coins_a, coins_b),
    )
    await db.commit()
    return db


async def _command(action, user_id, payload=None, command_id=None):
    return await m.bot.handle_web_game_command(
        {
            "id": command_id or f"{action}-{user_id}-{time.time()}",
            "action": action,
            "user_id": str(user_id),
            "guild_id": "42",
            "payload": payload or {},
        }
    )


def test_table_state_and_bets():
    async def run():
        db = await _setup()
        try:
            state = await _command("roulette_table_state", 2)
            table = state["table"]
            assert table["status"] == "betting"
            assert table["round"] == 1
            assert table["bets"] == []
            assert table["deadline"] > time.time()

            bet = await _command(
                "roulette_table_bet",
                2,
                {
                    "currency": "coins",
                    "bet_type": "color",
                    "bet_value": "black",
                    "amount": 100,
                },
            )
            assert bet["table"]["my_bet"]["bet_value"] == "black"
            assert bet["table"]["players"] == 1
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 900

            with pytest.raises(ValueError, match="уже сделали ставку"):
                await _command(
                    "roulette_table_bet",
                    2,
                    {
                        "currency": "coins",
                        "bet_type": "color",
                        "bet_value": "red",
                        "amount": 100,
                    },
                )

            await _command(
                "roulette_table_bet",
                3,
                {
                    "currency": "coins",
                    "bet_type": "color",
                    "bet_value": "red",
                    "amount": 100,
                },
            )
            state = await _command("roulette_table_state", 2)
            assert state["table"]["players"] == 2
            assert len(state["table"]["bets"]) == 2
        finally:
            await db.close()

    asyncio.run(run())


def test_table_spin_pays_all_bets():
    async def run():
        db = await _setup()
        try:
            await _command(
                "roulette_table_bet",
                2,
                {
                    "currency": "coins",
                    "bet_type": "color",
                    "bet_value": "black",
                    "amount": 100,
                },
            )
            await _command(
                "roulette_table_bet",
                3,
                {
                    "currency": "coins",
                    "bet_type": "color",
                    "bet_value": "red",
                    "amount": 100,
                },
            )
            table = m.bot._roulette_table_get(42)
            table["deadline"] = time.time() - 1
            with mock.patch.object(m, "spin_number", return_value=17):
                await m.bot._roulette_table_tick()
            assert table["status"] == "result"
            assert table["last"]["number"] == 17
            assert table["last"]["color"] == "black"
            assert table["history"] == [17]
            results = {
                entry["user_id"]: entry for entry in table["last"]["results"]
            }
            assert results["2"]["payout"] == 200
            assert results["2"]["net"] == 100
            assert results["3"]["payout"] == 0
            assert results["3"]["net"] == -100
            async with db.execute(
                "SELECT coins FROM players WHERE user_id IN (2, 3) "
                "ORDER BY user_id"
            ) as cursor:
                assert [row[0] for row in await cursor.fetchall()] == [1100, 900]
            async with db.execute(
                "SELECT COUNT(*) FROM casino_roulette_spins "
                "WHERE color = 'pending'"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 0

            table["deadline"] = time.time() - 1
            await m.bot._roulette_table_tick()
            assert table["status"] == "betting"
            assert table["round"] == 2
            assert table["bets"] == []
        finally:
            await db.close()

    asyncio.run(run())


def test_table_no_bets_extends_deadline():
    async def run():
        db = await _setup()
        try:
            table = m.bot._roulette_table_get(42)
            table["deadline"] = time.time() - 1
            await m.bot._roulette_table_tick()
            assert table["status"] == "betting"
            assert table["deadline"] > time.time()
        finally:
            await db.close()

    asyncio.run(run())


def test_table_bet_validation_and_closed_round():
    async def run():
        db = await _setup()
        try:
            with pytest.raises(ValueError, match="Неверная валюта"):
                await _command(
                    "roulette_table_bet",
                    2,
                    {
                        "currency": "silver",
                        "bet_type": "color",
                        "bet_value": "red",
                        "amount": 100,
                    },
                )
            with pytest.raises(ValueError, match="Неизвестный тип"):
                await _command(
                    "roulette_table_bet",
                    2,
                    {
                        "currency": "coins",
                        "bet_type": "lucky",
                        "bet_value": "red",
                        "amount": 100,
                    },
                )
            with pytest.raises(ValueError, match="Ставка должна быть"):
                await _command(
                    "roulette_table_bet",
                    2,
                    {
                        "currency": "coins",
                        "bet_type": "color",
                        "bet_value": "red",
                        "amount": 10,
                    },
                )
            table = m.bot._roulette_table_get(42)
            table["deadline"] = time.time() - 1
            with pytest.raises(ValueError, match="Приём ставок закрыт"):
                await _command(
                    "roulette_table_bet",
                    2,
                    {
                        "currency": "coins",
                        "bet_type": "color",
                        "bet_value": "red",
                        "amount": 100,
                    },
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_table_gems_and_recovery():
    async def run():
        db = await _setup()
        try:
            await db.execute(
                "UPDATE players SET gems = 50 WHERE user_id = 2"
            )
            await db.commit()
            bet = await _command(
                "roulette_table_bet",
                2,
                {
                    "currency": "gems",
                    "bet_type": "number",
                    "bet_value": "17",
                    "amount": 5,
                },
            )
            assert bet["table"]["my_bet"]["currency"] == "gems"
            table = m.bot._roulette_table_get(42)
            row_id = table["bets"][0]["row_id"]
            await db.execute(
                "DELETE FROM casino_roulette_spins WHERE id = ?",
                (row_id,),
            )
            await db.execute(
                "INSERT INTO casino_roulette_spins "
                "(user_id, guild_id, bet_type, bet_value, amount, "
                "currency, number, color, payout, net) "
                "VALUES (2, 42, 'color', 'red', 5, 'gems', -1, "
                "'pending', 0, -5)"
            )
            await db.commit()
            await m.bot._roulette_table_recover_bets()
            async with db.execute(
                "SELECT gems FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 50
            async with db.execute(
                "SELECT COUNT(*) FROM casino_roulette_spins "
                "WHERE color = 'pending'"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 0
        finally:
            await db.close()

    asyncio.run(run())


def test_table_invalid_values_and_result_phase():
    async def run():
        db = await _setup()
        try:
            invalid = [
                ("number", "abc"),
                ("number", "99"),
                ("color", "green"),
                ("parity", "zero"),
                ("range", "mid"),
                ("dozen", "9"),
            ]
            for index, (bet_type, bet_value) in enumerate(invalid):
                with pytest.raises(ValueError):
                    await _command(
                        "roulette_table_bet",
                        2,
                        {
                            "currency": "coins",
                            "bet_type": bet_type,
                            "bet_value": bet_value,
                            "amount": 100,
                        },
                    )
            with pytest.raises(ValueError, match="Некорректная ставка"):
                await _command(
                    "roulette_table_bet",
                    2,
                    {
                        "currency": "coins",
                        "bet_type": "color",
                        "bet_value": "red",
                        "amount": "abc",
                    },
                )
            table = m.bot._roulette_table_get(42)
            table["status"] = "result"
            table["deadline"] = time.time() + 5
            with pytest.raises(ValueError, match="Приём ставок закрыт"):
                await _command(
                    "roulette_table_bet",
                    2,
                    {
                        "currency": "coins",
                        "bet_type": "color",
                        "bet_value": "red",
                        "amount": 100,
                    },
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_table_gems_spin_and_empty_recovery():
    async def run():
        db = await _setup()
        try:
            await m.bot._roulette_table_recover_bets()
            await db.execute(
                "UPDATE players SET gems = 100 WHERE user_id = 2"
            )
            await db.commit()
            await _command(
                "roulette_table_bet",
                2,
                {
                    "currency": "gems",
                    "bet_type": "number",
                    "bet_value": "17",
                    "amount": 5,
                },
            )
            table = m.bot._roulette_table_get(42)
            table["deadline"] = time.time() - 1
            with mock.patch.object(m, "spin_number", return_value=17):
                await m.bot._roulette_table_tick()
            async with db.execute(
                "SELECT gems FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 275
            result = table["last"]["results"][0]
            assert result["payout"] == 180
            assert result["net"] == 175
        finally:
            await db.close()

    asyncio.run(run())


def test_table_task_handles_errors_and_history_limit():
    async def run():
        db = await _setup()
        old = m.bot.is_closed
        old_tick = m.bot._roulette_table_tick
        try:
            async def boom():
                raise RuntimeError("boom")

            m.bot._roulette_table_tick = boom
            m.bot.is_closed = mock.Mock(side_effect=[False, True])
            with mock.patch.object(
                m.asyncio, "sleep", new=mock.AsyncMock()
            ):
                await m.bot.roulette_table_task()

            m.bot._roulette_table_tick = old_tick
            await _command(
                "roulette_table_bet",
                2,
                {
                    "currency": "coins",
                    "bet_type": "color",
                    "bet_value": "red",
                    "amount": 100,
                },
            )
            table = m.bot._roulette_table_get(42)
            table["history"] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
            table["deadline"] = time.time() - 1
            with mock.patch.object(m, "spin_number", return_value=17):
                await m.bot._roulette_table_tick()
            assert len(table["history"]) == m.ROULETTE_TABLE_HISTORY
            assert table["history"][-1] == 17
        finally:
            m.bot.is_closed = old
            m.bot._roulette_table_tick = old_tick
            await db.close()

    asyncio.run(run())


def test_table_recovery_error_is_safe():
    async def run():
        db = await _setup()
        try:
            with mock.patch.object(
                m.bot.db, "execute", side_effect=RuntimeError("db down")
            ):
                await m.bot._roulette_table_recover_bets()
        finally:
            await db.close()

    asyncio.run(run())


def test_table_guard_branches():
    async def run():
        db = await _setup(coins_a=0)
        try:
            with pytest.raises(ValueError, match="Неизвестный тип"):
                await _command("roulette_table_bet", 2, "bad")
            with pytest.raises(ValueError, match="Недостаточно средств"):
                await _command(
                    "roulette_table_bet",
                    2,
                    {
                        "currency": "coins",
                        "bet_type": "color",
                        "bet_value": "red",
                        "amount": 100,
                    },
                )
            with mock.patch.object(
                m.CastleBot, "_casino_balances", return_value=(1000, 0)
            ):
                with pytest.raises(ValueError, match="Недостаточно средств"):
                    await _command(
                        "roulette_table_bet",
                        2,
                        {
                            "currency": "coins",
                            "bet_type": "color",
                            "bet_value": "red",
                            "amount": 100,
                        },
                    )
            old_db = m.bot.db
            m.bot.db = None
            try:
                await m.bot._roulette_table_recover_bets()
            finally:
                m.bot.db = old_db
        finally:
            await db.close()

    asyncio.run(run())


def test_table_task_cancelled_error():
    async def run():
        db = await _setup()
        old = m.bot.is_closed
        old_tick = m.bot._roulette_table_tick
        try:
            async def cancelled():
                raise asyncio.CancelledError()

            m.bot._roulette_table_tick = cancelled
            m.bot.is_closed = lambda: False
            with pytest.raises(asyncio.CancelledError):
                await m.bot.roulette_table_task()
        finally:
            m.bot.is_closed = old
            m.bot._roulette_table_tick = old_tick
            await db.close()

    asyncio.run(run())


def test_table_task_runs_once():
    async def run():
        db = await _setup()
        old = m.bot.is_closed
        try:
            m.bot.is_closed = lambda: True
            await m.bot.roulette_table_task()
        finally:
            m.bot.is_closed = old
            await db.close()

    asyncio.run(run())
