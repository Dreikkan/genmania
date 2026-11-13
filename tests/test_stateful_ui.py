import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_stateful_ui_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        return None


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))
        return SimpleNamespace(id=999)


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(id=user_id, name="Tester")
        self.guild_id = 1
        self.guild = None
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.channel = FakeChannel()
        self.embed = None
        self.view = None

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


def test_stateful_ui_and_settings():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) "
                "VALUES (1, 1000, 100), (2, 1000, 100)"
            )
            await db.commit()

            m.TopView(1)
            m.AdventView(1)
            m.MarketOrdersView(1, 0, 1, [], "all", None)
            m.SwapFirstView(1, "storage", [], 0, 1)

            interaction = FakeInteraction(1)
            settings = m.SettingsGeneralModal(1)
            settings.bot_name._value = "TestBot"
            settings.item_id._value = ""
            settings.emoji._value = ""
            await settings.on_submit(interaction)
            saved = await m.get_settings(1)
            assert saved["bot_name"] == "TestBot"

            interaction = FakeInteraction(1)
            settings = m.SettingsGeneralModal(1)
            settings.bot_name._value = ""
            settings.item_id._value = "basic_gen"
            settings.emoji._value = "👑"
            await settings.on_submit(interaction)
            saved = await m.get_settings(1)
            assert saved["custom_emojis"]["basic_gen"] == "👑"

            interaction = FakeInteraction(1)
            settings = m.SettingsGeneralModal(1)
            settings.bot_name._value = ""
            settings.item_id._value = ""
            settings.emoji._value = ""
            await settings.on_submit(interaction)
            assert interaction.followup.sent

            original_owner_check = m.is_global_owner

            async def owner_true(interaction):
                return True

            m.is_global_owner = owner_true
            try:
                interaction = FakeInteraction(1)
                role_modal = m.SettingsAdminRoleModal(1)
                role_modal.role_id._value = "0"
                await role_modal.on_submit(interaction)
                saved = await m.get_settings(1)
                assert saved["admin_role_id"] is None

                interaction = FakeInteraction(1)
                interaction.guild = SimpleNamespace(
                    get_role=lambda role_id: SimpleNamespace(id=role_id)
                )
                role_modal = m.SettingsAdminRoleModal(1)
                role_modal.role_id._value = "123"
                await role_modal.on_submit(interaction)
                saved = await m.get_settings(1)
                assert saved["admin_role_id"] == 123
            finally:
                m.is_global_owner = original_owner_check

            added = []
            role = SimpleNamespace(id=777)
            member = SimpleNamespace(
                add_roles=lambda *args, **kwargs: added.append(role)
            )

            async def add_roles(*args, **kwargs):
                added.append(args[0] if args else role)

            member.add_roles = add_roles
            guild = SimpleNamespace(
                get_member=lambda uid: member,
                get_role=lambda role_id: role,
            )
            await m.save_setting(
                1, "status_roles", {"vip": 777}, actor_id=1
            )
            interaction.guild = guild
            await m.grant_status_role(interaction, 1, "vip")
            assert added

            original_event = m.get_active_advent_event
            event = {
                "key": "test_event",
                "name": "Тест",
                "emoji": "🎄",
                "days": 5,
            }
            m.get_active_advent_event = lambda: (event, 1)
            try:
                interaction = FakeInteraction(1)
                advent = m.AdminOpenAdventModal(1)
                advent.user_id._value = "1"
                advent.day._value = "1"
                await advent.on_submit(interaction)
                async with db.execute(
                    "SELECT last_opened_day FROM advent_state "
                    "WHERE user_id = 1"
                ) as c:
                    assert (await c.fetchone())[0] == 1

                view = m.AdventView(1)
                day_btn = next(
                    item
                    for item in view.children
                    if getattr(item, "label", None) == "2"
                )
                interaction = FakeInteraction(1)
                await day_btn.callback(interaction)
                assert interaction.followup.sent
            finally:
                m.get_active_advent_event = original_event

            interaction = FakeInteraction(1)
            await m.create_duel_challenge(
                interaction, 1, 2, 50, "dice"
            )
            assert interaction.channel.sent
            assert interaction.followup.sent

            original_emojis = dict(m.BOT_BTN_EMOJIS)
            original_fetch = m.bot.fetch_application_emojis

            async def fake_fetch():
                return [
                    SimpleNamespace(
                        name="coin",
                        id=1,
                        __str__=lambda self: "<:coin:1>",
                    )
                ]

            m.bot.fetch_application_emojis = fake_fetch
            try:
                await m.bot.load_application_emojis()
            finally:
                m.bot.fetch_application_emojis = original_fetch
                m.BOT_BTN_EMOJIS.clear()
                m.BOT_BTN_EMOJIS.update(original_emojis)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
