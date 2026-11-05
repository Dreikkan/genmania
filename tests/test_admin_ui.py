import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_admin_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def run_checks(db):
    await m.bot.init_db()
    guild_id = 1
    user_id = 42
    await db.execute(
        "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,)
    )
    await db.execute(
        "INSERT OR IGNORE INTO players (user_id, coins) VALUES (?, ?)",
        (user_id, 20),
    )
    await db.commit()

    settings = await m.get_settings(guild_id)
    assert settings["battlepass_enabled"] is True

    original_multiplier = m.SEASON_WEEKEND_XP_MULT
    m.SEASON_WEEKEND_XP_MULT = 1.0
    try:
        await m.save_setting(guild_id, "battlepass_enabled", 0)
        settings = await m.get_settings(guild_id)
        assert settings["battlepass_enabled"] is False

        season_view = m.AdminSeasonView(user_id, False)
        assert season_view.btn_toggle.label == "Включить баттлпасс"
        assert len(season_view.children) <= 25

        market_view = m.AdminMarketView(user_id)
        prestige_view = m.AdminPrestigeView(user_id)
        assert len(market_view.children) <= 25
        assert len(prestige_view.children) <= 25

        embed = await m.build_admin_market_embed()
        assert "Управление биржей" in embed.title

        # При выключенном баттлпасе XP не начисляется.
        gained = await m.add_season_xp(user_id, 100, guild_id)
        assert gained == 0, gained

        await m.save_setting(guild_id, "battlepass_enabled", 1)
        gained = await m.add_season_xp(user_id, 100, guild_id)
        assert gained == 100, gained

        async with db.execute(
            "SELECT xp FROM season_progress WHERE user_id = ?", (user_id,)
        ) as c:
            assert (await c.fetchone())[0] == 100
    finally:
        m.SEASON_WEEKEND_XP_MULT = original_multiplier

    print("ADMIN UI TEST: OK")


async def main():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    try:
        await run_checks(db)
    finally:
        await db.close()
        m.bot.db = None


def test_admin_ui_and_battlepass():
    asyncio.run(main())
