import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_nav_route_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.response = FakeResponse()
        self.embed = None
        self.view = None

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


def test_nav_routes_render_views():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) "
                "VALUES (1, 100, 10)"
            )
            await db.commit()

            routes = [
                "main",
                "social",
                "shop",
                "quests",
                "settings",
                "daily",
                "storage",
                "profile",
                "clans",
                "unknown",
            ]
            for route in routes:
                interaction = FakeInteraction(1)
                await m.open_nav_route(interaction, 1, route)
                assert interaction.embed is not None, route
                assert interaction.view is not None, route

            for route in ("market", "pvp", "bank", "season", "craft"):
                interaction = FakeInteraction(1)
                await m.open_nav_route(interaction, 1, route)
                assert interaction.embed is not None, route
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
