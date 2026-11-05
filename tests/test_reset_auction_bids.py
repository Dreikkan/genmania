import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_reset_auction_test", BOT_PATH)
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
    def __init__(self, user_id=1, guild_id=None):
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = guild_id
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.message = None


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._top_cache.clear()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems) VALUES "
        "(1, 1000, 1000), (2, 100, 100)"
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._top_cache.clear()


async def _add_active_bid(
    db,
    seller_id: int = 2,
    bidder_id: int = 1,
    start_price: int = 100,
    current_bid: int = 150,
) -> int:
    end_time = (
        datetime.datetime.now() + datetime.timedelta(hours=1)
    ).isoformat()
    cursor = await db.execute(
        "INSERT INTO auctions "
        "(seller_id, item_id, stars, start_price, current_bid, "
        "current_bidder, buyout_price, end_time, status) "
        "VALUES (?, 'basic_gen', 0, ?, ?, ?, NULL, ?, 'active')",
        (seller_id, start_price, current_bid, bidder_id, end_time),
    )
    await db.commit()
    return int(cursor.lastrowid)


async def _auction_row(db, auction_id: int):
    async with db.execute(
        "SELECT current_bid, current_bidder, status FROM auctions WHERE id = ?",
        (auction_id,),
    ) as cursor:
        return await cursor.fetchone()


def test_release_active_auction_bids_refunds_and_resets_lot():
    async def run():
        db = await _init()
        try:
            auction_id = await _add_active_bid(db)
            async with m.db_transaction():
                released, refunded = await m.release_active_auction_bids(1)
            assert released == 1
            assert refunded == 150
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 1"
            ) as cursor:
                assert (await cursor.fetchone())[0] == 1150
            assert await _auction_row(db, auction_id) == (100, None, "active")
            async with db.execute(
                "SELECT bidder_id, amount, kind FROM auction_bids "
                "WHERE auction_id = ?",
                (auction_id,),
            ) as cursor:
                assert await cursor.fetchone() == (1, 150, "refund")
        finally:
            await _close(db)

    asyncio.run(run())


def test_user_reset_releases_foreign_auction_bid():
    async def run():
        db = await _init()
        try:
            auction_id = await _add_active_bid(db)
            modal = m.UserResetModal(1)
            modal.confirm._value = "СБРОСИТЬ"
            interaction = FakeInteraction(user_id=1)
            await modal.on_submit(interaction)

            assert interaction.followup.messages
            assert "ставки" in interaction.followup.messages[-1][0]
            assert await _auction_row(db, auction_id) == (100, None, "active")
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 1"
            ) as cursor:
                assert (await cursor.fetchone())[0] == m.DEFAULT_START_COINS
        finally:
            await _close(db)

    asyncio.run(run())


def test_admin_reset_releases_foreign_auction_bid():
    async def run():
        db = await _init()
        try:
            auction_id = await _add_active_bid(db)
            modal = m.AdminResetModal(2)
            modal.user_id._value = "1"
            modal.confirm._value = "ДА"
            interaction = FakeInteraction(user_id=2)
            await modal.on_submit(interaction)

            assert interaction.followup.messages
            assert "ставки" in interaction.followup.messages[-1][0]
            assert await _auction_row(db, auction_id) == (100, None, "active")
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 1"
            ) as cursor:
                assert (await cursor.fetchone())[0] == m.DEFAULT_START_COINS
        finally:
            await _close(db)

    asyncio.run(run())


def test_prestige_releases_foreign_auction_bid():
    async def run():
        db = await _init()
        try:
            auction_id = await _add_active_bid(db)
            await db.execute(
                "UPDATE players SET lifetime_production = ?, "
                "prestige_points = 0 WHERE user_id = 1",
                (m.PRESTIGE_BASE_REQUIREMENT,),
            )
            await db.commit()

            ok, message, gain, points = await m.do_prestige(1)
            assert ok, message
            assert gain >= 1
            assert points >= 1
            assert "ставки" in message
            assert await _auction_row(db, auction_id) == (100, None, "active")
            async with db.execute(
                "SELECT coins, prestige_points FROM players WHERE user_id = 1"
            ) as cursor:
                coins, prestige_points = await cursor.fetchone()
            assert coins == m.DEFAULT_START_COINS
            assert prestige_points >= 1
        finally:
            await _close(db)

    asyncio.run(run())
