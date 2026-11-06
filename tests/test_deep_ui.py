import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_deep_ui_test", BOT_PATH
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

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


def test_deep_ui_actions():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, grid_size) "
                "VALUES (1, 100000, 100000, 9)"
            )
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) VALUES "
                "(1, 0, 'basic_gen', 'storage', 0), "
                "(1, 1, 'basic_gen', 'storage', 0), "
                "(1, 5, 'basic_gen', 'profile', 1), "
                "(1, 20, 'basic_gen', 'profile', 0), "
                "(1, 21, 'basic_gen', 'profile', 0), "
                "(1, 22, 'basic_gen', 'profile', 0)"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            move = m.MoveView(1, "storage", [], 0, 1)
            await move.do_move(interaction, 0, "basic_gen", 0)
            assert interaction.embed is not None

            async with db.execute(
                "SELECT id, price_coins FROM grid_shop "
                "WHERE size > 9 LIMIT 1"
            ) as c:
                grid = await c.fetchone()
            assert grid
            interaction = FakeInteraction(1, [grid[0]])
            upgrades = m.UpgradesBuySelectView(1, [], 0, 1)
            await upgrades.upgrade_select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1, ["cat"])
            pets = m.PetsShopView(1, [])
            await pets.select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            auction = m.AuctionSellDetailsModal(
                1, 5, "basic_gen", 1
            )
            auction.start_price._value = "100"
            auction.buyout_price._value = "200"
            auction.hours._value = "24"
            await auction.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            sell = m.SellConfirmView(
                1, 1, "basic_gen", 0, 10, 0
            )
            sell_btn = next(
                item
                for item in sell.children
                if getattr(item, "label", None) == "Продать"
            )
            await sell_btn.callback(interaction)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            craft = m.CraftConfirmView(1, "basic_gen")
            await craft.do_craft(interaction, False)
            assert interaction.embed is not None
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
