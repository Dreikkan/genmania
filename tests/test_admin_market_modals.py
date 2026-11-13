import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_admin_market_modals_test", BOT_PATH
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

    async def send_modal(self, *args, **kwargs):
        return None


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(id=user_id, name="Tester")
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.embed = None
        self.view = None

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


def test_admin_market_modals():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        original_owner = m.is_global_owner
        try:
            await m.bot.init_db()

            async def owner_true(interaction):
                return True

            m.is_global_owner = owner_true
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) "
                "VALUES (?, 1000, 1000)",
                [(1,), (2,), (3,)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id) "
                "VALUES (1, 'Alpha', 1)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 1, 'member')"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            modal = m.MarketOrderCreateModal(1, "sell", "basic_gen")
            modal.quantity._value = "bad"
            modal.price._value = "100"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.MarketBuyModal(1, "basic_gen")
            modal.qty._value = "bad"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.MarketSellModal(1, "basic_gen")
            modal.qty._value = "bad"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.ClanKickModal(1, 1)
            modal.user_id._value = "1"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.ClanKickModal(1, 1)
            modal.user_id._value = "3"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.ClanKickModal(1, 1)
            modal.user_id._value = "2"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            view = m.TitlesView(1, [], 0, 1)
            interaction = FakeInteraction(1, ["missing"])
            await view.select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1, ["novice"])
            await view.select(interaction)
            assert interaction.followup.sent

            modal = m.AuctionBidModal(1, 99999)
            modal.amount._value = "0"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminSeasonResetModal(1)
            modal.user_id._value = "2"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            original_event = m.get_active_advent_event
            m.get_active_advent_event = lambda: (None, 0)
            try:
                modal = m.AdminOpenAdventModal(1)
                modal.user_id._value = "2"
                modal.day._value = "1"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.get_active_advent_event = original_event

            modal = m.AdminRemoveTitleModal(1)
            modal.user_id._value = "2"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            grant = m.AdminGrantView(1)
            interaction = FakeInteraction(1, ["gems"])
            await grant.currency_select(interaction)
            assert grant.currency == "gems"

            take = m.AdminTakeView(1)
            interaction = FakeInteraction(1, ["bad"])
            await take.currency_select(interaction)
            assert interaction.response.messages

            modal = m.EditStartCoinsModal(1)
            modal.value._value = "-1"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.EditStartCoinsModal(1)
            modal.value._value = "50"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
        finally:
            m.is_global_owner = original_owner
            await db.close()
            m.bot.db = None

    asyncio.run(run())
