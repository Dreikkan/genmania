import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_raid_invite_test", BOT_PATH
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


class FakeMessageable:
    pass


class FakeChannel(FakeMessageable):
    id = 555

    async def send(self, *args, **kwargs):
        return SimpleNamespace(
            id=999,
            edit=self._edit,
            delete=self._delete,
        )

    async def _edit(self, *args, **kwargs):
        return None

    async def _delete(self):
        return None


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(id=user_id, name="Tester")
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.channel = FakeChannel()
        self.message = SimpleNamespace(edit=self._edit)

    async def _edit(self, *args, **kwargs):
        return None

    async def edit_original_response(self, *args, **kwargs):
        return None


def test_raid_invite_and_accept():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000), (2, 1000)"
            )
            await db.commit()
            party_id = await m.create_raid_party(1)
            modal = m.RaidInviteModal(1, party_id)
            modal.target_id._value = "2"

            original_messageable = m.discord.abc.Messageable
            m.discord.abc.Messageable = FakeMessageable
            try:
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.discord.abc.Messageable = original_messageable

            view = m.RaidInviteView(party_id, 1, 2)
            view.message = SimpleNamespace(
                edit=interaction.message.edit
            )
            view._schedule_delete = lambda delay: None
            accept = next(
                item
                for item in view.children
                if getattr(item, "label", None) == "Принять"
            )
            interaction = FakeInteraction(2)
            interaction.message = view.message
            await accept.callback(interaction)

            party = await m.get_raid_party(2)
            assert party and party[0] == party_id

            decline_view = m.RaidInviteView(party_id, 1, 2)
            decline_view.message = SimpleNamespace(
                edit=interaction.message.edit
            )
            decline_view._schedule_delete = lambda delay: None
            decline = next(
                item
                for item in decline_view.children
                if getattr(item, "label", None) == "Отклонить"
            )
            interaction = FakeInteraction(2)
            interaction.message = decline_view.message
            await decline.callback(interaction)
            assert decline_view.resolved
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
