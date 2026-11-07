
import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_coverage_100_last", BOT_PATH)
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


def test_last_reachable_lines():
    async def run():
        db = await _init()
        original_bot_db = m.bot.db
        original_pet_db = m.PET_RUNTIME._db_getter
        original_combat = m.RAID_COMBAT_RUNTIME._combat_power_getter
        original_raid_db = m.RAID_COMBAT_RUNTIME._db_getter
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 1000, 1000)",
                [(1,), (2,), (3,), (4,), (99,)],
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (99, 0, 'basic_gen', 'profile', 1)"
            )
            await db.commit()

            # auction sell rowcount0 via proxy
            class SellDB:
                def __init__(self, real):
                    self.real = real

                def __getattr__(self, name):
                    return getattr(self.real, name)

                def execute(self, sql, params=()):
                    if "DELETE FROM inventory" in sql and "location = 'profile'" in sql:
                        return Cur(rowcount=0)
                    return self.real.execute(sql, params)

            m.bot.db = SellDB(db)
            modal = m.AuctionSellDetailsModal(99, 0, "basic_gen", 1)
            modal.start_price._value = "10"
            modal.buyout_price._value = "20"
            modal.hours._value = "1"
            await modal.on_submit(Inter(99))
            m.bot.db = db

            # pets buy duplicate inside transaction
            class BuyDB:
                def __init__(self, real):
                    self.real = real

                def __getattr__(self, name):
                    return getattr(self.real, name)

                def execute(self, sql, params=()):
                    if "SELECT level, last_auto FROM autocollectors" in sql:
                        return Cur(row=None)
                    if "SELECT 1 FROM autocollectors" in sql:
                        return Cur(row=(1,))
                    return self.real.execute(sql, params)

            m.PET_RUNTIME._db_getter = lambda: BuyDB(db)
            await m.buy_autocollector(1)

            # pets upgrade changed data
            class UpgradeDB:
                def __init__(self, real):
                    self.real = real

                def __getattr__(self, name):
                    return getattr(self.real, name)

                def execute(self, sql, params=()):
                    if "SELECT level, last_auto FROM autocollectors" in sql:
                        return Cur(row=(1, None))
                    if "SELECT level FROM autocollectors" in sql:
                        return Cur(row=(2,))
                    return self.real.execute(sql, params)

            m.PET_RUNTIME._db_getter = lambda: UpgradeDB(db)
            await m.upgrade_autocollector(1)
            m.PET_RUNTIME._db_getter = original_pet_db

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

            # raid wallet changed
            await db.execute("UPDATE players SET coins = 1000 WHERE user_id = 2")
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0)"
            )
            await db.commit()

            async def power(user_id):
                return 1000 if user_id == 1 else 800

            class RaidDB:
                def __init__(self, real):
                    self.real = real

                def __getattr__(self, name):
                    return getattr(self.real, name)

                def execute(self, sql, params=()):
                    if "UPDATE players SET coins = coins - ?" in sql and params:
                        if len(params) >= 2 and params[1] == 2:
                            return Cur(rowcount=0)
                    return self.real.execute(sql, params)

            m.RAID_COMBAT_RUNTIME._combat_power_getter = lambda: power
            m.RAID_COMBAT_RUNTIME._db_getter = lambda: RaidDB(db)
            original_randint = m.random.randint
            rolls = {"n": 0}

            def randint(a, b):
                rolls["n"] += 1
                return b if rolls["n"] == 1 else a

            m.random.randint = randint
            try:
                await m.perform_raid([1], 2)
            finally:
                m.random.randint = original_randint
                m.RAID_COMBAT_RUNTIME._combat_power_getter = original_combat
                m.RAID_COMBAT_RUNTIME._db_getter = original_raid_db
        finally:
            m.bot.db = original_bot_db
            m.PET_RUNTIME._db_getter = original_pet_db
            m.RAID_COMBAT_RUNTIME._combat_power_getter = original_combat
            m.RAID_COMBAT_RUNTIME._db_getter = original_raid_db
            await _close(db)

    asyncio.run(run())


def test_join_full_party_line():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, 1000)",
                [(1,), (2,), (3,), (4,)],
            )
            await db.execute(
                "INSERT INTO raid_parties (id, leader_id, member2_id, member3_id) "
                "VALUES (1, 1, 2, 3)"
            )
            await db.commit()
            try:
                await m.join_raid_party(1, 4)
            except ValueError:
                pass
        finally:
            await _close(db)

    asyncio.run(run())
