import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_extra_admin_market_test", BOT_PATH
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
    def __init__(self):
        self.edits = []

    async def edit(self, *args, **kwargs):
        self.edits.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.edited = []
        self.message = FakeMessage()
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


async def _submit(modal, **fields):
    interaction = FakeInteraction()
    for name, value in fields.items():
        getattr(modal, name)._value = str(value)
    await modal.on_submit(interaction)
    return interaction


def test_status_duration_and_market_order_confirm():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000)"
            )
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, price, quantity, filled, "
                "status, expires_at) "
                "VALUES (1, 1, 'sell', 'basic_gen', 13, 2, 0, 'active', ?), "
                "(2, 1, 'sell', 'basic_gen', 13, 1, 1, 'active', ?), "
                "(3, 1, 'sell', 'basic_gen', 13, 1, 0, 'closed', ?)",
                tuple(
                    (datetime.datetime.now() + datetime.timedelta(hours=1))
                    .isoformat()
                    for _ in range(3)
                ),
            )
            await db.commit()

            interaction = FakeInteraction(1)
            await m.open_market_order_fill_confirm(interaction, 1, 1, 0, "all")
            assert interaction.edited
            interaction = FakeInteraction(1)
            await m.open_market_order_fill_confirm(interaction, 1, 999, 0, "all")
            assert interaction.followup.sent
            interaction = FakeInteraction(1)
            await m.open_market_order_fill_confirm(interaction, 1, 2, 0, "all")
            assert interaction.followup.sent
            interaction = FakeInteraction(1)
            await m.open_market_order_fill_confirm(interaction, 1, 3, 0, "all")
            assert interaction.followup.sent

            original_purchase = m.purchase_status
            original_grant = m.grant_status_role
            original_embed = m.build_status_duration_embed

            async def purchase_fail(*args):
                return False, "no"

            async def purchase_ok(*args):
                return True, "ok"

            async def grant(*args):
                return None

            async def embed(*args):
                return m.BotEmbed(title="Status")

            m.grant_status_role = grant
            m.build_status_duration_embed = embed
            try:
                view = m.StatusDurationView(1, "vip", 0)
                callback = view._make_buy_callback(7)
                m.purchase_status = purchase_fail
                interaction = FakeInteraction(1)
                await callback(interaction)
                assert interaction.followup.sent
                m.purchase_status = purchase_ok
                interaction = FakeInteraction(1)
                await callback(interaction)
                assert interaction.edited
            finally:
                m.purchase_status = original_purchase
                m.grant_status_role = original_grant
                m.build_status_duration_embed = original_embed
        finally:
            await _close(db)

    asyncio.run(run())


def test_admin_advent_give_item_and_player_card():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 0, 0)",
                [(1,), (2,)],
            )
            await db.commit()

            original_event = m.get_active_advent_event
            original_log = m.log_admin_action
            original_exclude = m.enforce_top_exclusion
            original_grant = m.grant_item_or_compensation
            original_card = m.build_admin_player_card

            async def log(*args, **kwargs):
                return None

            async def exclude(*args, **kwargs):
                return None

            async def grant(*args, **kwargs):
                return "Item", True

            async def card(*args):
                return m.BotEmbed(title="Card")

            m.log_admin_action = log
            m.enforce_top_exclusion = exclude
            m.grant_item_or_compensation = grant
            m.build_admin_player_card = card
            try:
                m.get_active_advent_event = lambda: (
                    {"days": 30, "key": "x"},
                    0,
                )
                interaction = await _submit(
                    m.AdminOpenAdventModal(1), user_id="999", day="1"
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.AdminOpenAdventModal(1), user_id="1", day="1"
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.AdminOpenAdventModal(1), user_id="1", day="5"
                )
                assert interaction.followup.sent

                interaction = await _submit(
                    m.AdminPlayerIdModal(1), user_id="bad"
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.AdminPlayerIdModal(1), user_id="1"
                )
                assert interaction.followup.sent

                interaction = await _submit(
                    m.AdminGiveItemModal(1),
                    user_id="1",
                    item_id="basic_gen",
                    quantity="bad",
                    location="profile",
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.AdminGiveItemModal(1),
                    user_id="1",
                    item_id="basic_gen",
                    quantity="1",
                    location="bad",
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.AdminGiveItemModal(1),
                    user_id="1",
                    item_id="missing",
                    quantity="1",
                    location="profile",
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.AdminGiveItemModal(1),
                    user_id="1",
                    item_id="basic_gen",
                    quantity="1",
                    location="profile",
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.AdminGiveItemModal(1),
                    user_id="2",
                    item_id="basic_gen",
                    quantity="2",
                    location="storage",
                )
                assert interaction.followup.sent

                original_storage = m.get_storage_size

                async def storage_size(user_id):
                    return 0

                m.get_storage_size = storage_size
                try:
                    interaction = await _submit(
                        m.AdminGiveItemModal(1),
                        user_id="1",
                        item_id="basic_gen",
                        quantity="1",
                        location="storage",
                    )
                    assert interaction.followup.sent
                finally:
                    m.get_storage_size = original_storage
            finally:
                m.get_active_advent_event = original_event
                m.log_admin_action = original_log
                m.enforce_top_exclusion = original_exclude
                m.grant_item_or_compensation = original_grant
                m.build_admin_player_card = original_card
        finally:
            await _close(db)

    asyncio.run(run())


def test_modal_error_handler_and_giveaway_channel():
    async def run():
        class AsyncRaise:
            async def __call__(self, *args, **kwargs):
                raise m.discord.HTTPException.__new__(
                    m.discord.HTTPException
                )

        interaction = FakeInteraction(1)
        await m._handle_modal_error(interaction, RuntimeError("boom"))
        assert interaction.response.messages

        interaction = FakeInteraction(1)
        interaction.response.deferred = True
        await m._handle_modal_error(interaction, RuntimeError("boom"))
        assert interaction.followup.sent

        interaction = FakeInteraction(1)
        interaction.response.send_message = AsyncRaise()
        await m._handle_modal_error(interaction, RuntimeError("boom"))

        class BadChannel:
            def permissions_for(self, me):
                raise RuntimeError("boom")

        class GoodChannel:
            def permissions_for(self, me):
                return SimpleNamespace(
                    send_messages=True,
                    embed_links=True,
                    mention_everyone=True,
                )

        class NoPermChannel:
            def permissions_for(self, me):
                return SimpleNamespace(
                    send_messages=False,
                    embed_links=False,
                    mention_everyone=False,
                )

        guild = SimpleNamespace(
            system_channel=None,
            public_updates_channel=GoodChannel(),
            text_channels=[],
            me=None,
        )
        assert m.select_giveaway_channel(guild) is guild.public_updates_channel

        guild = SimpleNamespace(
            system_channel=BadChannel(),
            public_updates_channel=None,
            text_channels=[],
            me=object(),
        )
        assert m.select_giveaway_channel(guild) is guild.system_channel

        guild = SimpleNamespace(
            system_channel=None,
            public_updates_channel=None,
            text_channels=[NoPermChannel()],
            me=object(),
        )
        assert m.select_giveaway_channel(guild) is None

    asyncio.run(run())


def test_admin_profile_and_reset_branches():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 10)"
            )
            await db.executemany(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (1, ?, 'basic_gen', 'profile', 0)",
                [(slot,) for slot in range(31)],
            )
            await db.executemany(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (1, ?, 'basic_gen', 'storage', 0)",
                [(slot,) for slot in range(31)],
            )
            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, current_bid, current_bidder, "
                "end_time, status) "
                "VALUES (1, 1, 'basic_gen', 10, 2, ?, 'active')",
                (datetime.datetime.now().isoformat(),),
            )
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (2, 100)"
            )
            await db.commit()

            interaction = await _submit(
                m.AdminProfileModal(1), user_id="1"
            )
            assert interaction.followup.sent

            m.bot._onboarding_complete_cache = {1}
            try:
                modal = m.AdminResetModal(1)
                modal.user_id._value = "1"
                modal.confirm._value = "ДА"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                del m.bot._onboarding_complete_cache

            interaction = FakeInteraction(1)
            await m.build_main_embed(interaction)
            assert interaction is not None
        finally:
            await _close(db)

    asyncio.run(run())
