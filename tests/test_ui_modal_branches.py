import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_ui_modal_branches_test", BOT_PATH
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
        self.fail = fail
        self.edits = []
        self.deleted = False
        self.jump_url = "https://example.com/m"

    async def edit(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.edits.append((args, kwargs))

    async def delete(self):
        self.deleted = True


class FakeInteraction:
    def __init__(self, user_id=1, values=None, channel=None):
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
        self.channel = channel
        self.message = FakeMessage()
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


async def _submit(modal, **fields):
    interaction = FakeInteraction()
    for name, value in fields.items():
        getattr(modal, name)._value = str(value)
    await modal.on_submit(interaction)
    return interaction


def test_duel_pvp_profile_and_raid_invite_modals():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, ?)",
                [(1, 1000), (2, 1000), (3, 1000), (4, 1000)],
            )
            await db.commit()

            original_create = m.create_duel_challenge
            created = []

            async def fake_create(*args):
                created.append(args)

            m.create_duel_challenge = fake_create
            try:
                interaction = await _submit(
                    m.DuelModal(1), opponent_id="bad", bet="1", mode="dice"
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.DuelModal(1), opponent_id="2", bet="1", mode="bad"
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.DuelModal(1), opponent_id="2", bet="1", mode="dice"
                )
                assert created

                interaction = await _submit(
                    m.DuelBetModal(1, 2), bet="bad", mode="dice"
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.DuelBetModal(1, 2), bet="1", mode="bad"
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.DuelBetModal(1, 2), bet="1", mode="dice"
                )
                assert len(created) >= 2
            finally:
                m.create_duel_challenge = original_create

            original_lobby = m.open_duel_lobby

            async def fake_lobby(*args):
                fake_lobby.called = True

            fake_lobby.called = False
            m.open_duel_lobby = fake_lobby
            try:
                interaction = await _submit(m.PvPTargetModal(1), target_id="bad")
                assert interaction.response.messages
                interaction = await _submit(m.PvPTargetModal(1), target_id="1")
                assert interaction.response.messages
                interaction = await _submit(m.PvPTargetModal(1), target_id="2")
                assert fake_lobby.called
            finally:
                m.open_duel_lobby = original_lobby

            interaction = await _submit(m.ProfileIdModal(1), user_id="bad")
            assert interaction.followup.sent
            interaction = await _submit(m.ProfileIdModal(1), user_id="2")
            assert interaction.followup.sent

            interaction = await _submit(m.EspionageIdModal(1), user_id="bad")
            assert interaction.followup.sent
            interaction = await _submit(m.EspionageIdModal(1), user_id="1")
            assert interaction.followup.sent

            original_cd = m.get_espionage_cooldown_seconds

            async def cooldown(user_id):
                return 10

            m.get_espionage_cooldown_seconds = cooldown
            try:
                interaction = await _submit(m.EspionageIdModal(1), user_id="2")
                assert interaction.followup.sent
            finally:
                m.get_espionage_cooldown_seconds = original_cd

            # Raid invite view: guard clauses, accept failure/success, decline,
            # timeout and delete helper.
            view = m.RaidInviteView(1, 1, 2)
            interaction = FakeInteraction(1)
            assert await view.interaction_check(interaction) is False
            interaction = FakeInteraction(2)
            assert await view.interaction_check(interaction) is True

            view.message = FakeMessage()
            await view._delete_later(0)
            view.message = None
            view._schedule_delete(1)
            view.message = FakeMessage(fail=True)
            view._schedule_delete(1)
            view._schedule_delete(1)

            original_join = m.join_raid_party

            async def join_fail(*args):
                raise ValueError("bad join")

            view = m.RaidInviteView(1, 1, 2)
            view.message = FakeMessage()
            m.join_raid_party = join_fail
            try:
                interaction = FakeInteraction(2)
                await view.accept.callback(interaction)
                assert view.resolved
            finally:
                m.join_raid_party = original_join

            view = m.RaidInviteView(1, 1, 2)
            view.message = FakeMessage()
            interaction = FakeInteraction(2)
            await view.accept.callback(interaction)
            assert view.resolved

            view = m.RaidInviteView(1, 1, 2)
            view.resolved = True
            interaction = FakeInteraction(2)
            await view.accept.callback(interaction)

            view = m.RaidInviteView(1, 1, 2)
            view.message = FakeMessage(fail=True)
            interaction = FakeInteraction(2)
            await view.decline.callback(interaction)
            assert view.resolved

            view = m.RaidInviteView(1, 1, 2)
            view.resolved = True
            await view.on_timeout()

            view = m.RaidInviteView(1, 1, 2)
            view.message = None
            await view.on_timeout()

            view = m.RaidInviteView(1, 1, 2)
            view.message = FakeMessage(fail=True)
            await view.on_timeout()

            view = m.RaidInviteView(1, 1, 2)
            interaction = FakeInteraction(1)
            await view.on_error(interaction, RuntimeError("boom"), None)
            interaction = FakeInteraction(1)
            interaction.response.deferred = True
            await view.on_error(interaction, RuntimeError("boom"), None)
        finally:
            await _close(db)

    asyncio.run(run())


def test_raid_invite_modal_guards_and_success():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id) VALUES (?)",
                [(1,), (2,), (3,), (4,), (5,)],
            )
            await db.execute(
                "INSERT INTO raid_parties "
                "(id, leader_id, member2_id, member3_id) "
                "VALUES (1, 1, NULL, NULL), (2, 2, 1, 3)"
            )
            await db.execute(
                "INSERT INTO raid_parties "
                "(id, leader_id, member2_id, member3_id) "
                "VALUES (3, 5, NULL, NULL)"
            )
            await db.commit()

            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="bad")
            assert interaction.followup.sent
            interaction = await _submit(m.RaidInviteModal(9, 99), target_id="2")
            assert interaction.followup.sent
            interaction = await _submit(m.RaidInviteModal(1, 2), target_id="5")
            assert interaction.followup.sent
            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="1")
            assert interaction.followup.sent
            interaction = await _submit(m.RaidInviteModal(1, 2), target_id="3")
            assert interaction.followup.sent
            interaction = await _submit(m.RaidInviteModal(1, 2), target_id="4")
            assert interaction.followup.sent
            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="999")
            assert interaction.followup.sent
            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="5")
            assert interaction.followup.sent

            await db.executemany(
                "INSERT INTO raid_party_invites "
                "(party_id, inviter_id, target_id) VALUES (?, ?, ?)",
                [(1, 1, 2), (1, 1, 3), (1, 1, 4)],
            )
            await db.commit()
            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="6")
            assert interaction.followup.sent

            await db.execute("DELETE FROM raid_party_invites WHERE party_id = 1")
            await db.commit()

            class Channel:
                def __init__(self, fail=False):
                    self.fail = fail

                async def send(self, *args, **kwargs):
                    if self.fail:
                        raise m.discord.HTTPException.__new__(
                            m.discord.HTTPException
                        )
                    return FakeMessage()

            original_messageable = m.discord.abc.Messageable
            try:
                m.discord.abc.Messageable = Channel
                interaction = await _submit(m.RaidInviteModal(1, 1), target_id="2")
                interaction.channel = SimpleNamespace(id=1)
                await m.RaidInviteModal(1, 1).on_submit(interaction)
                assert interaction.followup.sent

                interaction = await _submit(m.RaidInviteModal(1, 1), target_id="2")
                interaction.channel = Channel()
                await m.RaidInviteModal(1, 1).on_submit(interaction)
                assert interaction.followup.sent

                interaction = await _submit(m.RaidInviteModal(1, 1), target_id="2")
                interaction.channel = Channel(fail=True)
                await m.RaidInviteModal(1, 1).on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.discord.abc.Messageable = original_messageable
        finally:
            await _close(db)

    asyncio.run(run())


def test_cosmetic_exchange_bank_and_auction_modals():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES "
                "(1, 1000, 1000), (2, 10, 0)"
            )
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "emoji, rarity, buyable) "
                "VALUES ('auction_gen', 'Auction', 100, 1, '⚙️', 'rare', 0)"
            )
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'auction_gen', 'profile', 0)"
            )
            await db.commit()

            interaction = await _submit(
                m.CosmeticBgModal(1, "hub", None), url="bad"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.CosmeticBgModal(1, "hub", FakeMessage()),
                url="https://example.com/bg.png",
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.CosmeticBgModal(1, "hub", FakeMessage(fail=True)),
                url="https://example.com/bg2.png",
            )
            assert interaction.followup.sent

            interaction = await _submit(
                m.CosmeticIconModal(1, "hub", None), emoji="bad"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.CosmeticIconModal(1, "hub", FakeMessage()), emoji="⚙️"
            )
            assert interaction.followup.sent

            interaction = await _submit(m.CoinsToGemsModal(1), amount="1")
            assert interaction.followup.sent
            interaction = await _submit(m.CoinsToGemsModal(1), amount="13")
            assert interaction.followup.sent
            interaction = await _submit(m.GemsToCoinsModal(1), amount="0")
            assert interaction.followup.sent
            interaction = await _submit(m.GemsToCoinsModal(2), amount="999")
            assert interaction.followup.sent
            interaction = await _submit(m.GemsToCoinsModal(1), amount="1")
            assert interaction.followup.sent

            interaction = await _submit(
                m.BankDepositModal(1, None), amount="bad", days="1"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.BankDepositModal(2, None), amount="100", days="1"
            )
            assert interaction.followup.sent
            await db.execute(
                "INSERT INTO bank_deposits (user_id, amount) VALUES (1, 10)"
            )
            await db.commit()
            interaction = await _submit(
                m.BankDepositModal(1, None), amount="10", days="1"
            )
            assert interaction.followup.sent
            await db.execute("DELETE FROM bank_deposits WHERE user_id = 1")
            await db.commit()
            interaction = await _submit(
                m.BankDepositModal(1, FakeMessage()), amount="10", days="1"
            )
            assert interaction.followup.sent

            interaction = await _submit(
                m.BankWithdrawModal(1, None), confirm="НЕТ"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.BankWithdrawModal(1, None), confirm="ДА"
            )
            assert interaction.followup.sent

            now = datetime.datetime.now()
            await db.execute(
                "INSERT INTO bank_deposits "
                "(user_id, amount, interest_rate, start_time, end_time) "
                "VALUES (1, 100, 0.04, ?, ?)",
                (
                    (now - datetime.timedelta(days=7)).isoformat(),
                    (now - datetime.timedelta(days=1)).isoformat(),
                ),
            )
            await db.commit()
            interaction = await _submit(
                m.BankWithdrawModal(1, FakeMessage()), confirm="ДА"
            )
            assert interaction.followup.sent

            original_loan = m.take_bank_loan

            async def loan_ok(*args):
                return True, "ok"

            async def loan_fail(*args):
                return False, "no"

            original_open_bank = m.open_bank_view

            async def open_bank(*args):
                return None

            m.open_bank_view = open_bank
            try:
                interaction = await _submit(
                    m.BankLoanAmountModal(1, "basic_gen", 0, 1000),
                    amount="bad",
                )
                assert interaction.followup.sent
                m.take_bank_loan = loan_fail
                interaction = await _submit(
                    m.BankLoanAmountModal(1, "basic_gen", 0, 1000),
                    amount="100",
                )
                assert interaction.followup.sent
                m.take_bank_loan = loan_ok
                interaction = await _submit(
                    m.BankLoanAmountModal(1, "basic_gen", 0, 1000),
                    amount="100",
                )
                assert interaction.followup.sent
            finally:
                m.take_bank_loan = original_loan
                m.open_bank_view = original_open_bank

            interaction = await _submit(
                m.AuctionSellDetailsModal(1, 0, "basic_gen", 0),
                start_price="bad",
                buyout_price="0",
                hours="1",
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.AuctionSellDetailsModal(1, 0, "basic_gen", 0),
                start_price="10",
                buyout_price="5",
                hours="1",
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.AuctionSellDetailsModal(1, 0, "legendary_gen", 0),
                start_price="10",
                buyout_price="0",
                hours="1",
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.AuctionSellDetailsModal(1, 0, "missing", 0),
                start_price="10",
                buyout_price="0",
                hours="1",
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.AuctionSellDetailsModal(1, 0, "auction_gen", 0),
                start_price="10",
                buyout_price="20",
                hours="1",
            )
            assert interaction.followup.sent

            original_bid = m.place_auction_bid
            original_open_auction = m.open_auction_view

            async def bid(*args):
                return True, "bid ok", None, False

            async def open_auction(*args):
                return None

            m.place_auction_bid = bid
            m.open_auction_view = open_auction
            try:
                interaction = await _submit(
                    m.AuctionBidModal(1, 1, 0), amount="0"
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.AuctionBidModal(1, 1, 0), amount="10"
                )
                assert interaction.followup.sent
            finally:
                m.place_auction_bid = original_bid
                m.open_auction_view = original_open_auction
        finally:
            await _close(db)

    asyncio.run(run())


def test_shop_quest_craft_and_reset_paths():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES "
                "(1, 10000, 1000), (2, 0, 0)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader')"
            )
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0), "
                "(1, 1, 'basic_gen', 'profile', 0), "
                "(1, 2, 'basic_gen', 'profile', 0)"
            )
            await db.commit()

            view = m.BuyItemQuantityView(1, "missing", 0)
            interaction = FakeInteraction(1, ["1"])
            await view.quantity_select(interaction)
            assert interaction.edited

            view = m.BuyItemQuantityView(1, "legendary_gen", 0)
            interaction = FakeInteraction(1, ["1"])
            await view.quantity_select(interaction)
            assert interaction.edited

            view = m.BuyItemQuantityView(2, "basic_gen", 0)
            interaction = FakeInteraction(2, ["1"])
            await view.quantity_select(interaction)
            assert interaction.edited

            view = m.BuyItemQuantityView(1, "basic_gen", 0)
            interaction = FakeInteraction(1, ["1"])
            await view.quantity_select(interaction)
            assert interaction.edited
            interaction = FakeInteraction(1)
            await view.back(interaction)
            assert interaction.edited

            original_place = m.place_items

            async def place_fail(*args, **kwargs):
                raise ValueError("no space")

            m.place_items = place_fail
            try:
                view = m.BuyItemQuantityView(1, "basic_gen", 0)
                interaction = FakeInteraction(1, ["1"])
                await view.quantity_select(interaction)
                assert interaction.edited
            finally:
                m.place_items = original_place

            original_quests = m.get_or_create_daily_quests

            async def quests(user_id):
                return {"craft_1": ("Desc", 1, 1, 1)}, {"craft_1": 0}, []

            m.get_or_create_daily_quests = quests
            try:
                view = m.ClaimQuestSelectView(
                    1, [m.discord.SelectOption(label="X", value="craft_1")], "hub"
                )
                interaction = FakeInteraction(1, ["craft_1"])
                await view.quest_select(interaction)
                assert interaction.edited

                async def quests_done(user_id):
                    return (
                        {"craft_1": ("Desc", 1, 1, 1)},
                        {"craft_1": 1},
                        [],
                    )

                m.get_or_create_daily_quests = quests_done
                view = m.ClaimQuestSelectView(
                    1, [m.discord.SelectOption(label="X", value="craft_1")], "hub"
                )
                interaction = FakeInteraction(1, ["craft_1"])
                await view.quest_select(interaction)
                assert interaction.edited
                interaction = FakeInteraction(1)
                await view.back(interaction)
                assert interaction.edited
            finally:
                m.get_or_create_daily_quests = original_quests

            view = m.CraftConfirmView(1, "basic_gen")
            interaction = FakeInteraction(1)
            await view.cancel.callback(interaction)
            assert interaction.edited

            deleted = []

            async def delete_item(*args, **kwargs):
                return None

            await db.execute("DELETE FROM items WHERE id = 'copper_gen'")
            await db.commit()
            interaction = FakeInteraction(1)
            await m.CraftConfirmView(1, "basic_gen").do_craft(interaction, False)
            assert interaction.edited

            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "emoji, rarity, buyable) "
                "VALUES ('copper_gen', 'Copper', 10, 1, '⚙️', 'common', 1)"
            )
            await db.execute(
                "UPDATE players SET gems = 0 WHERE user_id = 1"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 10, 'steel_gen', 'storage', 0), "
                "(1, 11, 'steel_gen', 'storage', 0), "
                "(1, 12, 'steel_gen', 'storage', 0)"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await m.CraftConfirmView(1, "steel_gen").do_craft(interaction, False)
            assert interaction.edited

            await db.execute(
                "UPDATE players SET gems = 100, catalysts = 0 WHERE user_id = 1"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await m.CraftConfirmView(1, "basic_gen").do_craft(interaction, True)
            assert interaction.edited

            await db.execute(
                "UPDATE players SET catalysts = 10 WHERE user_id = 1"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await m.CraftConfirmView(1, "basic_gen").do_craft(interaction, True)
            assert interaction.edited

            # Reset modal with an active auction and a main message.
            await db.execute(
                "INSERT INTO auctions "
                "(seller_id, item_id, current_bidder, current_bid, end_time, status) "
                "VALUES (1, 'basic_gen', 2, 10, ?, 'active')",
                (datetime.datetime.now().isoformat(),),
            )
            await db.commit()
            modal = m.UserResetModal(1, FakeMessage())
            modal.confirm._value = "СБРОСИТЬ"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
        finally:
            await _close(db)

    asyncio.run(run())
