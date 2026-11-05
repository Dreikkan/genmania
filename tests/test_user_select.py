import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_user_select_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.sent = None
        self.done = False

    def is_done(self):
        return self.done

    async def send_message(self, text=None, **kwargs):
        self.sent = (text, kwargs)
        self.done = True


class FakeMember:
    def __init__(self, user_id, admin=False, roles=()):
        self.id = user_id
        self.guild_permissions = SimpleNamespace(administrator=admin)
        self.roles = list(roles)


class FakeGuild:
    def __init__(self, owner_id, member):
        self.owner_id = owner_id
        self.member = member

    def get_member(self, user_id):
        return self.member if self.member and self.member.id == user_id else None


class FakeInteraction:
    def __init__(self, user, guild=None, guild_id=1):
        self.user = user
        self.guild = guild
        self.guild_id = guild_id
        self.response = FakeResponse()
        self.message = SimpleNamespace()


def test_clan_and_duel_views_use_user_select():
    clan_view = m.ClanTargetSelectView(1, 2, "invite")
    duel_view = m.DuelTargetSelectView(1)
    admin_view = m.AdminPlayerSelectView(1)
    for view in (clan_view, duel_view, admin_view):
        assert any(
            isinstance(child, m.discord.ui.UserSelect)
            for child in view.children
        ), type(view)
        assert any(
            isinstance(child, m.discord.ui.Button)
            and child.label == "Ввести ID"
            for child in view.children
        ), type(view)


def test_admin_access_uses_rechecked_permissions():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        await m.bot.init_db()
        try:
            original = m.get_settings

            async def fake_settings(guild_id):
                return {"admin_role_id": None}

            m.get_settings = fake_settings
            try:
                admin = FakeMember(1, admin=True)
                guild = FakeGuild(99, admin)
                interaction = FakeInteraction(admin, guild=guild)
                assert await m.has_admin_access(interaction) is True

                normal = FakeMember(2, admin=False)
                guild2 = FakeGuild(99, normal)
                interaction2 = FakeInteraction(normal, guild=guild2)
                assert await m.has_admin_access(interaction2) is False

                view = m.AdminPanelView(2)
                allowed = await view.interaction_check(interaction2)
                assert allowed is False
                assert interaction2.response.sent is not None
            finally:
                m.get_settings = original
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
