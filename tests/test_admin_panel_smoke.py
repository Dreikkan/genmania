import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_admin_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.messages = []
        self.done = False

    def is_done(self):
        return self.done

    async def send_message(self, content=None, embed=None, view=None, ephemeral=False):
        self.done = True
        self.messages.append(
            {"content": content, "embed": embed, "view": view, "ephemeral": ephemeral}
        )


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
    def __init__(self, user, guild=None, guild_id=None):
        self.user = user
        self.guild = guild
        self.guild_id = guild_id
        self.response = FakeResponse()


async def fake_settings(guild_id):
    return {"admin_role_id": None}


async def main():
    m.get_settings = fake_settings

    # 1. ЛС: User без guild_permissions не должен ронять команду.
    dm_user = SimpleNamespace(id=10)
    dm = FakeInteraction(dm_user)
    await m.admin_panel.callback(dm)
    assert dm.response.messages
    assert "только на сервере" in dm.response.messages[-1]["content"]

    # 2. Обычный участник сервера получает отказ.
    user = FakeMember(20, admin=False)
    guild = FakeGuild(owner_id=99, member=user)
    normal = FakeInteraction(user, guild=guild, guild_id=1)
    await m.admin_panel.callback(normal)
    assert normal.response.messages
    assert "нет доступа" in normal.response.messages[-1]["content"]

    # 3. Администратор получает панель.
    admin_user = FakeMember(30, admin=True)
    admin_guild = FakeGuild(owner_id=99, member=admin_user)
    admin = FakeInteraction(admin_user, guild=admin_guild, guild_id=1)
    await m.admin_panel.callback(admin)
    assert admin.response.messages
    assert "Панель администратора" in admin.response.messages[-1]["embed"].title
    admin_view = admin.response.messages[-1]["view"]
    admin_labels = [getattr(child, "label", None) for child in admin_view.children]
    assert "Владелец" not in admin_labels
    assert "Логи" not in admin_labels
    assert "Бэкап" not in admin_labels
    assert "Добавить генератор" not in admin_labels

    # 4. Владелец сервера получает панель без права administrator.
    owner = FakeMember(99, admin=False)
    owner_guild = FakeGuild(owner_id=99, member=owner)
    owner_interaction = FakeInteraction(owner, guild=owner_guild, guild_id=1)
    await m.admin_panel.callback(owner_interaction)
    assert owner_interaction.response.messages
    assert "Панель администратора" in owner_interaction.response.messages[-1]["embed"].title
    # Владелец сервера — не владелец бота: кнопки «Владелец» быть не должно.
    owner_view = owner_interaction.response.messages[-1]["view"]
    owner_labels = [getattr(child, "label", None) for child in owner_view.children]
    assert "Владелец" not in owner_labels

    # 5. Владелец бота видит кнопку «Владелец».
    original_is_owner = m.bot.is_owner

    async def fake_is_owner(user):
        return user.id == 99

    m.bot.is_owner = fake_is_owner
    try:
        bot_owner = FakeMember(99)
        bot_owner_guild = FakeGuild(owner_id=99, member=bot_owner)
        bot_owner_interaction = FakeInteraction(
            bot_owner, guild=bot_owner_guild, guild_id=1
        )
        await m.admin_panel.callback(bot_owner_interaction)
        assert bot_owner_interaction.response.messages
        bot_owner_view = bot_owner_interaction.response.messages[-1]["view"]
        labels = [getattr(child, "label", None) for child in bot_owner_view.children]
        assert "Владелец" in labels
    finally:
        m.bot.is_owner = original_is_owner

    print("ADMIN PANEL SMOKE TEST: OK")


def test_smoke():
    asyncio.run(main())
