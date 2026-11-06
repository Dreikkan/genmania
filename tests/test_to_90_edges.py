import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_to_90_edges_test", BOT_PATH
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

    async def send_modal(self, modal):
        self.messages.append((modal,))


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeMessage:
    def __init__(self):
        self.edits = []

    async def edit(self, *args, **kwargs):
        self.edits.append((args, kwargs))

    async def delete(self):
        return None


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
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
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


def test_shop_open_helpers_and_bulk_edges():
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

            original_shop = m.build_shop_page
            original_buy_select = m.open_shop_buy_select

            async def shop(interaction, page):
                return m.BotEmbed(title="Shop"), 2

            async def noop(*args, **kwargs):
                return None

            m.build_shop_page = shop
            m.open_shop_buy_select = noop
            try:
                view = m.ShopView(1, 1)
                interaction = FakeInteraction(1)
                await view.prev_page(interaction)
                assert interaction.edited
                interaction = FakeInteraction(1)
                await view.next_page(interaction)
                assert interaction.edited

                view = m.ShopBuySelectView(
                    1,
                    [m.discord.SelectOption(label="X", value="x")],
                    0,
                    2,
                )
                interaction = FakeInteraction(2)
                assert await view.interaction_check(interaction) is False
                interaction = FakeInteraction(1)
                assert await view.interaction_check(interaction) is True
                interaction = FakeInteraction(1)
                await view.prev_page(interaction)
                assert interaction.response.deferred
                interaction = FakeInteraction(1)
                await view.next_page(interaction)
                assert interaction.response.deferred
            finally:
                m.build_shop_page = original_shop
                m.open_shop_buy_select = original_buy_select

            option = m.discord.SelectOption(label="X", value="x")
            m.TitlesView(1, [option], 0, 1)

            interaction = FakeInteraction(1)
            await m.open_market_orders(interaction, 1, 0, "buy", 999)
            assert interaction.edited

            interaction = FakeInteraction(1)
            await m.open_pets_shop(interaction, 1)
            assert interaction.edited

            interaction = FakeInteraction(1)
            await m.open_auction_view(interaction, 1, 0, 999)
            assert interaction.edited

            ok, message, count, total = await m.perform_bulk_sell(1, "dupes")
            assert not ok
            ok, message, count, total = await m.perform_bulk_sell(1, "common")
            assert ok and count == 1
        finally:
            await _close(db)

    asyncio.run(run())


def test_background_error_branches_and_global_send():
    async def run():
        db = await _init()
        try:
            original_backup = m.bot.backup_database

            async def backup_fail(reason):
                raise RuntimeError("backup fail")

            m.bot.backup_database = backup_fail
            try:
                await _run_once(m.bot.backup_task)
            finally:
                m.bot.backup_database = original_backup

            original_db = m.bot.db

            class BrokenDB:
                async def execute(self, *args, **kwargs):
                    raise RuntimeError("db fail")

                async def commit(self):
                    return None

            m.bot.db = BrokenDB()
            try:
                await _run_once(m.bot.retention_task)
            finally:
                m.bot.db = original_db

            original_income = m.calculate_full_passive_income

            async def income_fail(user_id):
                raise RuntimeError("income fail")

            m.calculate_full_passive_income = income_fail
            try:
                await _run_once(m.bot.autocollector_task)
            finally:
                m.calculate_full_passive_income = original_income

            original_disabled = m.is_command_disabled
            original_channel = m.select_giveaway_channel
            original_send = m.send_giveaway_message

            async def disabled(guild_id, feature):
                return False

            async def no_channel(guild):
                return None

            async def send(*args):
                return FakeMessage()

            m.is_command_disabled = disabled
            m.select_giveaway_channel = no_channel
            m.send_giveaway_message = send
            try:
                assert (
                    await m._send_global_giveaway_to_guild(
                        SimpleNamespace(id=None), 1
                    )
                    is False
                )
                assert (
                    await m._send_global_giveaway_to_guild(
                        SimpleNamespace(id=1), 1
                    )
                    is False
                )
            finally:
                m.is_command_disabled = original_disabled
                m.select_giveaway_channel = original_channel
                m.send_giveaway_message = original_send
        finally:
            await _close(db)

    asyncio.run(run())


def test_craft_and_swap_edges():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, grid_size) "
                "VALUES (1, 1000, 1000, 9)"
            )
            await db.executemany(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, ?, 'basic_gen', 'profile', 0)",
                [(0,), (1,), (2,)],
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 3, 'basic_gen', 'profile', 0)"
            )
            await db.commit()

            original_chance = m.get_star_chance
            original_build = m.build_profile_embed
            original_quests = m.update_quest_progress
            original_story = m.update_story_quests
            original_achievements = m.check_achievements

            async def chance(*args):
                return 0.0, 0, False

            async def noop(*args, **kwargs):
                return None

            async def profile(interaction):
                return m.BotEmbed(title="Profile")

            async def achievements(user_id):
                return []

            m.get_star_chance = chance
            m.build_profile_embed = profile
            m.update_quest_progress = noop
            m.update_story_quests = noop
            m.check_achievements = achievements
            try:
                view = m.StarConfirmView(1, 0, "basic_gen", 0, 3, "profile")
                interaction = FakeInteraction(1)
                await view.confirm.callback(interaction)
                assert interaction.edited
            finally:
                m.get_star_chance = original_chance
                m.build_profile_embed = original_build
                m.update_quest_progress = original_quests
                m.update_story_quests = original_story
                m.check_achievements = original_achievements

            original_craft = m.get_craft_chance
            original_place = m.place_items
            original_random = m.random.random
            original_profile = m.build_profile_embed
            original_quests = m.update_quest_progress
            original_story = m.update_story_quests
            original_ach = m.check_achievements
            original_onboarding = m.complete_onboarding_step

            async def craft_chance(*args):
                return 1.0, 0, True

            async def place_fail(*args, **kwargs):
                raise ValueError("no space")

            async def profile(interaction):
                return m.BotEmbed(title="Profile")

            async def achievements(user_id):
                return []

            m.get_craft_chance = craft_chance
            m.place_items = place_fail
            m.random.random = lambda: 1.0
            m.build_profile_embed = profile
            m.update_quest_progress = noop
            m.update_story_quests = noop
            m.check_achievements = achievements
            m.complete_onboarding_step = noop
            try:
                interaction = FakeInteraction(1)
                await m.CraftConfirmView(1, "basic_gen").do_craft(interaction, False)
                assert interaction.edited
            finally:
                m.get_craft_chance = original_craft
                m.place_items = original_place
                m.random.random = original_random
                m.build_profile_embed = original_profile
                m.update_quest_progress = original_quests
                m.update_story_quests = original_story
                m.check_achievements = original_ach
                m.complete_onboarding_step = original_onboarding

            original_swap = m._build_swap_second_page

            async def swap(*args):
                return m.BotEmbed(title="Swap"), None, None

            m._build_swap_second_page = swap
            try:
                view = m.SwapSecondView(
                    1,
                    "profile",
                    0,
                    [m.discord.SelectOption(label="X", value="1")],
                    0,
                    1,
                )
                interaction = FakeInteraction(1, ["1"])
                await view.second_select(interaction)
                assert interaction.edited or interaction.followup.sent
                assert await m._build_swap_second_page(
                    "profile", 1, 0, 1
                )
            finally:
                m._build_swap_second_page = original_swap
        finally:
            await _close(db)

    asyncio.run(run())
