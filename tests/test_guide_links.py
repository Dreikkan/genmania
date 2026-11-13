import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_guide_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_guide_has_new_sections():
    for key in ("economy", "sets", "season", "power", "orders"):
        assert key in m.GUIDE_SECTIONS, key
    # Дублирующие разделы объединены: офлайн — в «Экономике»,
    # buyout — в «Аукционе».
    assert "offline" not in m.GUIDE_SECTIONS
    assert "buyout" not in m.GUIDE_SECTIONS


def test_guide_paths_and_units():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        await m.bot.init_db()
        try:
            economy = await m.build_guide_section_embed("economy")
            assert "Обмен валют" in economy.description
            assert "Мой профиль" not in economy.description

            autocollector = await m.build_guide_section_embed("autocollector")
            assert "100%" in autocollector.description
            assert "Мой профиль" not in autocollector.description

            sets = await m.build_guide_section_embed("sets")
            assert "Состав сетов" in sets.description
            assert "Металлы" in sets.description

            season = await m.build_guide_section_embed("season")
            assert "Синтез: +50" in season.description
            assert "Дневные лимиты" in season.description
            assert "Сюжетный квест: +200" in season.description
            assert "48 150" in season.description
            assert "+90" in season.description

            power = await m.build_guide_section_embed("power")
            assert "0.5 × звёзды" in power.description
            assert "Базовый генератор" in power.description

            for key in m.GUIDE_SECTIONS:
                embed = await m.build_guide_section_embed(key)
                assert embed.title and embed.description, key
                assert "/сек" not in embed.description, key
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_guide_reflects_latest_economy():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        await m.bot.init_db()
        try:
            economy = (await m._guide_section_data("economy"))[1]
            assert "500K" in economy
            assert "10%" in economy
            assert "5%" in economy
            assert "1 000" in economy or "1K" in economy
            assert "500 гемов" in economy

            generators = (await m._guide_section_data("generators"))[1]
            assert "×2.8" in generators
            assert "×2.2" in generators
            assert "×3.8" in generators
            assert "×3" in generators
            assert "10 💎/ч" in generators
            assert "20 💎/ч" in generators
            assert "40 💎/ч" in generators
            assert "2 одинаковых" in generators
            assert "5★ +400%" in generators

            orders = (await m._guide_section_data("orders"))[1]
            assert "72 ч" in orders
            assert "1Qi" in orders
            assert "5Qi" in orders
            assert "100 предметов" in orders

            pets = (await m._guide_section_data("pets"))[1]
            assert "19 эффективных уровней" in pets

            prestige = (await m._guide_section_data("prestige"))[1]
            assert "максимум +500%" in prestige

            collection = (await m._guide_section_data("collection"))[1]
            assert "максимум +15%" in collection

            season = (await m._guide_section_data("season"))[1]
            assert "150 💎" in season
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_start_coins_modal_default_is_8():
    modal = m.EditStartCoinsModal(1)
    assert modal.value.default == "8"
