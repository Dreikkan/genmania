import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_admin_actions_test", BOT_PATH
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

    async def send_message(self, *args, **kwargs):
        return None


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.embed = None
        self.view = None

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


def test_admin_action_modals():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems, streak_days) "
                "VALUES (?, 1000, 10, 5)",
                [(1,), (2,), (3,), (4,)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id) "
                "VALUES (1, 'Alpha', 1)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 1, 'member')"
            )
            await db.execute(
                "INSERT OR IGNORE INTO achievements "
                "(id, name, reward_gems) VALUES ('first_craft', 'Первый', 5)"
            )
            await db.execute(
                "INSERT INTO player_achievements "
                "(user_id, achievement_id) VALUES (2, 'first_craft')"
            )
            await db.execute(
                "INSERT INTO player_quests "
                "(user_id, quest_id, progress, completed) "
                "VALUES (2, 'q_first_gen', 1, 0)"
            )
            await db.execute(
                "INSERT INTO advent_progress (user_id, day) VALUES (2, 1)"
            )
            await db.execute(
                "INSERT INTO advent_state "
                "(user_id, last_opened_day, last_opened_date, event_key) "
                "VALUES (2, 1, ?, 'test')",
                (datetime.date.today().isoformat(),),
            )
            now = datetime.datetime.now()
            await db.execute(
                "INSERT INTO bank_deposits "
                "(user_id, amount, interest_rate, start_time, end_time) "
                "VALUES (2, 100, 0.1, ?, ?)",
                (
                    now.isoformat(),
                    (now + datetime.timedelta(days=7)).isoformat(),
                ),
            )
            await db.execute(
                "INSERT INTO auctions "
                "(seller_id, item_id, stars, start_price, current_bid, "
                " current_bidder, end_time, status) "
                "VALUES (2, 'basic_gen', 0, 100, 120, 3, ?, 'active')",
                ((now + datetime.timedelta(hours=2)).isoformat(),),
            )
            await db.commit()

            async def noop(*args, **kwargs):
                return None

            async def check_modal(modal):
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent

            modal = m.AdminSeasonXpModal(1)
            modal.user_id._value = "2"
            modal.amount._value = "100"
            await check_modal(modal)

            modal = m.AdminGrantPrestigeModal(1)
            modal.user_id._value = "2"
            modal.amount._value = "2"
            await check_modal(modal)

            modal = m.AdminRemoveAchievementModal(1)
            modal.user_id._value = "2"
            modal.ach_id._value = "first_craft"
            await check_modal(modal)

            modal = m.AdminResetStreakModal(1)
            modal.user_id._value = "2"
            await check_modal(modal)

            modal = m.AdminResetStoryModal(1)
            modal.user_id._value = "2"
            modal.confirm._value = "ДА"
            await check_modal(modal)

            modal = m.AdminResetAdventModal(1)
            modal.user_id._value = "2"
            modal.confirm._value = "ДА"
            await check_modal(modal)

            modal = m.AdminGiveAutocollectorModal(1)
            modal.user_id._value = "2"
            await check_modal(modal)

            modal = m.AdminSetAutocollectorLevelModal(1)
            modal.user_id._value = "2"
            modal.level._value = "3"
            await check_modal(modal)

            modal = m.AdminRemoveAutocollectorModal(1)
            modal.user_id._value = "2"
            await check_modal(modal)

            modal = m.AdminRemoveDepositModal(1)
            modal.user_id._value = "2"
            await check_modal(modal)

            original_grant = m.grant_item_or_compensation
            m.grant_item_or_compensation = noop
            try:
                modal = m.AdminRemoveAuctionModal(1)
                modal.auction_id._value = "1"
                await check_modal(modal)
            finally:
                m.grant_item_or_compensation = original_grant

            modal = m.AdminAddClanMemberModal(1)
            modal.clan_id._value = "1"
            modal.user_id._value = "4"
            modal.role._value = "member"
            await check_modal(modal)

            modal = m.AdminGiveItemModal(1)
            modal.user_id._value = "2"
            modal.item_id._value = "basic_gen"
            modal.quantity._value = "1"
            modal.location._value = "profile"
            await check_modal(modal)

            clan = (1, "Alpha", 1, 0, 0.0)
            inventory = await m.build_clan_inventory_embed(clan)
            assert inventory is not None

            interaction = FakeInteraction(1)
            admin_view = m.AdminView(1)
            await admin_view.back_to_main(interaction)
            assert interaction.embed is not None

            for action, target in (
                ("promote", 2),
                ("demote", 2),
                ("transfer", 2),
            ):
                modal = m.ClanTargetConfirmModal(1, 1, action, target)
                modal.confirm._value = "ДА"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
