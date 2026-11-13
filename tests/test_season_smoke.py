import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_season_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

SCHEMA = """
CREATE TABLE players (
    user_id INTEGER PRIMARY KEY,
    coins INTEGER DEFAULT 0,
    gems INTEGER DEFAULT 0,
    catalysts INTEGER DEFAULT 0,
    total_coins_earned INTEGER DEFAULT 0,
    total_gems_earned INTEGER DEFAULT 0,
    lifetime_production INTEGER DEFAULT 0
);
CREATE TABLE season_progress (
    user_id INTEGER,
    season_id TEXT,
    xp INTEGER DEFAULT 0,
    premium INTEGER DEFAULT 0,
    claimed_free TEXT DEFAULT '[]',
    claimed_premium TEXT DEFAULT '[]',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, season_id)
);
CREATE TABLE season_xp_log (
    user_id INTEGER,
    season_id TEXT,
    day TEXT,
    action TEXT,
    xp INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, season_id, day, action)
);
"""


async def main():
    db = await aiosqlite.connect(":memory:")
    try:
        await run_checks(db)
    finally:
        await db.close()


async def run_checks(db):
    await db.executescript(SCHEMA)
    await db.execute(
        "INSERT INTO players (user_id, coins, gems) VALUES (1, 0, 500)"
    )
    await db.commit()
    m.bot.db = db

    async def noop_achievements(user_id):
        return []

    m.check_achievements = noop_achievements

    # Формулы уровней: 300, 390, 480...
    assert m.season_xp_for_next_level(0) == 300
    assert m.season_xp_for_next_level(1) == 390
    assert m.season_level_from_xp(0) == (0, 0)
    assert m.season_level_from_xp(300) == (1, 0)
    assert m.season_level_from_xp(690) == (2, 0)

    data = await m.get_season_data(1)
    assert data["level"] == 0
    assert data["premium"] is False
    assert data["claimable_free"] == []

    # Первый уровень.
    expected = int(round(300 * m.season_event_multiplier()))
    gained = await m.add_season_xp(1, 300, action="prestige")
    assert gained == expected
    data = await m.get_season_data(1)
    assert data["level"] == 1, data
    assert data["claimable_free"] == [1], data

    # Бесплатная награда.
    ok, msg, totals = await m.claim_season_rewards(1)
    assert ok, msg
    assert totals["levels"] >= 1
    data = await m.get_season_data(1)
    assert data["claimable_free"] == []
    async with db.execute("SELECT coins, gems FROM players WHERE user_id = 1") as c:
        coins, gems = await c.fetchone()
    assert coins >= 150, (coins, gems)
    assert gems == 500, gems  # на 1 уровне бесплатная награда только монеты

    # Повторно забирать нечего.
    ok, msg, _ = await m.claim_season_rewards(1)
    assert not ok and "Нет наград" in msg, (ok, msg)

    # Покупка премиума.
    ok, msg = await m.buy_season_premium(1)
    assert ok, msg
    data = await m.get_season_data(1)
    assert data["premium"] is True
    assert data["claimable_premium"] == [1], data
    async with db.execute("SELECT gems FROM players WHERE user_id = 1") as c:
        gems = (await c.fetchone())[0]
    assert gems == 500 - m.SEASON_PREMIUM_COST_GEMS, gems

    # Премиум-награда.
    ok, msg, totals = await m.claim_season_rewards(1)
    assert ok, msg
    assert totals["levels"] >= 1
    data = await m.get_season_data(1)
    assert data["claimable_premium"] == []
    async with db.execute("SELECT coins, gems FROM players WHERE user_id = 1") as c:
        coins, gems = await c.fetchone()
    assert coins >= 300
    assert gems > 250

    # Дневной лимит действия и стоимость следующего уровня.
    daily_amount = m.SEASON_XP_ACTIONS["daily"]["amount"]
    assert await m.add_season_xp(1, daily_amount, action="daily") == daily_amount
    assert await m.add_season_xp(1, daily_amount, action="daily") == 0
    await db.execute(
        "UPDATE season_progress SET xp = 690 WHERE user_id = 1"
    )
    await db.commit()
    data = await m.get_season_data(1)
    assert data["level"] == 2, data
    assert data["needed"] == 480, data

    # Лимит на одно начисление: story_quest не больше per_tx.
    story = m.SEASON_XP_ACTIONS["story_quest"]
    expected = min(
        int(round(story["per_tx"] * m.season_event_multiplier())),
        story["daily"],
    )
    assert await m.add_season_xp(1, 999, action="story_quest") == expected

    # Покупка премиума дважды запрещена.
    ok, msg = await m.buy_season_premium(1)
    assert not ok and "уже активен" in msg, (ok, msg)

    # Экран сезона собирается.
    embed, data = await m.build_season_embed(1)
    assert "Сезон" in embed.title
    assert len(embed.fields) >= 4
    assert "Прогресс" in [field.name for field in embed.fields]

    print("SEASON SMOKE TEST: OK")


def test_smoke():
    asyncio.run(main())


def test_battle_pass_reachable_for_active_player():
    total_needed = sum(
        m.season_xp_for_next_level(level) for level in range(m.SEASON_LEVELS)
    )
    assert total_needed == m.SEASON_TOTAL_XP == 48150
    assert m.SEASON_TOTAL_XP_TEXT == "48 150"

    # Теоретический потолок дневных лимитов должен давать запас.
    daily_caps = sum(
        config["daily"]
        for action, config in m.SEASON_XP_ACTIONS.items()
        if action != "other"
    )
    assert daily_caps * 30 >= total_needed * 1.10

    # Реалистичный активный день должен закрывать 30 уровней за 30 дней.
    expected_daily = m.season_expected_daily_xp()
    assert expected_daily >= total_needed // 30
    assert expected_daily * 30 >= total_needed
    assert m.season_level_from_xp(expected_daily * 30)[0] == m.SEASON_LEVELS


def test_season_level_30_reward_is_capped():
    free = m.season_reward(30)
    assert free == {"coins": 1800, "gems": 11, "catalysts": 1}

    premium = m.season_reward(30, premium=True)
    assert premium["coins"] == 1800
    assert premium["gems"] == 13
    assert premium["catalysts"] == 1

    coins = [m.season_reward(level)["coins"] for level in range(1, 31)]
    assert coins == sorted(coins)
    assert m.season_reward(1)["coins"] == 205
