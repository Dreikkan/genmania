import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_auction_bank_war_test", BOT_PATH
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


def test_auction_bank_and_clan_war_views():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, grid_size) "
                "VALUES (1, 100000, 100000, 9)"
            )
            async with db.execute(
                "SELECT id FROM items ORDER BY price DESC LIMIT 1"
            ) as c:
                expensive_item = (await c.fetchone())[0]
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) VALUES "
                "(1, 0, 'basic_gen', 'profile', 1), "
                "(1, 1, ?, 'profile', 0), "
                "(1, 0, 'basic_gen', 'storage', 0), "
                "(1, 1, 'basic_gen', 'storage', 0)",
                (expensive_item,),
            )
            now = datetime.datetime.now()
            await db.execute(
                "INSERT INTO auctions "
                "(seller_id, item_id, stars, start_price, current_bid, "
                " current_bidder, buyout_price, end_time, status) "
                "VALUES (1, 'basic_gen', 1, 100, 120, 2, 200, ?, 'active')",
                ((now + datetime.timedelta(hours=2)).isoformat(),),
            )
            await db.execute(
                "INSERT INTO bank_loans "
                "(user_id, amount, interest_rate, due_time, "
                " collateral_item, collateral_stars, status) "
                "VALUES (1, 1000, 0.1, ?, 'basic_gen', 1, 'active')",
                ((now + datetime.timedelta(days=3)).isoformat(),),
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 1000), (2, 'Beta', 2, 1000)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 2, 'leader')"
            )
            await db.execute(
                "INSERT INTO clan_wars "
                "(clan1_id, clan2_id, start_time, status, "
                " clan1_hp, clan2_hp, clan1_max_hp, clan2_max_hp) "
                "VALUES (1, 2, ?, 'active', 1000, 1000, 1000, 1000)",
                (now.isoformat(),),
            )
            await db.commit()

            interaction = FakeInteraction(1)
            await m.open_auction_view(interaction, 1, selected_lot=1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_auction_sell_select(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_auction_cancel_select(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_bank_loan_select(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_bank_repay_confirm(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1, ["1"])
            swap = m.SwapSecondView(1, "storage", 0, [], 0, 1)
            await swap.second_select(interaction)
            assert interaction.embed is not None

            clan_menu = m.ClanMenuView(1, 1)
            war_btn = next(
                item
                for item in clan_menu.children
                if getattr(item, "label", None) == "Война"
            )
            interaction = FakeInteraction(1)
            await war_btn.callback(interaction)
            assert interaction.embed is not None

            clan_war = m.ClanWarView(1, 1, 1)
            attack_btn = next(
                item
                for item in clan_war.children
                if getattr(item, "label", None) == "Атаковать"
            )
            original_attack = m.attack_clan_war

            async def fake_attack(war_id, user_id):
                return True, "ok", False

            m.attack_clan_war = fake_attack
            try:
                interaction = FakeInteraction(1)
                await attack_btn.callback(interaction)
                assert interaction.embed is not None
            finally:
                m.attack_clan_war = original_attack

            m.GiveawayCreateModal(1, "coins")
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
