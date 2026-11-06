import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_admin_misc_test", BOT_PATH
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

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view

    async def delete_original_response(self):
        return None


def test_admin_misc_and_pets():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players "
                "(user_id, coins, gems, prestige_points, total_coins_earned) "
                "VALUES (1, 1000, 1000, 5, 500)"
            )
            await db.execute(
                "INSERT INTO user_pets_v2 "
                "(user_id, pet_id, level, last_fed) "
                "VALUES (1, 'cat', 1, NULL)"
            )
            await db.execute(
                "UPDATE players SET active_pet = 'cat' WHERE user_id = 1"
            )
            await db.execute(
                "INSERT INTO user_notifications "
                "(user_id, notif_type, enabled, last_sent) "
                "VALUES (1, 'pet_hungry', 1, '2020-01-01T00:00:00')"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            modal = m.AdminResetPrestigeModal(1)
            modal.user_id._value = "1"
            modal.confirm._value = "СБРОС"
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            async with db.execute(
                "SELECT prestige_points FROM players WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 0

            interaction = FakeInteraction(1)
            modal = m.AdminResetNotifCooldownModal(1)
            modal.user_id._value = "1"
            await modal.on_submit(interaction)
            async with db.execute(
                "SELECT last_sent FROM user_notifications "
                "WHERE user_id = 1 AND notif_type = 'pet_hungry'"
            ) as c:
                assert (await c.fetchone())[0] is None

            interaction = FakeInteraction(1)
            switch = m.PetSwitchView(1, [])
            await switch.select(
                FakeInteraction(1, ["none"])
            )
            async with db.execute(
                "SELECT active_pet FROM players WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] is None

            await db.execute(
                "UPDATE players SET active_pet = 'cat' WHERE user_id = 1"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            modal = m.AdminRemovePetModal(1)
            modal.user_id._value = "1"
            modal.pet_id._value = "cat"
            await modal.on_submit(interaction)
            async with db.execute(
                "SELECT active_pet FROM players WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] is None

            interaction = FakeInteraction(1)
            modal = m.PrestigeConfirmModal(1)
            modal.confirm._value = "НЕТ"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1, ["1"])
            quantity = m.BuyItemQuantityView(1, "basic_gen")
            await quantity.quantity_select(interaction)
            assert interaction.embed is not None

            m.UpgradesView(1, 0)

            interaction = FakeInteraction(1)
            modal = m.AdminResetModal(1)
            modal.user_id._value = "1"
            modal.confirm._value = "ДА"
            await modal.on_submit(interaction)
            assert interaction.followup.sent
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
