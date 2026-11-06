import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_economy_modals_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    async def defer(self, *args, **kwargs):
        return None


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(id=user_id, name="Tester")
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()


def test_exchange_bank_and_clan_modals():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) "
                "VALUES (1, 1000, 10), (2, 1000, 10)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id) "
                "VALUES (1, 'Alpha', 1)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 1, 'member')"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            exchange = m.CoinsToGemsModal(1)
            exchange.amount._value = "120"
            await exchange.on_submit(interaction)
            assert interaction.followup.messages

            interaction = FakeInteraction(1)
            exchange = m.GemsToCoinsModal(1)
            exchange.amount._value = "2"
            await exchange.on_submit(interaction)
            assert interaction.followup.messages

            interaction = FakeInteraction(1)
            deposit = m.BankDepositModal(1)
            deposit.amount._value = "100"
            deposit.days._value = "7"
            await deposit.on_submit(interaction)
            assert interaction.followup.messages
            async with db.execute(
                "SELECT amount FROM bank_deposits WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 100

            interaction = FakeInteraction(1)
            withdraw = m.BankWithdrawModal(1)
            withdraw.confirm._value = "ДА"
            await withdraw.on_submit(interaction)
            assert interaction.followup.messages

            interaction = FakeInteraction(1)
            role = m.ClanRoleModal(1, 1, "promote")
            role.user_id._value = "2"
            await role.on_submit(interaction)
            async with db.execute(
                "SELECT role FROM clan_members "
                "WHERE user_id = 2 AND clan_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == "veteran"

            interaction = FakeInteraction(1)
            transfer = m.ClanTransferModal(1, 1)
            transfer.user_id._value = "2"
            transfer.confirm._value = "ДА"
            await transfer.on_submit(interaction)
            async with db.execute(
                "SELECT leader_id FROM clans WHERE id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 2
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
