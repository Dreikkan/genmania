import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_guardrails_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, text=None, **kwargs):
        self.messages.append((text, kwargs))


class FakeResponse:
    async def defer(self, *args, **kwargs):
        return None

    async def send_message(self, *args, **kwargs):
        return None


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(id=user_id)
        self.response = FakeResponse()
        self.followup = FakeFollowup()


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _add_pet_player(db, user_id=1, level=1, coins=1000, gems=100):
    await db.execute(
        "INSERT INTO players (user_id, coins, gems, active_pet) "
        "VALUES (?, ?, ?, 'dog')",
        (user_id, coins, gems),
    )
    await db.execute(
        "INSERT INTO user_pets_v2 (user_id, pet_id, level, last_fed) "
        "VALUES (?, 'dog', ?, NULL)",
        (user_id, level),
    )
    await db.commit()


async def _pet_state(db, user_id=1):
    async with db.execute(
        "SELECT coins, gems FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        coins, gems = await c.fetchone()
    async with db.execute(
        "SELECT level, last_fed FROM user_pets_v2 "
        "WHERE user_id = ? AND pet_id = 'dog'",
        (user_id,),
    ) as c:
        level, last_fed = await c.fetchone()
    return coins, gems, level, last_fed


def test_feed_active_pet_is_atomic_and_cooldown_guarded():
    async def run():
        db = await _init()
        try:
            await _add_pet_player(db)
            ok, message, level, pet_id = await m.feed_active_pet(1)
            assert ok, message
            assert level == 2
            assert pet_id == "dog"

            coins, gems, stored_level, last_fed = await _pet_state(db)
            assert coins == 900
            assert gems == 99
            assert stored_level == 2
            assert last_fed is not None

            ok, message, _, _ = await m.feed_active_pet(1)
            assert ok is False
            assert "не голоден" in message
            coins, gems, stored_level, _ = await _pet_state(db)
            assert (coins, gems, stored_level) == (900, 99, 2)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_feed_active_pet_concurrent_only_one_succeeds():
    async def run():
        db = await _init()
        try:
            await _add_pet_player(db)
            results = await asyncio.gather(
                m.feed_active_pet(1),
                m.feed_active_pet(1),
            )
            assert sum(1 for result in results if result[0]) == 1
            coins, gems, level, _ = await _pet_state(db)
            assert (coins, gems, level) == (900, 99, 2)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_feed_active_pet_rejects_bad_state():
    async def run():
        db = await _init()
        try:
            await _add_pet_player(db, coins=50, gems=100)
            ok, message, _, _ = await m.feed_active_pet(1)
            assert ok is False
            assert "Нужно" in message
            coins, gems, level, _ = await _pet_state(db)
            assert (coins, gems, level) == (50, 100, 1)

            await db.execute(
                "UPDATE players SET coins = 1000 WHERE user_id = 1"
            )
            await db.execute(
                "UPDATE user_pets_v2 SET level = 10 WHERE user_id = 1"
            )
            await db.commit()
            ok, message, _, _ = await m.feed_active_pet(1)
            assert ok is False
            assert "максимального" in message
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_advent_open_is_transactional_and_guards_event():
    async def run():
        db = await _init()
        original_event = m.get_active_advent_event
        event = {"key": "test_event", "name": "Тест", "emoji": "🎄", "days": 5}
        m.get_active_advent_event = lambda: (event, 1)
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 0, 0)"
            )
            await db.commit()

            results = await asyncio.gather(
                m.open_advent_day(1, 1),
                m.open_advent_day(1, 1),
            )
            assert sum(1 for result in results if result[0]) == 1
            async with db.execute(
                "SELECT COUNT(*) FROM advent_progress WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 1
            async with db.execute(
                "SELECT coins, gems FROM players WHERE user_id = 1"
            ) as c:
                coins, gems = await c.fetchone()
            assert coins > 0
            assert gems >= 0

            ok, message, _ = await m.open_advent_day(1, 2)
            assert ok is False
            assert "сегодня" in message or "уже" in message

            m.get_active_advent_event = lambda: (None, 0)
            ok, message, _ = await m.open_advent_day(1, 1)
            assert ok is False
            assert "нет активного" in message
        finally:
            m.get_active_advent_event = original_event
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_admin_advent_respects_event_day_bounds():
    async def run():
        db = await _init()
        original_event = m.get_active_advent_event
        event = {"key": "test_event", "name": "Тест", "emoji": "🎄", "days": 5}
        m.get_active_advent_event = lambda: (event, 1)
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 0, 0)"
            )
            await db.commit()
            modal = m.AdminOpenAdventModal(1)
            modal.user_id._value = "1"
            modal.day._value = "30"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)

            assert interaction.followup.messages
            assert "1–5" in interaction.followup.messages[0][0]
            async with db.execute(
                "SELECT COUNT(*) FROM advent_progress WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 0
        finally:
            m.get_active_advent_event = original_event
            await db.close()
            m.bot.db = None

    asyncio.run(run())


async def _add_clans(db):
    await db.execute(
        "INSERT INTO players (user_id, coins) VALUES (1, 0), (2, 0), (3, 0)"
    )
    await db.execute(
        "INSERT INTO clans (id, name, leader_id, treasury) VALUES "
        "(1, 'Alpha', 1, 10000), (2, 'Beta', 2, 10000)"
    )
    await db.execute(
        "INSERT INTO clan_members (user_id, clan_id, role) VALUES "
        "(1, 1, 'leader'), (2, 2, 'leader'), (3, 1, 'member')"
    )
    await db.commit()


def test_clan_war_start_and_attack_are_serialized():
    async def run():
        db = await _init()
        original_power = m.get_combat_power

        async def fake_power(_user_id):
            return 1000

        m.get_combat_power = fake_power
        try:
            await _add_clans(db)

            results = await asyncio.gather(
                m.start_clan_war(1, 2),
                m.start_clan_war(1, 2),
                return_exceptions=True,
            )
            wars = [r for r in results if isinstance(r, int)]
            errors = [r for r in results if isinstance(r, ValueError)]
            assert len(wars) == 1, results
            assert len(errors) == 1, results
            war_id = wars[0]

            async with db.execute(
                "SELECT COUNT(*) FROM clan_wars WHERE status = 'active'"
            ) as c:
                assert (await c.fetchone())[0] == 1
            async with db.execute(
                "SELECT treasury FROM clans WHERE id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 10000 - m.CLAN_WAR_DECLARE_COST

            attacks = await asyncio.gather(
                m.attack_clan_war(war_id, 1),
                m.attack_clan_war(war_id, 1),
            )
            assert sum(1 for result in attacks if result[0]) == 1, attacks
            async with db.execute(
                "SELECT COUNT(*) FROM clan_war_attacks WHERE war_id = ?",
                (war_id,),
            ) as c:
                assert (await c.fetchone())[0] == 1
            async with db.execute(
                "SELECT status, winner_id FROM clan_wars WHERE id = ?",
                (war_id,),
            ) as c:
                status, winner_id = await c.fetchone()
            assert status == "finished"
            assert winner_id == 1
            async with db.execute(
                "SELECT treasury FROM clans WHERE id = 1"
            ) as c:
                assert (await c.fetchone())[0] == (
                    10000 - m.CLAN_WAR_DECLARE_COST + m.CLAN_WAR_REWARD
                )
        finally:
            m.get_combat_power = original_power
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_disband_requires_leader():
    async def run():
        db = await _init()
        try:
            await _add_clans(db)
            modal = m.ClanDisbandModal(3, 1)
            modal.confirm._value = "УДАЛИТЬ"
            interaction = FakeInteraction(3)
            await modal.on_submit(interaction)

            assert interaction.followup.messages
            assert "только лидер" in interaction.followup.messages[0][0]
            async with db.execute(
                "SELECT COUNT(*) FROM clans WHERE id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 1

            modal = m.ClanDisbandModal(1, 1)
            modal.confirm._value = "УДАЛИТЬ"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            async with db.execute(
                "SELECT COUNT(*) FROM clans WHERE id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 0
            async with db.execute(
                "SELECT COUNT(*) FROM clan_members WHERE clan_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 0
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
