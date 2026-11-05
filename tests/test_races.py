import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_races_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _db():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


class FakeResponse:
    async def defer(self, *args, **kwargs):
        return None


class FakeInteraction:
    def __init__(self, user_id):
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = 1
        self.response = FakeResponse()

    async def edit_original_response(self, *args, **kwargs):
        return None

    @property
    def followup(self):
        return self

    async def send(self, *args, **kwargs):
        return None


def test_daily_claim_is_atomic():
    async def run():
        db = await _db()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 0, 0)"
            )
            await db.commit()
            results = await asyncio.gather(
                m.claim_daily(1), m.claim_daily(1), return_exceptions=True
            )
            assert sum(1 for r in results if isinstance(r, dict) and r.get("ok")) == 1
            async with db.execute(
                "SELECT coins, gems FROM players WHERE user_id = 1"
            ) as c:
                # 30/0 — дейли, ещё 50/1 — награда за шаг онбординга.
                assert await c.fetchone() == (80, 1)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_collect_income_is_atomic():
    async def run():
        db = await _db()
        try:
            hour_ago = (
                datetime.datetime.now() - datetime.timedelta(hours=1)
            ).isoformat()
            await db.execute(
                "INSERT INTO players (user_id, coins, last_collected, "
                "last_gem_collected) VALUES (1, 0, ?, ?)",
                (hour_ago, hour_ago),
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0)"
            )
            await db.commit()
            results = await asyncio.gather(
                m.collect_income(1), m.collect_income(1), return_exceptions=True
            )
            total = sum(r[0] for r in results if isinstance(r, tuple))
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == total
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_clan_member_can_leave_and_leader_can_disband():
    async def run():
        db = await _db()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 0), (2, 0)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id) VALUES (1, 'Test', 1)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 1, 'member')"
            )
            await db.commit()

            member_view = m.ClanLeaveConfirmView(2, 1)
            await member_view.btn_confirm.callback(FakeInteraction(2))
            async with db.execute(
                "SELECT COUNT(*) FROM clan_members WHERE user_id = 2"
            ) as c:
                assert (await c.fetchone())[0] == 0
            async with db.execute("SELECT COUNT(*) FROM clans WHERE id = 1") as c:
                assert (await c.fetchone())[0] == 1

            leader_view = m.ClanLeaveConfirmView(1, 1)
            await leader_view.btn_confirm.callback(FakeInteraction(1))
            async with db.execute("SELECT COUNT(*) FROM clans WHERE id = 1") as c:
                assert (await c.fetchone())[0] == 0
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
