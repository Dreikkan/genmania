import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_empty_finance_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self):
        self.user = SimpleNamespace(id=1, name="Tester")
        self.guild_id = 1
        self.followup = FakeFollowup()
        self.response = SimpleNamespace(
            defer=self._defer, send_message=self._send_message
        )
        self.embed = None
        self.view = None

    async def _defer(self, *args, **kwargs):
        return None

    async def _send_message(self, *args, **kwargs):
        return None

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


async def _call(coro):
    return await coro


def test_empty_finance_screens():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 0, 0)"
            )
            await db.commit()
            for func in (
                m.open_auction_view,
                m.open_auction_sell_select,
                m.open_auction_cancel_select,
                m.open_bank_loan_select,
                m.open_bank_repay_confirm,
            ):
                interaction = FakeInteraction()
                if func is m.open_auction_view:
                    await func(interaction, 1)
                else:
                    await func(interaction, 1)
                assert interaction.embed is not None or interaction.followup.sent
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
