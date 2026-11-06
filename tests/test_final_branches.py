import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_final_branches_test", BOT_PATH
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


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(id=user_id, name="Tester")
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.embed = None
        self.view = None

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


def test_final_error_branches():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems, grid_size) "
                "VALUES (?, 1000, 1000, 9)",
                [(1,), (2,), (3,), (4,), (5,)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id) "
                "VALUES (1, 'Alpha', 1)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 1, 'member'), "
                "(3, 1, 'member')"
            )
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) VALUES "
                "(1, 20, 'basic_gen', 'profile', 0), "
                "(1, 21, 'basic_gen', 'profile', 0), "
                "(1, 22, 'basic_gen', 'profile', 0)"
            )
            await db.commit()

            async with db.execute(
                "SELECT id FROM grid_shop WHERE size > 9 LIMIT 2"
            ) as c:
                grids = [row[0] for row in await c.fetchall()]

            interaction = FakeInteraction(1, [grids[0]])
            upgrades = m.UpgradesBuySelectView(1, [], 0, 1)
            await upgrades.upgrade_select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1, [grids[0]])
            await upgrades.upgrade_select(interaction)
            assert interaction.followup.sent

            await db.execute(
                "UPDATE players SET coins = 0 WHERE user_id = 1"
            )
            await db.commit()
            interaction = FakeInteraction(1, [grids[1]])
            await upgrades.upgrade_select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            craft = m.CraftConfirmView(1, "basic_gen")
            await craft.do_craft(interaction, True)
            assert interaction.embed is not None

            await db.execute(
                "DELETE FROM inventory WHERE user_id = 1 "
                "AND item_id = 'basic_gen'"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            craft = m.CraftConfirmView(1, "basic_gen")
            await craft.do_craft(interaction, False)
            assert interaction.embed is not None

            party = await m.create_raid_party(1)
            modal = m.RaidInviteModal(1, party)
            modal.target_id._value = "bad"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.RaidInviteModal(1, party)
            modal.target_id._value = "1"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.RaidInviteModal(2, party)
            modal.target_id._value = "3"
            interaction = FakeInteraction(2)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.RaidInviteModal(1, 99999)
            modal.target_id._value = "2"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            for action, target in (
                ("kick", 1),
                ("promote", 1),
                ("promote", 4),
                ("demote", 2),
            ):
                modal = m.ClanTargetConfirmModal(1, 1, action, target)
                modal.confirm._value = "ДА"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent

            modal = m.ClanTargetConfirmModal(2, 1, "kick", 3)
            modal.confirm._value = "ДА"
            interaction = FakeInteraction(2)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            reset = m.UserResetModal(1)
            reset.confirm._value = "НЕТ"
            await reset.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            reset = m.UserResetModal(1)
            reset.confirm._value = "СБРОСИТЬ"
            await reset.on_submit(interaction)
            assert interaction.followup.sent

            await db.execute(
                "INSERT INTO bank_deposits "
                "(user_id, amount, interest_rate, start_time, end_time) "
                "VALUES (2, 100, 0.1, ?, ?)",
                (
                    datetime.datetime.now().isoformat(),
                    (
                        datetime.datetime.now()
                        + datetime.timedelta(days=1)
                    ).isoformat(),
                ),
            )
            await db.commit()
            interaction = FakeInteraction(2)
            reset = m.UserResetModal(2)
            reset.confirm._value = "СБРОСИТЬ"
            await reset.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminGiveItemModal(1)
            modal.user_id._value = "2"
            modal.item_id._value = "basic_gen"
            modal.quantity._value = "0"
            modal.location._value = "profile"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminGiveItemModal(1)
            modal.user_id._value = "2"
            modal.item_id._value = "basic_gen"
            modal.quantity._value = "1"
            modal.location._value = "bad"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            modal = m.AdminAddClanMemberModal(1)
            modal.clan_id._value = "1"
            modal.user_id._value = "5"
            modal.role._value = "leader"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            async with db.execute(
                "SELECT leader_id FROM clans WHERE id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 5
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
