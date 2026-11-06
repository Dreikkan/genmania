import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_coverage_90_edges_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.messages = []
        self.modals = []

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_modal(self, modal):
        self.modals.append(modal)

    async def edit_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeMessage:
    def __init__(self, fail=False):
        self.fail = fail
        self.edits = []
        self.deleted = False

    async def edit(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.edits.append((args, kwargs))

    async def delete(self):
        self.deleted = True


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(get_role=lambda rid: None)
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.message = FakeMessage()
        self.edited = []
        self.channel = None

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


def test_guards_confirm_views_and_open_helpers():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 100)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0), "
                "(1, 0, 'basic_gen', 'storage', 0)"
            )
            await db.commit()

            option = m.discord.SelectOption(label="X", value="x")
            for view in (
                m.UpgradesBuySelectView(1, [option]),
                m.StarSelectView(1, [option], 0, 1),
                m.StatusDurationView(1, "vip", 0),
                m.StarConfirmView(1, 0, "basic_gen", 0, 1, "profile"),
            ):
                interaction = FakeInteraction(2)
                assert await view.interaction_check(interaction) is False
                interaction = FakeInteraction(1)
                assert await view.interaction_check(interaction) is True

            welcome = m.WelcomeView(1)
            interaction = FakeInteraction(2)
            assert await welcome.interaction_check(interaction) is False
            interaction = FakeInteraction(1)
            assert await welcome.interaction_check(interaction) is True

            m.TitlesView(1, [option], 0, 1)

            original_top = m.build_top_embed

            async def top(*args, **kwargs):
                return m.BotEmbed(title="Top")

            m.build_top_embed = top
            try:
                view = m.TopView(1)
                interaction = FakeInteraction(1)
                await view.btn_refresh(interaction)
                assert interaction.edited
            finally:
                m.build_top_embed = original_top

            original_upgrades = m.build_upgrades_page

            async def upgrades(*args):
                return m.BotEmbed(title="Up"), 2

            m.build_upgrades_page = upgrades
            try:
                view = m.UpgradesView(1, 1)
                interaction = FakeInteraction(1)
                await view.prev_page(interaction)
                assert interaction.edited
                interaction = FakeInteraction(1)
                await view.next_page(interaction)
                assert interaction.edited
            finally:
                m.build_upgrades_page = original_upgrades

            original_main = m.build_main_embed
            original_quests = m.build_quests_embed
            original_storage = m.build_storage_embed

            async def main(interaction):
                return m.BotEmbed(title="Main")

            async def quests(interaction):
                return m.BotEmbed(title="Quests")

            async def storage(interaction, filter_mode="all"):
                return m.BotEmbed(title="Storage")

            m.build_main_embed = main
            m.build_quests_embed = quests
            m.build_storage_embed = storage
            try:
                view = m.StoryQuestsView(1, "main")
                view.back_to_main = lambda interaction: asyncio.sleep(0)
                interaction = FakeInteraction(1)
                await view.back.callback(interaction)

                view = m.StorageView(1, "profile")
                interaction = FakeInteraction(1, ["common"])
                await view.select_filter(interaction)
                assert interaction.edited
            finally:
                m.build_main_embed = original_main
                m.build_quests_embed = original_quests
                m.build_storage_embed = original_storage

            original_role = m.get_clan_role
            original_perm = m.has_clan_permission

            async def role(*args):
                return "member"

            m.get_clan_role = role
            m.has_clan_permission = lambda role, action: False
            try:
                view = m.ClanManageView(1, 1)
                interaction = FakeInteraction(1)
                assert await view._check(interaction, "kick") is None
                assert interaction.response.messages
                m.has_clan_permission = lambda role, action: True
                interaction = FakeInteraction(1)
                assert await view._check(interaction, "kick") == "member"
            finally:
                m.get_clan_role = original_role
                m.has_clan_permission = original_perm

            original_deny = m.deny_if_disabled
            original_espionage = m.open_espionage_select

            async def deny_false(*args):
                return False

            async def espionage(*args):
                return None

            m.deny_if_disabled = deny_false
            m.open_espionage_select = espionage
            try:
                view = m.SocialView(1)
                interaction = FakeInteraction(1)
                await view.btn_espionage.callback(interaction)
                assert interaction.response.deferred
            finally:
                m.deny_if_disabled = original_deny
                m.open_espionage_select = original_espionage

            assert await m.get_star_emoji("basic_gen", 5, "⚙️") is not None

            original_get_user = m.bot.get_user
            original_fetch = m.bot.fetch_user
            m.bot.get_user = lambda uid: None

            async def fetch(uid):
                raise m.discord.NotFound.__new__(m.discord.NotFound)

            m.bot.fetch_user = fetch
            try:
                embed, page, pages = await m.build_clan_members_embed(1)
                assert embed.title
            finally:
                m.bot.get_user = original_get_user
                m.bot.fetch_user = original_fetch

            view = m.BulkSellConfirmView(1, "common", 1, 10)
            assert view.count == 1

            original_repay = m.repay_bank_loan
            original_open_bank = m.open_bank_view

            async def repay(*args):
                return True, "ok"

            async def open_bank(*args):
                return None

            m.repay_bank_loan = repay
            m.open_bank_view = open_bank
            try:
                view = m.BankRepayConfirmView(1)
                interaction = FakeInteraction(1)
                await view.btn_confirm.callback(interaction)
                assert interaction.followup.sent
            finally:
                m.repay_bank_loan = original_repay
                m.open_bank_view = original_open_bank

            original_buyout = m.buyout_auction
            original_open_auction = m.open_auction_view

            async def buyout(*args):
                return True, "ok", 0

            async def open_auction(*args):
                return None

            m.buyout_auction = buyout
            m.open_auction_view = open_auction
            try:
                view = m.AuctionBuyoutConfirmView(1, 1)
                interaction = FakeInteraction(1)
                await view.btn_buy.callback(interaction)
                assert interaction.followup.sent
            finally:
                m.buyout_auction = original_buyout
                m.open_auction_view = original_open_auction
        finally:
            await _close(db)

    asyncio.run(run())


def test_open_helpers_main_menu_and_package_edges():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000)"
            )
            await db.commit()

            original_swap = m._build_swap_first_page
            original_pets = m.build_pets_embed
            original_duel = m.DuelTargetSelectView
            original_content = m.build_content_editor_embed

            async def swap_ok(*args):
                return m.BotEmbed(title="Swap"), None, None

            async def swap_err(*args):
                return None, None, "no items"

            async def pets(*args):
                return m.BotEmbed(title="Pets")

            async def content(*args):
                return m.BotEmbed(title="Content")

            m._build_swap_first_page = swap_ok
            m.build_pets_embed = pets
            m.build_content_editor_embed = content
            try:
                interaction = FakeInteraction(1)
                await m.open_swap_view(interaction, "profile", 1)
                assert interaction.followup.sent
                m._build_swap_first_page = swap_err
                interaction = FakeInteraction(1)
                await m.open_swap_view(interaction, "profile", 1)
                assert interaction.followup.sent

                interaction = FakeInteraction(1)
                await m.open_pets_shop(interaction, 1)
                assert interaction.edited

                interaction = FakeInteraction(1)
                await m.open_duel_setup(interaction, 1)
                assert interaction.edited

                interaction = FakeInteraction(1)
                await m.open_content_editor(interaction, 1)
                assert interaction.edited

                interaction = FakeInteraction(1)
                await m.open_auction_view(interaction, 1)
                assert interaction.edited
            finally:
                m._build_swap_first_page = original_swap
                m.build_pets_embed = original_pets
                m.DuelTargetSelectView = original_duel
                m.build_content_editor_embed = original_content

            original_welcome = m.build_welcome_embed
            original_notification = m.get_menu_welcome_notification
            original_collect = m.collect_income
            original_build_main = m.build_main_embed

            async def welcome(interaction):
                return m.BotEmbed(title="Welcome")

            async def notification(*args):
                return "hello"

            async def collect(*args):
                return 0, 0

            async def main(interaction):
                return m.BotEmbed(title="Main")

            m.build_welcome_embed = welcome
            m.get_menu_welcome_notification = notification
            m.collect_income = collect
            m.build_main_embed = main
            try:
                interaction = FakeInteraction(9)
                await m.main_menu.callback(interaction)
                assert interaction.response.messages
                interaction = FakeInteraction(1)
                await m.main_menu.callback(interaction)
                assert interaction.response.messages
            finally:
                m.build_welcome_embed = original_welcome
                m.get_menu_welcome_notification = original_notification
                m.collect_income = original_collect
                m.build_main_embed = original_build_main

            assert m.market_sparkline([]) == "—"
            assert m.loan_total_due(None) == 0
            embed = await m.build_bank_history_embed(1)
            assert embed
            assert await m.expire_statuses() == []

            assert m.party_member_ids(None) == []
            assert await m.detach_user_from_raid_party(999) == "none"

            assert (await m.update_item_appearance(1, "Bad ID", "⚙️", "1"))[0] is False
            assert (await m.update_item_appearance(1, "missing", "⚙️", "1"))[0] is False
            assert (await m.set_item_income(1, "Bad ID", 1, 0))[0] is False

            embed = await m.build_auction_history_embed(999)
            assert embed
        finally:
            await _close(db)

    asyncio.run(run())
