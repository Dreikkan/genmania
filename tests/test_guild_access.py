import asyncio
import importlib.util
import json
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_guild_access_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakePermissions:
    def __init__(self, administrator=False, value=0):
        self.administrator = administrator
        self.value = value


class FakeRole:
    def __init__(self, role_id, name="role", administrator=False):
        self.id = role_id
        self.name = name
        self.position = 1
        self.permissions = FakePermissions(
            administrator=administrator,
            value=8 if administrator else 0,
        )


class FakeMember:
    def __init__(
        self,
        user_id,
        *,
        roles=(),
        admin=False,
        value=0,
    ):
        self.id = user_id
        self.roles = list(roles)
        self.guild_permissions = FakePermissions(admin, value)
        self.display_name = f"user-{user_id}"
        self.name = f"user-{user_id}"


class FakeGuild:
    def __init__(
        self,
        guild_id=1,
        *,
        owner_id=99,
        roles=(),
        member=None,
        me=None,
    ):
        self.id = guild_id
        self.owner_id = owner_id
        self.roles = list(roles)
        self.member = member
        self.me = me
        self.member_count = 5
        self.owner = None

    def get_member(self, user_id):
        # Имитируем пустой кэш участников на чужом сервере.
        return None

    async def fetch_member(self, user_id):
        if user_id == self.owner_id:
            return FakeMember(self.owner_id)
        return self.member


class FakeResponse:
    def is_done(self):
        return False

    async def send_message(self, *args, **kwargs):
        return None


class FakeInteraction:
    def __init__(self, user, guild):
        self.user = user
        self.guild = guild
        self.guild_id = guild.id
        self.response = FakeResponse()


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._DB_TX_OWNER = None
    m._settings_cache.clear()


def test_admin_access_works_without_member_cache():
    async def run():
        db = await _init()
        original_settings = m.get_settings
        original_is_owner = m.bot.is_owner

        async def fake_settings(guild_id):
            return {"admin_role_id": 555}

        async def fake_is_owner(user):
            return False

        m.get_settings = fake_settings
        m.bot.is_owner = fake_is_owner
        try:
            # Владелец сервера: get_member возвращает None, но owner_id совпадает.
            owner = FakeMember(99)
            guild = FakeGuild(owner_id=99)
            assert await m.has_admin_access(FakeInteraction(owner, guild)) is True

            # Настроенная админ-роль: роли берутся из interaction.user.
            role_admin = FakeMember(2, roles=[FakeRole(555, "Админ")])
            guild = FakeGuild()
            interaction = FakeInteraction(role_admin, guild)
            assert await m.has_admin_access(interaction) is True

            # Право Administrator.
            admin = FakeMember(3, admin=True)
            guild = FakeGuild()
            assert await m.has_admin_access(FakeInteraction(admin, guild)) is True

            # Обычный участник.
            normal = FakeMember(4)
            guild = FakeGuild()
            assert await m.has_admin_access(FakeInteraction(normal, guild)) is False

            # Пустой кэш и User без ролей: подтягиваем Member через fetch_member.
            fetched_admin = FakeMember(7, admin=True)

            class FetchGuild(FakeGuild):
                async def fetch_member(self, user_id):
                    return fetched_admin

            plain_user = SimpleNamespace(id=7)
            guild = FetchGuild()
            assert await m.has_admin_access(FakeInteraction(plain_user, guild)) is True
        finally:
            m.get_settings = original_settings
            m.bot.is_owner = original_is_owner
            await _close(db)

    asyncio.run(run())


def test_sync_guild_access_reads_owner_roles_and_permissions():
    async def run():
        db = await _init()
        try:
            admin_role = FakeRole(555, "Админ", administrator=True)
            guild = FakeGuild(
                guild_id=10,
                owner_id=99,
                roles=[admin_role],
                me=FakeMember(1, admin=True, value=12345),
            )
            snapshot = await m.sync_guild_access(guild, reason="join")
            assert snapshot["owner_id"] == 99
            assert snapshot["admin_role_ids"] == [555]
            assert snapshot["role_count"] == 1
            assert snapshot["member_count"] == 5

            async with db.execute(
                "SELECT owner_id, admin_role_ids, roles_json, member_count, "
                "bot_permissions FROM guild_access WHERE guild_id = 10"
            ) as c:
                owner_id, admin_ids, roles_json, member_count, bot_permissions = (
                    await c.fetchone()
                )
            assert owner_id == 99
            assert json.loads(admin_ids) == [555]
            assert json.loads(roles_json)[0]["name"] == "Админ"
            assert member_count == 5
            assert bot_permissions == 12345

            async with db.execute(
                "SELECT 1 FROM guild_settings WHERE guild_id = 10"
            ) as c:
                assert await c.fetchone()

            snapshot = await m.get_guild_access_snapshot(10)
            assert snapshot["owner_id"] == 99
            assert snapshot["admin_role_ids"] == [555]
            assert snapshot["roles"][0]["name"] == "Админ"
            assert snapshot["member_count"] == 5
        finally:
            await _close(db)

    asyncio.run(run())
