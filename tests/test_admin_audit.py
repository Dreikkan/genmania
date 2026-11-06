import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_admin_audit_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_admin_log_has_guild_and_setting_audit():
    async def run():
        db = await _init()
        token_guild = m._CURRENT_GUILD_ID.set(77)
        token_actor = m._CURRENT_ACTOR_ID.set(1)
        try:
            await m.log_admin_action(1, 2, "test_action", "details")
            async with db.execute(
                "SELECT guild_id, action FROM admin_log ORDER BY id DESC LIMIT 1"
            ) as c:
                assert await c.fetchone() == (77, "test_action")

            await m.save_setting(77, "tax_rate", 0.03)
            async with db.execute(
                "SELECT guild_id, action, details FROM admin_log "
                "WHERE action = 'setting_change' ORDER BY id DESC LIMIT 1"
            ) as c:
                row = await c.fetchone()
            assert row and row[0] == 77, row
            assert "tax_rate=0.03" in row[2], row

            rows, total, page, total_pages = await m.get_admin_logs_page(
                77, 0, 10
            )
            assert total >= 2
            assert page == 0 and total_pages >= 1
            assert rows and rows[0][2] == "setting_change"
        finally:
            m._CURRENT_GUILD_ID.reset(token_guild)
            m._CURRENT_ACTOR_ID.reset(token_actor)
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_admin_logs_pagination_and_global_fallback():
    async def run():
        db = await _init()
        try:
            for target_id in range(15):
                await m.log_admin_action(
                    1, target_id, "bulk_action", "", guild_id=None
                )

            rows, total, page, total_pages = await m.get_admin_logs_page(
                None, 99, 10
            )
            assert total == 15
            assert total_pages == 2
            assert page == 1
            assert len(rows) == 5

            first_rows, _, first_page, _ = await m.get_admin_logs_page(
                None, -5, 10
            )
            assert first_page == 0
            assert len(first_rows) == 10
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_admin_indexes_exist():
    async def run():
        db = await _init()
        try:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ) as c:
                names = {row[0] for row in await c.fetchall()}
            for name in (
                "idx_players_coins",
                "idx_players_gems",
                "idx_bank_loans_status_due",
                "idx_clan_invites_target",
                "idx_raid_parties_member2",
                "idx_raid_parties_member3",
                "idx_admin_log_guild",
            ):
                assert name in names, name
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_retention_limits_cover_main_logs():
    assert set(m.RETENTION_LIMITS) == {
        "craft_log",
        "tax_log",
        "admin_log",
        "bank_history",
        "duel_history",
        "raid_loot_log",
        "season_xp_log",
    }
