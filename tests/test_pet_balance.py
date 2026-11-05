import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_pet_balance_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems, active_pet) "
        "VALUES (1, 1000, 100, 'dog')"
    )
    await db.execute(
        "INSERT INTO user_pets_v2 (user_id, pet_id, level, last_fed) "
        "VALUES (1, 'dog', 10, NULL)"
    )
    await db.commit()
    return db


def test_pet_effect_entries_include_secondary_effect():
    dog = m.get_pet_effect_entries(m.PET_TYPES["dog"])
    assert dog == [("craft_chance", 0.02), ("income_coins", 0.01)]

    phoenix = m.get_pet_effect_entries(m.PET_TYPES["phoenix"])
    assert phoenix == [("income_gems", 0.025), ("income_coins", 0.01)]

    cat = m.get_pet_effect_entries(m.PET_TYPES["cat"])
    assert cat == [("income_coins", 0.015)]


def test_pet_balance_values():
    max_level = m.PET_MAX_LEVEL
    cat_coin = m.PET_TYPES["cat"]["per_level"] * max_level
    dog_craft = m.PET_TYPES["dog"]["per_level"] * max_level
    dog_coin = m.PET_TYPES["dog"]["extra_effects"]["income_coins"] * max_level
    phoenix_gem = m.PET_TYPES["phoenix"]["per_level"] * max_level
    phoenix_coin = (
        m.PET_TYPES["phoenix"]["extra_effects"]["income_coins"] * max_level
    )

    assert cat_coin == 0.15
    assert dog_craft == 0.20
    assert dog_coin == 0.10
    assert phoenix_gem == 0.25
    assert phoenix_coin == 0.10
    assert dog_coin < cat_coin
    assert phoenix_coin < cat_coin
    assert m.PET_TYPES["dragon"]["per_level"] * max_level == 0.40
    assert m.PET_TYPES["wolf"]["per_level"] * max_level == 0.20


def test_get_pet_bonus_sums_primary_and_secondary():
    async def run():
        db = await _init()
        try:
            assert await m.get_pet_bonus(1, "craft_chance") == 0.20
            assert await m.get_pet_bonus(1, "income_coins") == 0.10
            assert await m.get_pet_bonus(1, "income_gems") == 0.0
            assert await m.get_pet_bonus(1, "combat_power") == 0.0

            await db.execute(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level, last_fed) "
                "VALUES (1, 'phoenix', 4, NULL)"
            )
            await db.execute(
                "UPDATE players SET active_pet = 'phoenix' WHERE user_id = 1"
            )
            await db.commit()

            assert await m.get_pet_bonus(1, "income_gems") == 0.10
            assert await m.get_pet_bonus(1, "income_coins") == 0.04
            assert await m.get_pet_bonus(1, "craft_chance") == 0.0
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_pet_embed_shows_both_effects():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "UPDATE user_pets_v2 SET level = 3 "
                "WHERE user_id = 1 AND pet_id = 'dog'"
            )
            await db.commit()
            interaction = SimpleNamespace(user=SimpleNamespace(id=1))
            embed = await m.build_pets_embed(interaction)
            dog_field = next(
                field for field in embed.fields if "Пёс" in field.name
            )
            assert "шанс синтеза" in dog_field.value
            assert "доход монет" in dog_field.value
            assert "+6%" in dog_field.value
            assert "+3%" in dog_field.value
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_pet_guide_values_match_rework():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        await m.bot.init_db()
        try:
            embed = await m.build_guide_section_embed("pets")
            pets_text = embed.description
            assert "+15% доход монет" in pets_text
            assert "+20% шанс синтеза" in pets_text
            assert "+25% доход гемов" in pets_text
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
