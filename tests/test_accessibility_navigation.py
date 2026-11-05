import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_accessibility_nav_test", BOT_PATH)
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

    async def send_message(self, *args, **kwargs):
        self.done = True


class FakeInteraction:
    def __init__(self, user_id=1, guild_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = guild_id
        self.response = FakeResponse()
        self.message = SimpleNamespace()
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


def _flatten_embed(embed) -> str:
    parts = [embed.description or ""]
    parts.extend(field.value or "" for field in embed.fields)
    return "\n".join(parts)


def test_accessibility_mode_toggle_persists():
    async def run():
        db = await _init()
        try:
            assert await m.is_accessibility_mode(1) is False
            assert await m.toggle_accessibility_mode(1) is True
            assert await m.is_accessibility_mode(1) is True

            async with db.execute(
                "SELECT accessibility_mode FROM players WHERE user_id = 1"
            ) as c:
                row = await c.fetchone()
            assert row[0] == 1

            assert await m.toggle_accessibility_mode(1) is False
            assert await m.is_accessibility_mode(1) is False
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_compact_profile_hides_avatar_and_hint():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(1)
            normal = await m.build_profile_embed(interaction)
            assert normal.thumbnail.url is not None
            assert m.INCOME_HINT in _flatten_embed(normal)

            await m.toggle_accessibility_mode(1)
            compact = await m.build_profile_embed(interaction)
            assert compact.thumbnail.url is None
            assert m.INCOME_HINT not in _flatten_embed(compact)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_compact_user_profile_hides_avatar():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(1)
            normal = await m.build_user_profile_embed(interaction)
            assert normal.thumbnail.url is not None

            await m.toggle_accessibility_mode(1)
            compact = await m.build_user_profile_embed(interaction)
            assert compact.thumbnail.url is None
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_nav_stack_push_pop_and_limit():
    m.reset_nav(1)
    m.push_nav(1, "main")
    m.push_nav(1, "social", tab="clans")
    m.push_nav(1, "social", tab="other")

    route, params = m.pop_nav(1)
    assert (route, params) == ("social", {"tab": "clans"})
    route, params = m.pop_nav(1)
    assert (route, params) == ("main", {})
    assert m.pop_nav(1, "profile") == ("profile", {})

    for index in range(m.NAV_STACK_LIMIT + 5):
        m.push_nav(1, f"route{index}")
    assert len(m.NAV_STACKS[1]) == m.NAV_STACK_LIMIT
    assert m.NAV_STACKS[1][-1][0] == f"route{m.NAV_STACK_LIMIT + 4}"
    m.reset_nav(1)
    assert 1 not in m.NAV_STACKS


def test_go_back_restores_previous_view():
    async def run():
        db = await _init()
        try:
            m.reset_nav(1)
            m.push_nav(1, "social")
            interaction = FakeInteraction(1)
            await m.go_back(interaction, 1, fallback="main")
            assert isinstance(interaction.view, m.SocialView), type(interaction.view)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_go_back_uses_fallback_when_stack_empty():
    async def run():
        db = await _init()
        try:
            m.reset_nav(1)
            interaction = FakeInteraction(1)
            await m.go_back(interaction, 1, fallback="social")
            assert isinstance(interaction.view, m.SocialView), type(interaction.view)

            m.reset_nav(1)
            interaction = FakeInteraction(1)
            await m.go_back(interaction, 1, fallback="main")
            assert isinstance(interaction.view, m.MainMenuView), type(interaction.view)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_settings_view_has_accessibility_button():
    view = m.UserSettingsView(1)
    labels = [child.label for child in view.children]
    assert "Доступность" in labels


def test_settings_accessibility_button_toggles_mode():
    async def run():
        db = await _init()
        try:
            view = m.UserSettingsView(1)
            button = next(
                child for child in view.children if child.label == "Доступность"
            )
            interaction = FakeInteraction(1)
            await button.callback(interaction)
            assert await m.is_accessibility_mode(1) is True
            assert isinstance(interaction.view, m.UserSettingsView)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
