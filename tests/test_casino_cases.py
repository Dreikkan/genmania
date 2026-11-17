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
            assert set(week47) == set(week48)
            assert len(set(week47)) == 15
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
            assert bronze["price"] > 0
            assert bronze["odds"]
            assert abs(sum(item["chance"] for item in bronze["stars"]) - 100) < 0.2
            golden = casino["cases"][2]
            assert golden["currency"] == "gems"
            assert golden["price"] > 0
            assert casino["history"] == []
        finally:
            await db.close()

    asyncio.run(run())


def test_casino_case_open_spends_coins_and_grants_item():
    async def run():
        db = await _setup(coins=100_000)
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
            assert result["price"] > 0
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
            assert coins == 100_000 - result["price"]
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
        db = await _setup(gems=5000)
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
            assert result["price"] > 0
            async with db.execute(
                "SELECT gems FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == (
                    5000 - result["price"]
                )
        finally:
            await db.close()

    asyncio.run(run())


def _shoe_with(*deal_order):
    """Собирает шуз так, чтобы pop() выдали карты в нужном порядке."""
    return ["2C"] * 20 + list(reversed(deal_order))


def test_roulette_spin_pays_and_records_history():
    async def run():
        db = await _setup(coins=100_000)
        try:
            with mock.patch.object(m, "spin_number", return_value=17):
                result = await m.bot.handle_web_game_command(
                    {
                        "id": "roulette-1",
                        "action": "roulette_spin",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {
                            "currency": "coins",
                            "bet_type": "color",
                            "bet_value": "black",
                            "amount": 1000,
                        },
                    }
                )
            assert result["ok"] is True
            assert result["number"] == 17
            assert result["color"] == "black"
            assert result["payout"] == 2000
            assert result["net"] == 1000
            assert result["message"].startswith("Выпало 17")
            roulette = result["state"]["casino"]["roulette"]
            assert roulette["history"][0]["number"] == 17
            assert roulette["stats"]["spins"] == 1
            assert roulette["stats"]["wins"] == 1
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 101_000
        finally:
            await db.close()

    asyncio.run(run())


def test_roulette_rejects_bad_bets_and_limits():
    async def run():
        db = await _setup(coins=100)
        try:
            with pytest.raises(ValueError, match="Неизвестный тип"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "roulette-bad-type",
                        "action": "roulette_spin",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {
                            "currency": "coins",
                            "bet_type": "lucky",
                            "bet_value": "red",
                            "amount": 100,
                        },
                    }
                )
            with pytest.raises(ValueError, match="Ставка должна быть"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "roulette-small",
                        "action": "roulette_spin",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {
                            "currency": "coins",
                            "bet_type": "color",
                            "bet_value": "red",
                            "amount": 10,
                        },
                    }
                )
            with pytest.raises(ValueError, match="Недостаточно средств"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "roulette-poor",
                        "action": "roulette_spin",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {
                            "currency": "gems",
                            "bet_type": "color",
                            "bet_value": "red",
                            "amount": 1,
                        },
                    }
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_start_and_stand():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "9H", "10D", "8C"),
            ):
                started = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-start-1",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            assert started["status"] == "player"
            assert started["player_total"] == 19
            assert started["dealer_total"] == 10
            assert started["dealer_hidden"] is True
            active = started["state"]["casino"]["blackjack"]["active"]
            assert active["can_hit"] is True
            assert active["can_double"] is True

            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "9H", "10D", "8C"),
            ):
                stood = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-stand-1",
                        "action": "blackjack_stand",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert stood["status"] == "done"
            assert stood["outcome"] == "win"
            assert stood["payout"] == 200
            assert stood["net"] == 100
            assert stood["dealer_hidden"] is False
            assert stood["state"]["casino"]["blackjack"]["active"] is None
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 1100
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_natural_pays_three_to_two():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("AS", "KH", "9D", "7C"),
            ):
                result = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-natural",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            assert result["status"] == "done"
            assert result["outcome"] == "blackjack"
            assert result["payout"] == 250
            assert result["net"] == 150
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 1150
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_hit_and_double():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("5S", "6H", "10D", "7C", "10S"),
            ):
                started = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-hit-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            assert started["player_total"] == 11

            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S"),
            ):
                hit = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-hit-1",
                        "action": "blackjack_hit",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert hit["status"] == "done"
            assert hit["outcome"] == "win"
            assert hit["payout"] == 200

            await db.execute(
                "UPDATE players SET coins = 1000 WHERE user_id = 2"
            )
            await db.commit()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("5S", "6H", "10D", "7C", "10S"),
            ):
                started2 = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dbl-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            assert started2["status"] == "player"
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S"),
            ):
                doubled = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-double-1",
                        "action": "blackjack_double",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert doubled["status"] == "done"
            assert doubled["payout"] == 400
            assert doubled["net"] == 200
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 1200
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_rejects_second_game_and_bad_bet():
    async def run():
        db = await _setup(coins=1000)
        try:
            with pytest.raises(ValueError, match="Ставка должна быть"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-bad-bet",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 10},
                    }
                )
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("5S", "6H", "10D", "7C"),
            ):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-active-1",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            with pytest.raises(ValueError, match="уже есть незавершённая"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-active-2",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_roulette_all_bet_types_and_gems():
    async def run():
        db = await _setup(coins=100_000, gems=100)
        try:
            expectations = [
                ("number", "17", 3600),
                ("parity", "odd", 200),
                ("range", "low", 200),
                ("dozen", "2", 300),
            ]
            for index, (bet_type, bet_value, payout) in enumerate(expectations):
                with mock.patch.object(m, "spin_number", return_value=17):
                    result = await m.bot.handle_web_game_command(
                        {
                            "id": f"roulette-type-{index}",
                            "action": "roulette_spin",
                            "user_id": "2",
                            "guild_id": "42",
                            "payload": {
                                "currency": "coins",
                                "bet_type": bet_type,
                                "bet_value": bet_value,
                                "amount": 100,
                            },
                        }
                    )
                assert result["payout"] == payout
            with mock.patch.object(m, "spin_number", return_value=17):
                gems = await m.bot.handle_web_game_command(
                    {
                        "id": "roulette-gems",
                        "action": "roulette_spin",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {
                            "currency": "gems",
                            "bet_type": "color",
                            "bet_value": "black",
                            "amount": 5,
                        },
                    }
                )
            assert gems["currency"] == "gems"
            assert gems["payout"] == 10
            async with db.execute(
                "SELECT gems FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 105
        finally:
            await db.close()

    asyncio.run(run())


def test_roulette_invalid_values():
    async def run():
        db = await _setup(coins=10_000)
        try:
            invalid = [
                ("color", "green"),
                ("parity", "zero"),
                ("range", "mid"),
                ("dozen", "9"),
                ("number", "99"),
            ]
            for index, (bet_type, bet_value) in enumerate(invalid):
                with pytest.raises(ValueError):
                    await m.bot.handle_web_game_command(
                        {
                            "id": f"roulette-invalid-{index}",
                            "action": "roulette_spin",
                            "user_id": "2",
                            "guild_id": "42",
                            "payload": {
                                "currency": "coins",
                                "bet_type": bet_type,
                                "bet_value": bet_value,
                                "amount": 100,
                            },
                        }
                    )
            with pytest.raises(ValueError, match="Неверная валюта"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "roulette-currency",
                        "action": "roulette_spin",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {
                            "currency": "silver",
                            "bet_type": "color",
                            "bet_value": "red",
                            "amount": 100,
                        },
                    }
                )
            with pytest.raises(ValueError, match="Некорректная ставка"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "roulette-amount",
                        "action": "roulette_spin",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {
                            "currency": "coins",
                            "bet_type": "color",
                            "bet_value": "red",
                            "amount": "abc",
                        },
                    }
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_dealer_natural_and_push():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "9H", "AD", "KC"),
            ):
                dealer_natural = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dealer-natural",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            assert dealer_natural["status"] == "done"
            assert dealer_natural["outcome"] == "lose"
            assert dealer_natural["payout"] == 0

            await db.execute(
                "UPDATE players SET coins = 1000 WHERE user_id = 2"
            )
            await db.commit()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "9H", "10D", "9C"),
            ):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-push-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            push = await m.bot.handle_web_game_command(
                {
                    "id": "bj-push-stand",
                    "action": "blackjack_stand",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert push["outcome"] == "push"
            assert push["payout"] == 100
            assert push["net"] == 0
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 1000
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_bust_and_double_bust():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "6H", "10D", "7C", "KD"),
            ):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-bust-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("KD"),
            ):
                bust = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-bust-hit",
                        "action": "blackjack_hit",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert bust["outcome"] == "bust"
            assert bust["payout"] == 0
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 900

            await db.execute(
                "UPDATE players SET coins = 1000 WHERE user_id = 2"
            )
            await db.commit()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "6H", "10D", "7C", "KD"),
            ):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dbl-bust-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("KD"),
            ):
                doubled = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dbl-bust",
                        "action": "blackjack_double",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert doubled["outcome"] == "bust"
            assert doubled["net"] == -200
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 800
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_double_insufficient_and_actions_without_game():
    async def run():
        db = await _setup(coins=150)
        try:
            with pytest.raises(ValueError, match="Нет активной раздачи"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-no-game-hit",
                        "action": "blackjack_hit",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "6H", "10D", "7C"),
            ):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dbl-poor-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            with pytest.raises(ValueError, match="Недостаточно средств"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dbl-poor",
                        "action": "blackjack_double",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_state_exposes_active_game():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("9S", "6H", "10D", "7C"),
            ):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-state-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            state = await m.bot.handle_web_game_command(
                {
                    "id": "bj-state",
                    "action": "state",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            active = state["casino"]["blackjack"]["active"]
            assert active["player_total"] == 15
            assert active["dealer_total"] == 10
            assert active["dealer_hidden"] is True
            assert active["can_hit"] is True
            assert active["can_double"] is True
            assert active["stake"] == 100
        finally:
            await db.close()

    asyncio.run(run())


def test_case_mailbox_fallback_and_emoji_fallbacks():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "place_items",
                side_effect=ValueError("no space"),
            ):
                result = await m.bot.handle_web_game_command(
                    {
                        "id": "case-mailbox",
                        "action": "case_open",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"case_id": "bronze_case"},
                    }
                )
            assert result["placed"] == "mailbox"
            async with db.execute(
                "SELECT COUNT(*) FROM mailbox WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 1

            assert m.bot._casino_item_emoji("📦", "not-json", 1) == "📦"
            assert m.bot._casino_item_emoji("📦", "{}", 1) == "📦"
            assert m.bot._casino_item_emoji(
                "📦", '{"1": "<:x:1>"}', 1
            ) == "<:x:1>"
        finally:
            await db.close()

    asyncio.run(run())


def test_case_open_empty_pool_and_bad_payload():
    async def run():
        db = await _setup(coins=1000)
        try:
            with pytest.raises(ValueError, match="Неизвестный кейс"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "case-payload-string",
                        "action": "case_open",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": "bad",
                    }
                )
            with mock.patch.object(
                m.CastleBot, "_casino_pool", return_value=[]
            ):
                with pytest.raises(ValueError, match="пул кейсов пуст"):
                    await m.bot.handle_web_game_command(
                        {
                            "id": "case-empty-pool",
                            "action": "case_open",
                            "user_id": "2",
                            "guild_id": "42",
                            "payload": {"case_id": "bronze_case"},
                        }
                    )
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_dealer_bust_and_double_after_hit():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "8H", "10D", "6C", "9S"),
            ):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dealer-bust-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("9S"),
            ):
                stood = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dealer-bust-stand",
                        "action": "blackjack_stand",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert stood["dealer_total"] > 21
            assert stood["outcome"] == "win"

            await db.execute(
                "UPDATE players SET coins = 1000 WHERE user_id = 2"
            )
            await db.commit()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("5S", "6H", "10D", "7C", "2S"),
            ):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dbl-late-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            await m.bot.handle_web_game_command(
                {
                    "id": "bj-dbl-late-hit",
                    "action": "blackjack_hit",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            with pytest.raises(ValueError, match="только на первых двух"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dbl-late",
                        "action": "blackjack_double",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_start_invalid_inputs():
    async def run():
        db = await _setup(coins=0)
        try:
            with pytest.raises(ValueError, match="Неверная валюта"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-bad-currency",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "silver", "amount": 100},
                    }
                )
            with pytest.raises(ValueError, match="Некорректная ставка"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-bad-amount",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": "abc"},
                    }
                )
            with pytest.raises(ValueError, match="Недостаточно средств"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-poor-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            with pytest.raises(ValueError, match="Нет активной раздачи"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-no-game-stand",
                        "action": "blackjack_stand",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            with pytest.raises(ValueError, match="Нет активной раздачи"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-no-game-double",
                        "action": "blackjack_double",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_casino_bet_limits_and_state_without_pool():
    async def run():
        db = await _setup(coins=50, gems=0)
        try:
            assert m.bot._casino_bet_limits(50, "coins")["max"] == 0
            assert m.bot._casino_bet_limits(1_000_000_000, "coins")["max"] == 1_000_000
            assert m.bot._casino_bet_limits(1000, "gems")["max"] == 100
            with mock.patch.object(
                m.CastleBot, "_casino_pool", return_value=[]
            ):
                casino = await m.bot._web_game_casino_state(2)
            assert casino["pool"] == []
            assert casino["cases"] == []
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_active_cannot_double_with_low_balance():
    async def run():
        db = await _setup(coins=150)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("5S", "6H", "10D", "7C"),
            ):
                result = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-low-balance-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            assert result["state"]["casino"]["blackjack"]["active"]["can_double"] is False
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_both_natural_and_double_win():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("AS", "KH", "AD", "KC"),
            ):
                both = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-both-natural",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            assert both["outcome"] == "push"
            assert both["payout"] == 100

            await db.execute(
                "UPDATE players SET coins = 1000 WHERE user_id = 2"
            )
            await db.commit()
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "9H", "10D", "9C", "2S"),
            ):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dbl-push-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("2S"),
            ):
                push = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dbl-push",
                        "action": "blackjack_double",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert push["outcome"] == "win"
            assert push["payout"] == 400
            assert push["net"] == 200
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_stale_game_actions():
    async def run():
        db = await _setup(coins=1000)
        stale = {
            "id": 999999,
            "bet": 100,
            "currency": "coins",
            "player": ["5S", "6H"],
            "dealer": ["10D", "7C"],
            "shoe": ["2C", "3C"],
            "doubled": False,
        }
        try:
            with mock.patch.object(
                m.CastleBot, "_blackjack_active", return_value=stale
            ):
                with pytest.raises(ValueError, match="уже завершена"):
                    await m.bot.handle_web_game_command(
                        {
                            "id": "bj-stale-hit",
                            "action": "blackjack_hit",
                            "user_id": "2",
                            "guild_id": "42",
                            "payload": {},
                        }
                    )
                with pytest.raises(ValueError, match="уже завершена"):
                    await m.bot.handle_web_game_command(
                        {
                            "id": "bj-stale-stand",
                            "action": "blackjack_stand",
                            "user_id": "2",
                            "guild_id": "42",
                            "payload": {},
                        }
                    )
                with pytest.raises(ValueError, match="уже завершена"):
                    await m.bot.handle_web_game_command(
                        {
                            "id": "bj-stale-double",
                            "action": "blackjack_double",
                            "user_id": "2",
                            "guild_id": "42",
                            "payload": {},
                        }
                    )
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_and_roulette_non_dict_payloads():
    async def run():
        db = await _setup(coins=1000)
        try:
            for action in ("blackjack_start", "roulette_spin"):
                with pytest.raises(ValueError):
                    await m.bot.handle_web_game_command(
                        {
                            "id": f"bad-payload-{action}",
                            "action": action,
                            "user_id": "2",
                            "guild_id": "42",
                            "payload": "bad",
                        }
                    )
            with pytest.raises(ValueError, match="Ставка должна быть"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "roulette-zero-amount",
                        "action": "roulette_spin",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {
                            "currency": "coins",
                            "bet_type": "color",
                            "bet_value": "red",
                            "amount": 0,
                        },
                    }
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_casino_price_rounding_and_week_bounds():
    assert m.casino_nice_price(0) == 5
    assert m.casino_nice_price(42) == 40
    assert m.casino_nice_price(420) == 420
    assert m.casino_nice_price(4200) == 4200
    assert m.casino_nice_price(42000) == 42000
    assert m.casino_nice_price(420000) == 420000
    assert m.casino_nice_price(4200000) == 4200000
    moment = m.datetime.datetime(
        2026, 11, 17, 12, 0, tzinfo=m.datetime.timezone.utc
    )
    year, week, start, end = m.bot._casino_week_bounds(moment)
    assert (year, week) == (2026, 47)
    assert start.weekday() == 0
    assert (end - start).days == 7


def test_casino_pool_empty_and_green_number():
    async def run():
        db = await _setup(coins=100_000)
        try:
            await db.execute("DELETE FROM items")
            await db.commit()
            assert await m.bot._casino_pool() == []

            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (3, 100000) "
                "ON CONFLICT(user_id) DO UPDATE SET coins = 100000"
            )
            await db.commit()
            with mock.patch.object(m, "spin_number", return_value=0):
                result = await m.bot.handle_web_game_command(
                    {
                        "id": "roulette-green",
                        "action": "roulette_spin",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {
                            "currency": "coins",
                            "bet_type": "number",
                            "bet_value": "0",
                            "amount": 100,
                        },
                    }
                )
            assert result["color"] == "green"
            assert result["payout"] == 3600
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_dealer_draws_multiple_cards():
    async def run():
        db = await _setup(coins=1000)
        try:
            shoe = ["3H", "2S", "2C", "10D", "9H", "10S"]
            with mock.patch.object(m, "new_shoe", return_value=shoe):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-multi-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            stood = await m.bot.handle_web_game_command(
                {
                    "id": "bj-multi-stand",
                    "action": "blackjack_stand",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert stood["dealer_total"] == 17
            assert stood["outcome"] == "win"
        finally:
            await db.close()

    asyncio.run(run())


def test_casino_gems_blackjack_and_empty_shoe():
    async def run():
        db = await _setup(coins=1000, gems=50)
        try:
            assert await m.bot._casino_balances(999) == (0, 0)
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "9H", "10D", "8C"),
            ):
                started = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-gems-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "gems", "amount": 1},
                    }
                )
            assert started["currency"] == "gems"
            assert started["status"] == "player"
            game_id = int(started["state"]["casino"]["blackjack"]["active"]["id"])
            stand = await m.bot.handle_web_game_command(
                {
                    "id": "bj-gems-stand",
                    "action": "blackjack_stand",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert stand["outcome"] == "win"
            async with db.execute(
                "SELECT gems FROM players WHERE user_id = 2"
            ) as cursor:
                assert int((await cursor.fetchone())[0]) == 51

            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "9H", "10D", "8C"),
            ):
                coins_game = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-empty-shoe-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            game_id = int(coins_game["state"]["casino"]["blackjack"]["active"]["id"])
            fake = {
                "id": game_id,
                "bet": 100,
                "currency": "coins",
                "player": ["10S", "9H"],
                "dealer": ["10D", "6C"],
                "shoe": [],
                "doubled": False,
            }
            with mock.patch.object(
                m.CastleBot, "_blackjack_active", return_value=fake
            ), mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("2S"),
            ):
                result = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-empty-shoe-stand",
                        "action": "blackjack_stand",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert result["status"] == "done"
        finally:
            await db.close()

    asyncio.run(run())


def test_casino_parse_cards_and_race_guards():
    async def run():
        assert m.bot._parse_cards("not-json") == []
        assert m.bot._parse_cards('{"a": 1}') == []
        assert m.bot._parse_cards('["AS", 5]') == ["AS"]

        db = await _setup(coins=0)
        try:
            with mock.patch.object(
                m.CastleBot, "_casino_balances", return_value=(1000, 0)
            ):
                with pytest.raises(ValueError, match="Недостаточно средств"):
                    await m.bot.handle_web_game_command(
                        {
                            "id": "roulette-race",
                            "action": "roulette_spin",
                            "user_id": "2",
                            "guild_id": "42",
                            "payload": {
                                "currency": "coins",
                                "bet_type": "color",
                                "bet_value": "red",
                                "amount": 100,
                            },
                        }
                    )
                with pytest.raises(ValueError, match="Недостаточно средств"):
                    await m.bot.handle_web_game_command(
                        {
                            "id": "bj-race",
                            "action": "blackjack_start",
                            "user_id": "2",
                            "guild_id": "42",
                            "payload": {"currency": "coins", "amount": 100},
                        }
                    )
        finally:
            await db.close()

    asyncio.run(run())


def test_roulette_number_parse_and_losing_message():
    async def run():
        db = await _setup(coins=1000)
        try:
            with pytest.raises(ValueError, match="Выберите число"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "roulette-number-bad",
                        "action": "roulette_spin",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {
                            "currency": "coins",
                            "bet_type": "number",
                            "bet_value": "abc",
                            "amount": 100,
                        },
                    }
                )
            with mock.patch.object(m, "spin_number", return_value=17):
                losing = await m.bot.handle_web_game_command(
                    {
                        "id": "roulette-lose",
                        "action": "roulette_spin",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {
                            "currency": "coins",
                            "bet_type": "color",
                            "bet_value": "red",
                            "amount": 100,
                        },
                    }
                )
            assert losing["payout"] == 0
            assert "не сыграла" in losing["message"]
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_empty_shoe_hit_and_stale_settle():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "9H", "10D", "8C"),
            ):
                started = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-empty-hit-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            game_id = int(started["state"]["casino"]["blackjack"]["active"]["id"])
            fake = {
                "id": game_id,
                "bet": 100,
                "currency": "coins",
                "player": ["10S", "8H"],
                "dealer": ["10D", "7C"],
                "shoe": [],
                "doubled": False,
            }
            with mock.patch.object(
                m.CastleBot, "_blackjack_active", return_value=fake
            ), mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("2S"),
            ):
                result = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-empty-hit",
                        "action": "blackjack_hit",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert result["player_total"] == 20

            stale = {
                "id": 999999,
                "bet": 100,
                "currency": "coins",
                "player": ["10S", "9H"],
                "dealer": ["10D", "7C"],
                "shoe": ["2C"],
                "doubled": False,
            }
            with mock.patch.object(
                m.CastleBot, "_blackjack_active", return_value=stale
            ):
                with pytest.raises(ValueError, match="уже завершена"):
                    await m.bot.handle_web_game_command(
                        {
                            "id": "bj-stale-settle",
                            "action": "blackjack_hit",
                            "user_id": "2",
                            "guild_id": "42",
                            "payload": {},
                        }
                    )
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_empty_shoe_dealer_loop():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "9H", "10D", "8C"),
            ):
                started = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-loop-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            game_id = int(started["state"]["casino"]["blackjack"]["active"]["id"])
            fake = {
                "id": game_id,
                "bet": 100,
                "currency": "coins",
                "player": ["10S", "9H"],
                "dealer": ["2D", "3C"],
                "shoe": [],
                "doubled": False,
            }
            with mock.patch.object(
                m.CastleBot, "_blackjack_active", return_value=fake
            ), mock.patch.object(
                m,
                "new_shoe",
                side_effect=[["9S"], ["3C"]],
            ):
                result = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-loop-stand",
                        "action": "blackjack_stand",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert result["status"] == "done"
            assert result["dealer_total"] >= 17
        finally:
            await db.close()

    asyncio.run(run())


def test_casino_case_offer_weekly_shift():
    async def run():
        db = await _setup(coins=1000)
        try:
            pool = await m.bot._casino_pool()
            assert m.casino_nice_price(-5) == 5
            for week in (1, 2, 3):
                with mock.patch.object(
                    m.CastleBot,
                    "_casino_week_bounds",
                    return_value=(2026, week, None, None),
                ):
                    for case in m.CASINO_CASES:
                        offer = m.bot._casino_case_offer(case, pool)
                        assert offer["price"] > 0
                        assert offer["items"]
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_hit_21_and_double_with_empty_shoe():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "9H", "10D", "8C"),
            ):
                started = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-empty21-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            game_id = int(started["state"]["casino"]["blackjack"]["active"]["id"])
            fake = {
                "id": game_id,
                "bet": 100,
                "currency": "coins",
                "player": ["10S", "9H"],
                "dealer": ["2D", "3C"],
                "shoe": ["2S"],
                "doubled": False,
            }
            with mock.patch.object(
                m.CastleBot, "_blackjack_active", return_value=fake
            ), mock.patch.object(
                m,
                "new_shoe",
                side_effect=[["9S"], ["3C"]],
            ):
                result = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-empty21-hit",
                        "action": "blackjack_hit",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert result["player_total"] == 21
            assert result["dealer_total"] >= 17

            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("5S", "6H", "10D", "7C"),
            ):
                started2 = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-empty-dbl-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            game_id2 = int(started2["state"]["casino"]["blackjack"]["active"]["id"])
            fake2 = {
                "id": game_id2,
                "bet": 100,
                "currency": "coins",
                "player": ["5S", "6H"],
                "dealer": ["2D", "3C"],
                "shoe": [],
                "doubled": False,
            }
            with mock.patch.object(
                m.CastleBot, "_blackjack_active", return_value=fake2
            ), mock.patch.object(
                m,
                "new_shoe",
                side_effect=[["10S"], ["9S"], ["3C"]],
            ):
                doubled = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-empty-dbl",
                        "action": "blackjack_double",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert doubled["player_total"] == 21
            assert doubled["status"] == "done"
        finally:
            await db.close()

    asyncio.run(run())


def test_casino_minor_branches():
    async def run():
        assert m.bot._casino_bet_limits(1000, "silver")["max"] == 100
        year, week, start, end = m.bot._casino_week_bounds()
        assert year >= 2024
        assert start <= end
        assert m.bot._casino_item_emoji("📦", "[1, 2]", 0) == "📦"

        db = await _setup(coins=1000)
        try:
            with pytest.raises(ValueError, match="Ставка должна быть"):
                await m.bot.handle_web_game_command(
                    {
                        "id": "roulette-over-limit",
                        "action": "roulette_spin",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {
                            "currency": "coins",
                            "bet_type": "color",
                            "bet_value": "red",
                            "amount": 500,
                        },
                    }
                )
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_stand_lose():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "8H", "10D", "9C"),
            ):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-stand-lose-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            lost = await m.bot.handle_web_game_command(
                {
                    "id": "bj-stand-lose",
                    "action": "blackjack_stand",
                    "user_id": "2",
                    "guild_id": "42",
                    "payload": {},
                }
            )
            assert lost["outcome"] == "lose"
            assert lost["payout"] == 0
            assert lost["net"] == -100
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_double_lose():
    async def run():
        db = await _setup(coins=1000)
        try:
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("10S", "6H", "10D", "9C"),
            ):
                await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dbl-lose-start",
                        "action": "blackjack_start",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {"currency": "coins", "amount": 100},
                    }
                )
            with mock.patch.object(
                m,
                "new_shoe",
                return_value=_shoe_with("2S"),
            ):
                lost = await m.bot.handle_web_game_command(
                    {
                        "id": "bj-dbl-lose",
                        "action": "blackjack_double",
                        "user_id": "2",
                        "guild_id": "42",
                        "payload": {},
                    }
                )
            assert lost["outcome"] == "lose"
            assert lost["payout"] == 0
            assert lost["net"] == -200
        finally:
            await db.close()

    asyncio.run(run())


def test_blackjack_double_race_guard():
    async def run():
        db = await _setup(coins=0)
        fake = {
            "id": 999999,
            "bet": 100,
            "currency": "coins",
            "player": ["5S", "6H"],
            "dealer": ["10D", "7C"],
            "shoe": ["2C"],
            "doubled": False,
        }
        try:
            with mock.patch.object(
                m.CastleBot, "_blackjack_active", return_value=fake
            ), mock.patch.object(
                m.CastleBot, "_casino_balances", return_value=(1000, 0)
            ):
                with pytest.raises(
                    ValueError, match="Недостаточно средств для удвоения"
                ):
                    await m.bot.handle_web_game_command(
                        {
                            "id": "bj-dbl-race",
                            "action": "blackjack_double",
                            "user_id": "2",
                            "guild_id": "42",
                            "payload": {},
                        }
                    )
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
