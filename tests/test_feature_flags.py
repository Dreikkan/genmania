import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_feature_flags_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.done = False
        self.messages = []

    def is_done(self):
        return self.done

    async def send_message(self, text=None, **kwargs):
        self.messages.append((text, kwargs))
        self.done = True


class FakeInteraction:
    def __init__(self, user_id=1, guild_id=1):
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = guild_id
        self.message = SimpleNamespace()
        self.response = FakeResponse()


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute("INSERT INTO players (user_id, coins) VALUES (1, 100)")
    await db.commit()
    return db


def test_toggleable_commands_cover_core_features():
    required = {
        "shop", "upgrades", "achievements", "quests", "storage", "stats",
        "market", "auction", "bank", "pvp", "clans", "craft", "stars",
        "daily", "exchange", "prestige", "pets", "autocollector",
    }
    assert required.issubset(m.TOGGLEABLE_COMMANDS.keys())


def test_disabled_feature_blocks_market_and_pvp():
    async def run():
        db = await _init()
        try:
            await m.save_setting(
                1, "disabled_commands", ["market", "pvp"], actor_id=1
            )
            assert await m.is_command_disabled(1, "market") is True
            assert await m.is_command_disabled(1, "shop") is False

            market = m.MarketView(1, total_pages=1)
            interaction = FakeInteraction(1)
            assert await market.interaction_check(interaction) is False
            assert interaction.response.messages
            assert "отключена" in interaction.response.messages[0][0]

            pvp = m.PvPHubView(1)
            interaction2 = FakeInteraction(1)
            assert await pvp.interaction_check(interaction2) is False

            shop = m.ShopHubView(1)
            interaction3 = FakeInteraction(1)
            assert await shop.interaction_check(interaction3) is True
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_enabled_feature_allows_view():
    async def run():
        db = await _init()
        try:
            await m.save_setting(1, "disabled_commands", [], actor_id=1)
            view = m.MarketView(1, total_pages=1)
            interaction = FakeInteraction(1)
            assert await view.interaction_check(interaction) is True
            assert not interaction.response.messages
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_settings_commands_view_lists_features():
    view = m.SettingsCommandsView(1, [])
    select = next(
        child for child in view.children
        if isinstance(child, m.discord.ui.Select)
    )
    values = {option.value for option in select.options}
    assert "market" in values
    assert "pvp" in values
    assert "bank" in values
    assert "craft" in values
