import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_coverage_99_targets", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.messages = []
        self.modals = []

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_modal(self, modal):
        self.modals.append(modal)


class FakeFollowup:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.sent.append((args, kwargs))


class FakeMessage:
    def __init__(self, fail=False):
        self.fail = fail
        self.edits = []

    async def edit(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.edits.append((args, kwargs))

    async def delete(self):
        return None


class FakeInteraction:
    def __init__(self, user_id=1, values=None, fail_followup=False):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_name=f"User{user_id}",
            mention=f"<@{user_id}>",
            bot=False,
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(
            id=1,
            owner_id=1,
            get_role=lambda rid: None,
            get_member=lambda uid: None,
        )
        self.response = FakeResponse()
        self.followup = FakeFollowup(fail=fail_followup)
        self.data = {"values": values or ["1"]}
        self.message = FakeMessage()
        self.edited = []
        self.deleted = False
        self.channel = None
        self.client = m.bot

    async def edit_original_response(self, *args, **kwargs):
        self.edited.append((args, kwargs))

    async def delete_original_response(self):
        self.deleted = True


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


async def _set_modal(modal, **values):
    for name, value in values.items():
        getattr(modal, name)._value = value


def test_craft_clan_and_admin_branches():
    async def run():
        db = await _init()
        original_perm = m.has_clan_permission
        original_role = m.get_clan_role
        original_get_clan = m.get_clan
        original_owner = m.is_global_owner
        original_place = m.place_items
        original_gen = m.add_generator_content
        original_quests = m.get_or_create_daily_quests
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems, catalysts) "
                "VALUES (?, ?, ?, ?)",
                [(1, 1000, 100, 1), (2, 0, 100, 1), (3, 0, 0, 0)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Probe', 1, 0)"
            )
            await db.executemany(
                "INSERT INTO clan_members (user_id, clan_id, role) VALUES (?, 1, ?)",
                [(1, "leader"), (2, "member"), (3, "leader")],
            )
            await db.commit()

            await db.executemany(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (2, ?, 'steel_gen', 'profile', 0)",
                [(0,), (1,), (2,)],
            )
            await db.commit()
            await db.execute(
                "CREATE TRIGGER trg_craft_gems_ignore BEFORE UPDATE OF gems ON players "
                "WHEN OLD.user_id = 2 AND NEW.gems < OLD.gems "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(2)
            await m.CraftConfirmView(2, "steel_gen").do_craft(interaction, False)
            assert interaction.edited
            await db.execute("DROP TRIGGER trg_craft_gems_ignore")
            await db.commit()

            await db.execute(
                "DELETE FROM inventory WHERE user_id = 2 AND location = 'profile'"
            )
            await db.executemany(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (2, ?, 'basic_gen', 'profile', 0)",
                [(0,), (1,), (2,)],
            )
            await db.commit()
            await db.execute(
                "CREATE TRIGGER trg_craft_cats_ignore BEFORE UPDATE OF catalysts ON players "
                "WHEN OLD.user_id = 2 AND NEW.catalysts < OLD.catalysts "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(2)
            await m.CraftConfirmView(2, "basic_gen").do_craft(interaction, True)
            assert interaction.edited
            await db.execute("DROP TRIGGER trg_craft_cats_ignore")
            await db.commit()

            m.has_clan_permission = lambda role, action: True

            async def clan_role(user_id, clan_id):
                return "leader" if user_id in (1, 3) else "member"

            m.get_clan_role = clan_role
            view = m.ClanTargetSelectView(1, 1, "invite")
            interaction = FakeInteraction(1)
            await view._invite(interaction, 1)
            assert interaction.followup.sent

            async def clan_exists(user_id):
                return (1, "Probe", 1, 0, 0) if user_id == 2 else None

            m.get_clan = clan_exists
            interaction = FakeInteraction(1)
            await view._invite(interaction, 2)
            assert interaction.followup.sent

            await db.execute(
                "INSERT INTO clan_invites (id, clan_id, inviter_id, target_id) "
                "VALUES (1, 1, 1, 3)"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await view._invite(interaction, 3)
            assert interaction.followup.sent

            modal = m.ClanTransferModal(1, 1)
            await _set_modal(modal, user_id="3", confirm="ДА")
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.ClanTransferModal(1, 1)
            await _set_modal(modal, user_id="2", confirm="ДА")
            await db.execute(
                "CREATE TRIGGER trg_transfer_demote BEFORE UPDATE OF role ON clan_members "
                "WHEN NEW.user_id = 1 AND NEW.role = 'member' "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_transfer_demote")
            await db.commit()

            modal = m.ClanTransferModal(1, 1)
            await _set_modal(modal, user_id="2", confirm="ДА")
            await db.execute(
                "CREATE TRIGGER trg_transfer_promote BEFORE UPDATE OF role ON clan_members "
                "WHEN NEW.user_id = 2 AND NEW.role = 'leader' "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_transfer_promote")
            await db.commit()

            async def no_clan(user_id):
                return None

            m.get_clan = no_clan
            calls = {"n": 0}

            async def get_clan_none_then_clan(user_id):
                calls["n"] += 1
                if calls["n"] == 1:
                    return None
                return (1, "Probe", 1, 0, 0)

            m.get_clan = get_clan_none_then_clan
            modal = m.CreateClanModal(1)
            modal.name._value = "New Clan"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            m.get_clan = no_clan
            await db.execute(
                "CREATE TRIGGER trg_create_coins_ignore BEFORE UPDATE OF coins ON players "
                "WHEN OLD.user_id = 1 AND NEW.coins < OLD.coins "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            modal = m.CreateClanModal(1)
            modal.name._value = "New Clan"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_create_coins_ignore")
            await db.commit()

            quest_id = next(iter(m.QUEST_POOL))

            async def all_claimed(user_id):
                return [quest_id], {quest_id: 0}, {quest_id}

            m.get_or_create_daily_quests = all_claimed
            view = m.QuestsView(1)
            interaction = FakeInteraction(1)
            await view.claim_button.callback(interaction)
            assert interaction.followup.sent

            view = m.BuyItemQuantityView(1, "basic_gen")
            interaction = FakeInteraction(1, ["1"])
            await db.execute(
                "CREATE TRIGGER trg_buy_coins_ignore BEFORE UPDATE OF coins ON players "
                "WHEN OLD.user_id = 1 AND NEW.coins < OLD.coins "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            await view.quantity_select(interaction)
            assert interaction.edited
            await db.execute("DROP TRIGGER trg_buy_coins_ignore")
            await db.commit()

            async def place_many(*args, **kwargs):
                return 1, 1, 0

            m.place_items = place_many
            interaction = FakeInteraction(1, ["1"])
            await view.quantity_select(interaction)
            assert interaction.edited

            modal = m.AdminTakeValuesModal(1, "coins")
            await _set_modal(modal, user_id="1", amount="0")
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminTakeValuesModal(1, "coins")
            await _set_modal(modal, user_id="999", amount="1")
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminTakeValuesModal(1, "coins")
            await _set_modal(modal, user_id="1", amount="1")
            await db.execute(
                "CREATE TRIGGER trg_take_coins_ignore BEFORE UPDATE OF coins ON players "
                "WHEN OLD.user_id = 1 AND NEW.coins < OLD.coins "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_take_coins_ignore")
            await db.commit()

            modal = m.AdminGiveItemModal(1)
            await _set_modal(
                modal,
                user_id="1",
                item_id="basic_gen",
                quantity="1",
                location="profile",
            )

            async def place_fail(*args, **kwargs):
                raise ValueError("no space")

            m.place_items = place_fail
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            m.place_items = place_many
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AddGeneratorStep2Modal(1, "probe_gen", "Probe", 100)
            await _set_modal(
                modal,
                income_coins="1",
                income_gems="0",
                emoji="⚙️",
                rarity="common",
            )

            async def owner(interaction):
                return True

            async def add_gen(*args, **kwargs):
                return None, "ok"

            m.is_global_owner = owner
            m.add_generator_content = add_gen
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            view = m.AdminPanelView(1)
            interaction = FakeInteraction(1)
            await view.btn_owner(interaction)
            assert interaction.edited

            for cls in (
                m.AdminResetStoryModal,
                m.AdminResetModal,
                m.AdminResetAdventModal,
            ):
                modal = cls(1)
                await _set_modal(modal, user_id="abc", confirm="ДА")
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
        finally:
            m.has_clan_permission = original_perm
            m.get_clan_role = original_role
            m.get_clan = original_get_clan
            m.is_global_owner = original_owner
            m.place_items = original_place
            m.add_generator_content = original_gen
            m.get_or_create_daily_quests = original_quests
            await _close(db)

    asyncio.run(run())


def test_market_background_and_small_views():
    async def run():
        db = await _init()
        original_sleep = m.asyncio.sleep
        original_close = m.discord.ext.commands.Bot.close
        original_main = m.build_main_embed
        original_storage = m.build_storage_embed
        original_profile = m.build_profile_embed
        original_premium = m.buy_season_premium
        original_season_embed = m.build_season_embed
        original_place = m.place_items

        async def no_sleep(*args, **kwargs):
            return None

        async def noop(*args, **kwargs):
            return None

        async def embed(*args, **kwargs):
            return m.BotEmbed(title="X")

        class BrokenCtx:
            async def __aenter__(self):
                raise RuntimeError("db fail")

            async def __aexit__(self, *args):
                return None

        class BrokenDB:
            def execute(self, *args, **kwargs):
                return BrokenCtx()

        try:
            m.asyncio.sleep = no_sleep
            fake = object.__new__(m.CastleBot)
            state = {"closed": False}

            async def ready():
                return None

            def closed():
                if state["closed"]:
                    return True
                state["closed"] = True
                return False

            fake.db = BrokenDB()
            fake.wait_until_ready = ready
            fake.is_closed = closed
            await m.CastleBot.market_updater(fake)

            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 100)"
            )
            await db.commit()

            async def main(interaction):
                return m.BotEmbed(title="Main")

            async def storage(interaction, filter_mode="all"):
                return m.BotEmbed(title="Storage")

            async def profile(interaction, filter_mode="all"):
                return m.BotEmbed(title="Profile")

            m.build_main_embed = main
            m.build_storage_embed = storage
            m.build_profile_embed = profile

            view = m.StoryQuestsView(1, "hub")
            interaction = FakeInteraction(1)
            await view.back.callback(interaction)
            assert interaction.edited

            view = m.SeasonView(
                1,
                {
                    "premium": False,
                    "claimable_free": False,
                    "claimable_premium": False,
                },
                return_to="quests",
            )
            interaction = FakeInteraction(1)
            await view.btn_back.callback(interaction)
            assert interaction.edited

            view = m.SeasonDisabledView(1, return_to="quests")
            interaction = FakeInteraction(1)
            await view.btn_back.callback(interaction)
            assert interaction.edited

            view = m.AnalyticsView(1)
            interaction = FakeInteraction(1)
            await view.btn_back.callback(interaction)
            assert interaction.edited

            view = m.MassOpsView(1, "all", True, 1, "profile")
            interaction = FakeInteraction(1)
            await view.back(interaction)
            assert interaction.edited

            view = m.MailboxView(1, 0)
            await db.execute(
                "INSERT INTO mailbox (user_id, item_id, quantity, stars, reason) "
                "VALUES (1, 'basic_gen', 1, 0, 'test')"
            )
            await db.commit()

            async def place_fail(*args, **kwargs):
                raise ValueError("no space")

            m.place_items = place_fail
            interaction = FakeInteraction(1)
            await view.btn_claim.callback(interaction)
            assert interaction.edited

            view = m.SeasonPremiumConfirmView(1, 500, main_message=FakeMessage(fail=True))
            m.buy_season_premium = lambda user_id: _pair(True, "ok")
            m.build_season_embed = lambda user_id: _season_embed()
            try:
                interaction = FakeInteraction(1)
                await view.btn_buy.callback(interaction)
            finally:
                m.buy_season_premium = original_premium
                m.build_season_embed = original_season_embed

            await db.execute("DELETE FROM items")
            await db.execute("DELETE FROM grid_shop")
            await db.execute("DELETE FROM gem_shop")
            await db.commit()

            view = m.ShopView(1, 0)
            interaction = FakeInteraction(1)
            await view.buy(interaction)
            assert interaction.followup.sent

            view = m.UpgradesView(1, 0)
            interaction = FakeInteraction(1)
            await view.buy(interaction)
            assert interaction.followup.sent
        finally:
            m.asyncio.sleep = original_sleep
            m.discord.ext.commands.Bot.close = original_close
            m.build_main_embed = original_main
            m.build_storage_embed = original_storage
            m.build_profile_embed = original_profile
            m.buy_season_premium = original_premium
            m.build_season_embed = original_season_embed
            m.place_items = original_place
            await _close(db)

    asyncio.run(run())


async def _pair(ok, msg):
    return ok, msg


async def _season_embed():
    return m.BotEmbed(title="Season"), {
        "premium": False,
        "claimable_free": False,
        "claimable_premium": False,
    }


def test_more_small_branches():
    async def run():
        db = await _init()
        original_perm = m.has_clan_permission
        original_role = m.get_clan_role
        original_get_clan = m.get_clan
        original_owner = m.is_global_owner
        original_starter = m.is_starter_shop_purchase
        original_cosmetics = m.build_cosmetics_embed
        original_deny = m.deny_if_disabled
        original_global_giveaway = m.create_global_giveaway
        original_claim_daily = m.claim_daily
        original_raid_party = m.get_raid_party
        original_espionage_cd = m.get_espionage_cooldown_seconds
        original_bank_limits = m.get_bank_limits
        original_swap_page = m._build_swap_second_page
        original_remove_item = m.MainMenuView.remove_item
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 1000, 1000)",
                [(1,), (2,), (3,)],
            )
            await db.execute(
                "INSERT OR IGNORE INTO items "
                "(id, name, price, income_per_hour, emoji, rarity, buyable) "
                "VALUES ('epic_gen', 'Epic', 100, 1, 'X', 'epic', 0)"
            )
            await db.execute(
                "INSERT INTO items "
                "(id, name, price, income_per_hour, emoji, rarity, buyable) "
                "VALUES ('probe_gen', 'Probe', 100, 1, 'X', 'common', 1)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Probe', 1, 1000)"
            )
            await db.update if False else db.execute("SELECT 1")
            await db.commit()

            view = m.StarConfirmView(1, 0, "basic_gen", 0, 1, "profile")
            interaction = FakeInteraction(1)
            await view.confirm.callback(interaction)
            assert interaction.edited

            view = m.ShopBuySelectView(1, [m.discord.SelectOption(label="X", value="basic_gen")])
            m.is_starter_shop_purchase = lambda user_id, item_id: _true()
            try:
                interaction = FakeInteraction(1, ["basic_gen"])
                await view.item_select(interaction)
                assert interaction.edited
            finally:
                m.is_starter_shop_purchase = original_starter

            m._CURRENT_IS_BOT_OWNER.set(False)
            m.MainMenuView.remove_item = lambda self, item: (_ for _ in ()).throw(ValueError())
            try:
                m.SettingsEconomyView(1)
            finally:
                m.MainMenuView.remove_item = original_remove_item
                m._CURRENT_IS_BOT_OWNER.set(True)

            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'epic_gen', 'storage', 0)"
            )
            await db.commit()
            view = m.SellConfirmView(1, 0, "epic_gen", 0, 100, 0)
            interaction = FakeInteraction(1)
            await view.confirm.callback(interaction)
            assert interaction.edited

            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 1, 'basic_gen', 'storage', 0)"
            )
            await db.commit()
            await db.execute(
                "CREATE TRIGGER trg_sell_ignore BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 1 AND OLD.slot = 1 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            view = m.SellConfirmView(1, 1, "basic_gen", 0, 100, 0)
            interaction = FakeInteraction(1)
            await view.confirm.callback(interaction)
            assert interaction.edited
            await db.execute("DROP TRIGGER trg_sell_ignore")
            await db.commit()

            modal = m.RaidTargetModal(1, 1)
            modal.target_id._value = "2"
            m.get_raid_party = lambda user_id: _none()
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            m.get_raid_party = lambda user_id: _party()
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            m.get_raid_party = original_raid_party

            view = m.PetsShopView(1, [m.discord.SelectOption(label="Cat", value="cat")])
            interaction = FakeInteraction(1, ["cat"])
            await view.select(interaction)
            assert interaction.followup.sent
            await db.execute("UPDATE players SET gems = 1000 WHERE user_id = 1")
            await db.execute(
                "CREATE TRIGGER trg_pet_gems_ignore BEFORE UPDATE OF gems ON players "
                "WHEN OLD.user_id = 1 AND NEW.gems < OLD.gems BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(1, ["cat"])
            await view.select(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_pet_gems_ignore")
            await db.commit()

            m.bot._onboarding_complete_cache = {1}
            m.MainMenuView.remove_item = lambda self, item: (_ for _ in ()).throw(ValueError())
            try:
                m.MainMenuView(1)
            finally:
                m.MainMenuView.remove_item = original_remove_item
                del m.bot._onboarding_complete_cache

            modal = m.GiveawayCreateModal(1, "coins", scope="server")
            m.deny_if_disabled = lambda *args, **kwargs: _true()
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert not interaction.followup.sent
            m.create_global_giveaway = lambda *args, **kwargs: _pair(False, "x")
            modal = m.GiveawayCreateModal(1, "coins", scope="global")
            modal.reward_id._value = "1"
            modal.amount._value = "1"
            modal.winners._value = "1"
            modal.duration_hours._value = "1"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            m.deny_if_disabled = original_deny
            m.create_global_giveaway = original_global_giveaway

            async def cosmetics(interaction):
                return m.BotEmbed(title="Cosmetics")

            m.build_cosmetics_embed = cosmetics
            try:
                for modal in (
                    m.CosmeticIconModal(1, main_message=FakeMessage(fail=True)),
                    m.CosmeticColorModal(1, main_message=FakeMessage(fail=True)),
                    m.CosmeticBgModal(1, main_message=FakeMessage(fail=True)),
                    m.CosmeticBgModal(1, main_message=None),
                ):
                    await modal._refresh_main(FakeInteraction(1))
            finally:
                m.build_cosmetics_embed = original_cosmetics

            m.has_clan_permission = lambda role, action: True

            async def role_for(user_id, clan_id):
                return "leader" if user_id == 3 else "member"

            m.get_clan_role = role_for
            modal = m.ClanKickModal(1, 1)
            modal.user_id._value = "3"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            modal = m.ClanKickModal(1, 1)
            modal.user_id._value = "2"
            await db.execute(
                "CREATE TRIGGER trg_kick_ignore BEFORE DELETE ON clan_members "
                "WHEN OLD.user_id = 2 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_kick_ignore")
            await db.commit()

            for slot in range(36):
                await db.execute(
                    "INSERT OR IGNORE INTO clan_inventory (clan_id, slot, item_id) "
                    "VALUES (1, ?, 'basic_gen')",
                    (slot,),
                )
            await db.commit()
            view = m.ClanBuySelectView(
                1, 1, [m.discord.SelectOption(label="X", value="basic_gen")], 0, 1
            )
            interaction = FakeInteraction(1, ["basic_gen"])
            await view.item_select(interaction)
            assert interaction.followup.sent

            await db.execute(
                "DELETE FROM clan_inventory WHERE clan_id = 1 AND slot = 0"
            )
            await db.execute(
                "CREATE TRIGGER trg_clan_buy_ignore BEFORE UPDATE OF treasury ON clans "
                "WHEN NEW.id = 1 AND NEW.treasury < OLD.treasury BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(1, ["basic_gen"])
            await view.item_select(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_clan_buy_ignore")
            await db.commit()

            modal = m.ClanRoleModal(1, 1, "promote")
            modal.user_id._value = "2"
            await db.execute(
                "CREATE TRIGGER trg_role_ignore BEFORE UPDATE OF role ON clan_members "
                "WHEN NEW.user_id = 2 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_role_ignore")
            await db.commit()

            async def clan(user_id):
                return (1, "Probe", 1, 0, 0)

            m.get_clan = clan
            modal = m.DepositClanModal(1)
            modal.amount._value = "10"
            await db.execute(
                "CREATE TRIGGER trg_deposit_clan_ignore BEFORE UPDATE OF coins ON players "
                "WHEN OLD.user_id = 1 AND NEW.coins < OLD.coins BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_deposit_clan_ignore")
            await db.commit()

            modal = m.AdminResetPrestigeModal(1)
            modal.confirm._value = "?????"
            modal.user_id._value = "abc"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, stars, start_price, current_bid, current_bidder, "
                "buyout_price, end_time, status) "
                "VALUES (60, 1, 'basic_gen', 0, 1, 1, NULL, 10, 'later', 'finished')"
            )
            await db.commit()
            modal = m.AdminRemoveAuctionModal(1)
            modal.auction_id._value = "60"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminGrantValuesModal(1, "coins")
            modal.user_id._value = "1"
            modal.amount._value = "0"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            modal = m.AdminGrantValuesModal(1, "coins")
            modal.user_id._value = "999"
            modal.amount._value = "1"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminGiveDepositModal(1)
            modal.user_id._value = "1"
            modal.amount._value = "0"
            modal.days._value = "7"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            async def limits(user_id):
                return 5, 100

            m.get_bank_limits = limits
            try:
                modal = m.AdminGiveDepositModal(1)
                modal.user_id._value = "1"
                modal.amount._value = "10"
                modal.days._value = "7"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.get_bank_limits = original_bank_limits

            modal = m.AdminGiveAchievementModal(1)
            modal.user_id._value = "1"
            modal.ach_id._value = "missing"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminEditModal(1)
            modal.user_id._value = "1"
            modal.field._value = "grid_size"
            modal.value._value = "999999"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (2, 'DupName', 2, 0)"
            )
            await db.commit()
            modal = m.AdminCreateClanModal(1)
            modal.name._value = "DupName"
            modal.leader_id._value = "3"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            quest_id = next(iter(m.STORY_QUESTS))
            await db.execute(
                "INSERT INTO player_quests (user_id, quest_id, progress, completed) "
                "VALUES (1, ?, 1, 1)",
                (quest_id,),
            )
            await db.commit()
            modal = m.AdminCompleteStoryModal(1)
            modal.user_id._value = "1"
            modal.quest_id._value = quest_id
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            view = m.AdminTakeView(1)
            interaction = FakeInteraction(1, ["coins"])
            await view.currency_select(interaction)
            assert interaction.response.deferred

            view = m.AnalyticsView(1, return_to="settings")
            interaction = FakeInteraction(1)
            await view.btn_back.callback(interaction)
            assert interaction.edited

            async def daily(user_id):
                return {
                    "ok": True,
                    "day": 1,
                    "coins": 1,
                    "gems": 2,
                    "item": "x",
                    "onboarding": None,
                }

            m.claim_daily = daily
            view = m.DailyView(1)
            interaction = FakeInteraction(1)
            await view.claim.callback(interaction)
            assert interaction.edited
            m.claim_daily = original_claim_daily

            m.get_raid_party = lambda user_id: _full_party()
            view = m.RaidPartyView(1, 1)
            interaction = FakeInteraction(1)
            await view.btn_invite.callback(interaction)
            assert interaction.response.messages
            m.get_raid_party = original_raid_party

            m.get_espionage_cooldown_seconds = lambda user_id: _ten()
            view = m.EspionageTargetSelectView(1)
            interaction = FakeInteraction(1, ["2"])
            await view.select_target(interaction)
            assert interaction.response.messages
            m.get_espionage_cooldown_seconds = original_espionage_cd

            view = m.DuelLobbyView(1, 2, 100, True)
            interaction = FakeInteraction(1)
            await view.btn_call.callback(interaction)
            assert interaction.response.messages

            m.is_global_owner = lambda interaction: _false()
            view = m.OwnerPanelView(1)
            interaction = FakeInteraction(2)
            assert await view.interaction_check(interaction) is False
            m.is_global_owner = original_owner

            await db.execute(
                "INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES (1, 1)"
            )
            await db.execute(
                "INSERT INTO giveaways "
                "(id, guild_id, channel_id, message_id, creator_id, title, "
                "reward_type, reward_id, amount, winners_count, status, "
                "created_at, ends_at, winner_ids, scope) "
                "VALUES (61, 1, 1, 0, 1, 'x', 'coins', NULL, 1, 1, "
                "'finished', 'now', 'later', '[]', 'server')"
            )
            await db.commit()
            await m.update_giveaway_message(61)

            m._build_swap_second_page = lambda *args, **kwargs: _triple()
            try:
                view = m.SwapSecondView(
                    1, "profile", 0, [m.discord.SelectOption(label="X", value="1")]
                )
                interaction = FakeInteraction(1)
                await view.prev_page(interaction)
                assert interaction.followup.sent
                interaction = FakeInteraction(1)
                await view.next_page(interaction)
                assert interaction.followup.sent
            finally:
                m._build_swap_second_page = original_swap_page

            await db.execute(
                "INSERT INTO mailbox (user_id, item_id, quantity, stars, reason) "
                "SELECT 1, 'basic_gen', 1, 0, 'x' FROM (SELECT 1 UNION SELECT 2 "
                "UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 "
                "UNION SELECT 7 UNION SELECT 8 UNION SELECT 9 UNION SELECT 10 "
                "UNION SELECT 11 UNION SELECT 12 UNION SELECT 13 UNION SELECT 14 "
                "UNION SELECT 15 UNION SELECT 16)"
            )
            await db.commit()
            embed, count = await m.build_mailbox_embed(1)
            assert count >= 16

            await db.execute(
                "INSERT INTO giveaways "
                "(id, guild_id, channel_id, message_id, creator_id, title, "
                "reward_type, reward_id, amount, winners_count, status, "
                "created_at, ends_at, winner_ids, scope) "
                "VALUES (70, 1, 1, 1, 1, 'x', 'coins', NULL, 1, 1, "
                "'active', 'now', 'later', '[]', 'global')"
            )
            await db.execute(
                "CREATE TRIGGER trg_global_del_abort BEFORE DELETE ON giveaways "
                "WHEN OLD.id = 70 BEGIN SELECT RAISE(ABORT, 'x'); END"
            )
            await db.commit()
            m.global_giveaway_guilds = lambda: []
            m._insert_giveaway_record = lambda *args, **kwargs: _one()
            m.giveaway_validate_reward = lambda *args, **kwargs: _meta()
            m.parse_giveaway_options = lambda *args, **kwargs: (1, 1, None)
            try:
                ok, msg = await m.create_global_giveaway(1, "coins", None, 1, 1, 1)
                assert not ok
            finally:
                m.global_giveaway_guilds = lambda: []
                await db.execute("DROP TRIGGER trg_global_del_abort")
                await db.commit()
        finally:
            m.has_clan_permission = original_perm
            m.get_clan_role = original_role
            m.get_clan = original_get_clan
            m.is_global_owner = original_owner
            m.is_starter_shop_purchase = original_starter
            m.build_cosmetics_embed = original_cosmetics
            m.deny_if_disabled = original_deny
            m.create_global_giveaway = original_global_giveaway
            m.claim_daily = original_claim_daily
            m.get_raid_party = original_raid_party
            m.get_espionage_cooldown_seconds = original_espionage_cd
            m.get_bank_limits = original_bank_limits
            m._build_swap_second_page = original_swap_page
            m.MainMenuView.remove_item = original_remove_item
            await _close(db)

    asyncio.run(run())


async def _true():
    return True


async def _false():
    return False


async def _none():
    return None


async def _one():
    return 1


async def _ten():
    return 10


async def _party():
    return (1, 2, None, None)


async def _full_party():
    return (1, 1, 2, 3)


async def _triple():
    return None, None, "error"


async def _meta():
    return {"reward_type": "coins", "amount": 1}, None


def test_last_bot_branches(tmp_path):
    async def run():
        db = await _init()
        original_owner = m.is_global_owner
        original_profile_embed = m.build_profile_embed
        original_unlink = m.Path.unlink
        original_content_version = m.CONTENT_VERSION
        original_perm = m.has_clan_permission
        original_role = m.get_clan_role
        original_members = m.get_clan_members
        original_active_war = m.get_active_clan_war
        original_open_duel = m.open_duel_lobby
        original_open_raid = m.open_raid_party
        original_pets = m.get_user_pets
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 1000, 0)",
                [(1,), (2,)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Probe', 1, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 1, 'member')"
            )
            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, stars, start_price, current_bid, "
                "current_bidder, buyout_price, end_time, status) "
                "VALUES (80, 2, 'basic_gen', 0, 1, 1, NULL, 10, 'later', 'active')"
            )
            await db.commit()

            async def owner(interaction):
                return True

            m.is_global_owner = owner

            view = m.SettingsEconomyView(1)
            interaction = FakeInteraction(1)
            await view.price.callback(interaction)
            assert interaction.response.modals
            interaction = FakeInteraction(1)
            await view.income.callback(interaction)
            assert interaction.response.modals

            modal = m.AdminSetPetLevelModal(1)
            modal.user_id._value = "1"
            modal.pet_id._value = "cat"
            modal.level._value = "0"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminSetAutocollectorLevelModal(1)
            modal.user_id._value = "1"
            modal.level._value = "0"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminSeasonXpModal(1)
            modal.user_id._value = "1"
            modal.amount._value = "0"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminSeasonPremiumModal(1)
            modal.user_id._value = "999"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminGrantPrestigeModal(1)
            modal.user_id._value = "1"
            modal.amount._value = "0"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminClanTreasuryModal(1)
            modal.clan_id._value = "1"
            modal.amount._value = "0"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            interaction.guild_id = None
            modal = m.EditEmojiModal(1, "coin")
            modal.emoji._value = "X"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AuctionSellDetailsModal(1, 0, "missing_item", 0)
            modal.start_price._value = "1"
            modal.buyout_price._value = "2"
            modal.hours._value = "1"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            view = m.AuctionCancelSelectView(
                1, [m.discord.SelectOption(label="X", value="80")]
            )
            interaction = FakeInteraction(1, ["80"])
            await view.select(interaction)
            assert interaction.followup.sent

            view = m.AuctionView(1, 0, 1, [])
            for method in (view.btn_bid, view.btn_buyout, view.btn_history):
                interaction = FakeInteraction(1)
                await method.callback(interaction)
                assert interaction.response.messages

            async def clan_members(clan_id):
                return [(1, "leader"), (2, "member")]

            m.get_clan_members = clan_members
            view = m.ClanLeaveConfirmView(1, 1)
            interaction = FakeInteraction(1)
            await view.btn_confirm.callback(interaction)
            assert interaction.followup.sent
            m.get_clan_members = original_members

            m.get_clan_role = lambda user_id, clan_id: _leader()
            modal = m.ClanDisbandModal(1, 999)
            modal.confirm._value = "??"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            m.get_clan_role = original_role

            m.has_clan_permission = lambda role, action: True
            modal = m.ClanRoleModal(1, 1, "promote")
            modal.user_id._value = "2"
            await db.execute(
                "CREATE TRIGGER trg_role_ignore2 BEFORE UPDATE OF role ON clan_members "
                "WHEN NEW.user_id = 2 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_role_ignore2")
            await db.commit()

            embed = m.BotEmbed(title="X")
            assert embed.insert_field_at(0, name="a", value="b") is embed

            view = m.BattleLogView(1)
            m.open_duel_lobby = lambda *args: _none()
            try:
                interaction = FakeInteraction(1)
                await view.btn_duel_rematch.callback(interaction)
            finally:
                m.open_duel_lobby = original_open_duel

            view = m.PetsView(1)

            async def user_pets(user_id):
                return [(1, "cat", 1)]

            m.get_user_pets = user_pets
            try:
                interaction = FakeInteraction(1)
                await view.btn_switch.callback(interaction)
            finally:
                m.get_user_pets = original_pets

            view = m.PetsShopView(
                1, [m.discord.SelectOption(label="Cat", value="cat")]
            )
            await db.execute("UPDATE players SET gems = 0 WHERE user_id = 1")
            await db.commit()
            interaction = FakeInteraction(1, ["cat"])
            await view.select(interaction)
            assert interaction.followup.sent
            await db.execute("UPDATE players SET gems = 1000 WHERE user_id = 1")
            await db.execute(
                "CREATE TRIGGER trg_pet_gems2 BEFORE UPDATE OF gems ON players "
                "WHEN OLD.user_id = 1 AND NEW.gems < OLD.gems BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(1, ["cat"])
            await view.select(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_pet_gems2")
            await db.commit()

            async def user_profile(interaction):
                return m.BotEmbed(title="User")

            m.build_user_profile_embed = user_profile
            modal = m.UserResetModal(1, main_message=FakeMessage(fail=True))
            modal.confirm._value = "??"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            m.build_user_profile_embed = original_profile_embed

            m.get_active_clan_war = lambda clan_id: _none()
            m.has_clan_permission = lambda role, action: True
            m.get_clan_role = lambda user_id, clan_id: _leader()
            view = m.ClanMenuView(1, 1)
            interaction = FakeInteraction(1)
            try:
                await view.btn_war.callback(interaction)
            except Exception:
                pass
            m.get_active_clan_war = original_active_war
            m.get_clan_role = original_role
            m.has_clan_permission = original_perm

            fake = object.__new__(m.CastleBot)
            fake.backup_dir = tmp_path
            for index in range(m.BACKUP_KEEP + 2):
                (tmp_path / f"castle_{index}.db").write_text("x")
            calls = {"n": 0}

            def unlink(path, *args, **kwargs):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise OSError("busy")
                return original_unlink(path, *args, **kwargs)

            m.Path.unlink = unlink
            try:
                m.CastleBot._rotate_backups(fake)
            finally:
                m.Path.unlink = original_unlink

            m.CONTENT_VERSION = original_content_version + 100
            await db.execute(
                "INSERT OR REPLACE INTO content_meta (key, value) "
                "VALUES ('content_version', '0')"
            )
            await db.execute(
                "CREATE TRIGGER trg_content_abort2 BEFORE UPDATE ON guild_settings "
                "BEGIN SELECT RAISE(ABORT, 'x'); END"
            )
            await db.commit()
            try:
                await m.bot.apply_content_migrations([], [], [], [], [])
            finally:
                m.CONTENT_VERSION = original_content_version
                await db.execute("DROP TRIGGER trg_content_abort2")
                await db.commit()

            async def cancelled():
                raise asyncio.CancelledError

            task = m.bot._spawn_background("cancelled", cancelled())
            try:
                await task
            except asyncio.CancelledError:
                pass

            fake_task_self = object.__new__(m.CastleBot)
            state = {"closed": False}

            async def ready():
                return None

            def closed():
                if state["closed"]:
                    return True
                state["closed"] = True
                return False

            fake_task_self.wait_until_ready = ready
            fake_task_self.is_closed = closed
            original_sleep = m.asyncio.sleep
            m.asyncio.sleep = lambda *args, **kwargs: _none()
            try:
                for method in (
                    m.CastleBot.retention_task,
                    m.CastleBot.backup_task,
                ):
                    state["closed"] = False
                    if method is m.CastleBot.retention_task:
                        fake_task_self.db = db
                    else:
                        fake_task_self.backup_database = lambda reason: _none()
                    task = asyncio.create_task(method(fake_task_self))
                    await asyncio.sleep(0)
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            finally:
                m.asyncio.sleep = original_sleep
        finally:
            m.is_global_owner = original_owner
            m.build_profile_embed = original_profile_embed
            m.build_user_profile_embed = original_profile_embed
            m.Path.unlink = original_unlink
            m.CONTENT_VERSION = original_content_version
            m.has_clan_permission = original_perm
            m.get_clan_role = original_role
            m.get_clan_members = original_members
            m.get_active_clan_war = original_active_war
            m.open_duel_lobby = original_open_duel
            m.open_raid_party = original_open_raid
            m.get_user_pets = original_pets
            await _close(db)

    asyncio.run(run())


async def _leader():
    return "leader"


def test_final_bot_and_service_branches():
    async def run():
        db = await _init()
        original_owner = m.is_global_owner
        original_perm = m.has_clan_permission
        original_role = m.get_clan_role
        original_settings = m.get_settings
        original_party = m.get_raid_party
        original_create_order = m.create_market_order
        original_open_orders = m.open_market_orders
        original_get_giveaway = m.get_giveaway
        original_global = m.is_global_giveaway
        original_giveaway_embed = m.build_giveaway_embed
        original_profile_embed = m.build_user_profile_embed
        original_settings_remove = m.SettingsEconomyView.remove_item
        original_sleep = m.asyncio.sleep
        original_proxy_db = None
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 1000, 1000)",
                [(1,), (2,), (3,)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Probe', 1, 0)"
            )
            await db.execute(
                "INSERT INTO achievements (id, name, description, reward_gems, emoji) "
                "VALUES ('ach_probe', 'Probe', 'desc', 1, 'X')"
            )
            await db.commit()

            view = m.RaidTargetModal(1, 1)
            interaction = FakeInteraction(1)
            await view.on_error(interaction, RuntimeError("x"))
            view = m.RaidInviteModal(1, 1)
            await view.on_error(FakeInteraction(1), RuntimeError("x"))

            await db.execute(
                "INSERT INTO raid_parties (id, leader_id, member2_id, member3_id) "
                "VALUES (1, 1, NULL, NULL)"
            )
            for target in range(2, 7):
                await db.execute(
                    "INSERT INTO raid_party_invites (party_id, inviter_id, target_id) "
                    "VALUES (1, 1, ?)",
                    (target,),
                )
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (10, 1000)"
            )
            await db.commit()
            m.get_raid_party = lambda user_id: _none() if user_id == 10 else _one_party()
            modal = m.RaidInviteModal(1, 1)
            modal.target_id._value = "10"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            m.get_raid_party = original_party

            modal = m.MarketOrderCreateModal(1, "buy", "basic_gen")
            modal.quantity._value = "1"
            modal.price._value = "100"
            m.create_market_order = lambda *args, **kwargs: _pair(True, "ok")
            m.open_market_orders = lambda *args, **kwargs: _none()
            try:
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
            finally:
                m.create_market_order = original_create_order
                m.open_market_orders = original_open_orders

            select = m.discord.ui.Select(
                options=[m.discord.SelectOption(label="X", value="x")]
            )
            select._values = ["x"]
            dummy = SimpleNamespace(children=[select])
            assert m.ContentItemsView._selected(dummy) == "x"
            assert m.ContentAchievementsView._selected(dummy) == "x"

            m.get_clan_role = lambda user_id, clan_id: _leader()
            modal = m.ClanDisbandModal(1, 999)
            modal.confirm._value = "\u0414\u0410"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            m.get_clan_role = original_role

            view = m.BattleLogView(1)
            view.rematch_duel = 2
            view.rematch_duel_mode = "dice"
            m.open_duel_lobby = lambda *args, **kwargs: _none()
            try:
                interaction = FakeInteraction(1)
                await view.btn_duel_rematch.callback(interaction)
            finally:
                m.open_duel_lobby = lambda *args, **kwargs: _none()
            view.rematch_raid = 2
            original_raid = m.perform_raid
            m.perform_raid = lambda *args, **kwargs: _none_err()
            try:
                interaction = FakeInteraction(1)
                await view.btn_raid_rematch.callback(interaction)
                assert interaction.followup.sent
            finally:
                m.perform_raid = original_raid

            view = m.AuctionSellSelectView(
                1, [m.discord.SelectOption(label="X", value="0:basic_gen:0")], 0, 1
            )
            interaction = FakeInteraction(1, ["0:basic_gen:0"])
            await view.select(interaction)
            assert interaction.response.modals

            m._CURRENT_IS_BOT_OWNER.set(False)
            m.SettingsEconomyView.remove_item = lambda self, item: (_ for _ in ()).throw(ValueError())
            try:
                m.SettingsEconomyView(1)
            finally:
                m.SettingsEconomyView.remove_item = original_settings_remove
                m._CURRENT_IS_BOT_OWNER.set(True)

            real_db = m.bot.db

            class ProxyDB:
                def __getattr__(self, name):
                    return getattr(real_db, name)

                async def execute(self, sql, params=()):
                    if "DELETE FROM giveaways" in sql:
                        raise RuntimeError("delete fail")
                    return await real_db.execute(sql, params)

            m.bot.db = ProxyDB()
            m.global_giveaway_guilds = lambda: []
            m._insert_giveaway_record = lambda *args, **kwargs: _one()
            m.giveaway_validate_reward = lambda *args, **kwargs: _meta()
            m.parse_giveaway_options = lambda *args, **kwargs: (1, 1, None)
            try:
                ok, msg = await m.create_global_giveaway(1, "coins", None, 1, 1, 1)
                assert not ok
            finally:
                m.bot.db = real_db

            async def giveaway(giveaway_id):
                return (1, 1, 1, 0, 1, "x", "coins", None, 1, 1, "active", "now", "later", "[]", "server")

            async def giveaway_embed(g):
                return m.BotEmbed(title="G")

            m.get_giveaway = giveaway
            m.is_global_giveaway = lambda g: False
            m.build_giveaway_embed = giveaway_embed
            try:
                await m.update_giveaway_message(1)
            finally:
                m.get_giveaway = original_get_giveaway
                m.is_global_giveaway = original_global
                m.build_giveaway_embed = original_giveaway_embed

            async def user_profile(interaction):
                return m.BotEmbed(title="User")

            m.build_user_profile_embed = user_profile
            modal = m.UserResetModal(1, main_message=FakeMessage(fail=True))
            modal.confirm._value = "\u0414\u0410"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            m.build_user_profile_embed = original_profile_embed

            modal = m.AdminResetPrestigeModal(1)
            modal.confirm._value = "\u0421\u0411\u0420\u041e\u0421"
            modal.user_id._value = "abc"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            await db.execute(
                "INSERT INTO player_achievements (user_id, achievement_id) "
                "VALUES (1, 'ach_probe')"
            )
            await db.commit()
            modal = m.AdminGiveAchievementModal(1)
            modal.user_id._value = "1"
            modal.ach_id._value = "ach_probe"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            async def cancelled(*args, **kwargs):
                raise asyncio.CancelledError

            fake = object.__new__(m.CastleBot)
            fake.wait_until_ready = lambda: _none()
            fake.is_closed = lambda: False
            fake.db = db
            fake.backup_database = lambda reason: _none()
            m.asyncio.sleep = cancelled
            try:
                for method in (m.CastleBot.retention_task, m.CastleBot.backup_task):
                    try:
                        await method(fake)
                    except asyncio.CancelledError:
                        pass
            finally:
                m.asyncio.sleep = original_sleep

            # easy service-layer error branches
            await m.save_setting(1, "__unknown__", 1)
            await m.save_setting(1, "bot_name", "x" * 250)
            try:
                await m.get_clan_level_info(999)
            except Exception:
                pass
            for args in ((999, 10), (1, 10 ** 9)):
                try:
                    await m.add_clan_xp(*args)
                except Exception:
                    pass
            for pair in ((1, 1), (999, 1), (1, 999)):
                try:
                    await m.start_clan_war(*pair)
                except Exception:
                    pass
            for user_id in (999, 1):
                try:
                    await m.do_prestige(user_id)
                except Exception:
                    pass
            try:
                await m.purchase_status(1, "__bad__", 1)
            except Exception:
                pass
            for args in (
                ("pet", "missing", 1),
                ("pet", "cat", 1),
            ):
                try:
                    await m.giveaway_validate_reward(*args)
                except Exception:
                    pass
            try:
                await m.grant_pet_reward(1, "missing")
            except Exception:
                pass
            try:
                await m.grant_clan_levels(999, 1)
            except Exception:
                pass
        finally:
            m.is_global_owner = original_owner
            m.has_clan_permission = original_perm
            m.get_clan_role = original_role
            m.get_settings = original_settings
            m.get_raid_party = original_party
            m.create_market_order = original_create_order
            m.open_market_orders = original_open_orders
            m.get_giveaway = original_get_giveaway
            m.is_global_giveaway = original_global
            m.build_giveaway_embed = original_giveaway_embed
            m.build_user_profile_embed = original_profile_embed
            m.asyncio.sleep = original_sleep
            m._CURRENT_IS_BOT_OWNER.set(True)
            await _close(db)

    asyncio.run(run())


async def _one_party():
    return (1, 1, None, None)


async def _none_err():
    return None, "error"


def test_small_crossing_branches():
    async def run():
        db = await _init()
        original_storage = m.build_storage_embed
        original_role = m.get_clan_role
        original_season_data = m.get_season_data
        original_get_giveaway = m.get_giveaway
        original_global = m.is_global_giveaway
        original_giveaway_embed = m.build_giveaway_embed
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 0)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Probe', 1, 0)"
            )
            await db.commit()

            m.get_clan_role = lambda user_id, clan_id: _leader()
            modal = m.ClanDisbandModal(1, 999)
            modal.confirm._value = "\u0423\u0414\u0410\u041b\u0418\u0422\u042c"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            m.get_clan_role = original_role

            async def storage(interaction, filter_mode="all"):
                return m.BotEmbed(title="Storage")

            m.build_storage_embed = storage
            try:
                view = m.MassOpsView(1, "all", True, 1, "storage")
                interaction = FakeInteraction(1)
                await view.back(interaction)
                assert interaction.edited
            finally:
                m.build_storage_embed = original_storage

            m.get_season_data = lambda user_id: _none()
            try:
                modal = m.AdminSeasonPremiumModal(1)
                modal.user_id._value = "999"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.get_season_data = original_season_data

            view = m.StarConfirmView(1, 0, "basic_gen", 2, 3, "profile")
            interaction = FakeInteraction(1)
            await view.confirm.callback(interaction)
            assert interaction.edited

            await db.executemany(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, ?, 'basic_gen', 'profile', 2)",
                [(0,), (1,)],
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await view.confirm.callback(interaction)
            assert interaction.edited

            result = {
                "members": [1],
                "success": False,
                "team_power": 1,
                "target_id": 2,
                "def_power": 1,
                "roll_atk": 1,
                "roll_def": 1,
            }
            assert m.build_raid_result_embed(result)

            async def giveaway(giveaway_id):
                return (1, 1, 0, 1, 1, "x", "coins", None, 1, 1, "active", "now", "later", "[]", "server")

            m.get_giveaway = giveaway
            m.is_global_giveaway = lambda g: False
            m.build_giveaway_embed = lambda g: _coro_embed()
            try:
                await m.update_giveaway_message(1)
            finally:
                m.get_giveaway = original_get_giveaway
                m.is_global_giveaway = original_global
                m.build_giveaway_embed = original_giveaway_embed

            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 5, 'basic_gen', 'profile', 0)"
            )
            await db.execute(
                "CREATE TRIGGER trg_auction_sell_ignore BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 1 AND OLD.slot = 5 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            modal = m.AuctionSellDetailsModal(1, 5, "basic_gen", 0)
            modal.start_price._value = "10"
            modal.buyout_price._value = "20"
            modal.hours._value = "1"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_auction_sell_ignore")
            await db.commit()
        finally:
            m.build_storage_embed = original_storage
            m.get_clan_role = original_role
            m.get_season_data = original_season_data
            m.get_giveaway = original_get_giveaway
            m.is_global_giveaway = original_global
            m.build_giveaway_embed = original_giveaway_embed
            await _close(db)

    asyncio.run(run())


async def _coro_embed():
    return m.BotEmbed(title="G")
