import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_view_constructors_test", BOT_PATH
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


class FakeMessage:
    def __init__(self):
        self.edits = []
        self.id = 1

    async def edit(self, *args, **kwargs):
        self.edits.append((args, kwargs))

    async def delete(self):
        return None


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
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


def test_main_menu_clan_and_back_callbacks():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 100)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 1, 'member')"
            )
            await db.commit()

            original_deny = m.deny_if_disabled
            original_push = m.push_nav
            original_onboarding = m.complete_onboarding_step
            original_daily = m.build_daily_embed
            original_prestige = m.build_prestige_embed

            async def deny_false(*args):
                return False

            async def noop(*args, **kwargs):
                return None

            def push(*args):
                return None

            async def daily(interaction):
                return m.BotEmbed(title="Daily")

            async def prestige(interaction):
                return m.BotEmbed(title="Prestige")

            m.deny_if_disabled = deny_false
            m.push_nav = push
            m.complete_onboarding_step = noop
            m.build_daily_embed = daily
            m.build_prestige_embed = prestige
            try:
                view = m.MainMenuView(1)
                for name in ("tab_shop", "tab_daily", "tab_exchange", "tab_prestige"):
                    interaction = FakeInteraction(1)
                    await getattr(view, name).callback(interaction)
                    assert interaction.edited
            finally:
                m.deny_if_disabled = original_deny
                m.push_nav = original_push
                m.complete_onboarding_step = original_onboarding
                m.build_daily_embed = original_daily
                m.build_prestige_embed = original_prestige

            original_role = m.get_clan_role
            original_perm = m.has_clan_permission
            original_clan = m.get_clan
            original_members = m.get_clan_members
            original_inv = m.build_clan_inventory_embed
            original_embed = m.build_clan_embed

            async def role(user_id, clan_id):
                return "leader"

            async def clan(user_id):
                return (1, "Alpha", 1, 100, 0.0, 1)

            async def members(clan_id):
                return [(1, "leader"), (2, "member")]

            async def inv(clan):
                return m.BotEmbed(title="Inventory")

            async def embed(*args):
                return m.BotEmbed(title="Clan")

            m.get_clan_role = role
            m.has_clan_permission = lambda role, action: True
            m.get_clan = clan
            m.get_clan_members = members
            m.build_clan_inventory_embed = inv
            m.build_clan_embed = embed
            try:
                view = m.ClanMenuView(1, 1)
                for name in ("btn_manage", "btn_inventory", "btn_leave"):
                    interaction = FakeInteraction(1)
                    await getattr(view, name).callback(interaction)
                    assert interaction.edited or interaction.followup.sent

                for cls, args in (
                    (m.ClanInventoryView, (1, 1)),
                    (m.ClanUpgradesView, (1, 1)),
                    (m.ClanWarView, (1, 1, 1)),
                    (m.ClanApplicationsView, (1, 1, [])),
                ):
                    sub = cls(*args)
                    interaction = FakeInteraction(1)
                    if hasattr(sub, "btn_back"):
                        await sub.btn_back.callback(interaction)
                    else:
                        await sub.back(interaction)
                    assert interaction.edited or interaction.followup.sent
            finally:
                m.get_clan_role = original_role
                m.has_clan_permission = original_perm
                m.get_clan = original_clan
                m.get_clan_members = original_members
                m.build_clan_inventory_embed = original_inv
                m.build_clan_embed = original_embed

            original_main = m.build_main_embed
            original_reset = m.reset_nav
            original_profile = m.build_user_profile_embed
            original_storage = m.build_storage_embed
            original_market = m.build_market_embed

            async def main(interaction):
                return m.BotEmbed(title="Main")

            def reset(user_id):
                return None

            async def profile(interaction):
                return m.BotEmbed(title="Profile")

            async def storage(interaction, *args):
                return m.BotEmbed(title="Storage")

            async def market(interaction):
                return m.BotEmbed(title="Market"), 1

            m.build_main_embed = main
            m.reset_nav = reset
            m.build_user_profile_embed = profile
            m.build_storage_embed = storage
            m.build_market_embed = market
            try:
                safe = m.SafeView()
                safe.author_id = 1
                interaction = FakeInteraction(1)
                await safe.back_to_home(interaction)
                assert interaction.edited

                view = m.SeasonView(
                    1,
                    {
                        "premium": False,
                        "claimable_free": False,
                        "claimable_premium": False,
                    },
                )
                interaction = FakeInteraction(1)
                await view.btn_back.callback(interaction)
                assert interaction.edited

                view = m.SeasonDisabledView(1, "main")
                interaction = FakeInteraction(1)
                await view.btn_back.callback(interaction)
                assert interaction.edited

                view = m.GuideView(1, 0)
                interaction = FakeInteraction(1)
                await view.next_page(interaction)
                assert interaction.edited

                view = m.ProfileView(1)
                m.deny_if_disabled = deny_false
                interaction = FakeInteraction(1)
                await view.storage_button.callback(interaction)
                assert interaction.edited

                view = m.PetsView(1, "profile")
                interaction = FakeInteraction(1)
                await view.btn_back.callback(interaction)
                assert interaction.edited

                view = m.AutocollectorView(1, "profile")
                interaction = FakeInteraction(1)
                await view.btn_back.callback(interaction)
                assert interaction.edited

                view = m.AnalyticsView(1, "profile")
                interaction = FakeInteraction(1)
                await view.btn_back.callback(interaction)
                assert interaction.edited

                view = m.SocialView(1)
                m.deny_if_disabled = deny_false
                interaction = FakeInteraction(1)
                await view.btn_market.callback(interaction)
                assert interaction.edited
            finally:
                m.build_main_embed = original_main
                m.reset_nav = original_reset
                m.build_user_profile_embed = original_profile
                m.build_storage_embed = original_storage
                m.build_market_embed = original_market
                m.deny_if_disabled = original_deny
        finally:
            await _close(db)

    asyncio.run(run())


def test_view_constructors_and_move_selects():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, grid_size) "
                "VALUES (1, 10000, 9)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0)"
            )
            await db.commit()

            option = m.discord.SelectOption(label="X", value="0:basic_gen:0")
            for cls, args in (
                (m.ShopBuySelectView, (1, [option])),
                (m.StarSelectView, (1, [option])),
                (m.LockSelectView, (1, [option], 0, 1)),
                (m.SwapFirstView, (1, "profile", [option])),
                (m.SwapSecondView, (1, "profile", 0, [option])),
                (m.MoveView, (1, "profile", [option], 0, 1)),
                (m.BankLoanSelectView, (1, [m.discord.SelectOption(label="X", value="basic_gen:0")], 0, 1, 1000)),
                (m.AuctionSellSelectView, (1, [option], 0, 1)),
            ):
                view = cls(*args)
                assert view is not None

            view = m.AuctionView(1, 0, 1, [], None, None)
            assert view is not None

            original_profile = m.build_profile_embed

            async def profile(interaction):
                return m.BotEmbed(title="Profile")

            m.build_profile_embed = profile
            try:
                view = m.MoveView(1, "profile", [option], 0, 1)
                interaction = FakeInteraction(1, ["0:basic_gen:0"])
                await view.item_select(interaction)
                assert interaction.edited

                interaction = FakeInteraction(1, ["0:basic_gen:0"])
                await view.item_select(interaction)
                assert interaction.edited
            finally:
                m.build_profile_embed = original_profile
        finally:
            await _close(db)

    asyncio.run(run())
