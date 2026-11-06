import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_coverage_91_part1_test", BOT_PATH
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

    async def edit(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
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
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


def test_interaction_checks_and_navigation_buttons():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000)"
            )
            await db.commit()

            option = m.discord.SelectOption(label="X", value="x")
            checks = (
                (m.ExchangeView(1), 2),
                (m.DuelChallengeView(1, 2, 10, "dice"), 1),
                (m.CraftSelectView(1, [option]), 2),
                (m.CraftConfirmView(1, "basic_gen"), 2),
                (m.MoveView(1, "profile", [option], 0, 1), 2),
            )
            for view, other in checks:
                interaction = FakeInteraction(other)
                assert await view.interaction_check(interaction) is False
                owner = 1 if other == 2 else 2
                interaction = FakeInteraction(owner)
                assert await view.interaction_check(interaction) is True

            original_push = m.push_nav
            original_profile = m.build_profile_embed
            original_user_profile = m.build_user_profile_embed
            original_guide = m.build_guide_section_page
            original_collection = m.build_collection_embed
            original_hub = m.open_trading_hub
            original_market = m.open_market_view

            def push(*args):
                return None

            async def embed(*args, **kwargs):
                return m.BotEmbed(title="X"), 1

            async def noop(*args, **kwargs):
                return None

            m.push_nav = push
            async def profile_embed(interaction):
                return _embed("Profile")

            async def user_profile_embed(interaction):
                return _embed("User")

            m.build_profile_embed = profile_embed
            m.build_user_profile_embed = user_profile_embed
            m.build_guide_section_page = embed
            m.build_collection_embed = embed
            m.open_trading_hub = noop
            m.open_market_view = noop
            try:
                view = m.MainMenuView(1)
                interaction = FakeInteraction(1)
                await view.tab_profile.callback(interaction)
                assert interaction.edited
                interaction = FakeInteraction(1)
                await view.tab_my_profile.callback(interaction)
                assert interaction.edited

                view = m.GuideView(1, 1)
                interaction = FakeInteraction(1)
                await view.prev_page(interaction)
                assert interaction.edited

                view = m.GuideSectionView(1, "key", 1, 0, 2)
                interaction = FakeInteraction(1)
                await view.btn_prev(interaction)
                assert interaction.edited
                interaction = FakeInteraction(1)
                await view.btn_next(interaction)
                assert interaction.edited

                view = m.CollectionView(1, 1, 2)
                interaction = FakeInteraction(1)
                await view.prev_page(interaction)
                assert interaction.edited
                interaction = FakeInteraction(1)
                await view.next_page(interaction)
                assert interaction.edited

                view = m.OrderBookSelectView(1, [option], 0, 1, "hub")
                interaction = FakeInteraction(1)
                await view.back(interaction)
                assert interaction.response.deferred
                view = m.OrderBookSelectView(1, [option], 0, 1, "market")
                interaction = FakeInteraction(1)
                await view.back(interaction)
                assert interaction.response.deferred

                view = m.OrderBookView(1, "basic_gen", "hub")
                interaction = FakeInteraction(1)
                await view.btn_back.callback(interaction)
                assert interaction.response.deferred
                view = m.OrderBookView(1, "basic_gen", "market")
                interaction = FakeInteraction(1)
                await view.btn_back.callback(interaction)
                assert interaction.response.deferred
            finally:
                m.push_nav = original_push
                m.build_profile_embed = original_profile
                m.build_user_profile_embed = original_user_profile
                m.build_guide_section_page = original_guide
                m.build_collection_embed = original_collection
                m.open_trading_hub = original_hub
                m.open_market_view = original_market
        finally:
            await _close(db)

    asyncio.run(run())


def _embed(title):
    return m.BotEmbed(title=title)


def test_exchange_market_massops_pet_and_admin_callbacks():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, ?, ?)",
                [(1, 1000, 100), (2, 0, 0)],
            )
            await db.execute(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level) "
                "VALUES (1, 'cat', 1)"
            )
            await db.commit()

            modal = m.CoinsToGemsModal(1)
            modal.amount._value = "0"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            modal = m.CoinsToGemsModal(1)
            modal.amount._value = "1"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            modal = m.CoinsToGemsModal(2)
            modal.amount._value = "12"
            interaction = FakeInteraction(2)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            view = m.MarketOrdersView(1, 0, 1, [], "all", None)
            interaction = FakeInteraction(1)
            await view.btn_fill.callback(interaction)
            assert interaction.response.messages
            view = m.MarketOrdersView(1, 0, 1, [], "all", 1)
            original_fill = m.open_market_order_fill_confirm

            async def fill(*args):
                return None

            m.open_market_order_fill_confirm = fill
            try:
                interaction = FakeInteraction(1)
                await view.btn_fill.callback(interaction)
                assert interaction.response.deferred
            finally:
                m.open_market_order_fill_confirm = original_fill

            original_move_storage = m.mass_move_zero_star_to_storage
            original_move_profile = m.mass_move_zero_star_to_profile

            async def move(*args):
                return True, "ok", 1

            m.mass_move_zero_star_to_storage = move
            m.mass_move_zero_star_to_profile = move
            try:
                view = m.MassOpsConfirmView(1, "all", "move_zero", "profile")
                interaction = FakeInteraction(1)
                await view.confirm.callback(interaction)
                assert interaction.edited
                view = m.MassOpsConfirmView(1, "all", "move_zero", "storage")
                interaction = FakeInteraction(1)
                await view.confirm.callback(interaction)
                assert interaction.edited
            finally:
                m.mass_move_zero_star_to_storage = original_move_storage
                m.mass_move_zero_star_to_profile = original_move_profile

            original_pets = m.build_pets_embed
            original_commit = m.commit_if_needed

            async def pets(interaction):
                return m.BotEmbed(title="Pets")

            async def commit():
                return None

            m.build_pets_embed = pets
            m.commit_if_needed = commit
            try:
                view = m.PetSwitchView(
                    1, [m.discord.SelectOption(label="Cat", value="cat")], "profile"
                )
                interaction = FakeInteraction(1, ["cat"])
                await view.select(interaction)
                assert interaction.followup.sent
            finally:
                m.build_pets_embed = original_pets
                m.commit_if_needed = original_commit

            original_owner = m.is_global_owner
            original_open = m.open_content_editor

            async def owner_false(interaction):
                return False

            async def owner_true(interaction):
                return True

            async def open_content(*args):
                return None

            view = m.AdminPanelPage2(1)
            m.is_global_owner = owner_false
            interaction = FakeInteraction(1)
            await view.btn_content(interaction)
            assert interaction.response.messages
            m.is_global_owner = owner_true
            m.open_content_editor = open_content
            try:
                interaction = FakeInteraction(1)
                await view.btn_content(interaction)
                assert interaction.response.deferred
            finally:
                m.is_global_owner = original_owner
                m.open_content_editor = original_open
        finally:
            await _close(db)

    asyncio.run(run())
