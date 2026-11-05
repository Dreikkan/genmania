import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_swap_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.edited = None

    async def defer(self):
        self.deferred = True

    async def edit_original_response(self, embed=None, view=None):
        self.edited = {"embed": embed, "view": view}


class FakeInteraction:
    def __init__(self, user_id=1, guild_id=1, values=None):
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = guild_id
        self.data = {"values": values or []}
        self.response = FakeResponse()
        self.message = None

    async def edit_original_response(self, **kwargs):
        self.response.edited = kwargs


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, grid_size) VALUES (1, 100, 9)"
    )
    await db.execute(
        "INSERT INTO inventory (user_id, slot, item_id, location, stars, is_locked) "
        "VALUES (1, 0, 'basic_gen', 'profile', 0, 0)"
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._DB_TX_OWNER = None
    m._settings_cache.clear()


def test_swap_second_page_offers_empty_slots():
    async def run():
        db = await _init()
        try:
            embed, view, error = await m._build_swap_second_page(
                "profile", 1, 0, 1
            )
            assert not error
            assert "пустой" in embed.description
            select = next(
                child for child in view.children
                if isinstance(child, m.discord.ui.Select)
            )
            values = [option.value for option in select.options]
            labels = [option.label for option in select.options]
            assert "1" in values
            assert "0" not in values
            assert any("пусто" in label for label in labels)
        finally:
            await _close(db)

    asyncio.run(run())


def test_swap_moves_item_into_empty_slot():
    async def run():
        db = await _init()
        try:
            embed, view, error = await m._build_swap_second_page(
                "profile", 1, 0, 1
            )
            assert not error
            interaction = FakeInteraction(values=["1"])
            await view.second_select(interaction)
            assert interaction.response.deferred
            assert interaction.response.edited is not None
            assert "перемещён" in interaction.response.edited["embed"].description

            async with db.execute(
                "SELECT slot FROM inventory WHERE user_id = 1 "
                "AND location = 'profile' AND item_id = 'basic_gen'"
            ) as c:
                slots = [row[0] for row in await c.fetchall()]
            assert slots == [1]
        finally:
            await _close(db)

    asyncio.run(run())
