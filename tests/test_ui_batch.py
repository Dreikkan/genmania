import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_ui_batch_test", BOT_PATH
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


def test_ui_batch():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, grid_size) "
                "VALUES (1, 100000, 100000, 9)"
            )
            now = datetime.datetime.now()
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) VALUES "
                "(1, 0, 'basic_gen', 'storage', 0), "
                "(1, 0, 'basic_gen', 'profile', 1)"
            )
            await db.execute(
                "INSERT INTO auctions "
                "(seller_id, item_id, stars, start_price, current_bid, "
                " current_bidder, end_time, status) "
                "VALUES (1, 'basic_gen', 0, 100, 120, 2, ?, 'active')",
                ((now + datetime.timedelta(hours=2)).isoformat(),),
            )
            await db.execute(
                "INSERT INTO mailbox "
                "(user_id, item_id, quantity, stars) "
                "VALUES (1, 'basic_gen', 1, 0)"
            )
            await db.commit()

            m.ShopBuySelectView(1, [])
            m.SeasonPreviewView(1, 0, 2)
            m.OrderBookSelectView(1, [], 0, 2, "market")
            m.AdminLogsView(1, 0, 2)
            m.StarEmojiPaginatedView(1, [], 0, 2)
            m.MarketFiltersView(1, None, "change")
            m.CollectionView(1, 0, 2)
            m.GuideSectionView(1, "economy", 0, 0, 2)

            interaction = FakeInteraction(1, ["1"])
            cancel = m.AuctionCancelSelectView(1, [])
            await cancel.select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1, ["0:basic_gen:0"])
            sell = m.SellSelectView(1, [], 0, 1)
            await sell.item_select(interaction)
            assert interaction.embed is not None

            interaction = FakeInteraction(1, ["1"])
            catalyst = m.CatalystSelectView(1)
            await catalyst.quantity_select(interaction)
            assert interaction.embed is not None

            mailbox = m.MailboxView(1, 1)
            claim = next(
                item
                for item in mailbox.children
                if getattr(item, "label", None) == "Забрать всё"
            )
            interaction = FakeInteraction(1)
            await claim.callback(interaction)
            assert interaction.embed is not None

            quests = m.ClaimQuestSelectView(1, [], "main")
            interaction = FakeInteraction(1, ["missing_quest"])
            await quests.quest_select(interaction)
            assert interaction.embed is not None

            interaction = FakeInteraction(1, ["basic_gen"])
            shop = m.ShopBuySelectView(1, [])
            await shop.item_select(interaction)
            assert interaction.embed is not None

            quests_view = m.QuestsView(1)
            claim_btn = next(
                item
                for item in quests_view.children
                if getattr(item, "label", None) == "Забрать награду"
            )
            interaction = FakeInteraction(1)
            await claim_btn.callback(interaction)
            assert interaction.embed is not None or interaction.followup.sent
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
