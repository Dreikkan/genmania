import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_coverage_98_targets", BOT_PATH)
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
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)


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


def test_plain_module_helpers():
    async def run():
        db = await _init()
        original_day_profile = m.SEASON_ACTIVE_DAY_PROFILE
        original_settings = m.get_settings
        original_quests = m.get_or_create_daily_quests
        original_onboarding_progress = m.get_onboarding_progress
        original_next_step = m.get_next_onboarding_step
        original_status = m.get_status_bonus
        original_clan = m.get_clan
        original_pet = m.get_pet_bonus
        original_title = m.get_title_bonus
        original_prestige = m.get_prestige_bonus
        original_collection = m.get_collection_bonus
        original_set = m.get_set_bonus
        original_pity = m.get_craft_pity
        original_sync = m.sync_guild_access
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 100)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Probe', 1, 0)"
            )
            await db.execute(
                "INSERT INTO clan_inventory (clan_id, slot, item_id, stars) "
                "VALUES (1, 0, 'basic_gen', 0)"
            )
            await db.executemany(
                "INSERT INTO mailbox "
                "(user_id, item_id, quantity, stars, reason) "
                "VALUES (1, 'basic_gen', 1, 0, 'test')",
                (),
            )
            for index in range(16):
                await db.execute(
                    "INSERT INTO mailbox "
                    "(user_id, item_id, quantity, stars, reason) "
                    "VALUES (1, 'basic_gen', 1, ?, 'test')",
                    (index,),
                )
            await db.commit()

            m.SEASON_ACTIVE_DAY_PROFILE = {"__unknown__": 1}
            assert m.season_expected_daily_xp() == 0
            m.SEASON_ACTIVE_DAY_PROFILE = original_day_profile

            assert m.get_emoji("__unknown__") == "❔"
            assert m.format_pet_effect_summary(m.PET_TYPES["cat"], None)
            try:
                await m.verify_columns(db, "items", ["__missing__"])
            except RuntimeError:
                pass

            guild = SimpleNamespace(id=1, owner_id=1, get_member=lambda uid: None)
            assert await m.resolve_guild_member(guild, SimpleNamespace()) is None
            access = await m.read_member_access(
                guild, SimpleNamespace(id=1, roles=[])
            )
            assert access["user_id"] == 1
            assert await m.get_guild_access_snapshot(999) is None
            assert (
                await m.has_admin_access(
                    SimpleNamespace(guild=None, guild_id=None)
                )
                is False
            )

            assert m.replace_emojis_in_text(123) == 123
            assert m.clip_embed_text("x" * 100, 10).endswith("…")
            embed = m.BotEmbed(title="X", description="Y")
            embed.set_author(name="Author")
            await m.fix_embed_emojis(embed)

            assert await m.calculate_passive_income(999) == (0, 0)
            assert await m.calculate_full_passive_income(999) == (0, 0)
            assert await m.get_menu_welcome_notification(999) is None

            async def zero(user_id, *args):
                return 0

            async def zero_pair(user_id, effect):
                return 0.0

            async def prestige(user_id):
                return 0.1

            async def no_clan(user_id):
                return None

            m.get_status_bonus = zero
            m.get_clan = no_clan
            m.get_pet_bonus = zero_pair
            m.get_title_bonus = zero_pair
            m.get_prestige_bonus = prestige
            m.get_collection_bonus = zero
            m.get_set_bonus = zero
            try:
                line = await m.get_total_bonus_line(1)
                assert "престиж" in line
            finally:
                m.get_status_bonus = original_status
                m.get_clan = original_clan
                m.get_pet_bonus = original_pet
                m.get_title_bonus = original_title
                m.get_prestige_bonus = original_prestige
                m.get_collection_bonus = original_collection
                m.get_set_bonus = original_set

            clan_embed = await m.build_clan_inventory_embed(
                (1, "Probe", 1, 0, 0)
            )
            assert clan_embed

            async def settings(guild_id):
                return {"custom_emojis": {}}

            async def no_quests(user_id):
                return [], {}, set()

            m.get_settings = settings
            m.get_or_create_daily_quests = no_quests
            try:
                quests_embed = await m.build_quests_embed(FakeInteraction(1))
                assert quests_embed
            finally:
                m.get_settings = original_settings
                m.get_or_create_daily_quests = original_quests

            assert await m.complete_onboarding_step(1, "__bad__") is None

            async def all_steps(user_id):
                return set(m.ONBOARDING_STEPS)

            m.get_onboarding_progress = all_steps
            m.get_next_onboarding_step = lambda completed: (None, None)
            try:
                onboarding = await m.build_onboarding_embed(
                    FakeInteraction(1)
                )
                assert onboarding
            finally:
                m.get_onboarding_progress = original_onboarding_progress
                m.get_next_onboarding_step = original_next_step

            assert await m.get_profile_rows(1) == await m.get_inventory_rows(
                1, "profile"
            )

            async def high_pity(user_id, item_id):
                return m.CRAFT_HARD_PITY - 1

            m.get_craft_pity = high_pity
            try:
                chance, pity, guaranteed = await m.get_craft_chance(
                    1, "basic_gen", False
                )
                assert guaranteed and chance == 1.0
            finally:
                m.get_craft_pity = original_pity

            await db.execute("DELETE FROM market_prices")
            await db.commit()
            interaction = FakeInteraction(1)
            await m.open_order_book_select(interaction, 1)
            assert interaction.followup.sent
            interaction = FakeInteraction(1)
            await m.open_market_history_select(interaction, 1)
            assert interaction.followup.sent
            interaction = FakeInteraction(1)
            await m.open_market_buy_select(interaction, 1)
            assert interaction.followup.sent

            assert m.global_giveaway_guilds() == []

            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, stars, start_price, current_bid, "
                "current_bidder, buyout_price, end_time, status) "
                "VALUES (50, 1, 'basic_gen', 0, 10, 10, NULL, NULL, "
                "'9999-01-01T00:00:00', 'active')"
            )
            await db.execute(
                "INSERT INTO clan_invites (id, clan_id, inviter_id, target_id) "
                "VALUES (1, 1, 1, 1)"
            )
            for invite_id in range(2, 28):
                await db.execute(
                    "INSERT INTO clan_invites "
                    "(id, clan_id, inviter_id, target_id) "
                    "VALUES (?, 1, 1, 1)",
                    (invite_id,),
                )
            await db.execute(
                "INSERT INTO giveaways "
                "(id, guild_id, channel_id, message_id, creator_id, title, "
                "reward_type, reward_id, amount, winners_count, status, "
                "created_at, ends_at, winner_ids, scope) "
                "VALUES (1, 1, 1, 0, 1, 'x', 'coins', NULL, 1, 1, "
                "'active', 'now', 'later', '[]', 'server')"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await m.open_clan_invites(interaction, 1)
            assert interaction.edited
            interaction = FakeInteraction(1)
            await m.open_auction_buyout_confirm(interaction, 1, 50)
            assert interaction.followup.sent
            await m.update_giveaway_message(1)

            await m.on_guild_remove(SimpleNamespace(id=1))
            await m.on_member_join(SimpleNamespace(id=1))
            await m.on_member_remove(SimpleNamespace(id=1))

            async def sync(*args, **kwargs):
                return None

            m.sync_guild_access = sync
            try:
                await m.on_guild_role_update(
                    SimpleNamespace(guild=SimpleNamespace(id=1)),
                    SimpleNamespace(guild=SimpleNamespace(id=1)),
                )
                await m.on_guild_role_delete(
                    SimpleNamespace(guild=SimpleNamespace(id=1))
                )
            finally:
                m.sync_guild_access = original_sync
        finally:
            await _close(db)

    asyncio.run(run())


def test_small_view_branches():
    async def run():
        db = await _init()
        original_build_advent = m.build_advent_embed
        original_open_day = m.open_advent_day
        original_commit = m.commit_if_needed
        original_build_profile = m.build_profile_embed
        original_build_storage = m.build_storage_embed
        original_open_bulk = m.open_bulk_sell_confirm
        original_open_raid = m.join_raid_party
        original_advent_event = m.get_active_advent_event
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 0)"
            )
            await db.execute(
                "INSERT INTO tax_log (user_id, amount, tax_type) "
                "VALUES (1, 10, 'daily')"
            )
            await db.commit()

            view = m.SafeView()
            await view.on_timeout()
            view.message = FakeMessage(fail=True)
            await view.on_timeout()
            view.author_id = 1
            interaction = FakeInteraction(2)
            interaction.response.deferred = True
            await view.check_owner(interaction)
            assert interaction.followup.sent

            view = m.DuelChallengeView(1, 2, 10, "dice")
            interaction = FakeInteraction(2)
            interaction.message = FakeMessage(fail=True)

            async def resolve(*args, **kwargs):
                return True, "ok"

            original_resolve = m.resolve_duel
            m.resolve_duel = resolve
            try:
                await view.accept.callback(interaction)
            finally:
                m.resolve_duel = original_resolve
            view = m.DuelChallengeView(1, 2, 10, "dice")
            interaction = FakeInteraction(2)
            interaction.message = FakeMessage(fail=True)
            await view.decline.callback(interaction)
            view = m.DuelChallengeView(1, 2, 10, "dice")
            view.resolved = True
            await view.on_timeout()
            view = m.DuelChallengeView(1, 2, 10, "dice")
            view.message = FakeMessage(fail=True)
            await view.on_timeout()
            view = m.DuelChallengeView(1, 2, 10, "dice")
            view.message = FakeMessage()
            view._delete_task = asyncio.create_task(asyncio.sleep(10))
            view._schedule_delete(1)
            view.message = FakeMessage(fail=True)
            await view._delete_later(0)
            view._delete_task.cancel()

            view = m.AdventView(1, 0)
            interaction = FakeInteraction(1)
            await view.btn_prev(interaction)
            interaction = FakeInteraction(1)
            await view.btn_next(interaction)

            async def advent_embed(*args, **kwargs):
                return m.BotEmbed(title="Advent")

            async def open_day(*args, **kwargs):
                return True, "ok", {"coins": 1, "gems": 2, "item": "x"}

            m.build_advent_embed = advent_embed
            m.open_advent_day = open_day
            try:
                callback = view._make_day_callback(1)
                interaction = FakeInteraction(1)
                await callback(interaction)
                assert interaction.followup.sent
            finally:
                m.build_advent_embed = original_build_advent
                m.open_advent_day = original_open_day

            view = m.RaidInviteView(1, 1, 2)
            interaction = FakeInteraction(2)
            interaction.response.deferred = True
            interaction.followup.fail = True
            await view.on_error(interaction, RuntimeError("x"), None)
            view = m.RaidInviteView(1, 1, 2)
            interaction = FakeInteraction(2)
            interaction.message = FakeMessage(fail=True)
            m.commit_if_needed = lambda: _none()
            try:
                await view.decline.callback(interaction)
            finally:
                m.commit_if_needed = original_commit
            view.message = FakeMessage(fail=True)
            await view._delete_later(0)

            view = m.CatalystSelectView(1, return_to="profile")
            interaction = FakeInteraction(1, ["25"])
            await view.quantity_select(interaction)
            assert interaction.edited
            await db.execute(
                "UPDATE players SET gems = 1000 WHERE user_id = 1"
            )
            await db.commit()

            async def profile_embed(interaction):
                return _embed("Profile")

            m.build_profile_embed = profile_embed
            try:
                interaction = FakeInteraction(1, ["1"])
                await view.quantity_select(interaction)
                assert interaction.followup.sent
            finally:
                m.build_profile_embed = original_build_profile

            view = m.SocialView(1)
            interaction = FakeInteraction(1)
            await view._back_to_social(interaction)
            interaction = FakeInteraction(1)
            await view.btn_taxes.callback(interaction)
            assert interaction.edited

            summary = {
                key: {"count": 0, "total": 0}
                for key in ("common", "uncommon", "rare", "epic", "dupes")
            }
            view = m.BulkSellView(1, summary)
            interaction = FakeInteraction(1)
            await view.back(interaction)
            callback = view._make_mode("common")
            interaction = FakeInteraction(1)
            m.open_bulk_sell_confirm = lambda *args: _none()
            try:
                await callback(interaction)
            finally:
                m.open_bulk_sell_confirm = original_open_bulk

            original_remove = m.UserProfileView.remove_item
            m.get_active_advent_event = lambda: (None, 0)
            m.UserProfileView.remove_item = lambda self, item: (_ for _ in ()).throw(ValueError())
            try:
                m.UserProfileView(1)
            finally:
                m.get_active_advent_event = original_advent_event
                m.UserProfileView.remove_item = original_remove
            view = m.UserProfileView(1)
            interaction = FakeInteraction(1)
            await view.btn_advent.callback(interaction)
            assert interaction.edited
        finally:
            await _close(db)

    asyncio.run(run())


async def _none():
    return None


def _embed(title):
    return m.BotEmbed(title=title)


def test_bank_modal_branches():
    async def run():
        db = await _init()
        original_limits = m.get_bank_limits
        original_deposit = m.get_deposit
        original_bank_embed = m.build_bank_embed
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 100)"
            )
            await db.commit()

            modal = m.BankDepositModal(1)
            modal.amount._value = "0"
            modal.days._value = "7"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            async def limits(user_id):
                return 10, 100

            m.get_bank_limits = limits
            try:
                modal = m.BankDepositModal(1)
                modal.amount._value = "100"
                modal.days._value = "7"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.get_bank_limits = original_limits

            async def no_deposit(user_id):
                return None

            m.get_deposit = no_deposit
            await db.execute(
                "CREATE TRIGGER trg_deposit_ignore BEFORE UPDATE OF coins ON players "
                "WHEN OLD.user_id = 1 AND NEW.coins < OLD.coins "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            try:
                modal = m.BankDepositModal(1)
                modal.amount._value = "10"
                modal.days._value = "7"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                await db.execute("DROP TRIGGER trg_deposit_ignore")
                await db.commit()

            modal = m.BankDepositModal(1, main_message=FakeMessage(fail=True))
            async def bank_embed(user_id):
                return m.BotEmbed(title="Bank"), False, False

            m.build_bank_embed = bank_embed
            try:
                await modal._refresh_main()
            finally:
                m.build_bank_embed = original_bank_embed

            modal = m.BankWithdrawModal(1)
            modal.confirm._value = "ДА"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.BankWithdrawModal(1, main_message=FakeMessage(fail=True))
            m.build_bank_embed = bank_embed
            try:
                await modal._refresh_main()
            finally:
                m.build_bank_embed = original_bank_embed
        finally:
            m.get_bank_limits = original_limits
            m.get_deposit = original_deposit
            m.build_bank_embed = original_bank_embed
            await _close(db)

    asyncio.run(run())
