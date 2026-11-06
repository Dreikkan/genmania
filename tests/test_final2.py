import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_final2_test", BOT_PATH
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


class FakeMessage:
    def __init__(self):
        self.edited = False

    async def edit(self, *args, **kwargs):
        self.edited = True

    async def delete(self):
        return None


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.message = FakeMessage()
        self.embed = None
        self.view = None

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


def test_final_error_branches_two():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) "
                "VALUES (?, 1000, 1000)",
                [(1,), (2,), (3,), (4,)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id) "
                "VALUES (1, 'Alpha', 1), (2, 'Beta', 2)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 2, 'leader'), (3, 2, 'member')"
            )
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'storage', 0)"
            )
            await db.execute(
                "INSERT INTO user_cosmetics (user_id) VALUES (1)"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            modal = m.CosmeticColorModal(1)
            modal.hex_code._value = "ZZZ"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.CosmeticColorModal(1)
            modal.hex_code._value = "FF0000"
            modal.main_message = FakeMessage()
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            for author, target, confirm in (
                (1, 1, "ДА"),
                (1, 99, "ДА"),
                (2, 3, "НЕТ"),
                (2, 3, "ДА"),
            ):
                modal = m.ClanTransferModal(author, 2 if author == 2 else 1)
                modal.user_id._value = str(target)
                modal.confirm._value = confirm
                interaction = FakeInteraction(author)
                await modal.on_submit(interaction)
                assert interaction.followup.sent

            sell = m.SellConfirmView(1, 99, "basic_gen", 0, 10, 0)
            sell_btn = next(
                item
                for item in sell.children
                if getattr(item, "label", None) == "Продать"
            )
            interaction = FakeInteraction(1)
            await sell_btn.callback(interaction)
            assert interaction.embed is not None

            cancel_btn = next(
                item
                for item in sell.children
                if getattr(item, "label", None) == "Отмена"
            )
            interaction = FakeInteraction(1)
            await cancel_btn.callback(interaction)
            assert interaction.embed is not None

            party = await m.create_raid_party(1)
            await db.execute(
                "INSERT INTO raid_party_invites "
                "(party_id, inviter_id, target_id) VALUES (?, 1, 2)",
                (party,),
            )
            await db.commit()
            view = m.RaidInviteView(party, 1, 2)
            view.message = FakeMessage()
            view._schedule_delete = lambda delay: None
            await view.on_timeout()
            assert view.resolved

            ok, _ = await m.create_giveaway(
                1, None, None, "coins", None, "100", "1", "24"
            )
            assert not ok
            ok, _ = await m.create_giveaway(
                1, 1, None, "coins", None, "100", "1", "24"
            )
            assert not ok
            ok, _ = await m.create_giveaway(
                1, 1, FakeMessage(), "unknown", None, "100", "1", "24"
            )
            assert not ok

            modal = m.AdminGiveItemModal(1)
            modal.user_id._value = "2"
            modal.item_id._value = "missing_item"
            modal.quantity._value = "1"
            modal.location._value = "profile"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            await db.execute(
                "UPDATE players SET storage_size = 0 WHERE user_id = 2"
            )
            await db.commit()
            modal = m.AdminGiveItemModal(1)
            modal.user_id._value = "2"
            modal.item_id._value = "basic_gen"
            modal.quantity._value = "1"
            modal.location._value = "storage"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            for role, clan, uid in (
                ("bad", "1", "4"),
                ("member", "999", "4"),
                ("member", "1", "1"),
            ):
                modal = m.AdminAddClanMemberModal(1)
                modal.clan_id._value = clan
                modal.user_id._value = uid
                modal.role._value = role
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent

            await db.execute(
                "UPDATE clans SET treasury = 1000 WHERE id = 1"
            )
            await db.commit()
            clan_menu = m.ClanMenuView(1, 1)
            war_btn = next(
                item
                for item in clan_menu.children
                if getattr(item, "label", None) == "Война"
            )
            interaction = FakeInteraction(1)
            await war_btn.callback(interaction)
            assert interaction.embed is not None or interaction.followup.sent

            interaction = FakeInteraction(1)
            await war_btn.callback(interaction)
            assert interaction.embed is not None or interaction.followup.sent

            original_event = m.get_active_advent_event
            m.get_active_advent_event = lambda: (None, 0)
            try:
                interaction = FakeInteraction(1)
                modal = m.AdminOpenAdventModal(1)
                modal.user_id._value = "1"
                modal.day._value = "1"
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.get_active_advent_event = original_event
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
