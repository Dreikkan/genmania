import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_pet_breakthrough_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.guild_id = 1


async def _init(level=9, coins=10000, gems=1000, last_fed=None):
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems, active_pet) "
        "VALUES (1, ?, ?, 'cat')",
        (coins, gems),
    )
    await db.execute(
        "INSERT INTO user_pets_v2 (user_id, pet_id, level, last_fed) "
        "VALUES (1, 'cat', ?, ?)",
        (level, last_fed),
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


def test_breakthrough_levels_and_feed_costs():
    assert m.PET_BREAKTHROUGH_LEVELS == (
        10, 25, 50, 75, 100, 125, 150, 175, 200
    )
    assert m.PET_MAX_LEVEL == 200

    assert m.pet_breakthrough_count(9) == 0
    assert m.pet_breakthrough_count(10) == 1
    assert m.pet_breakthrough_count(25) == 2
    assert m.pet_breakthrough_count(50) == 3
    assert m.pet_breakthrough_count(200) == 9

    assert m.pet_effective_level(0) == 0
    assert m.PET_RUNTIME.effective_level(0) == 0
    assert m.pet_effective_level(200) == 19.0
    assert m.PET_RUNTIME.effective_level(200) == 19.0
    assert m.pet_feed_cost(200) == (32269, 39)
    assert m.pet_next_breakthrough(9) == 10
    assert m.pet_next_breakthrough(10) == 25
    assert m.pet_next_breakthrough(200) is None

    assert m.pet_feed_cost(9) == (100, 1)
    assert m.pet_feed_cost(10) == (190, 2)
    assert m.pet_feed_cost(25) == (361, 3)
    assert m.pet_feed_cost(50) == (686, 4)

    costs = [m.pet_feed_cost(level) for level in m.PET_BREAKTHROUGH_LEVELS]
    for previous, current in zip(costs, costs[1:]):
        assert current[0] > previous[0]
        assert current[1] > previous[1]


def test_feed_breakthrough_and_max_level():
    async def run():
        db = await _init(level=9)
        try:
            ok, message, level, pet_id = await m.feed_active_pet(1)
            assert ok, message
            assert level == 10
            assert pet_id == "cat"
            assert "Прорыв" in message
            assert "190" in message
            assert "2" in message

            async with db.execute(
                "SELECT coins, gems FROM players WHERE user_id = 1"
            ) as c:
                coins, gems = await c.fetchone()
            assert (coins, gems) == (9900, 999)

            await db.execute(
                "UPDATE user_pets_v2 SET last_fed = '2000-01-01T00:00:00' "
                "WHERE user_id = 1 AND pet_id = 'cat'"
            )
            await db.commit()
            ok, message, level, _ = await m.feed_active_pet(1)
            assert ok, message
            assert level == 11
            assert "🔓 Прорыв!" not in message
            assert "Следующее кормление" in message

            await db.execute(
                "UPDATE user_pets_v2 SET level = 199 WHERE user_id = 1"
            )
            await db.execute(
                "UPDATE players SET coins = 10000000, gems = 10000 "
                "WHERE user_id = 1"
            )
            await db.execute(
                "UPDATE user_pets_v2 SET last_fed = '2000-01-01T00:00:00' "
                "WHERE user_id = 1 AND pet_id = 'cat'"
            )
            await db.commit()
            ok, message, level, _ = await m.feed_active_pet(1)
            assert ok, message
            assert level == m.PET_MAX_LEVEL
            assert "Достигнут максимальный уровень" in message

            ok, message, _, _ = await m.feed_active_pet(1)
            assert not ok
            assert "максимального" in message
        finally:
            await _close(db)

    asyncio.run(run())


def test_pet_embed_shows_breakthrough_and_cost():
    async def run():
        db = await _init(level=10)
        try:
            embed = await m.build_pets_embed(FakeInteraction(1))
            field = next(
                field for field in embed.fields if "Кот" in field.name
            )
            assert "190" in field.value
            assert "2" in field.value
            assert "Прорывов" in field.value
            assert "1/9" in field.value
            assert "До прорыва" in field.value

            await db.execute(
                "UPDATE user_pets_v2 SET level = ? WHERE user_id = 1",
                (m.PET_MAX_LEVEL,),
            )
            await db.commit()
            embed = await m.build_pets_embed(FakeInteraction(1))
            field = next(
                field for field in embed.fields if "Кот" in field.name
            )
            assert "Максимальный уровень" in field.value
            assert "До прорыва" not in field.value
        finally:
            await _close(db)

    asyncio.run(run())
