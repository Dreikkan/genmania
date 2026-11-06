import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_more_paths_test", BOT_PATH
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
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.embed = None
        self.view = None
        self.channel = SimpleNamespace(
            send=self._send,
        )

    async def _send(self, *args, **kwargs):
        return SimpleNamespace(id=1, jump_url="url")

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


def test_more_error_paths():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, grid_size) "
                "VALUES (1, 1000, 1000, 9), (2, 1000, 1000, 9), "
                "(3, 1000, 1000, 9)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id) "
                "VALUES (1, 'Alpha', 2)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (2, 1, 'leader'), (1, 1, 'member')"
            )
            await db.commit()

            async with db.execute(
                "SELECT id FROM grid_shop LIMIT 2"
            ) as c:
                grids = [row[0] for row in await c.fetchall()]
            await db.execute(
                "INSERT INTO player_upgrades (user_id, upgrade_id) "
                "VALUES (1, ?)",
                (grids[0],),
            )
            await db.commit()
            interaction = FakeInteraction(1, [grids[0]])
            upgrades = m.UpgradesBuySelectView(1, [], 0, 1)
            await upgrades.upgrade_select(interaction)
            assert interaction.followup.sent

            await db.execute(
                "UPDATE players SET coins = 0 WHERE user_id = 1"
            )
            await db.commit()
            interaction = FakeInteraction(1, [grids[1]])
            await upgrades.upgrade_select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            craft = m.CraftConfirmView(1, "basic_gen")
            await craft.do_craft(interaction, False)
            assert interaction.embed is not None

            party = await m.create_raid_party(2)
            modal = m.RaidInviteModal(1, party)
            modal.target_id._value = "3"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.RaidInviteModal(2, party)
            modal.target_id._value = "2"
            interaction = FakeInteraction(2)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AuctionSellDetailsModal(
                1, 0, "basic_gen", 0
            )
            modal.start_price._value = "0"
            modal.buyout_price._value = "0"
            modal.hours._value = "24"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AuctionSellDetailsModal(
                1, 0, "basic_gen", 0
            )
            modal.start_price._value = "100"
            modal.buyout_price._value = "50"
            modal.hours._value = "24"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1, ["1"])
            quantity = m.BuyItemQuantityView(1, "basic_gen")
            await quantity.quantity_select(interaction)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.create_duel_challenge(
                interaction, 1, 1, 10, "dice"
            )
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            await m.create_duel_challenge(
                interaction, 1, 2, 0, "dice"
            )
            assert interaction.followup.sent

            modal = m.ClanRoleModal(1, 1, "promote")
            modal.user_id._value = "3"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            await m.open_market_order_fill_confirm(
                interaction, 1, 99999, 0, "all"
            )
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            await m.open_clan_invites(interaction, 1)
            assert interaction.followup.sent

            sell = m.SellConfirmView(1, 0, "basic_gen", 0, 10, 0)
            cancel = next(
                item
                for item in sell.children
                if getattr(item, "label", None) == "Отмена"
            )
            interaction = FakeInteraction(1)
            await cancel.callback(interaction)
            assert interaction.embed is not None

            modal = m.AdminEditModal(1)
            modal.user_id._value = "1"
            modal.field._value = "bad"
            modal.value._value = "1"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.CoinsToGemsModal(1)
            modal.amount._value = "13"
            await modal.on_submit(interaction)
            assert interaction.followup.sent
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
