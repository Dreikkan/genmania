import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_background_tasks_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._tax_rate_cache.clear()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _run_once(task, **patches):
    original_wait = m.bot.wait_until_ready
    original_closed = m.bot.is_closed
    original_sleep = m.asyncio.sleep
    state = {"closed": False}

    async def ready():
        return None

    def is_closed():
        if state["closed"]:
            return True
        state["closed"] = True
        return False

    async def no_sleep(*args, **kwargs):
        return None

    m.bot.wait_until_ready = ready
    m.bot.is_closed = is_closed
    m.asyncio.sleep = no_sleep
    originals = {}
    try:
        for name, value in patches.items():
            originals[name] = getattr(m, name)
            setattr(m, name, value)
        await task()
    finally:
        m.bot.wait_until_ready = original_wait
        m.bot.is_closed = original_closed
        m.asyncio.sleep = original_sleep
        for name, value in originals.items():
            setattr(m, name, value)


def test_tax_collector_charges_daily_tax():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, last_tax_time) "
                "VALUES (1, 1000, NULL)"
            )
            await db.commit()

            async def fake_rates():
                return {1: 0.10}

            await _run_once(
                m.bot.tax_collector, get_tax_rate_map=fake_rates
            )

            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 900
            async with db.execute(
                "SELECT amount FROM tax_log WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 100
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_autocollector_task_collects_income():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 0, 0)"
            )
            await db.execute(
                "INSERT INTO autocollectors (user_id, level, last_auto) "
                "VALUES (1, 1, NULL)"
            )
            await db.commit()

            async def fake_income(uid):
                return 100, 5

            async def noop(*args, **kwargs):
                return None

            await _run_once(
                m.bot.autocollector_task,
                calculate_full_passive_income=fake_income,
                update_quest_progress=noop,
                update_story_quests=noop,
                check_achievements=noop,
            )

            async with db.execute(
                "SELECT coins, gems FROM players WHERE user_id = 1"
            ) as c:
                assert await c.fetchone() == (100, 5)
            async with db.execute(
                "SELECT last_auto FROM autocollectors WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] is not None
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_war_closer_finishes_expired_war():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 0), (2, 'Beta', 2, 0)"
            )
            started = (
                datetime.datetime.now()
                - datetime.timedelta(
                    hours=m.CLAN_WAR_DURATION_HOURS + 1
                )
            ).isoformat()
            await db.execute(
                "INSERT INTO clan_wars "
                "(clan1_id, clan2_id, start_time, status, "
                " clan1_hp, clan2_hp, clan1_damage, clan2_damage) "
                "VALUES (1, 2, ?, 'active', 900, 500, 10, 5)",
                (started,),
            )
            await db.commit()

            async def noop(*args, **kwargs):
                return None

            await _run_once(
                m.bot.war_closer,
                log_clan=noop,
                update_clan_quest=noop,
                add_clan_xp=noop,
            )

            async with db.execute(
                "SELECT status, winner_id FROM clan_wars"
            ) as c:
                assert await c.fetchone() == ("finished", 1)
            async with db.execute(
                "SELECT treasury FROM clans WHERE id = 1"
            ) as c:
                assert (await c.fetchone())[0] == m.CLAN_WAR_REWARD
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_auction_closer_pays_seller_and_finishes():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 0), (2, 0)"
            )
            ended = (
                datetime.datetime.now() - datetime.timedelta(minutes=1)
            ).isoformat()
            await db.execute(
                "INSERT INTO auctions "
                "(seller_id, item_id, stars, current_bid, current_bidder, "
                " end_time, status) "
                "VALUES (1, 'basic_gen', 0, 100, 2, ?, 'active')",
                (ended,),
            )
            await db.commit()

            async def noop(*args, **kwargs):
                return None

            await _run_once(
                m.bot.auction_closer,
                grant_item_or_compensation=noop,
            )

            async with db.execute(
                "SELECT status FROM auctions"
            ) as c:
                assert (await c.fetchone())[0] == "finished"
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 95
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
