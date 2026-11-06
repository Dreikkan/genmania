import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_service_leftovers_test", BOT_PATH
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


async def _close(db):
    await db.close()
    m.bot.db = None
    m._DB_TX_OWNER = None


def test_transaction_helpers_and_status_formatting():
    async def run():
        db = await _init()
        try:
            m._DB_TX_OWNER = object()
            await m.commit_if_needed()
            await m.rollback_if_needed()
            assert m.status_rank("bad") == -1
            assert m.status_rank("vip") >= 0
            assert m.format_status_expiry(None) == "бессрочно"
            assert m.format_status_expiry("bad") == "bad"
        finally:
            await _close(db)

    asyncio.run(run())


def test_giveaway_scope_validation_and_join_edges():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 0), (2, 0)"
            )
            now = datetime.datetime.now()
            await db.executemany(
                "INSERT INTO giveaways "
                "(id, guild_id, creator_id, title, reward_type, reward_id, "
                "amount, winners_count, status, ends_at, scope) "
                "VALUES (?, ?, ?, 'G', 'coins', NULL, 1, 1, ?, ?, ?)",
                [
                    (1, 1, 2, "finished", now.isoformat(), "server"),
                    (
                        2,
                        1,
                        2,
                        "active",
                        (now - datetime.timedelta(hours=1)).isoformat(),
                        "server",
                    ),
                    (
                        3,
                        None,
                        2,
                        "active",
                        (now + datetime.timedelta(hours=1)).isoformat(),
                        "global",
                    ),
                    (4, None, 2, "active", "bad", "global"),
                ],
            )
            await db.commit()

            assert m.giveaway_scope(None) == "server"
            assert m.giveaway_scope((1,)) == "server"
            assert await m.giveaway_validate_reward("catalysts", None, 0)
            assert await m.giveaway_validate_reward("generator", "basic_gen", 0)
            assert await m.giveaway_validate_reward("pet", "bad", 1)
            assert await m.giveaway_validate_reward("pet_level", "cat", 0)

            ok, message = await m.join_giveaway(1, 1, 1)
            assert not ok and "завершён" in message
            ok, message = await m.join_giveaway(2, 1, 1)
            assert not ok and "истекло" in message
            ok, message = await m.join_giveaway(3, 1, None)
            assert not ok and "сервере" in message
            await m.join_giveaway(4, 1, 1)
        finally:
            await _close(db)

    asyncio.run(run())


def test_market_cancel_clan_apply_bank_and_raids():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, ?)",
                [(1, 1000), (2, 1000), (3, 1000), (4, 1000)],
            )
            now = (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat()
            await db.executemany(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, price, quantity, filled, "
                "status, expires_at) VALUES (?, ?, 'sell', 'basic_gen', 13, ?, ?, ?, ?)",
                [
                    (1, 1, 1, 0, "active", now),
                    (2, 2, 1, 0, "active", now),
                    (3, 1, 1, 0, "closed", now),
                    (4, 1, 1, 1, "active", now),
                ],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 2, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (2, 1, 'leader')"
            )
            await db.execute(
                "INSERT INTO bank_loans "
                "(user_id, amount, interest_rate, due_time, collateral_item, "
                "collateral_stars, status) "
                "VALUES (3, 100, 0.1, ?, 'basic_gen', 0, 'active')",
                ((datetime.datetime.now() + datetime.timedelta(days=1)).isoformat(),),
            )
            await db.execute(
                "INSERT INTO raid_parties "
                "(id, leader_id, member2_id, member3_id) "
                "VALUES (1, 1, 2, 3), (2, 1, 4, NULL), (3, 1, 2, 3)"
            )
            await db.commit()

            ok, message = await m.cancel_market_order(999, 1)
            assert not ok and "не найден" in message
            ok, message = await m.cancel_market_order(1, 2)
            assert not ok and "твой" in message
            ok, message = await m.cancel_market_order(3, 1)
            assert not ok and "закрыт" in message
            ok, message = await m.cancel_market_order(4, 1)
            assert not ok and "исполнен" in message
            ok, message = await m.cancel_market_order(1, 1)
            assert ok

            ok, message = await m.apply_to_clan(2, 1)
            assert not ok and "уже" in message
            ok, message = await m.apply_to_clan(1, 999)
            assert not ok and "не существует" in message
            ok, message = await m.apply_to_clan(1, 1)
            assert ok

            ok, message = await m.repay_bank_loan(1)
            assert not ok and "нет активного" in message
            ok, message = await m.repay_bank_loan(3)
            assert ok

            try:
                await m.join_raid_party(1, 4)
            except ValueError as exc:
                assert "укомплектован" in str(exc)

            try:
                await m.join_raid_party(2, 3)
            except ValueError as exc:
                assert "другом" in str(exc)

            status = await m.detach_user_from_raid_party(3)
            assert status == "left"
        finally:
            await _close(db)

    asyncio.run(run())
