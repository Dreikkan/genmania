import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_clan_flows_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.messages = []
        self.modal = None

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_modal(self, modal):
        self.modal = modal


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(id=user_id, name=f"User{user_id}")
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.edited = []
        self.message = SimpleNamespace()

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


def test_clan_creation_invite_role_and_kick_modals():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, ?)",
                [
                    (1, 1000),
                    (2, 1000),
                    (3, 1000),
                    (4, 1000),
                    (5, 1000),
                    (6, 1000),
                    (7, 0),
                    (8, 1000),
                    (9, 1000),
                ],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 0)"
            )
            await db.executemany(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (?, 1, ?)",
                [
                    (1, "leader"),
                    (2, "veteran"),
                    (3, "member"),
                    (4, "deputy"),
                    (5, "member"),
                ],
            )
            await db.execute(
                "INSERT INTO clan_invites "
                "(clan_id, inviter_id, target_id) VALUES (1, 1, 8)"
            )
            await db.commit()

            interaction = await _submit(
                m.CreateClanModal(7), name="My Clan"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.CreateClanModal(1), name="My Clan"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.CreateClanModal(6), name="X"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.CreateClanModal(6), name="My Clan"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.CreateClanModal(8), name="Alpha"
            )
            assert interaction.followup.sent

            interaction = await _submit(
                m.ClanInviteModal(1, 1), user_id="bad"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanInviteModal(1, 1), user_id="1"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanInviteModal(3, 1), user_id="2"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanInviteModal(1, 1), user_id="2"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanInviteModal(1, 1), user_id="8"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanInviteModal(1, 1), user_id="7"
            )
            assert interaction.followup.sent

            interaction = await _submit(
                m.ClanRoleModal(1, 1, "promote"), user_id="bad"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanRoleModal(1, 1, "promote"), user_id="99"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanRoleModal(1, 1, "promote"), user_id="1"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanRoleModal(1, 1, "promote"), user_id="4"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanRoleModal(1, 1, "demote"), user_id="3"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanRoleModal(1, 1, "promote"), user_id="2"
            )
            assert interaction.followup.sent

            interaction = await _submit(
                m.ClanKickModal(1, 1), user_id="bad"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanKickModal(1, 1), user_id="1"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanKickModal(3, 1), user_id="2"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanKickModal(1, 1), user_id="1"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanKickModal(1, 1), user_id="99"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanKickModal(1, 1), user_id="5"
            )
            assert interaction.followup.sent
        finally:
            await _close(db)

    asyncio.run(run())


def test_clan_transfer_deposit_leave_and_target_select():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, ?)",
                [(1, 1000), (2, 1000), (3, 1000), (7, 0)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 100), (2, 'Beta', 2, 100), "
                "(3, 'Gamma', 9, 100)"
            )
            await db.executemany(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (?, ?, ?)",
                [
                    (1, 1, "leader"),
                    (2, 2, "leader"),
                    (3, 1, "member"),
                    (7, 2, "member"),
                    (9, 3, "leader"),
                ],
            )
            await db.execute(
                "INSERT INTO clan_inventory (clan_id, slot, item_id) "
                "VALUES (2, 0, 'basic_gen')"
            )
            await db.commit()

            interaction = await _submit(
                m.ClanTransferModal(1, 1), user_id="2", confirm="НЕТ"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTransferModal(1, 1), user_id="bad", confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTransferModal(1, 1), user_id="1", confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTransferModal(3, 1), user_id="2", confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTransferModal(1, 1), user_id="2", confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTransferModal(1, 1), user_id="3", confirm="ДА"
            )
            assert interaction.followup.sent

            interaction = await _submit(
                m.DepositClanModal(1), amount="bad"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.DepositClanModal(7), amount="10"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.DepositClanModal(1), amount="2000"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.DepositClanModal(1), amount="100"
            )
            assert interaction.followup.sent

            view = m.ClanLeaveConfirmView(7, 2)
            interaction = FakeInteraction(7)
            await view.btn_confirm.callback(interaction)
            assert interaction.followup.sent

            view = m.ClanLeaveConfirmView(2, 2)
            interaction = FakeInteraction(2)
            await view.btn_confirm.callback(interaction)
            assert interaction.followup.sent

            view = m.ClanLeaveConfirmView(9, 3)
            interaction = FakeInteraction(9)
            await view.btn_confirm.callback(interaction)
            assert interaction.followup.sent

            view = m.ClanLeaveConfirmView(99, 999)
            interaction = FakeInteraction(99)
            await view.btn_confirm.callback(interaction)
            assert interaction.followup.sent

            view = m.ClanLeaveConfirmView(99, 1)
            interaction = FakeInteraction(99)
            await view.btn_cancel.callback(interaction)
            assert interaction.edited

            original_get_user = m.bot.get_user
            m.bot.get_user = lambda uid: SimpleNamespace(name=f"User{uid}")
            try:
                view = m.ClanMembersView(2, 1, 0, 2)
                interaction = FakeInteraction(1)
                await view.btn_prev.callback(interaction)
                interaction = FakeInteraction(1)
                await view.btn_next.callback(interaction)
                interaction = FakeInteraction(1)
                await view.btn_back.callback(interaction)
                assert interaction.edited

                view = m.ClanMembersView(99, 1, 0, 1)
                interaction = FakeInteraction(99)
                await view.btn_back.callback(interaction)
                assert interaction.edited
            finally:
                m.bot.get_user = original_get_user

            view = m.ClanQuestsView(2, 1)
            interaction = FakeInteraction(1)
            await view.btn_back.callback(interaction)
            assert interaction.edited

            view = m.ClanQuestsView(99, 1)
            interaction = FakeInteraction(99)
            await view.btn_back.callback(interaction)
            assert interaction.edited

            for action in ("invite", "promote", "kick", "transfer"):
                view = m.ClanTargetSelectView(1, 1, action)
                interaction = FakeInteraction(1)
                await view.enter_id(interaction)
                assert interaction.response.modal is not None

            view = m.ClanTargetSelectView(1, 1, "promote")
            interaction = FakeInteraction(1, ["1"])
            await view.select_target(interaction)
            assert interaction.response.messages

            view = m.ClanTargetSelectView(1, 1, "promote")
            interaction = FakeInteraction(1, ["2"])
            await view.select_target(interaction)
            assert interaction.response.modal is not None

            view = m.ClanTargetSelectView(3, 1, "invite")
            interaction = FakeInteraction(3, ["2"])
            await view.select_target(interaction)
            assert interaction.followup.sent

            view = m.ClanTargetSelectView(1, 1, "invite")
            interaction = FakeInteraction(1, ["2"])
            await view.select_target(interaction)
            assert interaction.followup.sent

            view = m.ClanTargetSelectView(99, 1, "invite")
            interaction = FakeInteraction(99)
            await view.back(interaction)
            assert interaction.followup.sent
        finally:
            await _close(db)

    asyncio.run(run())


def test_clan_views_and_target_confirm_modal():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, ?)",
                [(1, 1000), (2, 1000), (3, 1000), (4, 1000)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 1000)"
            )
            await db.executemany(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (?, 1, ?)",
                [
                    (1, "leader"),
                    (2, "veteran"),
                    (3, "member"),
                    (4, "deputy"),
                ],
            )
            await db.commit()

            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "promote", 2), confirm="НЕТ"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "promote", 1), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "promote", 4), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "kick", 1), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "kick", 99), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "transfer", 1), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "transfer", 99), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(3, 1, "kick", 2), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "promote", 2), confirm="ДА"
            )
            assert interaction.followup.sent

            view = m.ClanWarView(2, 1, 1)
            original_war = m.get_active_clan_war
            original_build_war = m.build_clan_war_embed

            async def no_war(clan_id):
                return None

            async def war(clan_id):
                return (1, 1, 2, "start", "active", 100, 100)

            async def build_war(*args):
                return m.BotEmbed(title="War")

            m.get_active_clan_war = no_war
            m.build_clan_war_embed = build_war
            try:
                interaction = FakeInteraction(2)
                await view.btn_refresh.callback(interaction)
                assert interaction.edited

                m.get_active_clan_war = war
                interaction = FakeInteraction(2)
                await view.btn_refresh.callback(interaction)
                assert interaction.edited
            finally:
                m.get_active_clan_war = original_war
                m.build_clan_war_embed = original_build_war

            await db.execute("UPDATE clans SET treasury = 0 WHERE id = 1")
            await db.commit()
            view = m.ClanBuySelectView(
                2, 1, [m.discord.SelectOption(label="X", value="x")], 0, 2
            )
            interaction = FakeInteraction(2, ["missing"])
            await view.item_select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(2, ["basic_gen"])
            await view.item_select(interaction)
            assert interaction.followup.sent

            await db.execute(
                "UPDATE clans SET treasury = 100000 WHERE id = 1"
            )
            await db.commit()
            interaction = FakeInteraction(2, ["basic_gen"])
            await view.item_select(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(2)
            await view.back(interaction)
            assert interaction.edited
        finally:
            await _close(db)

    asyncio.run(run())
