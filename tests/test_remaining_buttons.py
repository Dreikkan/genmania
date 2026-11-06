import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_remaining_buttons_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.messages = []
        self.modal = None

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_modal(self, modal):
        self.modal = modal


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(get_role=lambda role_id: None)
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.message = SimpleNamespace()
        self.edited = []

    async def edit_original_response(self, *args, **kwargs):
        self.edited.append((args, kwargs))


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


def test_user_profile_buttons():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000)"
            )
            await db.commit()
            original_deny = m.deny_if_disabled
            original_ach = m.build_achievements_page
            original_analytics = m.build_analytics_embed
            original_pets = m.build_pets_embed

            async def deny_false(*args):
                return False

            async def ach(interaction, page):
                return m.BotEmbed(title="Ach"), 1

            async def analytics(interaction):
                return m.BotEmbed(title="Analytics")

            async def pets(interaction):
                return m.BotEmbed(title="Pets")

            m.deny_if_disabled = deny_false
            m.build_achievements_page = ach
            m.build_analytics_embed = analytics
            m.build_pets_embed = pets
            try:
                view = m.UserProfileView(1)
                for name in ("btn_achievements", "btn_analytics", "btn_pets"):
                    interaction = FakeInteraction(1)
                    await getattr(view, name).callback(interaction)
                    assert interaction.edited
            finally:
                m.deny_if_disabled = original_deny
                m.build_achievements_page = original_ach
                m.build_analytics_embed = original_analytics
                m.build_pets_embed = original_pets
        finally:
            await _close(db)

    asyncio.run(run())


def test_swap_pages_and_selects():
    async def run():
        db = await _init()
        try:
            option = m.discord.SelectOption(label="X", value="0")
            original_first = m._build_swap_first_page
            original_second = m._build_swap_second_page
            original_open = m.open_swap_view

            async def first_ok(*args):
                return m.BotEmbed(title="Swap"), None, None

            async def first_error(*args):
                return None, None, "no slots"

            async def second_ok(*args):
                return m.BotEmbed(title="Swap2"), None, None

            async def second_error(*args):
                return None, None, "no slots"

            view = m.SwapFirstView(1, "profile", [option], 1, 2)

            m._build_swap_first_page = first_ok
            m._build_swap_second_page = second_ok
            try:
                interaction = FakeInteraction(1)
                await view.prev_page(interaction)
                assert interaction.edited
                interaction = FakeInteraction(1)
                await view.next_page(interaction)
                assert interaction.edited

                m._build_swap_first_page = first_error
                interaction = FakeInteraction(1)
                await view.prev_page(interaction)
                assert interaction.followup.sent

                interaction = FakeInteraction(1, ["0"])
                await view.first_select(interaction)
                assert interaction.edited

                m._build_swap_second_page = second_error
                interaction = FakeInteraction(1, ["0"])
                await view.first_select(interaction)
                assert interaction.followup.sent
            finally:
                m._build_swap_first_page = original_first
                m._build_swap_second_page = original_second

            view2 = m.SwapSecondView(1, "profile", 0, [option], 1, 2)
            m._build_swap_second_page = second_ok
            try:
                interaction = FakeInteraction(1)
                await view2.prev_page(interaction)
                assert interaction.edited
                interaction = FakeInteraction(1)
                await view2.next_page(interaction)
                assert interaction.edited
            finally:
                m._build_swap_second_page = original_second

            original_profile = m.build_user_profile_embed
            original_main = m.build_main_embed

            async def profile(interaction):
                return m.BotEmbed(title="Profile")

            async def main(interaction):
                return m.BotEmbed(title="Main")

            m.build_user_profile_embed = profile
            m.build_main_embed = main
            try:
                for return_to in ("profile", "hub", "main"):
                    view = m.TitlesView(
                        1, [option], 0, 1, return_to=return_to
                    )
                    interaction = FakeInteraction(1)
                    await view.back(interaction)
                    assert interaction.edited
            finally:
                m.build_user_profile_embed = original_profile
                m.build_main_embed = original_main
        finally:
            await _close(db)

    asyncio.run(run())


def test_content_views_settings_and_bank_loan_select():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 100)"
            )
            await db.commit()

            option = m.discord.SelectOption(label="X", value="basic_gen")
            view = m.ContentItemsView(1, [option], 1, 2)
            interaction = FakeInteraction(1)
            await view.on_select(interaction)
            assert interaction.response.messages
            view._selected = lambda: "basic_gen"
            original_open_item = m.open_content_item

            async def open_item(*args):
                return None

            m.open_content_item = open_item
            try:
                interaction = FakeInteraction(1)
                await view.on_select(interaction)
                assert interaction.edited or interaction.response.deferred
            finally:
                m.open_content_item = original_open_item

            view = m.ContentAchievementsView(1, [option], 1, 2)
            interaction = FakeInteraction(1)
            await view.on_select(interaction)
            assert interaction.response.messages
            view._selected = lambda: "a1"
            original_open_ach = m.open_content_achievement

            async def open_ach(*args):
                return None

            m.open_content_achievement = open_ach
            try:
                interaction = FakeInteraction(1)
                await view.on_select(interaction)
                assert interaction.edited or interaction.response.deferred
            finally:
                m.open_content_achievement = original_open_ach

            original_save = m.save_setting
            original_toggle = m.TOGGLEABLE_COMMANDS

            async def save(*args, **kwargs):
                return None

            m.save_setting = save
            m.TOGGLEABLE_COMMANDS = {"daily": "Дейли"}
            try:
                view = m.SettingsCommandsView(1, [])
                interaction = FakeInteraction(1, ["daily"])
                await view.toggle(interaction)
                assert interaction.followup.sent
            finally:
                m.save_setting = original_save
                m.TOGGLEABLE_COMMANDS = original_toggle

            original_settings = m.get_settings
            original_admin_log = m.log_admin_action
            original_season_embed = m.build_admin_season_embed
            original_admin_view = m.AdminSeasonView

            async def settings(guild_id):
                return {"battlepass_enabled": True}

            async def log(*args, **kwargs):
                return None

            def season_embed(enabled):
                return m.BotEmbed(title="Season")

            m.get_settings = settings
            m.log_admin_action = log
            m.build_admin_season_embed = season_embed
            view = original_admin_view(1, True)
            m.AdminSeasonView = lambda author_id, enabled: m.BotEmbed(
                title="View"
            )
            try:
                interaction = FakeInteraction(1)
                await view.btn_toggle.callback(interaction)
                assert interaction.edited
            finally:
                m.get_settings = original_settings
                m.log_admin_action = original_admin_log
                m.build_admin_season_embed = original_season_embed
                m.AdminSeasonView = original_admin_view

            original_global = m.is_global_owner
            original_super = m.AdminView.interaction_check

            async def super_check(self, interaction):
                return True

            async def global_false(interaction):
                return False

            async def global_true(interaction):
                return True

            m.AdminView.interaction_check = super_check
            try:
                view = m.OwnerPanelView(1)
                m.is_global_owner = global_false
                interaction = FakeInteraction(1)
                assert await view.interaction_check(interaction) is False
                m.is_global_owner = global_true
                interaction = FakeInteraction(1)
                assert await view.interaction_check(interaction) is True
            finally:
                m.AdminView.interaction_check = original_super
                m.is_global_owner = original_global

            original_collateral = m.get_collateral_value

            async def collateral(item_id, stars):
                return 1000

            m.get_collateral_value = collateral
            try:
                option = m.discord.SelectOption(
                    label="X", value="basic_gen:0"
                )
                view = m.BankLoanSelectView(1, [option], 0, 2, 1000)
                interaction = FakeInteraction(1, ["basic_gen:0"])
                await view.select_item(interaction)
                assert interaction.response.modal is not None
            finally:
                m.get_collateral_value = original_collateral

            original_upgrades = m.open_clan_applications

            async def open_apps(*args):
                return None

            m.open_clan_applications = open_apps
            try:
                view = m.ClanApplicationsView(1, 1, [option])
                interaction = FakeInteraction(1)
                await view.back(interaction)
                assert interaction.followup.sent or interaction.edited
            finally:
                m.open_clan_applications = original_upgrades
        finally:
            await _close(db)

    asyncio.run(run())
