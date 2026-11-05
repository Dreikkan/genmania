import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_concurrency_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._tax_rate_cache.clear()
    m._top_cache.clear()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems) VALUES "
        "(1, 1000, 100), (2, 1000, 100), (3, 1000, 100)"
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._tax_rate_cache.clear()
    m._top_cache.clear()


def test_concurrent_db_transactions_are_serialized():
    async def run():
        db = await _init()
        try:
            await db.execute("UPDATE players SET coins = 0 WHERE user_id = 1")
            await db.commit()

            async def worker():
                async with m.db_transaction():
                    await db.execute(
                        "UPDATE players SET coins = coins + 1 "
                        "WHERE user_id = 1"
                    )

            await asyncio.gather(*(worker() for _ in range(50)))
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 1"
            ) as cursor:
                assert (await cursor.fetchone())[0] == 50
        finally:
            await _close(db)

    asyncio.run(run())


def test_concurrent_equal_auction_bids_only_one_wins():
    async def run():
        db = await _init()
        try:
            end_time = (
                datetime.datetime.now() + datetime.timedelta(hours=1)
            ).isoformat()
            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, stars, start_price, current_bid, "
                "current_bidder, end_time, status) "
                "VALUES (1, 3, 'basic_gen', 0, 100, 100, NULL, ?, 'active')",
                (end_time,),
            )
            await db.commit()

            results = await asyncio.gather(
                m.place_auction_bid(1, 1, 150),
                m.place_auction_bid(2, 1, 150),
            )
            winners = [
                (user_id, result)
                for user_id, result in zip((1, 2), results)
                if result[0]
            ]
            assert len(winners) == 1, results
            winner_id, _result = winners[0]
            loser_id = 2 if winner_id == 1 else 1

            async with db.execute(
                "SELECT current_bid, current_bidder, status "
                "FROM auctions WHERE id = 1"
            ) as cursor:
                assert await cursor.fetchone() == (150, winner_id, "active")

            async with db.execute(
                "SELECT coins FROM players WHERE user_id = ?", (winner_id,)
            ) as cursor:
                assert (await cursor.fetchone())[0] == 850
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = ?", (loser_id,)
            ) as cursor:
                assert (await cursor.fetchone())[0] == 1000

            async with db.execute(
                "SELECT COUNT(*) FROM auction_bids "
                "WHERE auction_id = 1 AND kind = 'bid'"
            ) as cursor:
                assert (await cursor.fetchone())[0] == 1
        finally:
            await _close(db)

    asyncio.run(run())


def test_concurrent_season_xp_respects_daily_cap():
    async def run():
        db = await _init()
        try:
            results = await asyncio.gather(
                *(m.add_season_xp(1, 25, action="daily") for _ in range(20))
            )
            total = sum(results)
            assert total <= m.SEASON_XP_ACTIONS["daily"]["daily"]
            assert total > 0

            async with db.execute(
                "SELECT xp FROM season_progress WHERE user_id = 1"
            ) as cursor:
                assert (await cursor.fetchone())[0] == total
            async with db.execute(
                "SELECT xp FROM season_xp_log "
                "WHERE user_id = 1 AND action = 'daily'"
            ) as cursor:
                assert (await cursor.fetchone())[0] == total
        finally:
            await _close(db)

    asyncio.run(run())
