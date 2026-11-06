import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_giveaway_flow_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeChannel:
    id = 555

    async def send(self, *args, **kwargs):
        return SimpleNamespace(
            id=999,
            jump_url="https://discord.example/999",
            delete=self._delete,
        )

    async def _delete(self):
        return None


class FakeResponse:
    async def defer(self, *args, **kwargs):
        return None


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self):
        self.user = SimpleNamespace(id=1)
        self.guild_id = 1
        self.channel = FakeChannel()
        self.response = FakeResponse()
        self.followup = FakeFollowup()


def test_giveaway_creation_and_modal():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000)"
            )
            await db.commit()

            ok, message = await m.create_giveaway(
                1,
                1,
                FakeChannel(),
                "coins",
                None,
                "100",
                "1",
                "24",
            )
            assert ok, message
            async with db.execute(
                "SELECT COUNT(*) FROM giveaways"
            ) as c:
                assert (await c.fetchone())[0] == 1

            class FailingChannel(FakeChannel):
                async def send(self, *args, **kwargs):
                    raise RuntimeError("send failed")

            ok, _ = await m.create_giveaway(
                1, 1, FailingChannel(), "coins", None, "100", "1", "24"
            )
            assert not ok

            original_guilds = m.global_giveaway_guilds
            original_send = m._send_global_giveaway_to_guild

            async def fake_send(guild, giveaway_id):
                return True

            m.global_giveaway_guilds = lambda: [SimpleNamespace()]
            m._send_global_giveaway_to_guild = fake_send
            try:
                ok, message = await m.create_global_giveaway(
                    1, "coins", None, "100", "1", "24"
                )
                assert ok, message

                m.global_giveaway_guilds = lambda: []
                ok, _ = await m.create_global_giveaway(
                    1, "coins", None, "100", "1", "24"
                )
                assert not ok
            finally:
                m.global_giveaway_guilds = original_guilds
                m._send_global_giveaway_to_guild = original_send

            original_deny = m.deny_if_disabled
            original_create = m.create_giveaway

            async def allow(*args, **kwargs):
                return False

            async def create(*args, **kwargs):
                return True, "ok"

            m.deny_if_disabled = allow
            m.create_giveaway = create
            try:
                interaction = FakeInteraction()
                modal = m.GiveawayCreateModal(1, "coins")
                modal.amount._value = "100"
                modal.winners._value = "1"
                modal.duration_hours._value = "24"
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.deny_if_disabled = original_deny
                m.create_giveaway = original_create
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
