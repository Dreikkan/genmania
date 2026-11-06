import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_more_callbacks_89_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.messages = []
        self.modal = None

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_modal(self, modal):
        self.modal = modal


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeMessage:
    def __init__(self, fail=False):
        self.edits = []
        self.fail = fail
        self.deleted = False

    async def edit(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.edits.append((args, kwargs))

    async def delete(self):
        self.deleted = True


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(get_role=lambda rid: None)
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.message = FakeMessage()
        self.edited = []
        self.channel = None

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


async def _run_once(task, **patches):
    original_wait = m.bot.wait_until_ready
    original_closed = m.bot.is_closed
    original_sleep = m.asyncio.sleep
    state = {"closed": False}

    async def ready():
        return None

    def closed():
        if state["closed"]:
            return True
        state["closed"] = True
        return False

    async def no_sleep(*args, **kwargs):
        return None

    m.bot.wait_until_ready = ready
    m.bot.is_closed = closed
    m.asyncio.sleep = no_sleep
    originals = {}
    try:
        for name, value in patches.items():
            originals[name] = getattr(m, name)
            setattr(m, name, value)
        await task()
    finally:
        m.bot.wait_until_ready = original_wait
        m.bot.is_closed = original_closed
        m.asyncio.sleep = original_sleep
        for name, value in originals.items():
            setattr(m, name, value)


def test_simple_view_callbacks():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 100)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0), "
                "(1, 1, 'basic_gen', 'profile', 0)"
            )
            await db.commit()

            original_deny = m.deny_if_disabled
            original_push = m.push_nav
            original_onboarding = m.complete_onboarding_step
            original_star = m.open_star_view
            original_craft = m.open_craft_view
            original_main = m.build_main_embed

            async def deny_false(*args):
                return False

            def push(*args):
                return None

            async def noop(*args, **kwargs):
                return None

            async def main(interaction):
                return m.BotEmbed(title="Main")

            m.deny_if_disabled = deny_false
            m.push_nav = push
            m.complete_onboarding_step = noop
            m.open_star_view = noop
            m.open_craft_view = noop
            m.build_main_embed = main
            try:
                view = m.MainMenuView(1)
                interaction = FakeInteraction(1)
                await view.tab_social.callback(interaction)
                assert interaction.edited

                view = m.QuestsView(1, "quests")
                interaction = FakeInteraction(1)
                await view.back.callback(interaction)
                assert interaction.edited

                view = m.QuestsView(1, "main")
                view.back_to_main = noop
                interaction = FakeInteraction(1)
                await view.back.callback(interaction)

                view = m.ProfileView(1)
                interaction = FakeInteraction(1)
                await view.stars_button.callback(interaction)
                assert interaction.response.deferred
                interaction = FakeInteraction(1)
                await view.craft_button.callback(interaction)
                assert interaction.response.deferred

                view = m.PvPTargetsView(1, [], "dice", 0, 0)
                interaction = FakeInteraction(1)
                await view.btn_profile.callback(interaction)
                assert interaction.response.messages
            finally:
                m.deny_if_disabled = original_deny
                m.push_nav = original_push
                m.complete_onboarding_step = original_onboarding
                m.open_star_view = original_star
                m.open_craft_view = original_craft
                m.build_main_embed = original_main

            view = m.MoveView(1, "profile", [m.discord.SelectOption(label="X", value="0:basic_gen:0")], 1, 2)
            interaction = FakeInteraction(1)
            await view.prev_page(interaction)
            assert interaction.edited
            interaction = FakeInteraction(1)
            await view.next_page(interaction)
            assert interaction.edited

            original_daily = m.build_daily_embed
            original_hub = m.CustomizationHubView

            async def daily(interaction):
                return m.BotEmbed(title="Daily")

            m.build_daily_embed = daily
            m.CustomizationHubView = lambda author_id: m.BotEmbed(title="Hub")
            try:
                view = m.DailyView(1, "hub")
                interaction = FakeInteraction(1)
                await view.back.callback(interaction)
                assert interaction.edited
                view = m.DailyView(1, "main")
                view.back_to_main = noop
                interaction = FakeInteraction(1)
                await view.back.callback(interaction)
            finally:
                m.build_daily_embed = original_daily
                m.CustomizationHubView = original_hub

            original_backup = m.bot.backup_database
            original_toggle = m.toggle_item_lock

            async def backup(reason):
                return SimpleNamespace(name="b.db")

            async def backup_none(reason):
                return None

            m.bot.backup_database = backup
            try:
                view = m.OwnerPanelView(1)
                interaction = FakeInteraction(1)
                await view.btn_backup.callback(interaction)
                assert interaction.followup.sent
                m.bot.backup_database = backup_none
                interaction = FakeInteraction(1)
                await view.btn_backup.callback(interaction)
                assert interaction.followup.sent
            finally:
                m.bot.backup_database = original_backup

            original_configure = m.GiveawayCreateModal
            original_admin_giveaways = m.open_admin_giveaways

            async def open_admin(*args):
                return None

            m.open_admin_giveaways = open_admin
            try:
                view = m.GiveawayCreateTypeView(1)
                interaction = FakeInteraction(1)
                await view.configure(interaction)
                assert interaction.response.messages
                view.reward_type = "coins"
                interaction = FakeInteraction(1)
                await view.configure(interaction)
                assert interaction.response.modal is not None

                view = m.GiveawayCreateTypeView(1, source="owner")
                interaction = FakeInteraction(1)
                await view.back(interaction)
                assert interaction.edited
                view = m.GiveawayCreateTypeView(1)
                interaction = FakeInteraction(1)
                await view.back(interaction)
                assert interaction.response.deferred
            finally:
                m.GiveawayCreateModal = original_configure
                m.open_admin_giveaways = original_admin_giveaways
        finally:
            await _close(db)

    asyncio.run(run())


def test_open_helpers_bulk_and_guild_sync():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000)"
            )
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "emoji, rarity, buyable) "
                "VALUES ('common_gen', 'Common', 100, 1, '⚙️', 'common', 1)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'common_gen', 'storage', 0)"
            )
            await db.commit()

            original_party = m.get_raid_party
            original_create = m.create_raid_party
            original_by_id = m.get_raid_party_by_id
            original_touch = m.touch_raid_party
            original_commit = m.commit_if_needed
            original_build = m.build_raid_party_embed

            async def noop(*args, **kwargs):
                return None

            async def fail(*args):
                raise ValueError("bad party")

            async def party_none(*args):
                return None

            async def party_row(*args):
                return (1, 1, None, None)

            async def build(*args):
                return m.BotEmbed(title="Party")

            m.get_raid_party = party_none
            m.create_raid_party = fail
            m.touch_raid_party = noop
            m.commit_if_needed = noop
            m.build_raid_party_embed = build
            try:
                interaction = FakeInteraction(1)
                await m.open_raid_party(interaction, 1, create=True)
                assert interaction.edited

                async def create_ok(uid):
                    return 1

                m.create_raid_party = create_ok
                m.get_raid_party_by_id = party_row
                interaction = FakeInteraction(1)
                await m.open_raid_party(interaction, 1, create=True)
                assert interaction.edited

                m.get_raid_party = party_none
                interaction = FakeInteraction(1)
                await m.open_raid_party(interaction, 1)
                assert interaction.edited
            finally:
                m.get_raid_party = original_party
                m.create_raid_party = original_create
                m.get_raid_party_by_id = original_by_id
                m.touch_raid_party = original_touch
                m.commit_if_needed = original_commit
                m.build_raid_party_embed = original_build

            original_targets = m.get_pvp_targets
            original_pvp_embed = m.build_pvp_targets_embed
            original_raid_cd = m.get_raid_cooldown_seconds
            original_duel_cd = m.get_duel_cooldown_seconds

            async def targets(*args):
                return []

            async def pvp_embed(*args):
                return m.BotEmbed(title="PvP")

            async def zero(user_id):
                return 0

            m.get_pvp_targets = targets
            m.build_pvp_targets_embed = pvp_embed
            m.get_raid_cooldown_seconds = zero
            m.get_duel_cooldown_seconds = zero
            try:
                interaction = FakeInteraction(1)
                await m.open_pvp_targets(interaction, 1)
                assert interaction.edited
            finally:
                m.get_pvp_targets = original_targets
                m.build_pvp_targets_embed = original_pvp_embed
                m.get_raid_cooldown_seconds = original_raid_cd
                m.get_duel_cooldown_seconds = original_duel_cd

            interaction = FakeInteraction(1)
            await m.open_clan_applications(interaction, 1, 1)
            assert interaction.edited

            original_sync = m.sync_guild_access
            original_guilds = type(m.bot).guilds

            async def sync(guild, reason="join"):
                return None

            m.sync_guild_access = sync
            try:
                type(m.bot).guilds = property(lambda self: [SimpleNamespace(id=1)])
                await m.sync_all_guild_access()
            finally:
                type(m.bot).guilds = original_guilds
                m.sync_guild_access = original_sync

            ok, message, count, total = await m.perform_bulk_sell(1, "bad")
            assert not ok
            ok, message, count, total = await m.perform_bulk_sell(1, "common")
            assert ok and count == 1
        finally:
            await _close(db)

    asyncio.run(run())


def test_market_modals_and_duel_callbacks():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000)"
            )
            await db.commit()

            original_buy = m.buy_market_item
            original_sell = m.sell_market_item
            original_create = m.create_market_order
            original_build = m.build_market_embed
            original_open = m.open_market_orders
            original_fill = m.fill_market_order

            async def ok(*args):
                return True, "ok"

            async def no(*args):
                return False, "no"

            async def build(interaction):
                return m.BotEmbed(title="Market"), 1

            async def noop(*args, **kwargs):
                return None

            m.build_market_embed = build
            m.open_market_orders = noop
            try:
                modal = m.MarketBuyModal(1, "basic_gen")
                modal.qty._value = "1"
                m.buy_market_item = ok
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.edited

                modal = m.MarketSellModal(1, "basic_gen")
                modal.qty._value = "1"
                m.sell_market_item = ok
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.edited

                modal = m.MarketOrderCreateModal(1, "sell", "basic_gen")
                modal.quantity._value = "1"
                modal.price._value = "13"
                m.create_market_order = no
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent

                view = m.MarketOrderFillConfirmView(1, 1, 0, "all")
                m.fill_market_order = ok
                interaction = FakeInteraction(1)
                await view.btn_confirm.callback(interaction)
                assert interaction.followup.sent
            finally:
                m.buy_market_item = original_buy
                m.sell_market_item = original_sell
                m.create_market_order = original_create
                m.build_market_embed = original_build
                m.open_market_orders = original_open
                m.fill_market_order = original_fill

            original_lobby = m.open_duel_lobby

            async def lobby(*args):
                return None

            m.open_duel_lobby = lobby
            try:
                view = m.DuelTargetSelectView(1)
                interaction = FakeInteraction(1, ["1"])
                await view.select_target(interaction)
                assert interaction.response.messages
                interaction = FakeInteraction(1, ["2"])
                await view.select_target(interaction)
                assert interaction.response.deferred
            finally:
                m.open_duel_lobby = original_lobby

            view = m.DuelChallengeView(1, 2, 10, "dice")
            view._schedule_delete(1)
            view.message = FakeMessage()
            view._delete_task = None
            view._schedule_delete(1)
            await view._delete_later(0)
            view.message = FakeMessage(fail=True)
            await view._delete_later(0)
            assert view.message

            original_deny = m.deny_content_edit
            original_update = m.update_achievement_content

            async def deny_false(interaction):
                return False

            async def update(*args, **kwargs):
                return True, "ok"

            m.deny_content_edit = deny_false
            m.update_achievement_content = update
            try:
                modal = m.EditAchievementRewardModal(
                    1,
                    ("a1", "Name", "Desc", 1, "🏆"),
                )
                modal.ach_id._value = "Bad ID"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
                modal.ach_id._value = "missing"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.deny_content_edit = original_deny
                m.update_achievement_content = original_update
        finally:
            await _close(db)

    asyncio.run(run())


def test_raid_target_clan_war_tax_and_swap_edges():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, ?)",
                [(1, 1000), (2, 1000)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader')"
            )
            await db.commit()

            modal = m.RaidTargetModal(1, None)
            modal.target_id._value = "bad"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            original_perform = m.perform_raid
            original_send = m.send_raid_result

            async def perform(*args):
                return None, "error"

            async def send(*args):
                return None

            m.perform_raid = perform
            m.send_raid_result = send
            try:
                modal = m.RaidTargetModal(1, None)
                modal.target_id._value = "2"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.perform_raid = original_perform
                m.send_raid_result = original_send

            original_attack = m.attack_clan_war
            original_war = m.get_active_clan_war
            original_build_war = m.build_clan_war_embed
            original_build_clan = m.build_clan_embed

            async def attack_fail(*args):
                return False, "no", False

            async def attack_win(*args):
                return True, "ok", True

            async def attack_hit(*args):
                return True, "ok", False

            async def war_none(*args):
                return None

            async def build(*args):
                return m.BotEmbed(title="X")

            m.build_clan_war_embed = build
            m.build_clan_embed = build
            try:
                view = m.ClanWarView(1, 1, 1)
                m.attack_clan_war = attack_fail
                interaction = FakeInteraction(1)
                await view.btn_attack.callback(interaction)
                assert interaction.followup.sent

                m.attack_clan_war = attack_win
                interaction = FakeInteraction(1)
                await view.btn_attack.callback(interaction)
                assert interaction.followup.sent

                m.attack_clan_war = attack_hit
                m.get_active_clan_war = war_none
                interaction = FakeInteraction(1)
                await view.btn_attack.callback(interaction)
                assert interaction.followup.sent
            finally:
                m.attack_clan_war = original_attack
                m.get_active_clan_war = original_war
                m.build_clan_war_embed = original_build_war
                m.build_clan_embed = original_build_clan

            original_rates = m.get_tax_rate_map
            original_parse = m._parse_db_time
            original_log = m.log

            async def fail_rates():
                raise RuntimeError("boom")

            m.get_tax_rate_map = fail_rates
            try:
                await _run_once(m.bot.tax_collector)
            finally:
                m.get_tax_rate_map = original_rates

            async def rates():
                return {1: 0.1}

            def parse_fail(value):
                raise RuntimeError("boom")

            m.get_tax_rate_map = rates
            m._parse_db_time = parse_fail
            try:
                await _run_once(m.bot.tax_collector)
            finally:
                m._parse_db_time = original_parse
                m.get_tax_rate_map = original_rates

            original_swap = m._build_swap_second_page

            async def swap_ok(*args):
                return m.BotEmbed(title="Swap"), None, None

            m._build_swap_second_page = swap_ok
            try:
                view = m.SwapSecondView(
                    1, "profile", 0, [m.discord.SelectOption(label="X", value="1")], 0, 1
                )
                interaction = FakeInteraction(1, ["1"])
                interaction.message = FakeMessage()
                await view.second_select(interaction)
                assert interaction.edited
            finally:
                m._build_swap_second_page = original_swap
        finally:
            await _close(db)

    asyncio.run(run())
