import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_deep_ui2_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        return None

    async def send_modal(self, *args, **kwargs):
        return None


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.embed = None
        self.view = None
        self.message = SimpleNamespace(id=123)

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


def test_deep_ui_batch_two():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players "
                "(user_id, coins, gems, grid_size, catalysts) "
                "VALUES (1, 100000, 100000, 9, 5)"
            )
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) VALUES "
                "(1, 0, 'basic_gen', 'storage', 0), "
                "(1, 1, 'basic_gen', 'storage', 0), "
                "(1, 20, 'basic_gen', 'profile', 0), "
                "(1, 21, 'basic_gen', 'profile', 0), "
                "(1, 22, 'basic_gen', 'profile', 0), "
                "(1, 10, 'basic_gen', 'profile', 1)"
            )
            await db.commit()

            async with db.execute(
                "SELECT id FROM gem_shop LIMIT 1"
            ) as c:
                gem_upgrade = (await c.fetchone())[0]
            interaction = FakeInteraction(1, [gem_upgrade])
            upgrades = m.UpgradesBuySelectView(1, [], 0, 1)
            await upgrades.upgrade_select(interaction)
            assert interaction.followup.sent or interaction.embed is not None

            original_random = m.random.random
            m.random.random = lambda: 1.0
            try:
                interaction = FakeInteraction(1)
                craft = m.CraftConfirmView(1, "basic_gen")
                await craft.do_craft(interaction, True)
                assert interaction.embed is not None
            finally:
                m.random.random = original_random

            original_owner = m.is_global_owner

            async def owner(interaction):
                return True

            m.is_global_owner = owner
            try:
                modal = m.AddGeneratorModal(1)
                modal.__dict__["id"] = SimpleNamespace(value="test_gen")
                modal.name._value = "Тестовый генератор"
                modal.price._value = "100"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.embed is not None
            finally:
                m.is_global_owner = original_owner

            view = m.MoveView(1, "storage", [], 0, 2)
            interaction = FakeInteraction(1)
            await view.prev_page(interaction)
            assert interaction.view is not None
            interaction = FakeInteraction(1)
            await view.next_page(interaction)
            assert interaction.view is not None

            embed, swap_view, error = await m._build_swap_first_page(
                "storage", 1, 1, 0, None
            )
            assert embed is not None and not error

            interaction = FakeInteraction(1, ["1"])
            swap = m.SwapSecondView(1, "storage", 0, [], 0, 1)
            await swap.second_select(interaction)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            auction = m.AuctionSellDetailsModal(
                1, 10, "basic_gen", 0
            )
            auction.start_price._value = "100"
            auction.buyout_price._value = "0"
            auction.hours._value = "24"
            await auction.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            emoji = m.StarEmojiModal1(1, "basic_gen")
            emoji.e0._value = "<:basic_0:1>"
            emoji.e1._value = ""
            emoji.e2._value = ""
            await emoji.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            emoji2 = m.StarEmojiModal2(1, "basic_gen")
            emoji2.e3._value = "<:basic_3:3>"
            emoji2.e4._value = ""
            emoji2.e5._value = ""
            await emoji2.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            edit = m.EditEmojiModal(1, "_coin")
            edit.emoji._value = "👑"
            await edit.on_submit(interaction)
            assert interaction.followup.sent

            original_deny = m.deny_content_edit

            async def allow(interaction):
                return False

            m.deny_content_edit = allow
            try:
                interaction = FakeInteraction(1)
                ach = m.EditAchievementRewardModal(1)
                ach.ach_id._value = "first_craft"
                ach.name._value = "Новое"
                ach.description._value = ""
                ach.reward._value = "10"
                ach.emoji._value = ""
                await ach.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.deny_content_edit = original_deny
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
