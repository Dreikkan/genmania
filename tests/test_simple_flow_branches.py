import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_simple_flow_branches_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self, fail_defer=False):
        self.deferred = False
        self.fail_defer = fail_defer
        self.messages = []
        self.modal = None

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        if self.fail_defer:
            raise m.discord.InteractionResponded.__new__(
                m.discord.InteractionResponded
            )
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_modal(self, modal):
        self.modal = modal


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
        self.deleted = False
        self.id = 1

    async def edit(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.edits.append((args, kwargs))

    async def delete(self):
        self.deleted = True


class FakeInteraction:
    def __init__(
        self,
        user_id=1,
        values=None,
        edit_mode="ok",
        followup_fail=False,
        fail_defer=False,
    ):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(get_role=lambda role_id: None)
        self.response = FakeResponse(fail_defer=fail_defer)
        self.followup = FakeFollowup(fail=followup_fail)
        self.data = {"values": values or []}
        self.channel = None
        self.message = FakeMessage()
        self.edit_mode = edit_mode
        self.edited = []

    async def edit_original_response(self, *args, **kwargs):
        if self.edit_mode == "not_found":
            raise m.discord.NotFound.__new__(m.discord.NotFound)
        if self.edit_mode == "http":
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.edited.append((args, kwargs))


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


def test_daily_bonus_member_and_error_helpers():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players "
                "(user_id, coins, last_daily, streak_days) "
                "VALUES (1, 1000, NULL, 3), (2, 1000, ?, 4)",
                (datetime.datetime.now().isoformat(),),
            )
            await db.commit()

            embed = await m.build_daily_embed(FakeInteraction(1))
            assert embed.title
            embed = await m.build_daily_embed(FakeInteraction(2))
            assert embed.title
            await db.execute(
                "UPDATE players SET last_daily = ? WHERE user_id = 1",
                (
                    (datetime.datetime.now() - datetime.timedelta(days=1))
                    .isoformat(),
                ),
            )
            await db.commit()
            embed = await m.build_daily_embed(FakeInteraction(1))
            assert embed.title
            await db.execute(
                "UPDATE players SET last_daily = ? WHERE user_id = 1",
                (
                    (datetime.datetime.now() - datetime.timedelta(days=5))
                    .isoformat(),
                ),
            )
            await db.commit()
            embed = await m.build_daily_embed(FakeInteraction(1))
            assert embed.title

            line = await m.get_total_bonus_line(1)
            assert isinstance(line, str)

            assert await m.resolve_guild_member(None, None) is None
            guild = SimpleNamespace(id=1, get_member=lambda uid: None)
            user = SimpleNamespace(id=1, guild=SimpleNamespace(id=1))
            assert await m.resolve_guild_member(guild, user) is user
            user2 = SimpleNamespace(
                id=2,
                roles=[],
                guild_permissions=SimpleNamespace(value=0),
            )
            assert await m.resolve_guild_member(guild, user2) is user2
            user3 = SimpleNamespace(id=3)
            guild3 = SimpleNamespace(
                id=1, get_member=lambda uid: SimpleNamespace(id=uid)
            )
            assert (await m.resolve_guild_member(guild3, user3)).id == 3
            guild4 = SimpleNamespace(
                id=1,
                get_member=lambda uid: None,
                fetch_member=lambda uid: None,
            )

            async def fetch_ok(uid):
                return SimpleNamespace(id=uid)

            guild4.fetch_member = fetch_ok
            assert (await m.resolve_guild_member(guild4, user3)).id == 3

            async def fetch_fail(uid):
                raise m.discord.NotFound.__new__(m.discord.NotFound)

            guild4.fetch_member = fetch_fail
            assert await m.resolve_guild_member(guild4, user3) is None
            assert await m.resolve_guild_member(
                SimpleNamespace(id=1), SimpleNamespace(id=1)
            ) is None

            interaction = FakeInteraction(1)
            await m.on_app_command_error(interaction, RuntimeError("boom"))
            assert interaction.response.messages
            interaction = FakeInteraction(1)
            interaction.response.deferred = True
            await m.on_app_command_error(interaction, RuntimeError("boom"))
            assert interaction.followup.sent
            interaction = FakeInteraction(1)
            interaction.response.send_message = AsyncRaise()
            await m.on_app_command_error(interaction, RuntimeError("boom"))
        finally:
            await _close(db)

    asyncio.run(run())


class AsyncRaise:
    async def __call__(self, *args, **kwargs):
        raise m.discord.HTTPException.__new__(m.discord.HTTPException)


def test_admin_back_prestige_safeview_and_views():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, streak_days) "
                "VALUES (1, 1000, 1)"
            )
            await db.commit()

            original_build_main = m.build_main_embed

            async def build_main(interaction):
                return m.BotEmbed(title="Main")

            m.build_main_embed = build_main
            try:
                view = m.AdminView(1)
                interaction = FakeInteraction(1)
                await view.back_to_main(interaction)
                assert interaction.edited

                interaction = FakeInteraction(1, edit_mode="not_found")
                await view.back_to_main(interaction)
                assert interaction.followup.sent

                interaction = FakeInteraction(1, edit_mode="http")
                await view.back_to_main(interaction)
                assert interaction.followup.sent

                interaction = FakeInteraction(1, fail_defer=True)
                await view.back_to_main(interaction)
                assert interaction.edited

                interaction = FakeInteraction(
                    1, edit_mode="http", followup_fail=True
                )
                await view.back_to_main(interaction)
            finally:
                m.build_main_embed = original_build_main

            original_prestige = m.do_prestige
            original_build = m.build_main_embed

            async def prestige_fail(*args):
                return False, "no", 0, 0

            async def prestige_ok(*args):
                return True, "ok", 1, 1

            async def build_main2(interaction):
                return m.BotEmbed(title="Main")

            m.build_main_embed = build_main2
            try:
                modal = m.PrestigeConfirmModal(1)
                modal.confirm._value = "НЕТ"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent

                m.do_prestige = prestige_fail
                modal = m.PrestigeConfirmModal(1)
                modal.confirm._value = "ПЕРЕРОДИТЬСЯ"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent

                m.do_prestige = prestige_ok
                modal = m.PrestigeConfirmModal(1)
                modal.confirm._value = "ПЕРЕРОДИТЬСЯ"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent

                modal = m.PrestigeConfirmModal(1)
                modal.confirm._value = "ПЕРЕРОДИТЬСЯ"
                interaction = FakeInteraction(1, edit_mode="http")
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.do_prestige = original_prestige
                m.build_main_embed = original_build

            safe = m.SafeView()
            interaction = FakeInteraction(1)
            assert await safe.interaction_check(interaction) is True
            interaction = FakeInteraction(1)
            await safe.on_error(interaction, RuntimeError("boom"), None)
            assert interaction.response.messages
            interaction = FakeInteraction(1)
            interaction.response.deferred = True
            await safe.on_error(interaction, RuntimeError("boom"), None)
            assert interaction.followup.sent
            interaction = FakeInteraction(1)
            interaction.response.send_message = AsyncRaise()
            await safe.on_error(interaction, RuntimeError("boom"), None)

            view = m.AchievementsView(1, 0)
            assert len(view.children) >= 3
            view = m.SettingsEconomyView(1)
            assert view.author_id == 1
            view = m.NotificationsView(1)
            toggle = view._make_toggle("daily_ready")
            interaction = FakeInteraction(1)
            original_build_notif = m.build_notifications_embed

            async def build_notif(interaction):
                return m.BotEmbed(title="Notifications")

            m.build_notifications_embed = build_notif
            try:
                await toggle(interaction)
                assert interaction.edited
                await toggle(interaction)
                assert interaction.edited
            finally:
                m.build_notifications_embed = original_build_notif
            interaction = FakeInteraction(1)
            await view.btn_back(interaction)
            assert interaction.edited
        finally:
            await _close(db)

    asyncio.run(run())


def test_extra_callback_branches():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000), (2, 1000)"
            )
            await db.commit()

            original_perform = m.perform_raid
            original_send = m.send_raid_result

            async def perform(*args):
                return {"ok": True}, None

            async def send(*args):
                return None

            m.perform_raid = perform
            m.send_raid_result = send
            try:
                view = m.PvPTargetsView(1, [], "dice", 0, 0)
                view.selected = {"user_id": 2}
                interaction = FakeInteraction(1)
                await view.btn_attack.callback(interaction)
                assert interaction.followup.sent is not None

                view = m.BattleLogView(1, "all", None, 2)
                interaction = FakeInteraction(1)
                await view.btn_raid_rematch.callback(interaction)
            finally:
                m.perform_raid = original_perform
                m.send_raid_result = original_send

            view = m.PvPTargetsView(1, [], "dice", 0, 0)
            interaction = FakeInteraction(1)
            await view.btn_attack.callback(interaction)
            assert interaction.response.messages

            view = m.BattleLogView(1, "all", None, None)
            interaction = FakeInteraction(1)
            await view.btn_raid_rematch.callback(interaction)
            assert interaction.response.messages

            original_deny = m.deny_if_disabled
            original_onboarding = m.complete_onboarding_step
            original_push = m.push_nav

            async def deny_false(interaction, feature):
                return False

            async def onboarding(*args):
                return None

            def push(*args):
                return None

            m.deny_if_disabled = deny_false
            m.complete_onboarding_step = onboarding
            m.push_nav = push
            try:
                view = m.MainMenuView(1)
                interaction = FakeInteraction(1)
                await view.tab_quests_hub.callback(interaction)
                assert interaction.edited
            finally:
                m.deny_if_disabled = original_deny
                m.complete_onboarding_step = original_onboarding
                m.push_nav = original_push

            original_advent = m.open_advent_day
            original_build_advent = m.build_advent_embed

            async def open_day(user_id, day):
                return True, "ok", {"coins": 1, "gems": 0, "item": None}

            async def build_advent(interaction, page):
                return m.BotEmbed(title="Advent")

            m.open_advent_day = open_day
            m.build_advent_embed = build_advent
            try:
                view = m.AdventView(1, 0)
                callback = view._make_day_callback(1)
                interaction = FakeInteraction(1)
                await callback(interaction)
                assert interaction.followup.sent
            finally:
                m.open_advent_day = original_advent
                m.build_advent_embed = original_build_advent

            original_profile = m.build_profile_embed

            async def build_profile(*args, **kwargs):
                return m.BotEmbed(title="Profile")

            m.build_profile_embed = build_profile
            try:
                view = m.MassOpsView(1, "all", True, 1, "profile")
                interaction = FakeInteraction(1)
                await view.back(interaction)
                assert interaction.edited
            finally:
                m.build_profile_embed = original_profile

            original_cd = m.get_espionage_cooldown_seconds
            original_set_cd = m.set_espionage_cooldown
            original_public = m.build_public_profile_embed

            async def zero(user_id):
                return 0

            async def set_cd(user_id):
                return None

            async def public(target_id, detailed=False):
                return m.BotEmbed(title="Profile")

            m.get_espionage_cooldown_seconds = zero
            m.set_espionage_cooldown = set_cd
            m.build_public_profile_embed = public
            try:
                view = m.EspionageTargetSelectView(1)
                interaction = FakeInteraction(1, ["1"])
                await view.select_target(interaction)
                assert interaction.response.messages
                interaction = FakeInteraction(1, ["2"])
                await view.select_target(interaction)
                assert interaction.edited
            finally:
                m.get_espionage_cooldown_seconds = original_cd
                m.set_espionage_cooldown = original_set_cd
                m.build_public_profile_embed = original_public
        finally:
            await _close(db)

    asyncio.run(run())


def test_pets_lock_autocollector_shop_and_mass_move():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, grid_size) "
                "VALUES (1, 10000, 1000, 9), (2, 0, 0, 9)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'storage', 0), "
                "(1, 1, 'basic_gen', 'profile', 0)"
            )
            await db.commit()

            original_feed = m.feed_active_pet
            original_build_pets = m.build_pets_embed

            async def feed_fail(user_id):
                return False, "no", 0, ""

            async def feed_ok(user_id):
                return True, "ok", 1, "cat"

            async def build_pets(interaction):
                return m.BotEmbed(title="Pets")

            m.build_pets_embed = build_pets
            try:
                view = m.PetsView(1, "profile")
                m.feed_active_pet = feed_fail
                interaction = FakeInteraction(1)
                await view.btn_feed.callback(interaction)
                assert interaction.followup.sent
                m.feed_active_pet = feed_ok
                interaction = FakeInteraction(1)
                await view.btn_feed.callback(interaction)
                assert interaction.edited
            finally:
                m.feed_active_pet = original_feed
                m.build_pets_embed = original_build_pets

            original_toggle = m.toggle_item_lock
            original_open_lock = m.open_lock_view

            async def toggle_fail(*args):
                return False, False, "no"

            async def toggle_ok(*args):
                return True, True, "ok"

            async def open_lock(*args):
                return None

            m.open_lock_view = open_lock
            try:
                view = m.LockSelectView(
                    1,
                    [m.discord.SelectOption(label="X", value="x")],
                    0,
                    1,
                )
                m.toggle_item_lock = toggle_fail
                interaction = FakeInteraction(1, ["0:basic_gen:0"])
                await view.item_select(interaction)
                assert interaction.followup.sent
                m.toggle_item_lock = toggle_ok
                interaction = FakeInteraction(1, ["0:basic_gen:0"])
                await view.item_select(interaction)
                assert interaction.followup.sent
            finally:
                m.toggle_item_lock = original_toggle
                m.open_lock_view = original_open_lock

            original_buy_auto = m.buy_autocollector
            original_upgrade_auto = m.upgrade_autocollector
            original_build_auto = m.build_autocollector_embed

            async def buy_fail(user_id):
                return False, "no"

            async def buy_ok(user_id):
                return True, "ok"

            async def upgrade_fail(user_id):
                return False, "no"

            async def upgrade_ok(user_id):
                return True, "ok"

            async def build_auto(interaction):
                return m.BotEmbed(title="Auto")

            m.build_autocollector_embed = build_auto
            try:
                view = m.AutocollectorView(1, "shop")
                m.buy_autocollector = buy_fail
                interaction = FakeInteraction(1)
                await view.btn_buy.callback(interaction)
                assert interaction.followup.sent
                m.buy_autocollector = buy_ok
                interaction = FakeInteraction(1)
                await view.btn_buy.callback(interaction)
                assert interaction.edited
                m.upgrade_autocollector = upgrade_fail
                interaction = FakeInteraction(1)
                await view.btn_upgrade.callback(interaction)
                assert interaction.followup.sent
                m.upgrade_autocollector = upgrade_ok
                interaction = FakeInteraction(1)
                await view.btn_upgrade.callback(interaction)
                assert interaction.edited
            finally:
                m.buy_autocollector = original_buy_auto
                m.upgrade_autocollector = original_upgrade_auto
                m.build_autocollector_embed = original_build_auto

            original_premium = m.buy_season_premium
            original_build_season = m.build_season_embed

            async def premium_fail(user_id):
                return False, "no"

            async def premium_ok(user_id):
                return True, "ok"

            async def build_season(user_id):
                return m.BotEmbed(title="Season"), {
                    "premium": False,
                    "claimable_free": False,
                    "claimable_premium": False,
                }

            m.build_season_embed = build_season
            try:
                view = m.SeasonPremiumConfirmView(1, 10, "hub", FakeMessage())
                m.buy_season_premium = premium_fail
                interaction = FakeInteraction(1)
                await view.btn_buy.callback(interaction)
                assert interaction.followup.sent
                m.buy_season_premium = premium_ok
                interaction = FakeInteraction(1)
                await view.btn_buy.callback(interaction)
                assert interaction.edited
            finally:
                m.buy_season_premium = original_premium
                m.build_season_embed = original_build_season

            original_open_shop = m.open_shop_buy_select

            async def open_shop(*args):
                return None

            m.open_shop_buy_select = open_shop
            try:
                view = m.ShopView(1, 0)
                interaction = FakeInteraction(1)
                await view.buy(interaction)
                assert interaction.edited is not None
            finally:
                m.open_shop_buy_select = original_open_shop

            interaction = FakeInteraction(1)
            await m.open_giveaway_create(interaction, 1)
            assert interaction.edited
            interaction = FakeInteraction(1)
            await m.open_giveaway_create(interaction, 1, "owner")
            assert interaction.edited

            ok, message, count = await m.mass_move_zero_star(
                1, "bad", "bad"
            )
            assert not ok
            ok, message, count = await m.mass_move_zero_star(
                2, "profile", "storage"
            )
            assert not ok
            ok, message, count = await m.mass_move_zero_star(
                1, "profile", "storage"
            )
            assert ok and count == 1
        finally:
            await _close(db)

    asyncio.run(run())
