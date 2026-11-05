import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_welcome_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.done = False

    def is_done(self):
        return self.done

    async def defer(self, *args, **kwargs):
        self.done = True


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name="Новичок",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.response = FakeResponse()
        self.embed = None
        self.view = None

    async def edit_original_response(self, embed=None, view=None, **kwargs):
        self.embed = embed
        self.view = view


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_welcome_embed_atmosphere_variant():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction()
            embed = await m.build_welcome_embed(interaction)
            assert "хранитель" in embed.title
            assert "Энергостанция проснулась" in embed.description
            names = [field.name for field in embed.fields]
            assert "🎯 Цель" in names
            assert any("Старт" in name for name in names)
            assert any("Совет" in name for name in names)
            assert "Экономика" not in names
            assert "PvP" not in names
            assert "Принять пост" in embed.footer.text
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_welcome_buttons_create_player():
    async def run():
        db = await _init()
        try:
            view = m.WelcomeView(1)
            labels = [
                child.label
                for child in view.children
                if isinstance(child, m.discord.ui.Button)
            ]
            assert labels == ["Принять пост", "Правила"]

            interaction = FakeInteraction()
            await view.btn_accept.callback(interaction)
            assert isinstance(interaction.view, m.MainMenuView)
            async with db.execute(
                "SELECT COUNT(*) FROM players WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 1

            interaction = FakeInteraction()
            await view.btn_rules.callback(interaction)
            assert isinstance(interaction.view, m.GuideView)
            async with db.execute(
                "SELECT COUNT(*) FROM players WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 1
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
