import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_navigation_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    async def defer(self, *args, **kwargs):
        return None


class FakeInteraction:
    def __init__(self, user_id):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.response = FakeResponse()
        self.message = None
        self.embed = None
        self.view = None

    async def edit_original_response(self, embed=None, view=None, **kwargs):
        self.embed = embed
        self.view = view


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute("INSERT INTO players (user_id, coins, gems) VALUES (1, 100, 10)")
    await db.commit()
    return db


def test_story_quests_back_to_quests_hub():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(1)
            view = m.StoryQuestsView(1, return_to="quests")
            await view.back.callback(interaction)
            assert isinstance(interaction.view, m.QuestsHubView), type(interaction.view)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_pets_shop_back_keeps_profile_route():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(1)
            options = [m.discord.SelectOption(label="Кот", value="cat")]
            view = m.PetsShopView(1, options, return_to="profile")
            await view.back(interaction)
            assert isinstance(interaction.view, m.PetsView), type(interaction.view)
            assert interaction.view.return_to == "profile"
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_raid_party_back_to_raid_menu():
    async def run():
        interaction = FakeInteraction(1)
        view = m.RaidPartyView(1, 1)
        await view.btn_back.callback(interaction)
        assert isinstance(interaction.view, m.RaidMenuView), type(interaction.view)

    asyncio.run(run())


def test_titles_back_to_profile():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(1)
            options = [m.discord.SelectOption(label="Новичок", value="novice")]
            view = m.TitlesView(1, options, 0, 1, return_to="profile")
            await view.back(interaction)
            assert isinstance(interaction.view, m.UserProfileView), type(interaction.view)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
