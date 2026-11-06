import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_remaining_flows_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.messages = []

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeMessage:
    def __init__(self, fail=False):
        self.edits = []
        self.fail = fail

    async def edit(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.edits.append((args, kwargs))


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


def test_extra_view_constructors_and_decisions():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, ?, ?)",
                [(1, 1000, 1000), (2, 0, 0), (3, 1000, 1000)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 2, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (2, 1, 'leader')"
            )
            await db.execute(
                "INSERT INTO clan_invites "
                "(clan_id, inviter_id, target_id) VALUES (1, 2, 1)"
            )
            await db.commit()

            option = m.discord.SelectOption(label="X", value="0:basic_gen:0")
            for cls, args in (
                (m.ShopBuySelectView, (1, [option], 0, 2)),
                (m.StarSelectView, (1, [option], 0, 2)),
                (m.LockSelectView, (1, [option], 0, 2)),
                (m.SwapFirstView, (1, "profile", [option], 0, 2)),
                (m.SwapSecondView, (1, "profile", 0, [option], 0, 2)),
                (
                    m.BankLoanSelectView,
                    (1, [m.discord.SelectOption(label="X", value="basic_gen:0")], 0, 2, 1000),
                ),
                (m.AuctionSellSelectView, (1, [option], 0, 2)),
                (m.MarketSellSelectView, (1, [option], 0, 2)),
                (m.SellSelectView, (1, [option], 0, 2)),
                (m.MarketOrdersView, (1, 0, 2, [], "all", None)),
                (m.MarketMyOrdersView, (1, [option], None, 0, 2)),
                (m.AdventView, (1, 0)),
                (m.PetsShopView, (1, [option], "shop")),
                (m.ClanInvitesView, (1, [option])),
                (m.ClanApplicationsView, (1, 1, [option])),
            ):
                view = cls(*args)
                assert view is not None

            original_decide = m.decide_clan_application
            original_open = m.open_clan_applications
            original_log = m.log_clan
            original_story = m.update_story_quests
            original_capacity = m.get_clan_capacity
            original_count = m.get_clan_member_count

            async def decide(*args):
                return True, "ok"

            async def open_apps(*args):
                return None

            async def noop(*args, **kwargs):
                return None

            async def capacity(clan_id):
                return 10

            async def count(clan_id):
                return 1

            m.decide_clan_application = decide
            m.open_clan_applications = open_apps
            m.log_clan = noop
            m.update_story_quests = noop
            m.get_clan_capacity = capacity
            m.get_clan_member_count = count
            try:
                view = m.ClanApplicationsView(1, 1, [option])
                interaction = FakeInteraction(1)
                await view._decide(interaction, True)
                assert interaction.response.messages

                view.selected_app = 1
                interaction = FakeInteraction(1)
                await view._decide(interaction, True)
                assert interaction.followup.sent

                view = m.ClanInvitesView(1, [option])
                interaction = FakeInteraction(1, ["1:1"])
                await view.select(interaction)
                assert interaction.edited or interaction.followup.sent

                interaction = FakeInteraction(3, ["1:999"])
                await view.select(interaction)
                assert interaction.followup.sent
            finally:
                m.decide_clan_application = original_decide
                m.open_clan_applications = original_open
                m.log_clan = original_log
                m.update_story_quests = original_story
                m.get_clan_capacity = original_capacity
                m.get_clan_member_count = original_count
        finally:
            await _close(db)

    asyncio.run(run())


def test_pets_shop_star_confirm_and_reset():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, grid_size) "
                "VALUES (1, 1000, 1000, 9), (2, 0, 0, 9), (3, 1000, 0, 9)"
            )
            await db.executemany(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (1, ?, 'basic_gen', 'profile', 0)",
                [(slot,) for slot in range(2)],
            )
            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, current_bid, current_bidder, "
                "end_time, status) "
                "VALUES (1, 3, 'basic_gen', 10, 2, ?, 'active')",
                (datetime.datetime.now().isoformat(),),
            )
            await db.commit()

            view = m.PetsShopView(1, [m.discord.SelectOption(label="Cat", value="cat")], "shop")
            interaction = FakeInteraction(1, ["bad"])
            await view.select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(2, ["cat"])
            await view.select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1, ["cat"])
            await view.select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1, ["cat"])
            await view.select(interaction)
            assert interaction.followup.sent

            original_chance = m.get_star_chance
            original_random = m.random.random
            original_build = m.build_profile_embed
            original_quests = m.update_quest_progress
            original_story = m.update_story_quests
            original_achievements = m.check_achievements

            async def chance_ok(*args):
                return 1.0, 0, True

            async def chance_fail(*args):
                return 0.0, 0, False

            async def noop(*args, **kwargs):
                return None

            async def profile(interaction):
                return m.BotEmbed(title="Profile")

            async def achievements(user_id):
                return []

            m.build_profile_embed = profile
            m.update_quest_progress = noop
            m.update_story_quests = noop
            m.check_achievements = achievements
            try:
                m.get_star_chance = chance_ok
                view = m.StarConfirmView(1, 0, "basic_gen", 0, 1, "profile")
                interaction = FakeInteraction(1)
                await view.confirm.callback(interaction)
                assert interaction.edited

                await db.execute(
                    "INSERT INTO inventory "
                    "(user_id, slot, item_id, location, stars) "
                    "VALUES (1, 10, 'basic_gen', 'profile', 0), "
                    "(1, 11, 'basic_gen', 'profile', 0)"
                )
                await db.commit()
                m.get_star_chance = chance_fail
                m.random.random = lambda: 1.0
                view = m.StarConfirmView(1, 10, "basic_gen", 0, 1, "profile")
                interaction = FakeInteraction(1)
                await view.confirm.callback(interaction)
                assert interaction.edited
            finally:
                m.get_star_chance = original_chance
                m.random.random = original_random
                m.build_profile_embed = original_build
                m.update_quest_progress = original_quests
                m.update_story_quests = original_story
                m.check_achievements = original_achievements

            m.bot._onboarding_complete_cache = {3}
            try:
                modal = m.UserResetModal(3, FakeMessage())
                modal.confirm._value = "СБРОСИТЬ"
                interaction = FakeInteraction(3)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                del m.bot._onboarding_complete_cache
        finally:
            await _close(db)

    asyncio.run(run())


def test_bonus_line_upgrades_and_global_giveaway_helpers():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, title, grid_size) "
                "VALUES (1, 1000, 100, 'Строитель', 9)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury, bonus) "
                "VALUES (1, 'Alpha', 1, 0, 0.05)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader')"
            )
            await db.execute(
                "INSERT INTO player_upgrades "
                "(user_id, upgrade_id, level, expires_at) "
                "VALUES (1, 'vip', 1, ?)",
                ((datetime.datetime.now() + datetime.timedelta(days=1)).isoformat(),),
            )
            await db.execute(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level) "
                "VALUES (1, 'cat', 3)"
            )
            await db.execute(
                "INSERT INTO player_collection (user_id, item_id) "
                "VALUES (1, 'basic_gen')"
            )
            await db.commit()

            line = await m.get_total_bonus_line(1)
            assert "клан" in line and "статус" in line

            original_status = m.get_active_statuses
            original_open_status = m.open_status_duration_view

            async def statuses(user_id):
                return []

            async def open_status(*args):
                return None

            m.get_active_statuses = statuses
            m.open_status_duration_view = open_status
            try:
                interaction = FakeInteraction(1)
                await m.open_upgrades_buy_select(
                    interaction,
                    1,
                    [
                        ("grid_4x4", "Small", 10, "🔲", "coins", 16),
                        ("vip", "VIP", 10, "💎", "gems", 0),
                        ("owned", "Owned", 10, "⚙️", "coins", 0),
                    ],
                    {"owned"},
                    0,
                )
                assert interaction.edited
            finally:
                m.get_active_statuses = original_status
                m.open_status_duration_view = original_open_status

            original_disabled = m.is_command_disabled
            original_channel = m.select_giveaway_channel
            original_send = m.send_giveaway_message
            original_insert = m._insert_giveaway_record
            original_guilds = m.global_giveaway_guilds
            original_log = m.log_admin_action

            async def disabled(guild_id, feature):
                return False

            async def no_channel(guild):
                return None

            async def noop(*args, **kwargs):
                return None

            class Guild:
                id = 1
                me = None

            async def send_ok(*args):
                return FakeMessage()

            async def insert(*args):
                return 1

            async def log(*args, **kwargs):
                return None

            m.is_command_disabled = disabled
            m.select_giveaway_channel = no_channel
            m.send_giveaway_message = send_ok
            m._insert_giveaway_record = insert
            m.global_giveaway_guilds = lambda: [Guild()]
            m.log_admin_action = log
            try:
                assert await m._send_global_giveaway_to_guild(Guild(), 1) is False

                m.global_giveaway_guilds = lambda: []
                ok, message = await m.create_global_giveaway(
                    1, "coins", None, 10, 1, 24
                )
                assert not ok

                ok, message = await m.create_global_giveaway(
                    1, "coins", None, "bad", 1, 24
                )
                assert not ok
            finally:
                m.is_command_disabled = original_disabled
                m.select_giveaway_channel = original_channel
                m.send_giveaway_message = original_send
                m._insert_giveaway_record = original_insert
                m.global_giveaway_guilds = original_guilds
                m.log_admin_action = original_log
        finally:
            await _close(db)

    asyncio.run(run())
