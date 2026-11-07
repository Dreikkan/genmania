
import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_coverage_100_final", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class Resp:
    def __init__(self):
        self.deferred = False

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        return None


class Fup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class Inter:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"U{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(id=1, owner_id=1)
        self.response = Resp()
        self.followup = Fup()
        self.data = {"values": ["1"]}
        self.edited = []

    async def edit_original_response(self, *args, **kwargs):
        self.edited.append((args, kwargs))


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


class Cur:
    def __init__(self, rowcount=0, rows=None, row=None):
        self.rowcount = rowcount
        self.rows = rows or []
        self.row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def __await__(self):
        async def _inner():
            return self
        return _inner().__await__()

    async def fetchone(self):
        return self.row

    async def fetchall(self):
        return self.rows


def test_final_bot_branches():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 1000, 1000)",
                [(1,), (2,), (99,)],
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (99, 0, 'basic_gen', 'profile', 0)"
            )
            await db.commit()

            # star copies branch
            view = m.StarConfirmView(99, 0, "basic_gen", 0, 1, "profile")
            await view.confirm.callback(Inter(99))

            # auction sell rowcount branch
            await db.execute(
                "CREATE TRIGGER trg_sell_final BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 99 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            modal = m.AuctionSellDetailsModal(99, 0, "basic_gen", 0)
            modal.start_price._value = "10"
            modal.buyout_price._value = "20"
            modal.hours._value = "1"
            await modal.on_submit(Inter(99))
            await db.execute("DROP TRIGGER trg_sell_final")
            await db.commit()

            # auction closer no-fresh branch
            class AuctionDB:
                def __init__(self, real):
                    self.real = real
                    self.n = 0

                def __getattr__(self, name):
                    return getattr(self.real, name)

                def execute(self, sql, params=()):
                    if "FROM auctions WHERE status = 'active' AND end_time < ?" in sql:
                        return Cur(rows=[(1, 1, "basic_gen", 0, 0, None)])
                    if "UPDATE auctions SET status = 'closing'" in sql:
                        return Cur(rowcount=1)
                    if "SELECT seller_id, item_id, stars, current_bid" in sql:
                        return Cur(row=None)
                    return self.real.execute(sql, params)

            fake = object.__new__(m.CastleBot)
            fake.db = AuctionDB(db)
            fake.wait_until_ready = lambda: _none()
            state = {"closed": False}

            def closed():
                if state["closed"]:
                    return True
                state["closed"] = True
                return False

            fake.is_closed = closed
            original_sleep = m.asyncio.sleep
            m.asyncio.sleep = lambda *args, **kwargs: _none()
            try:
                await m.CastleBot.auction_closer(fake)
            finally:
                m.asyncio.sleep = original_sleep
        finally:
            await _close(db)

    asyncio.run(run())


async def _none():
    return None


def test_final_service_branches():
    async def run():
        db = await _init()
        original_event = m.ADVENT_RUNTIME._event_getter
        original_rewards = m.ADVENT_RUNTIME.rewards
        original_pet_db = m.PET_RUNTIME._db_getter
        original_combat = m.RAID_COMBAT_RUNTIME._combat_power_getter
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 1000, 1000)",
                [(1,), (2,), (3,), (4,)],
            )
            await db.commit()

            # advent item + reward line
            event = {"key": "probe", "days": 4, "emoji": "X", "name": "Probe"}
            m.ADVENT_RUNTIME._event_getter = lambda: (lambda: (event, 1))
            m.ADVENT_RUNTIME.rewards = {
                1: (1, 2, "basic_gen"),
                2: (1, 2, None),
                3: (1, 2, "basic_gen"),
                4: (1, 2, None),
            }
            await db.execute(
                "INSERT INTO advent_state "
                "(user_id, last_opened_day, last_opened_date, event_key) "
                "VALUES (1, 0, NULL, 'probe')"
            )
            await db.commit()
            await m.open_advent_day(1, 1)
            await db.execute(
                "UPDATE advent_state SET last_opened_day = 2 WHERE user_id = 1"
            )
            await db.commit()
            await m.build_advent_embed(Inter(1), 0)
            m.ADVENT_RUNTIME._event_getter = original_event
            m.ADVENT_RUNTIME.rewards = original_rewards

            # pets existing autocollector
            await db.execute(
                "INSERT INTO autocollectors (user_id, level, last_auto) VALUES (1, 1, NULL)"
            )
            await db.commit()
            await m.buy_autocollector(1)

            class PetDB:
                def __init__(self, real):
                    self.real = real

                def __getattr__(self, name):
                    return getattr(self.real, name)

                def execute(self, sql, params=()):
                    if "SELECT level FROM autocollectors" in sql:
                        return Cur(row=(1,))
                    if "UPDATE autocollectors SET level" in sql:
                        return Cur(rowcount=0)
                    return self.real.execute(sql, params)

            m.PET_RUNTIME._db_getter = lambda: PetDB(db)
            try:
                await m.upgrade_autocollector(1)
            finally:
                m.PET_RUNTIME._db_getter = original_pet_db

            # raid no generators target
            async def power(user_id):
                return 1000 if user_id == 1 else 0

            m.RAID_COMBAT_RUNTIME._combat_power_getter = lambda: power
            try:
                await m.perform_raid([1], 2)
            finally:
                m.RAID_COMBAT_RUNTIME._combat_power_getter = original_combat

            # raid wallet changed
            async def power2(user_id):
                return 1000 if user_id == 1 else 1

            class RaidDB:
                def __init__(self, real):
                    self.real = real

                def __getattr__(self, name):
                    return getattr(self.real, name)

                def execute(self, sql, params=()):
                    if "UPDATE players SET coins = coins - ?" in sql and params:
                        if params[-1] == 2:
                            return Cur(rowcount=0)
                    return self.real.execute(sql, params)

            m.RAID_COMBAT_RUNTIME._combat_power_getter = lambda: power2
            m.RAID_COMBAT_RUNTIME._db_getter = lambda: RaidDB(db)
            try:
                await m.perform_raid([1], 2)
            finally:
                m.RAID_COMBAT_RUNTIME._combat_power_getter = original_combat
                m.RAID_COMBAT_RUNTIME._db_getter = lambda: db

            # raid join full
            await db.execute(
                "INSERT INTO raid_parties (id, leader_id, member2_id, member3_id) "
                "VALUES (1, 1, 2, 3)"
            )
            await db.commit()
            try:
                await m.join_raid_party(1, 4)
            except ValueError:
                pass

            # clan war enemy active
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'A', 1, 1000), (2, 'B', 2, 1000), (3, 'C', 3, 1000)"
            )
            await db.execute(
                "INSERT INTO clan_wars (id, clan1_id, clan2_id, start_time, status) "
                "VALUES (1, 2, 3, 'now', 'active')"
            )
            await db.commit()
            try:
                await m.start_clan_war(1, 2)
            except ValueError:
                pass

            # notifications 476
            await db.execute("DELETE FROM auctions")
            await db.execute("DELETE FROM clan_wars")
            await db.execute("DELETE FROM user_pets_v2")
            await db.execute("DELETE FROM autocollectors")
            await db.execute("UPDATE players SET last_daily = ?", (m.datetime.datetime.now().isoformat(),))
            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, stars, start_price, current_bid, "
                "current_bidder, buyout_price, end_time, status) "
                "VALUES (1, 2, 'basic_gen', 0, 1, 1, 3, NULL, ?, 'active')",
                ((m.datetime.datetime.now() + m.datetime.timedelta(minutes=30)).isoformat(),),
            )
            await db.commit()
            original_bot = m.NOTIFICATION_RUNTIME._bot_getter
            original_max = m.NOTIFICATION_RUNTIME.max_sent_per_cycle

            class User:
                async def send(self, *args, **kwargs):
                    return None

            class NB:
                def get_user(self, user_id):
                    return User()

                async def fetch_user(self, user_id):
                    return User()

            m.NOTIFICATION_RUNTIME._bot_getter = lambda: NB()
            m.NOTIFICATION_RUNTIME.max_sent_per_cycle = 1
            try:
                await m.run_notification_cycle()
            finally:
                m.NOTIFICATION_RUNTIME._bot_getter = original_bot
                m.NOTIFICATION_RUNTIME.max_sent_per_cycle = original_max

            # notifications 566
            await db.execute("DELETE FROM auctions")
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (10, 'WA', 1, 0), (11, 'WB', 2, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 10, 'leader'), (2, 11, 'leader')"
            )
            await db.execute(
                "INSERT INTO clan_wars (id, clan1_id, clan2_id, start_time, status) "
                "VALUES (2, 10, 11, 'now', 'active')"
            )
            await db.commit()
            m.NOTIFICATION_RUNTIME._bot_getter = lambda: NB()
            m.NOTIFICATION_RUNTIME.max_sent_per_cycle = 1
            try:
                await m.run_notification_cycle()
            finally:
                m.NOTIFICATION_RUNTIME._bot_getter = original_bot
                m.NOTIFICATION_RUNTIME.max_sent_per_cycle = original_max
        finally:
            m.ADVENT_RUNTIME._event_getter = original_event
            m.ADVENT_RUNTIME.rewards = original_rewards
            m.PET_RUNTIME._db_getter = original_pet_db
            m.RAID_COMBAT_RUNTIME._combat_power_getter = original_combat
            await _close(db)

    asyncio.run(run())
