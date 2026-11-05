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
    for key in ("offline", "sets", "season", "power", "buyout", "orders"):
        assert key in m.GUIDE_SECTIONS, key


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
            assert "46 500" in season.description
            assert "+100" in season.description

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


def test_start_coins_modal_default_is_20():
    modal = m.EditStartCoinsModal(1)
    assert modal.value.default == "20"
