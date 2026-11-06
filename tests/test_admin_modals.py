import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_admin_modals_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    async def defer(self, *args, **kwargs):
        return None


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(id=user_id, name="Admin")
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()


def test_admin_modals_update_target_player():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) "
                "VALUES (2, 1000, 10)"
            )
            await db.execute(
                "INSERT OR IGNORE INTO achievements "
                "(id, name, reward_gems) "
                "VALUES ('first_craft', 'Первый синтез', 5)"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            modal = m.AdminProfileModal(1)
            modal.user_id._value = "2"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminGiveItemModal(1)
            modal.user_id._value = "2"
            modal.item_id._value = "basic_gen"
            modal.quantity._value = "1"
            modal.location._value = "storage"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminGivePetModal(1)
            modal.user_id._value = "2"
            modal.pet_id._value = "cat"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminSetPetLevelModal(1)
            modal.user_id._value = "2"
            modal.pet_id._value = "cat"
            modal.level._value = "5"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminGiveAchievementModal(1)
            modal.user_id._value = "2"
            modal.ach_id._value = "first_craft"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminCompleteStoryModal(1)
            modal.user_id._value = "2"
            modal.quest_id._value = "q_first_gen"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminGiveDepositModal(1)
            modal.user_id._value = "2"
            modal.amount._value = "100"
            modal.days._value = "7"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminTakeValuesModal(1, "coins")
            modal.user_id._value = "2"
            modal.amount._value = "50"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminEditModal(1)
            modal.user_id._value = "2"
            modal.field._value = "gems"
            modal.value._value = "77"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            async with db.execute(
                "SELECT gems FROM players WHERE user_id = 2"
            ) as c:
                assert (await c.fetchone())[0] == 77
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
