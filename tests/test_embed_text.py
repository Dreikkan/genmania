import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_embed_text_test", BOT_PATH)
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


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute("INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 100)")
    await db.execute(
        "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
        "VALUES (1, 0, 'basic_gen', 'profile', 0)"
    )
    await db.commit()
    return db


def _embed_text(embed) -> str:
    parts = [embed.title or "", embed.description or ""]
    for field in embed.fields:
        parts.append(field.name or "")
        parts.append(field.value or "")
    return "\n".join(parts)


def test_income_hint_is_not_duplicated_in_one_embed():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(1)
            main = await m.build_main_embed(interaction)
            assert _embed_text(main).count(m.INCOME_HINT) == 1

            profile = await m.build_profile_embed(interaction)
            assert _embed_text(profile).count(m.INCOME_HINT) == 1

            details, _ = await m.build_generator_details_embed(interaction)
            assert _embed_text(details).count(m.INCOME_HINT) == 1

            shop, _ = await m.build_shop_page(interaction, 0)
            assert _embed_text(shop).count(m.INCOME_HINT) == 1
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_guide_text_matches_current_mechanics():
    async def run():
        db = await _init()
        try:
            economy = (await m._guide_section_data("economy"))[1]
            assert "70% текущей цены" in economy
            assert "с комиссией" not in economy

            prestige = (await m._guide_section_data("prestige"))[1]
            assert "активные временные статусы" in prestige

            auction = (await m._guide_section_data("auction"))[1]
            assert "кроме synthesis-only" in auction

            orders = (await m._guide_section_data("orders"))[1]
            assert "исполнение частичное" in orders
            assert "исполняется полностью" not in orders

            notifications = (await m._guide_section_data("notifications"))[1]
            assert "аукцион — 1 ч" in notifications
            assert "24 ч на каждый тип" not in notifications
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
