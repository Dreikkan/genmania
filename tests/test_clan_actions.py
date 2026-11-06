import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_clan_actions_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False

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


def test_clan_actions_and_modals():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, ?)",
                [
                    (1, 1000),
                    (2, 1000),
                    (3, 1000),
                    (4, 1000),
                    (5, 1000),
                    (6, 1000),
                ],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury, capacity) "
                "VALUES (1, 'Alpha', 1, 10000, 10), "
                "(2, 'Beta', 99, 0, 10)"
            )
            await db.executemany(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (?, 1, ?)",
                [(1, "leader"), (2, "member"), (3, "member")],
            )
            await db.execute(
                "INSERT INTO clan_invites (clan_id, inviter_id, target_id) "
                "VALUES (1, 1, 5)"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            modal = m.ClanInviteModal(1, 1)
            modal.user_id._value = "4"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.ClanKickModal(1, 1)
            modal.user_id._value = "2"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.ClanTargetConfirmModal(1, 1, "kick", 3)
            modal.confirm._value = "ДА"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(4)
            modal = m.CreateClanModal(4)
            modal.name._value = "NewClan"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.DepositClanModal(1)
            modal.amount._value = "100"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            async with db.execute(
                "SELECT id FROM clan_invites WHERE target_id = 5"
            ) as c:
                invite_id = (await c.fetchone())[0]
            interaction = FakeInteraction(5, [f"{invite_id}:1"])
            invites = m.ClanInvitesView(5, [])
            await invites.select(interaction)
            assert interaction.embed is not None

            interaction = FakeInteraction(1, ["basic_gen"])
            buy = m.ClanBuySelectView(1, 1, [], 0, 1)
            await buy.item_select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            upgrades = m.ClanUpgradesView(1, 1)
            expand = next(
                item
                for item in upgrades.children
                if getattr(item, "label", None) == "Расширить состав"
            )
            await expand.callback(interaction)
            assert interaction.embed is not None

            m.ClanApplicationsView(1, 1, [])
            m.ClanBrowserView(1, [], 0, 2, None)
            quests = await m.build_clan_quests_embed(1)
            assert quests is not None

            interaction = FakeInteraction(1)
            target_view = m.ClanTargetSelectView(1, 1, "invite")
            await target_view._invite(interaction, 6)
            assert interaction.followup.sent
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
