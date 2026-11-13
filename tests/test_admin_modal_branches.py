import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_admin_modal_branches_test", BOT_PATH
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


class FakeInteraction:
    def __init__(self, user_id=999):
        self.user = SimpleNamespace(id=user_id, name="Admin")
        self.guild_id = 1
        self.guild = SimpleNamespace(get_role=lambda role_id: None)
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.edited = []
        self.data = {"values": []}

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
        attr = getattr(modal, name)
        if not hasattr(attr, "_value"):
            attr = type(modal).__dict__.get(name)
            if attr is not None:
                modal.__dict__[name] = attr
        attr._value = str(value)
    await modal.on_submit(interaction)
    return interaction


def test_admin_modal_id_validation_branches():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 100, 10)"
            )
            await db.commit()

            assert (await _submit(m.AdminSeasonResetModal(1), user_id="bad")).followup.sent
            assert (await _submit(m.AdminSeasonPremiumModal(1), user_id="bad")).followup.sent
            assert (await _submit(m.AdminSeasonXpModal(1), user_id="bad", amount="1")).followup.sent
            assert (await _submit(m.AdminCancelMarketOrderModal(1), order_id="bad")).followup.sent
            assert (await _submit(m.AdminGrantPrestigeModal(1), user_id="bad", amount="1")).followup.sent
            assert (await _submit(m.AdminResetNotifCooldownModal(1), user_id="bad")).followup.sent
            assert (await _submit(m.AdminGiveAchievementModal(1), user_id="bad", ach_id="a1")).followup.sent
            assert (await _submit(m.AdminRemoveAchievementModal(1), user_id="bad", ach_id="a1")).followup.sent
            assert (await _submit(m.AdminResetStreakModal(1), user_id="bad")).followup.sent
            assert (await _submit(m.AdminCompleteStoryModal(1), user_id="bad", quest_id="q")).followup.sent
            assert (await _submit(m.AdminOpenAdventModal(1), user_id="bad", day="1")).followup.sent
            assert (await _submit(m.AdminGiveAutocollectorModal(1), user_id="bad")).followup.sent
            assert (await _submit(m.AdminSetAutocollectorLevelModal(1), user_id="bad", level="1")).followup.sent
            assert (await _submit(m.AdminRemoveAutocollectorModal(1), user_id="bad")).followup.sent
            assert (await _submit(m.AdminGiveDepositModal(1), user_id="bad", amount="1", days="1")).followup.sent
            assert (await _submit(m.AdminRemoveDepositModal(1), user_id="bad")).followup.sent
            assert (await _submit(m.AdminRemoveAuctionModal(1), auction_id="bad")).followup.sent
            assert (await _submit(m.AdminFinishAuctionModal(1), auction_id="bad")).followup.sent
            assert (await _submit(m.AdminCreateClanModal(1), name="X", leader_id="bad")).followup.sent
            assert (await _submit(m.AdminDisbandClanModal(1), clan_id="bad")).followup.sent
            assert (await _submit(m.AdminAddClanMemberModal(1), clan_id="bad", user_id="1", role="member")).followup.sent
            assert (await _submit(m.AdminClanTreasuryModal(1), clan_id="bad", amount="1")).followup.sent
            assert (await _submit(m.AdminSetTitleModal(1), user_id="bad", title_id="novice")).followup.sent
            assert (await _submit(m.AdminRemoveTitleModal(1), user_id="bad")).followup.sent
            assert (await _submit(m.AdminGivePetModal(1), user_id="bad", pet_id="cat")).followup.sent
            assert (await _submit(m.AdminSetPetLevelModal(1), user_id="bad", pet_id="cat", level="1")).followup.sent
            assert (await _submit(m.AdminRemovePetModal(1), user_id="bad", pet_id="cat")).followup.sent
            assert (await _submit(m.AdminGrantValuesModal(1, "coins"), user_id="1", amount="bad")).followup.sent
            assert (await _submit(m.AdminTakeValuesModal(1, "coins"), user_id="1", amount="bad")).followup.sent
            assert (await _submit(m.AdminProfileModal(1), user_id="bad")).followup.sent
            assert (await _submit(m.AdminEditModal(1), user_id="bad", field="coins", value="1")).followup.sent
            assert (await _submit(m.AdminGiveItemModal(1), user_id="bad", item_id="basic_gen", quantity="1", location="profile")).followup.sent
        finally:
            await _close(db)

    asyncio.run(run())


def test_admin_modal_missing_and_duplicate_entities():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, ?, ?)",
                [(1, 100, 10), (2, 100, 10)],
            )
            await db.execute(
                "INSERT INTO achievements (id, name, description, reward_gems) "
                "VALUES ('a1', 'Ach', 'Desc', 1)"
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
                "INSERT INTO autocollectors (user_id, level) VALUES (1, 1)"
            )
            await db.execute(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level) "
                "VALUES (1, 'cat', 1)"
            )
            await db.execute(
                "INSERT INTO bank_deposits (user_id, amount) VALUES (1, 10)"
            )
            await db.execute(
                "INSERT INTO market_orders "
                "(user_id, side, item_id, price, quantity, status) "
                "VALUES (1, 'sell', 'basic_gen', 13, 1, 'active')"
            )
            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, end_time, status) "
                "VALUES (1, 1, 'basic_gen', ?, 'active'), "
                "(2, 1, 'basic_gen', ?, 'finished')",
                (
                    datetime.datetime.now().isoformat(),
                    datetime.datetime.now().isoformat(),
                ),
            )
            await db.commit()

            assert (await _submit(m.AdminGrantPrestigeModal(1), user_id="999", amount="1")).followup.sent
            assert (await _submit(m.AdminGiveAchievementModal(1), user_id="1", ach_id="missing")).followup.sent
            assert (await _submit(m.AdminResetStreakModal(1), user_id="999")).followup.sent
            assert (await _submit(m.AdminCompleteStoryModal(1), user_id="1", quest_id="missing")).followup.sent
            assert (await _submit(m.AdminCancelMarketOrderModal(1), order_id="999")).followup.sent
            assert (await _submit(m.AdminGiveAutocollectorModal(1), user_id="1")).followup.sent
            assert (await _submit(m.AdminGiveAutocollectorModal(1), user_id="999")).followup.sent
            assert (await _submit(m.AdminSetAutocollectorLevelModal(1), user_id="1", level="bad")).followup.sent
            assert (await _submit(m.AdminSetAutocollectorLevelModal(1), user_id="999", level="2")).followup.sent
            assert (await _submit(m.AdminRemoveAutocollectorModal(1), user_id="999")).followup.sent
            assert (await _submit(m.AdminGiveDepositModal(1), user_id="1", amount="10", days="1")).followup.sent
            assert (await _submit(m.AdminGiveDepositModal(1), user_id="999", amount="10", days="1")).followup.sent
            assert (await _submit(m.AdminRemoveDepositModal(1), user_id="999")).followup.sent
            assert (await _submit(m.AdminRemoveAuctionModal(1), auction_id="999")).followup.sent
            assert (await _submit(m.AdminFinishAuctionModal(1), auction_id="999")).followup.sent
            assert (await _submit(m.AdminFinishAuctionModal(1), auction_id="2")).followup.sent
            assert (await _submit(m.AdminCreateClanModal(1), name="X", leader_id="1")).followup.sent
            assert (await _submit(m.AdminCreateClanModal(1), name="New Clan", leader_id="2")).followup.sent
            assert (await _submit(m.AdminDisbandClanModal(1), clan_id="999")).followup.sent
            assert (await _submit(m.AdminClanTreasuryModal(1), clan_id="999", amount="1")).followup.sent
            assert (await _submit(m.AdminSetTitleModal(1), user_id="1", title_id="missing")).followup.sent
            assert (await _submit(m.AdminGivePetModal(1), user_id="1", pet_id="cat")).followup.sent
            assert (await _submit(m.AdminGivePetModal(1), user_id="1", pet_id="bad")).followup.sent
            assert (await _submit(m.AdminSetPetLevelModal(1), user_id="1", pet_id="bad", level="1")).followup.sent
            assert (await _submit(m.AdminSetPetLevelModal(1), user_id="1", pet_id="dog", level="1")).followup.sent
            assert (await _submit(m.AdminTakeValuesModal(1, "coins"), user_id="999", amount="1")).followup.sent
            assert (await _submit(m.AdminTakeValuesModal(1, "coins"), user_id="1", amount="1000")).followup.sent
            assert (await _submit(m.AdminProfileModal(1), user_id="999")).followup.sent
            assert (await _submit(m.AdminEditModal(1), user_id="1", field="bad", value="1")).followup.sent
            assert (await _submit(m.AdminEditModal(1), user_id="1", field="coins", value="-1")).followup.sent
            assert (await _submit(m.AdminEditModal(1), user_id="1", field="coins", value="999999999999")).followup.sent
            assert (await _submit(m.AdminGiveItemModal(1), user_id="1", item_id="missing", quantity="1", location="profile")).followup.sent
            assert (await _submit(m.AdminGiveItemModal(1), user_id="1", item_id="basic_gen", quantity="1", location="bad")).followup.sent

            assert (await _submit(m.AdminResetModal(1), user_id="1", confirm="НЕТ")).followup.sent
            assert (await _submit(m.AdminResetModal(1), user_id="1", confirm="ДА")).followup.sent
            assert (await _submit(m.AdminResetPrestigeModal(1), user_id="1", confirm="НЕТ")).followup.sent
            assert (await _submit(m.AdminResetStoryModal(1), user_id="1", confirm="НЕТ")).followup.sent
            assert (await _submit(m.AdminResetAdventModal(1), user_id="1", confirm="НЕТ")).followup.sent

            original_event = m.get_active_advent_event
            m.get_active_advent_event = lambda: (None, 0)
            try:
                assert (await _submit(m.AdminOpenAdventModal(1), user_id="1", day="1")).followup.sent
            finally:
                m.get_active_advent_event = original_event
            m.get_active_advent_event = lambda: ({"days": 30, "key": "x"}, 0)
            try:
                assert (await _submit(m.AdminOpenAdventModal(1), user_id="1", day="99")).followup.sent
            finally:
                m.get_active_advent_event = original_event
        finally:
            await _close(db)

    asyncio.run(run())


def test_content_and_settings_modal_branches():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 100, 10)"
            )
            await db.commit()
            original_owner = m.is_global_owner
            original_deny = m.deny_content_edit

            async def owner_false(interaction):
                return False

            async def owner_true(interaction):
                return True

            async def deny_false(interaction):
                return False

            try:
                m.is_global_owner = owner_false
                assert (await _submit(m.AddGeneratorModal(1), id="new_gen", name="New", price="10")).response.messages
                assert (await _submit(m.AddGeneratorStep2Modal(1, "new_gen", "New", 10), income_coins="1", income_gems="0", emoji="⚙️", rarity="common")).response.messages
                assert (await _submit(m.EditItemPriceModal(1), item_id="basic_gen", price="10")).response.messages
                assert (await _submit(m.EditItemIncomeModal(1), item_id="basic_gen", income_coins="1", income_gems="0")).response.messages

                m.is_global_owner = owner_true
                assert (await _submit(m.AddGeneratorModal(1), id="Bad ID", name="New", price="10")).followup.sent
                assert (await _submit(m.AddGeneratorModal(1), id="new_gen", name="New", price="bad")).followup.sent
                assert (await _submit(m.AddGeneratorModal(1), id="new_gen", name="", price="10")).followup.sent
                assert (await _submit(m.AddGeneratorModal(1), id="basic_gen", name="New", price="10")).followup.sent
                assert (await _submit(m.AddGeneratorModal(1), id="new_gen", name="New", price="10")).edited

                assert (await _submit(m.EditItemPriceModal(1), item_id="basic_gen", price="10")).followup.sent
                assert (await _submit(m.EditItemIncomeModal(1), item_id="basic_gen", income_coins="1", income_gems="0")).followup.sent

                m.deny_content_edit = owner_false
                assert (await _submit(m.DeleteAchievementModal(1, "a1"), ach_id="a1", confirm="ДА")).followup.sent
                assert (await _submit(m.AddAchievementModal(1), ach_id="a2", name="A", desc="D", reward="1", emoji="🏆")).followup.sent
            finally:
                m.is_global_owner = original_owner
                m.deny_content_edit = original_deny

            interaction = await _submit(m.SettingsCurrencyModal(1), coins="🪙", gems="💎")
            assert interaction.followup.sent
            assert (await _submit(m.SettingsStatusRoleModal(1), status="bad", role_id="1")).followup.sent
            assert (await _submit(m.SettingsStatusRoleModal(1), status="vip", role_id="bad")).followup.sent
            m.is_global_owner = owner_true
            try:
                assert (await _submit(m.SettingsAdminRoleModal(1), role_id="bad")).followup.sent
                assert (await _submit(m.SettingsAdminRoleModal(1), role_id="999")).followup.sent
                assert (await _submit(m.StarEmojiModal2(1, "missing"), e3="⚙️", e4="⚙️", e5="⚙️")).followup.sent
            finally:
                m.is_global_owner = original_owner
            assert (await _submit(m.EditEmojiModal(1, "_coin"), emoji="bad emoji")).followup.sent
            assert (await _submit(m.EditEmojiModal(1, "_coin"), emoji="")).followup.sent
        finally:
            await _close(db)

    asyncio.run(run())
