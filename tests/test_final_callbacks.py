import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_final_callbacks_test", BOT_PATH
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
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(
            get_member=lambda uid: None,
            get_role=lambda rid: None,
        )
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.message = SimpleNamespace()
        self.edited = []
        self.created_at = datetime.datetime.now(datetime.UTC)

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


def test_social_shop_buttons_and_sort_menus():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (1, 0, 'basic_gen', 'profile'), "
                "(1, 0, 'basic_gen', 'storage')"
            )
            await db.commit()

            original_deny = m.deny_if_disabled
            original_push = m.push_nav
            original_auction = m.open_auction_view
            original_bank = m.open_bank_view
            original_market = m.build_market_embed
            original_upgrades = m.build_upgrades_page
            original_pets = m.build_pets_embed
            original_auto = m.build_autocollector_embed

            async def deny_false(*args):
                return False

            def push(*args):
                return None

            async def noop(*args, **kwargs):
                return None

            async def embed(*args, **kwargs):
                return m.BotEmbed(title="X"), 1

            async def embed1(*args, **kwargs):
                return m.BotEmbed(title="X")

            m.deny_if_disabled = deny_false
            m.push_nav = push
            m.open_auction_view = noop
            m.open_bank_view = noop
            m.build_market_embed = embed
            m.build_upgrades_page = embed
            m.build_pets_embed = embed1
            m.build_autocollector_embed = embed1
            try:
                view = m.SocialView(1)
                for name in ("btn_auction", "btn_bank", "btn_pvp"):
                    interaction = FakeInteraction(1)
                    await getattr(view, name).callback(interaction)
                    assert interaction.edited or interaction.response.messages or interaction.response.deferred

                view = m.ShopHubView(1)
                for name in ("btn_upgrades", "btn_pets", "btn_autocollector"):
                    interaction = FakeInteraction(1)
                    await getattr(view, name).callback(interaction)
                    assert interaction.edited
            finally:
                m.deny_if_disabled = original_deny
                m.push_nav = original_push
                m.open_auction_view = original_auction
                m.open_bank_view = original_bank
                m.build_market_embed = original_market
                m.build_upgrades_page = original_upgrades
                m.build_pets_embed = original_pets
                m.build_autocollector_embed = original_auto

            original_sort = m.sort_inventory_by
            original_quest = m.update_quest_progress
            original_profile = m.build_profile_embed
            original_storage = m.build_storage_embed

            async def sort(*args):
                return None

            async def profile(*args):
                return m.BotEmbed(title="Profile")

            async def storage(*args):
                return m.BotEmbed(title="Storage")

            m.sort_inventory_by = sort
            m.update_quest_progress = noop
            m.build_profile_embed = profile
            m.build_storage_embed = storage
            try:
                view = m.SortMenuView(1)
                interaction = FakeInteraction(1)
                await view._do_sort(interaction, "price_desc")
                assert interaction.edited
                view = m.StorageSortMenuView(1)
                interaction = FakeInteraction(1)
                await view._do_sort(interaction, "price_desc")
                assert interaction.edited
            finally:
                m.sort_inventory_by = original_sort
                m.update_quest_progress = original_quest
                m.build_profile_embed = original_profile
                m.build_storage_embed = original_storage
        finally:
            await _close(db)

    asyncio.run(run())


def test_star_select_pvp_target_and_market_orders():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000), (2, 1000)"
            )
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, price, quantity, filled, "
                "status, expires_at) VALUES "
                "(1, 1, 'sell', 'basic_gen', 13, 1, 0, 'active', ?)",
                ((datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat(),),
            )
            await db.commit()

            option = m.discord.SelectOption(
                label="X", value="profile:0:basic_gen:5"
            )
            view = m.StarSelectView(1, [option], 0, 1)
            interaction = FakeInteraction(1, ["profile:0:basic_gen:5"])
            await view.item_select(interaction)
            assert interaction.followup.sent

            original_star = m.show_star_confirm

            async def star(*args, **kwargs):
                return None

            m.show_star_confirm = star
            try:
                view = m.StarSelectView(1, [option], 0, 1)
                interaction = FakeInteraction(1, ["0:basic_gen:0"])
                await view.item_select(interaction)
                assert interaction.response.deferred
            finally:
                m.show_star_confirm = original_star

            original_lobby = m.open_duel_lobby

            async def lobby(*args):
                return None

            m.open_duel_lobby = lobby
            try:
                view = m.PvPTargetsView(1, [], "dice", 0, 0)
                interaction = FakeInteraction(1, ["1"])
                await view.select_user(interaction)
                assert interaction.response.messages
                interaction = FakeInteraction(1, ["2"])
                await view.select_user(interaction)
                assert interaction.response.deferred
            finally:
                m.open_duel_lobby = original_lobby

            original_cancel = m.cancel_market_order
            original_open = m.open_market_my_orders

            async def cancel(*args):
                return True, "ok"

            async def open_orders(*args):
                return None

            m.cancel_market_order = cancel
            m.open_market_my_orders = open_orders
            try:
                view = m.MarketMyOrdersView(1, [option], None, 0, 1)
                interaction = FakeInteraction(1)
                await view.cancel_order(interaction)
                assert interaction.response.messages
                view.selected_order = 1
                interaction = FakeInteraction(1)
                await view.cancel_order(interaction)
                assert interaction.followup.sent
            finally:
                m.cancel_market_order = original_cancel
                m.open_market_my_orders = original_open
        finally:
            await _close(db)

    asyncio.run(run())


def test_role_deletion_metrics_and_content_modals():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000)"
            )
            await db.commit()

            original_settings = m.get_settings

            async def settings(guild_id):
                return {"status_roles": {"vip": 10}}

            m.get_settings = settings
            try:
                interaction = FakeInteraction(1)
                await m.grant_status_role(interaction, 1, "vip")
                interaction = FakeInteraction(1)
                interaction.guild = None
                await m.grant_status_role(interaction, 1, "vip")
            finally:
                m.get_settings = original_settings

            original_sleep = m.asyncio.sleep

            async def no_sleep(*args):
                return None

            m.asyncio.sleep = no_sleep
            try:
                class Message:
                    async def delete(self):
                        return None

                await m.delete_message_later(Message(), 1)

                class BadMessage:
                    async def delete(self):
                        raise m.discord.HTTPException.__new__(
                            m.discord.HTTPException
                        )

                await m.delete_message_later(BadMessage(), 1)
            finally:
                m.asyncio.sleep = original_sleep

            await m.on_app_command_completion(
                FakeInteraction(1), SimpleNamespace(qualified_name="menu")
            )
            interaction = FakeInteraction(1)
            interaction.created_at = None
            await m.on_app_command_completion(
                interaction, SimpleNamespace(qualified_name="menu")
            )

            original_owner = m.is_global_owner
            original_update = m.update_item_content
            original_appearance = m.update_item_appearance

            async def owner_false(interaction):
                return False

            async def owner_true(interaction):
                return True

            async def update(*args):
                return True, "ok"

            async def appearance(*args):
                return True, "ok"

            item = (
                "basic_gen",
                "Basic",
                15,
                2,
                0,
                "⚙️",
                "common",
                1,
            )
            modal = m.ContentItemEditModal(1, item)
            interaction = FakeInteraction(1)
            m.is_global_owner = owner_false
            await modal.on_submit(interaction)
            assert interaction.response.messages
            m.is_global_owner = owner_true
            m.update_item_content = update
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.ContentItemAppearanceModal(1, item)
            interaction = FakeInteraction(1)
            m.is_global_owner = owner_false
            await modal.on_submit(interaction)
            assert interaction.response.messages
            m.is_global_owner = owner_true
            m.update_item_appearance = appearance
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            m.is_global_owner = original_owner
            m.update_item_content = original_update
            m.update_item_appearance = original_appearance
        finally:
            await _close(db)

    asyncio.run(run())


def test_giveaway_embed_auction_advent_and_duel_edges():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000), (2, 1000)"
            )
            await db.commit()

            embed = await m.build_giveaway_embed(None)
            assert "не найден" in embed.title

            base = (
                1,
                1,
                10,
                20,
                2,
                "G",
                "coins",
                None,
                10,
                1,
                "active",
                "2026-01-01",
                "bad",
                None,
                "server",
            )
            embed = await m.build_giveaway_embed(base)
            assert embed.title
            finished = list(base)
            finished[10] = "finished"
            finished[13] = "bad-json"
            embed = await m.build_giveaway_embed(tuple(finished))
            assert embed.title
            cancelled = list(base)
            cancelled[10] = "cancelled"
            embed = await m.build_giveaway_embed(tuple(cancelled))
            assert embed.title

            lot = (1, 2, "basic_gen", 0, 10, None, 20, "2026", "Basic", "⚙️")
            view = m.AuctionView(1, 0, 2, [lot], 1, 20)
            assert view is not None

            original_event = m.get_active_advent_event
            m.get_active_advent_event = lambda: (
                {"days": 30, "key": "x"},
                0,
            )
            try:
                view = m.AdventView(1, 1)
                assert view is not None
            finally:
                m.get_active_advent_event = original_event

            result = {
                "members": [1],
                "success": True,
                "team_power": 10,
                "synergy_pct": 0,
                "target_id": 2,
                "def_power": 5,
                "roll_atk": 10,
                "roll_def": 5,
                "loot": {},
                "capped": [],
            }
            embed = m.build_raid_result_embed(result)
            assert embed.title
            result["members"] = [1, 2]
            result["loot"] = {1: 10}
            result["capped"] = [1]
            result["target_capped"] = True
            embed = m.build_raid_result_embed(result)
            assert embed.title

            original_validate = m.validate_power_duel
            original_channel = m.DuelChallengeView

            async def deny(*args):
                return False, "no"

            m.validate_power_duel = deny
            interaction = FakeInteraction(1)
            await m.create_duel_challenge(interaction, 1, 2, 10, "power")
            assert interaction.followup.sent

            async def allow(*args):
                return True, ""

            m.validate_power_duel = allow
            interaction = FakeInteraction(1)
            interaction.channel = SimpleNamespace(
                send=lambda *args, **kwargs: (_ for _ in ()).throw(
                    m.discord.HTTPException.__new__(m.discord.HTTPException)
                )
            )

            async def send(*args, **kwargs):
                raise m.discord.HTTPException.__new__(m.discord.HTTPException)

            interaction.channel = SimpleNamespace(send=send)
            try:
                await m.create_duel_challenge(interaction, 1, 2, 10, "power")
                assert interaction.followup.sent
            finally:
                m.validate_power_duel = original_validate

            original_statuses = m.get_active_statuses
            original_open = m.open_status_duration_view

            async def statuses(user_id):
                return ["gold"]

            async def open_status(*args):
                return None

            m.get_active_statuses = statuses
            m.open_status_duration_view = open_status
            try:
                interaction = FakeInteraction(1)
                await m.open_upgrades_buy_select(
                    interaction,
                    1,
                    [
                        ("grid_4x4", "Small", 10, "🔲", "coins", 16),
                        ("vip", "VIP", 10, "💎", "gems", 0),
                        ("gold", "Gold", 10, "💎", "gems", 0),
                        ("owned", "Owned", 10, "⚙️", "coins", 0),
                    ],
                    {"owned"},
                    0,
                )
                assert interaction.edited
            finally:
                m.get_active_statuses = original_statuses
                m.open_status_duration_view = original_open
        finally:
            await _close(db)

    asyncio.run(run())


def test_build_main_embed_smoke():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 100, 10)"
            )
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "income_gems_per_hour, emoji, rarity, buyable) "
                "VALUES ('gem_gen', 'Gem', 10, 0, 1, '💎', 'rare', 1)"
            )
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'gem_gen', 'profile', 0)"
            )
            await db.commit()
            embed = await m.build_main_embed(FakeInteraction(1))
            assert embed.title
        finally:
            await _close(db)

    asyncio.run(run())


def test_bulk_sell_global_giveaway_and_advent_init():
    async def run():
        db = await _init()
        try:
            original_summary = m.get_bulk_sell_summary
            original_bulk = m.BulkSellConfirmView

            async def empty(user_id):
                return {"common": {"count": 0, "total": 0}}

            async def filled(user_id):
                return {"common": {"count": 2, "total": 10}}

            m.get_bulk_sell_summary = empty
            interaction = FakeInteraction(1)
            await m.open_bulk_sell_confirm(interaction, 1, "common")
            assert interaction.followup.sent

            m.get_bulk_sell_summary = filled
            m.BulkSellConfirmView = lambda *args: m.BotEmbed(title="X")
            try:
                interaction = FakeInteraction(1)
                await m.open_bulk_sell_confirm(interaction, 1, "common")
                assert interaction.edited
            finally:
                m.get_bulk_sell_summary = original_summary
                m.BulkSellConfirmView = original_bulk

            original_insert = m._insert_giveaway_record
            original_guilds = m.global_giveaway_guilds
            original_log = m.log_admin_action

            async def noop(*args, **kwargs):
                return None

            async def insert_fail(*args):
                raise ValueError("bad insert")

            async def insert_crash(*args):
                raise RuntimeError("boom")

            m.global_giveaway_guilds = lambda: []
            m.log_admin_action = noop
            try:
                ok, message = await m.create_global_giveaway(
                    1, "coins", None, 10, 0, 24
                )
                assert not ok
                m._insert_giveaway_record = insert_fail
                ok, message = await m.create_global_giveaway(
                    1, "coins", None, 10, 1, 24
                )
                assert not ok
                m._insert_giveaway_record = insert_crash
                ok, message = await m.create_global_giveaway(
                    1, "coins", None, 10, 1, 24
                )
                assert not ok
            finally:
                m._insert_giveaway_record = original_insert
                m.global_giveaway_guilds = original_guilds
                m.log_admin_action = original_log

            view = m.AdventView(1, 1)
            assert view is not None
        finally:
            await _close(db)

    asyncio.run(run())
