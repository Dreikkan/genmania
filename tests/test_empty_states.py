import asyncio
import importlib.util
import json
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_empty_states_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1

    async def edit_original_response(self, *args, **kwargs):
        return None


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute("INSERT INTO players (user_id, coins, gems) VALUES (1, 100, 10)")
    await db.commit()
    return db


def test_main_menu_cta_when_no_generators():
    async def run():
        db = await _init()
        try:
            embed = await m.build_main_embed(FakeInteraction(1))
            income = next(f for f in embed.fields if f.name == "Доход")
            assert "купи первый" in income.value.lower(), income.value
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_empty_storage_cta():
    async def run():
        db = await _init()
        try:
            embed = await m.build_storage_embed(FakeInteraction(1))
            assert "Хранилище пусто" in embed.description, embed.description
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_empty_temp_storage_cta():
    async def run():
        db = await _init()
        try:
            embed = await m.build_temp_storage_embed(FakeInteraction(1))
            assert "Временное хранилище пусто" in embed.description
            assert f"0/{m.TEMP_STORAGE_SIZE}" in embed.description
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_shop_shows_balance_and_page_total():
    async def run():
        db = await _init()
        try:
            embed, _pages = await m.build_shop_page(FakeInteraction(1), 0)
            assert "Баланс" in embed.description, embed.description
            assert "Стоимость всей страницы" in embed.description, embed.description
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_quests_all_claimed_message():
    async def run():
        db = await _init()
        try:
            quests, _progress, _claimed = await m.get_or_create_daily_quests(1)
            await db.execute(
                "UPDATE players SET daily_quest_claimed = ? WHERE user_id = 1",
                (json.dumps(quests),),
            )
            await db.commit()
            embed = await m.build_quests_embed(FakeInteraction(1))
            assert "Все награды" in embed.description, embed.description
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
