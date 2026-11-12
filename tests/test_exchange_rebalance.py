import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_exchange_rebalance_test", BOT_PATH
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
        self.user = SimpleNamespace(id=user_id)
        self.response = FakeResponse()
        self.followup = FakeFollowup()


async def _init(coins=0, gems=0):
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems) VALUES (1, ?, ?)",
        (coins, gems),
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


def test_exchange_rate_is_rebalanced():
    assert m.COINS_PER_GEM == 1000
    assert m.GEMS_PER_COIN_RATE == 800
    assert m.COIN_EXCHANGE_MIN == m.COINS_PER_GEM


def test_exchange_320k_coins_gives_modest_gems():
    async def run():
        db = await _init(coins=320_500)
        try:
            modal = m.CoinsToGemsModal(1)
            modal.amount._value = "320500"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)

            async with db.execute(
                "SELECT coins, gems FROM players WHERE user_id = 1"
            ) as c:
                coins, gems = await c.fetchone()
            assert coins == 500
            assert gems == 292
            assert interaction.followup.sent
            assert "Остаток" in interaction.followup.sent[-1][0][0]
        finally:
            await _close(db)

    asyncio.run(run())


def test_exchange_1k_coins_gives_one_gem_before_fee():
    async def run():
        db = await _init(coins=10_000)
        try:
            modal = m.CoinsToGemsModal(1)
            modal.amount._value = "1000"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)

            async with db.execute(
                "SELECT coins, gems FROM players WHERE user_id = 1"
            ) as c:
                coins, gems = await c.fetchone()
            assert coins == 9000
            assert gems == 1
        finally:
            await _close(db)

    asyncio.run(run())


def test_reverse_exchange_rate_is_consistent():
    async def run():
        db = await _init(gems=10)
        try:
            modal = m.GemsToCoinsModal(1)
            modal.amount._value = "10"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)

            async with db.execute(
                "SELECT coins, gems FROM players WHERE user_id = 1"
            ) as c:
                coins, gems = await c.fetchone()
            assert gems == 0
            assert coins == 7680
        finally:
            await _close(db)

    asyncio.run(run())
