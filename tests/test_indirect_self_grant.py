import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_indirect_self_grant_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, text=None, **kwargs):
        self.messages.append((text, kwargs))


class FakeResponse:
    async def defer(self, *args, **kwargs):
        return None

    async def send_message(self, *args, **kwargs):
        return None


class FakeInteraction:
    def __init__(self, user_id=1, guild_id=None):
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = guild_id
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.message = None


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._tax_rate_cache.clear()
    m._top_cache.clear()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems) VALUES "
        "(1, 1000, 1000), (2, 100, 100)"
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._tax_rate_cache.clear()
    m._top_cache.clear()


async def _top_excluded(db, user_id: int) -> int:
    async with db.execute(
        "SELECT COALESCE(top_excluded, 0) FROM players WHERE user_id = ?",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0] if row else 0)


def test_self_title_grant_flags_top_exclusion_and_notifies():
    async def run():
        db = await _init()
        try:
            title_id = next(iter(m.TITLES))
            modal = m.AdminSetTitleModal(1)
            modal.user_id._value = "1"
            modal.title_id._value = title_id
            interaction = FakeInteraction(user_id=1)
            await modal.on_submit(interaction)

            assert await _top_excluded(db, 1) == 1
            assert any(
                "исключён из топов" in (text or "")
                for text, _kwargs in interaction.followup.messages
            )

            modal2 = m.AdminSetTitleModal(1)
            modal2.user_id._value = "2"
            modal2.title_id._value = title_id
            interaction2 = FakeInteraction(user_id=1)
            await modal2.on_submit(interaction2)
            assert await _top_excluded(db, 2) == 0
        finally:
            await _close(db)

    asyncio.run(run())


def test_self_clan_treasury_flags_only_for_member():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (100, 'Self Clan', 1, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 100, 'leader')"
            )
            await db.commit()

            modal = m.AdminClanTreasuryModal(1)
            modal.clan_id._value = "100"
            modal.amount._value = "100"
            interaction = FakeInteraction(user_id=1)
            await modal.on_submit(interaction)

            assert await _top_excluded(db, 1) == 1
            async with db.execute(
                "SELECT treasury FROM clans WHERE id = 100"
            ) as cursor:
                assert (await cursor.fetchone())[0] == 100
        finally:
            await _close(db)

    asyncio.run(run())


def test_self_finish_auction_flags_only_for_bidder():
    async def run():
        db = await _init()
        try:
            end_time = (
                datetime.datetime.now() + datetime.timedelta(hours=1)
            ).isoformat()
            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, stars, start_price, current_bid, "
                "current_bidder, end_time, status) "
                "VALUES (1, 2, 'basic_gen', 0, 100, 150, 1, ?, 'active')",
                (end_time,),
            )
            await db.commit()

            modal = m.AdminFinishAuctionModal(1)
            modal.auction_id._value = "1"
            interaction = FakeInteraction(user_id=1)
            await modal.on_submit(interaction)

            assert await _top_excluded(db, 1) == 1
        finally:
            await _close(db)

    asyncio.run(run())


def test_self_create_clan_flags_top_exclusion():
    async def run():
        db = await _init()
        try:
            modal = m.AdminCreateClanModal(1)
            modal.name._value = "Self Created"
            modal.leader_id._value = "1"
            interaction = FakeInteraction(user_id=1)
            await modal.on_submit(interaction)

            assert await _top_excluded(db, 1) == 1
            async with db.execute(
                "SELECT COUNT(*) FROM clans WHERE name = 'Self Created'"
            ) as cursor:
                assert (await cursor.fetchone())[0] == 1
        finally:
            await _close(db)

    asyncio.run(run())


def test_self_add_to_clan_flags_top_exclusion():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (100, 'Join Clan', 2, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (2, 100, 'leader')"
            )
            await db.commit()

            modal = m.AdminAddClanMemberModal(1)
            modal.clan_id._value = "100"
            modal.user_id._value = "1"
            modal.role._value = "member"
            interaction = FakeInteraction(user_id=1)
            await modal.on_submit(interaction)

            assert await _top_excluded(db, 1) == 1
        finally:
            await _close(db)

    asyncio.run(run())


def test_self_disband_clan_flags_top_exclusion():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (100, 'Disband Clan', 1, 100)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 100, 'leader')"
            )
            await db.commit()

            modal = m.AdminDisbandClanModal(1)
            modal.clan_id._value = "100"
            interaction = FakeInteraction(user_id=1)
            await modal.on_submit(interaction)

            assert await _top_excluded(db, 1) == 1
            async with db.execute(
                "SELECT COUNT(*) FROM clans WHERE id = 100"
            ) as cursor:
                assert (await cursor.fetchone())[0] == 0
        finally:
            await _close(db)

    asyncio.run(run())
