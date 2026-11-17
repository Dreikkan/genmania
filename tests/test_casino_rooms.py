"""Тесты комнат блэкджека: создание, вход, ходы, таймер, выплаты."""
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
spec = importlib.util.spec_from_file_location("genmania_casino_rooms_test", BOT_PATH)
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
            FakeMember(4, "Nova"),
            FakeMember(5, "Rook"),
            FakeMember(6, "Echo"),
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


def _shoe_with(*deal_order):
    return ["2C"] * 30 + list(reversed(deal_order))


async def _setup(coins_a: int = 1000, coins_b: int = 1000):
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    m.bot.data_dir = pathlib.Path(tempfile.mkdtemp())
    m.bot._web_game_table_ready = False
    await m.bot.init_db()
    m._settings_cache.clear()
    _guild()
    m.bot._casino_rooms.clear()
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


async def _create_and_join():
    created = await _command(
        "room_create", 2, {"currency": "coins", "amount": 100}
    )
    code = created["room"]["code"]
    await _command(
        "room_join", 3, {"code": code, "currency": "coins", "amount": 100}
    )
    return code


def test_room_create_join_and_lobby():
    async def run():
        db = await _setup()
        try:
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            assert created["ok"] is True
            assert len(created["room"]["players"]) == 1
            assert created["room"]["status"] == "waiting"
            code = created["room"]["code"]
            assert len(code) == 6

            joined = await _command(
                "room_join",
                3,
                {"code": code, "currency": "coins", "amount": 100},
            )
            assert len(joined["room"]["players"]) == 2
            assert joined["rooms"][0]["players"] == 2

            state = await _command("room_state", 2)
            assert state["room"]["code"] == code
            assert len(state["rooms"]) == 1

            async with db.execute(
                "SELECT coins FROM players WHERE user_id IN (2, 3) "
                "ORDER BY user_id"
            ) as cursor:
                assert [row[0] for row in await cursor.fetchall()] == [900, 900]
            async with db.execute(
                "SELECT COUNT(*) FROM casino_blackjack_games "
                "WHERE status = 'room'"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 2
        finally:
            await db.close()

    asyncio.run(run())


def test_room_start_requires_two_and_hides_dealer_card():
    async def run():
        db = await _setup()
        try:
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            code = created["room"]["code"]
            with pytest.raises(ValueError, match="минимум 2"):
                await _command("room_start", 2)
            await _command(
                "room_join",
                3,
                {"code": code, "currency": "coins", "amount": 100},
            )
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "10S", "9H", "10D", "6C", "10C", "7S"
                ),
            ):
                started = await _command("room_start", 2)
            room = started["room"]
            assert room["status"] == "playing"
            assert room["dealer_hidden"] is True
            assert len(room["dealer_cards"]) == 1
            assert room["turn_user_id"] == "2"
            assert room["players"][0]["total"] == 19
            assert room["players"][1]["total"] == 16
            assert room["turn_deadline"] > time.time()
        finally:
            await db.close()

    asyncio.run(run())


def test_room_hit_stand_and_payouts():
    async def run():
        db = await _setup()
        try:
            code = await _create_and_join()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "10S", "9H", "10D", "6C", "10C", "7S"
                ),
            ):
                await _command("room_start", 2)
            stood = await _command("room_stand", 2)
            assert stood["room"]["turn_user_id"] == "3"
            finished = await _command("room_stand", 3)
            room = finished["room"]
            assert room["status"] == "finished"
            assert room["dealer_hidden"] is False
            assert room["dealer_total"] == 17
            assert room["players"][0]["outcome"] == "win"
            assert room["players"][0]["payout"] == 200
            assert room["players"][1]["outcome"] == "lose"
            assert room["players"][1]["payout"] == 0

            async with db.execute(
                "SELECT coins FROM players WHERE user_id IN (2, 3) "
                "ORDER BY user_id"
            ) as cursor:
                assert [row[0] for row in await cursor.fetchall()] == [1100, 900]
            async with db.execute(
                "SELECT COUNT(*) FROM casino_blackjack_games "
                "WHERE status = 'done'"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 2
        finally:
            await db.close()

    asyncio.run(run())


def test_room_hit_and_double():
    async def run():
        db = await _setup()
        try:
            code = await _create_and_join()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "5S", "6H", "5D", "6C", "10C", "7S", "10S", "10H"
                ),
            ):
                await _command("room_start", 2)
            hit = await _command("room_hit", 2)
            assert hit["room"]["players"][0]["total"] == 21
            assert hit["room"]["turn_user_id"] == "3"

            doubled = await _command("room_double", 3)
            assert doubled["room"]["players"][1]["doubled"] is True
            assert doubled["room"]["status"] == "finished"
            assert doubled["room"]["players"][1]["payout"] == 400
        finally:
            await db.close()

    asyncio.run(run())


def test_room_leave_waiting_refunds_and_transfers_host():
    async def run():
        db = await _setup()
        try:
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            code = created["room"]["code"]
            await _command(
                "room_join",
                3,
                {"code": code, "currency": "coins", "amount": 100},
            )
            left = await _command("room_leave", 3)
            assert len(left["room"]["players"]) == 1
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 3"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 1000
            host_left = await _command("room_leave", 2)
            assert host_left["room"] is None
            assert host_left["rooms"] == []
            async with db.execute(
                "SELECT COUNT(*) FROM casino_blackjack_games "
                "WHERE status = 'room'"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 0
        finally:
            await db.close()

    asyncio.run(run())


def test_room_timeout_auto_stands_and_finishes():
    async def run():
        db = await _setup()
        try:
            code = await _create_and_join()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "10S", "9H", "10D", "6C", "10C", "7S"
                ),
            ):
                await _command("room_start", 2)
            room = m.bot._casino_room_find(42, code)
            room["turn_deadline"] = time.time() - 1
            await m.bot._casino_room_tick()
            assert room["players"][0]["status"] == "stand"
            assert room["players"][0]["auto_stood"] is True
            assert room["turn_index"] == 1
            assert room["players"][1]["status"] == "playing"

            room["turn_deadline"] = time.time() - 1
            await m.bot._casino_room_tick()
            assert room["status"] == "finished"
            assert room["players"][0]["outcome"] == "win"
        finally:
            await db.close()

    asyncio.run(run())


def test_room_recovery_returns_stakes():
    async def run():
        db = await _setup(coins_a=900)
        try:
            await db.execute(
                "INSERT INTO casino_blackjack_games "
                "(user_id, guild_id, bet, currency, status) "
                "VALUES (2, 42, 100, 'coins', 'room')"
            )
            await db.commit()
            await m.bot._casino_room_recover_stakes()
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 1000
            async with db.execute(
                "SELECT COUNT(*) FROM casino_blackjack_games "
                "WHERE status = 'room'"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 0
        finally:
            await db.close()

    asyncio.run(run())


def test_room_state_without_room_and_leave_without_room():
    async def run():
        db = await _setup()
        try:
            state = await _command("room_state", 2)
            assert state["room"] is None
            assert state["rooms"] == []
            left = await _command("room_leave", 2)
            assert left["room"] is None
            assert "не находитесь" in left["message"]
        finally:
            await db.close()

    asyncio.run(run())


def test_room_create_validation_and_gems():
    async def run():
        db = await _setup(coins_a=1000, coins_b=10)
        try:
            await db.execute(
                "UPDATE players SET coins = 50 WHERE user_id = 2"
            )
            await db.commit()
            with pytest.raises(ValueError, match="Недостаточно средств"):
                await _command(
                    "room_create", 2, {"currency": "coins", "amount": 100}
                )
            await db.execute(
                "UPDATE players SET coins = 1000 WHERE user_id = 2"
            )
            await db.commit()
            with pytest.raises(ValueError, match="Ставка должна быть"):
                await _command(
                    "room_create", 2, {"currency": "coins", "amount": 0}
                )
            await db.execute(
                "UPDATE players SET gems = 10 WHERE user_id = 3"
            )
            await db.commit()
            created = await _command(
                "room_create", 3, {"currency": "gems", "amount": 1}
            )
            assert created["room"]["currency"] == "gems"
            async with db.execute(
                "SELECT gems FROM players WHERE user_id = 3"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 9
        finally:
            await db.close()

    asyncio.run(run())


def test_room_join_errors_and_full_room():
    async def run():
        db = await _setup()
        try:
            with pytest.raises(ValueError, match="не найдена"):
                await _command(
                    "room_join",
                    2,
                    {"code": "ZZZZZZ", "currency": "coins", "amount": 100},
                )
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            code = created["room"]["code"]
            await db.executemany(
                "INSERT OR REPLACE INTO players (user_id, coins) "
                "VALUES (?, 1000)",
                [(4,), (5,), (6,)],
            )
            await db.commit()
            for user_id in (3, 4, 5, 6):
                await _command(
                    "room_join",
                    user_id,
                    {"code": code, "currency": "coins", "amount": 100},
                )
            async with db.execute(
                "SELECT COUNT(*) FROM casino_blackjack_games "
                "WHERE status = 'room'"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 5
            await db.execute(
                "INSERT OR REPLACE INTO players (user_id, coins) "
                "VALUES (7, 1000)"
            )
            await db.commit()
            guild = m.bot.get_guild(42)
            guild.members.append(FakeMember(7, "Seven"))
            with pytest.raises(ValueError, match="нет свободных мест"):
                await _command(
                    "room_join",
                    7,
                    {"code": code, "currency": "coins", "amount": 100},
                )
            guild.members = [
                member for member in guild.members if member.id != 7
            ]
        finally:
            await db.close()

    asyncio.run(run())


def test_room_start_and_turn_errors():
    async def run():
        db = await _setup()
        try:
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            code = created["room"]["code"]
            await _command(
                "room_join",
                3,
                {"code": code, "currency": "coins", "amount": 100},
            )
            with pytest.raises(ValueError, match="Только хозяин"):
                await _command("room_start", 3)
            with mock.patch.object(
                m, "new_shoe", return_value=_shoe_with("10S", "9H", "10D", "9C", "10C", "8S")
            ):
                await _command("room_start", 2)
            with pytest.raises(ValueError, match="уже началась"):
                await _command("room_start", 2)
            with pytest.raises(ValueError, match="ход другого"):
                await _command("room_stand", 3)
            with pytest.raises(ValueError, match="ход другого"):
                await _command("room_hit", 3)
            with pytest.raises(ValueError, match="ход другого"):
                await _command("room_double", 3)
        finally:
            await db.close()

    asyncio.run(run())


def test_room_actions_without_active_game():
    async def run():
        db = await _setup()
        try:
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            for action in ("room_hit", "room_stand", "room_double"):
                with pytest.raises(ValueError, match="нет активной раздачи"):
                    await _command(action, 2)
            await _command("room_leave", 2)
            with pytest.raises(ValueError, match="не находитесь"):
                await _command("room_hit", 2)
        finally:
            await db.close()

    asyncio.run(run())


def test_room_double_errors():
    async def run():
        db = await _setup()
        try:
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            code = created["room"]["code"]
            await _command(
                "room_join",
                3,
                {"code": code, "currency": "coins", "amount": 100},
            )
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("5S", "6H", "5D", "6C", "10C", "8S", "2S", "3S"),
            ):
                await _command("room_start", 2)
            await _command("room_stand", 2)
            await _command("room_hit", 3)
            with pytest.raises(ValueError, match="только на первых двух"):
                await _command("room_double", 3)
        finally:
            await db.close()

    asyncio.run(run())


def test_room_double_insufficient():
    async def run():
        db = await _setup()
        try:
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            code = created["room"]["code"]
            await _command(
                "room_join",
                3,
                {"code": code, "currency": "coins", "amount": 100},
            )
            await db.execute(
                "UPDATE players SET coins = 50 WHERE user_id = 3"
            )
            await db.commit()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("5S", "6H", "5D", "6C", "10C", "8S", "2S"),
            ):
                await _command("room_start", 2)
            await _command("room_stand", 2)
            with pytest.raises(ValueError, match="Недостаточно средств"):
                await _command("room_double", 3)
        finally:
            await db.close()

    asyncio.run(run())


def test_room_leave_during_play_and_finished_cleanup():
    async def run():
        db = await _setup()
        try:
            code = await _create_and_join()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "10S", "9H", "10D", "6C", "10C", "7S"
                ),
            ):
                await _command("room_start", 2)
            left = await _command("room_leave", 2)
            assert left["room"]["status"] == "playing"
            assert left["room"]["players"][0]["status"] == "stand"
            finished = await _command("room_leave", 3)
            assert finished["room"]["status"] == "finished"
            room = m.bot._casino_room_find(42, code)
            room["finished_at"] = time.time() - 1000
            await m.bot._casino_room_tick()
            assert m.bot._casino_room_find(42, code) is None
        finally:
            await db.close()

    asyncio.run(run())


def test_room_waiting_expiry_refunds():
    async def run():
        db = await _setup()
        try:
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            room = m.bot._casino_room_find(42, created["room"]["code"])
            room["created_at"] = time.time() - 1000
            await m.bot._casino_room_tick()
            assert m.bot._casino_room_find(42, created["room"]["code"]) is None
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 1000
        finally:
            await db.close()

    asyncio.run(run())


def test_room_player_natural_skips_turn():
    async def run():
        db = await _setup()
        try:
            code = await _create_and_join()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "AS", "KH", "10D", "6C", "10C", "7S"
                ),
            ):
                started = await _command("room_start", 2)
            room = started["room"]
            assert room["players"][0]["status"] == "blackjack"
            assert room["turn_user_id"] == "3"
        finally:
            await db.close()

    asyncio.run(run())


def test_room_gems_flow():
    async def run():
        db = await _setup()
        try:
            await db.execute(
                "UPDATE players SET gems = 100 WHERE user_id IN (2, 3)"
            )
            await db.commit()
            created = await _command(
                "room_create", 2, {"currency": "gems", "amount": 5}
            )
            code = created["room"]["code"]
            await _command(
                "room_join",
                3,
                {"code": code, "currency": "gems", "amount": 5},
            )
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "10S", "9H", "10D", "6C", "10C", "7S"
                ),
            ):
                await _command("room_start", 2)
            await _command("room_stand", 2)
            finished = await _command("room_stand", 3)
            assert finished["room"]["currency"] == "gems"
            async with db.execute(
                "SELECT gems FROM players WHERE user_id IN (2, 3) "
                "ORDER BY user_id"
            ) as cursor:
                assert [row[0] for row in await cursor.fetchall()] == [105, 95]
        finally:
            await db.close()

    asyncio.run(run())


def test_room_task_runs_once():
    async def run():
        db = await _setup()
        old = m.bot.is_closed
        try:
            m.bot.is_closed = lambda: True
            await m.bot.casino_room_task()
        finally:
            m.bot.is_closed = old
            await db.close()

    asyncio.run(run())


def test_room_host_transfer_and_finished_leave():
    async def run():
        db = await _setup()
        try:
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            code = created["room"]["code"]
            await _command(
                "room_join",
                3,
                {"code": code, "currency": "coins", "amount": 100},
            )
            left = await _command("room_leave", 2)
            assert left["room"]["host_id"] == "3"
            assert left["room"]["players"][0]["is_host"] is True

            await _command("room_leave", 3)
            assert m.bot._casino_room_find(42, code) is None
        finally:
            await db.close()

    asyncio.run(run())


def test_room_join_playing_and_already_in_room():
    async def run():
        db = await _setup()
        try:
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            code = created["room"]["code"]
            await _command(
                "room_join",
                3,
                {"code": code, "currency": "coins", "amount": 100},
            )
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "10S", "9H", "10D", "6C", "10C", "7S"
                ),
            ):
                await _command("room_start", 2)
            await db.execute(
                "INSERT OR REPLACE INTO players (user_id, coins) "
                "VALUES (4, 1000)"
            )
            await db.commit()
            with pytest.raises(ValueError, match="уже идёт игра"):
                await _command(
                    "room_join",
                    4,
                    {"code": code, "currency": "coins", "amount": 100},
                )

            second = await _command(
                "room_create", 4, {"currency": "coins", "amount": 100}
            )
            with pytest.raises(ValueError, match="уже находитесь"):
                await _command(
                    "room_join",
                    2,
                    {
                        "code": second["room"]["code"],
                        "currency": "coins",
                        "amount": 100,
                    },
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_room_dealer_natural_and_all_blackjack():
    async def run():
        db = await _setup()
        try:
            code = await _create_and_join()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "10S", "9H", "10D", "6C", "AD", "KC"
                ),
            ):
                created = await _command("room_start", 2)
            assert created["room"]["status"] == "finished"
            assert created["room"]["dealer_hidden"] is False

            await db.execute("DELETE FROM casino_blackjack_games")
            await db.commit()
            m.bot._casino_rooms.clear()
            code2 = await _create_and_join()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "AS", "KH", "AD", "KC", "10C", "7S"
                ),
            ):
                all_bj = await _command("room_start", 2)
            assert all_bj["room"]["status"] == "finished"
            assert all_bj["room"]["players"][0]["outcome"] == "blackjack"
            assert all_bj["room"]["players"][0]["payout"] == 250
        finally:
            await db.close()

    asyncio.run(run())


def test_room_leave_non_turn_keeps_turn_and_fallback_history():
    async def run():
        db = await _setup()
        try:
            code = await _create_and_join()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "10S", "9H", "10D", "6C", "10C", "7S"
                ),
            ):
                await _command("room_start", 2)
            room = m.bot._casino_room_find(42, code)
            room["players"][0]["stake_row_id"] = 0
            room["players"][1]["stake_row_id"] = 0
            left = await _command("room_leave", 3)
            assert left["room"]["status"] == "playing"
            assert left["room"]["turn_user_id"] == "2"
            finished = await _command("room_stand", 2)
            assert finished["room"]["status"] == "finished"
            async with db.execute(
                "SELECT COUNT(*) FROM casino_blackjack_games "
                "WHERE status = 'done'"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 2
        finally:
            await db.close()

    asyncio.run(run())


def test_room_hit_bust_and_dealer_draws():
    async def run():
        db = await _setup()
        try:
            code = await _create_and_join()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "10S", "6H", "10D", "9C", "2C", "3D", "KD"
                ),
            ):
                await _command("room_start", 2)
            bust = await _command("room_hit", 2)
            assert bust["room"]["players"][0]["status"] == "bust"
            assert bust["room"]["turn_user_id"] == "3"
            finished = await _command("room_stand", 3)
            assert finished["room"]["status"] == "finished"
            assert finished["room"]["dealer_total"] >= 17
            assert finished["room"]["players"][0]["outcome"] == "bust"
        finally:
            await db.close()

    asyncio.run(run())


def test_room_code_collision_and_empty_recovery():
    async def run():
        db = await _setup()
        try:
            with mock.patch.object(
                m.CastleBot, "_casino_room_find", return_value={}
            ):
                with pytest.raises(ValueError, match="Не удалось создать"):
                    m.bot._casino_room_code(42)
            await m.bot._casino_room_recover_stakes()
            async with db.execute(
                "SELECT COUNT(*) FROM casino_blackjack_games"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 0
        finally:
            await db.close()

    asyncio.run(run())


def test_room_invalid_payloads_and_no_room_actions():
    async def run():
        db = await _setup()
        try:
            with pytest.raises(ValueError, match="Ставка должна быть"):
                await _command("room_create", 2, "bad")
            with pytest.raises(ValueError, match="Некорректный код"):
                await _command("room_join", 2, "bad")
            for action in ("room_stand", "room_double"):
                with pytest.raises(ValueError, match="не находитесь"):
                    await _command(action, 2)
            with pytest.raises(ValueError, match="не находитесь"):
                await _command("room_start", 2)
        finally:
            await db.close()

    asyncio.run(run())


def test_room_finished_leave_and_outsider_state():
    async def run():
        db = await _setup()
        try:
            code = await _create_and_join()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "10S", "9H", "10D", "6C", "10C", "7S"
                ),
            ):
                await _command("room_start", 2)
            await _command("room_stand", 2)
            await _command("room_stand", 3)
            await db.execute(
                "INSERT OR REPLACE INTO players (user_id, coins) "
                "VALUES (4, 1000)"
            )
            await db.commit()
            outsider = await _command("room_state", 4)
            assert outsider["room"] is None
            assert outsider["rooms"] == []

            left = await _command("room_leave", 2)
            assert left["room"] is not None
            assert len(left["room"]["players"]) == 1
            final = await _command("room_leave", 3)
            assert final["room"] is None
            assert m.bot._casino_room_find(42, code) is None
        finally:
            await db.close()

    asyncio.run(run())


def test_room_double_twice_and_empty_shoe():
    async def run():
        db = await _setup()
        try:
            code = await _create_and_join()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with(
                    "5S", "6H", "5D", "6C", "10C", "7S", "2S"
                ),
            ):
                await _command("room_start", 2)
            room = m.bot._casino_room_find(42, code)
            room["players"][0]["doubled"] = True
            with pytest.raises(ValueError, match="только на первых двух"):
                await _command("room_double", 2)
            room["players"][0]["doubled"] = False
            room["shoe"] = []
            hit = await _command("room_hit", 2)
            assert hit["room"]["players"][0]["total"] >= 11
        finally:
            await db.close()

    asyncio.run(run())


def test_room_invalid_amount_and_zero_bet_refund():
    async def run():
        db = await _setup()
        try:
            with pytest.raises(ValueError, match="Некорректная ставка"):
                await _command(
                    "room_create",
                    2,
                    {"currency": "coins", "amount": "abc"},
                )
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            with pytest.raises(ValueError, match="Некорректная ставка"):
                await _command(
                    "room_join",
                    3,
                    {
                        "code": created["room"]["code"],
                        "currency": "coins",
                        "amount": "abc",
                    },
                )
            room = m.bot._casino_room_find(42, created["room"]["code"])
            room["players"][0]["bet"] = 0
            room["created_at"] = time.time() - 1000
            await m.bot._casino_room_tick()
            assert m.bot._casino_room_find(
                42, created["room"]["code"]
            ) is None
        finally:
            await db.close()

    asyncio.run(run())


def test_room_errors():
    async def run():
        db = await _setup()
        try:
            with pytest.raises(ValueError, match="Неверная валюта"):
                await _command(
                    "room_create",
                    2,
                    {"currency": "silver", "amount": 100},
                )
            with pytest.raises(ValueError, match="Некорректный код"):
                await _command(
                    "room_join",
                    2,
                    {"code": "bad", "currency": "coins", "amount": 100},
                )
            created = await _command(
                "room_create", 2, {"currency": "coins", "amount": 100}
            )
            code = created["room"]["code"]
            await db.execute(
                "UPDATE players SET gems = 10 WHERE user_id = 3"
            )
            await db.commit()
            with pytest.raises(ValueError, match="Валюта комнаты"):
                await _command(
                    "room_join",
                    3,
                    {"code": code, "currency": "gems", "amount": 1},
                )
            with pytest.raises(ValueError, match="уже находитесь"):
                await _command(
                    "room_create", 2, {"currency": "coins", "amount": 100}
                )
        finally:
            await db.close()

    asyncio.run(run())
