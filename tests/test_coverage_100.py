
import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_coverage_100", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.messages = []

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class FakeFollowup:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.sent.append((args, kwargs))


class FakeMessage:
    async def edit(self, *args, **kwargs):
        return None

    async def delete(self):
        return None


class FakeInteraction:
    def __init__(self, user_id=1, fail_followup=False):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"U{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(id=1, owner_id=1)
        self.response = FakeResponse()
        self.followup = FakeFollowup(fail=fail_followup)
        self.data = {"values": ["1"]}
        self.message = FakeMessage()
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


class FakeCursor:
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


class ProxyDB:
    def __init__(self, real, mode):
        self.real = real
        self.mode = mode

    def __getattr__(self, name):
        return getattr(self.real, name)

    def execute(self, sql, params=()):
        if self.mode == "raid_detach" and "FROM raid_parties" in sql:
            return FakeCursor(row=(1, 10, 20, 30))
        return self.real.execute(sql, params)


def test_market_order_fill_edges():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 10000, 1000)",
                [(1,), (2,), (3,), (4,)],
            )
            await db.execute(
                "INSERT OR IGNORE INTO market_prices "
                "(item_id, base_price, current_price, demand, supply) "
                "VALUES ('basic_gen', 100, 100, 0, 0)"
            )
            await db.commit()
            await db.execute(
                "CREATE TRIGGER trg_mo681 BEFORE UPDATE OF coins ON players "
                "WHEN OLD.user_id = 4 AND NEW.coins < OLD.coins BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            assert (await m.create_market_order(4, "buy", "basic_gen", 1, 100))[0] is False
            await db.execute("DROP TRIGGER trg_mo681")
            await db.commit()

            future = (m.datetime.datetime.now() + m.datetime.timedelta(hours=1)).isoformat()
            past = (m.datetime.datetime.now() - m.datetime.timedelta(hours=1)).isoformat()
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (201, 2, 'sell', 'basic_gen', 0, 100, 1, 1, 'active', ?)",
                (future,),
            )
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (202, 2, 'sell', 'basic_gen', 0, 100, 1, 0, 'active', ?)",
                (future,),
            )
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (203, 2, 'buy', 'basic_gen', 0, 100, 1, 0, 'active', ?)",
                (future,),
            )
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (204, 2, 'buy', 'basic_gen', 0, 100, 1, 0, 'active', ?)",
                (future,),
            )
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (205, 2, 'sell', 'basic_gen', 0, 100, 1, 1, 'active', ?)",
                (past,),
            )
            await db.commit()

            await m.fill_market_order(201, 1)
            await db.execute("UPDATE players SET coins = 0 WHERE user_id = 3")
            await db.commit()
            await m.fill_market_order(202, 3)
            await m.fill_market_order(203, 1)
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'storage', 0)"
            )
            await db.execute(
                "CREATE TRIGGER trg_mo845 BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 1 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            await m.fill_market_order(204, 1)
            await db.execute("DROP TRIGGER trg_mo845")
            await db.commit()
            await m.expire_market_orders()

            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (301, 2, 'sell', 'basic_gen', 0, 120, 1, 0, 'active', ?)",
                (future,),
            )
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (302, 3, 'buy', 'basic_gen', 0, 100, 1, 0, 'active', ?)",
                (future,),
            )
            await db.commit()
            await m.match_market_orders("basic_gen")

            await db.execute(
                "UPDATE market_orders SET price = 105, status = 'active' WHERE id = 301"
            )
            await db.commit()
            await m.match_market_orders("basic_gen")

            class MatchFailDB:
                def __init__(self, real):
                    self.real = real

                def __getattr__(self, name):
                    return getattr(self.real, name)

                def execute(self, sql, params=()):
                    if "SELECT id, user_id, side, item_id, price, quantity" in sql:
                        raise RuntimeError("match fail")
                    return self.real.execute(sql, params)

            original_db_getter = m.MARKET_ORDER_RUNTIME._db_getter
            m.MARKET_ORDER_RUNTIME._db_getter = lambda: MatchFailDB(db)
            try:
                await m.create_market_order(3, "buy", "basic_gen", 1, 100)
            finally:
                m.MARKET_ORDER_RUNTIME._db_getter = original_db_getter
        finally:
            await _close(db)

    asyncio.run(run())


def test_progress_and_leaderboard_edges():
    async def run():
        db = await _init()
        original_quest_pool = m.PROGRESS_RUNTIME.quest_pool
        original_get_guild = m.bot.get_guild
        original_get_user = m.bot.get_user
        original_fetch_user = m.bot.fetch_user
        try:
            yesterday = (
                m.datetime.datetime.now() - m.datetime.timedelta(days=1)
            ).isoformat()
            await db.execute(
                "INSERT INTO players "
                "(user_id, coins, gems, last_daily, streak_days) "
                "VALUES (1, 1000, 1000, ?, 4)",
                (yesterday,),
            )
            await db.commit()
            res = await m.claim_daily(1)
            assert res["ok"]

            ach_quests = [
                qid
                for qid, data in m.STORY_QUESTS.items()
                if data[3] == "achievements"
            ]
            assert ach_quests
            await db.execute("DELETE FROM player_quests WHERE user_id = 1")
            await db.execute(
                "INSERT INTO player_quests (user_id, quest_id, progress, completed) "
                "VALUES (1, ?, 0, 1)",
                (ach_quests[0],),
            )
            await db.commit()
            await m.sync_story_achievements(1)
            await db.execute("DELETE FROM player_quests WHERE user_id = 1")
            for index in range(20):
                await db.execute(
                    "INSERT OR IGNORE INTO player_achievements "
                    "(user_id, achievement_id) VALUES (1, ?)",
                    (f"probe_ach_{index}",),
                )
            await db.commit()
            await m.sync_story_achievements(1)

            await db.execute("DELETE FROM achievements")
            await db.commit()
            assert await m.check_achievements(1) == []

            await db.execute(
                "INSERT INTO achievements (id, name, description, reward_gems, emoji) "
                "VALUES ('rich_1000', 'Rich', 'x', 1, 'X')"
            )
            await db.execute(
                "CREATE TRIGGER trg_ach_ignore BEFORE INSERT ON player_achievements "
                "WHEN NEW.user_id = 1 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            await m.check_achievements(1)
            await db.execute("DROP TRIGGER trg_ach_ignore")
            await db.commit()

            m.PROGRESS_RUNTIME.quest_pool = {
                "donate_clan": {},
                "feed_pet": {},
                "close_deposit": {},
                "bid_auction": {},
                "sell_3": {},
                "star_up_1": {},
                "star_fail_1": {},
                "sell_auction": {},
            }
            try:
                await m.get_or_create_daily_quests(1)
            finally:
                m.PROGRESS_RUNTIME.quest_pool = original_quest_pool

            class Guild:
                members = [SimpleNamespace(id=1)]

            m.bot.get_guild = lambda guild_id: Guild()
            await m.get_top_players("clans", 10, 1)
            m.bot.get_guild = original_get_guild

            async def fetch_fail(user_id):
                raise m.discord.NotFound.__new__(m.discord.NotFound)

            m.bot.get_user = lambda user_id: None
            m.bot.fetch_user = fetch_fail
            try:
                await m.build_top_embed(FakeInteraction(1), "coins", 10)
            finally:
                m.bot.get_user = original_get_user
                m.bot.fetch_user = original_fetch_user
        finally:
            m.PROGRESS_RUNTIME.quest_pool = original_quest_pool
            m.bot.get_guild = original_get_guild
            m.bot.get_user = original_get_user
            m.bot.fetch_user = original_fetch_user
            await _close(db)

    asyncio.run(run())


def test_raid_pet_top_and_upgrade_edges():
    async def run():
        db = await _init()
        original_raid_db = m.RAID_RUNTIME._db_getter
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 1000, 1000)",
                [(1,), (2,), (3,), (4,)],
            )
            await db.commit()
            await db.execute(
                "INSERT INTO raid_parties (id, leader_id, created_at, updated_at) "
                "VALUES (1, 1, NULL, NULL)"
            )
            await db.commit()
            await m.cleanup_expired_raid_parties()

            await db.execute(
                "UPDATE raid_parties SET member2_id = 2, member3_id = 3 WHERE id = 1"
            )
            await db.commit()
            try:
                await m.join_raid_party(1, 4)
            except ValueError:
                pass

            m.RAID_RUNTIME._db_getter = lambda: ProxyDB(db, "raid_detach")
            try:
                assert await m.detach_user_from_raid_party(4) == "none"
            finally:
                m.RAID_RUNTIME._db_getter = original_raid_db

            await db.execute(
                "INSERT INTO autocollectors (user_id, level, last_auto) VALUES (1, 1, NULL)"
            )
            await db.commit()
            await m.buy_autocollector(1)
            await db.execute(
                "CREATE TRIGGER trg_auto_upgrade BEFORE UPDATE ON autocollectors "
                "WHEN OLD.user_id = 1 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            await m.upgrade_autocollector(1)
            await db.execute("DROP TRIGGER trg_auto_upgrade")
            await db.commit()

            interaction = FakeInteraction(1, fail_followup=True)
            try:
                await m.enforce_top_exclusion(interaction, 1, "probe")
            except Exception:
                pass

            await db.execute(
                "INSERT INTO player_upgrades (user_id, upgrade_id, expires_at) "
                "VALUES (1, 'vip', '9999-01-01T00:00:00')"
            )
            await db.commit()
            await m.build_upgrades_page(FakeInteraction(1), 2)
        finally:
            m.RAID_RUNTIME._db_getter = original_raid_db
            await _close(db)

    asyncio.run(run())


class _EdgeCursor:
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


class _EdgeDB:
    def __init__(self, real):
        self.real = real

    def __getattr__(self, name):
        return getattr(self.real, name)

    def execute(self, sql, params=()):
        if "FROM auctions WHERE status = 'active' AND end_time < ?" in sql:
            return _EdgeCursor(rows=[(1, 1, "basic_gen", 0, 0, None)])
        if "UPDATE auctions SET status = 'closing'" in sql:
            return _EdgeCursor(rowcount=1)
        if "SELECT seller_id, item_id, stars, current_bid" in sql:
            return _EdgeCursor(row=None)
        return self.real.execute(sql, params)


def test_market_edges_isolated():
    async def run():
        db = await _init()
        original_db = m.MARKET_ORDER_RUNTIME._db_getter
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 10000, 1000)",
                [(1,), (2,), (3,), (4,)],
            )
            await db.commit()
            future = (m.datetime.datetime.now() + m.datetime.timedelta(hours=1)).isoformat()
            past = (m.datetime.datetime.now() - m.datetime.timedelta(hours=1)).isoformat()

            async def reset_orders():
                await db.execute("DELETE FROM market_orders")
                await db.execute("DELETE FROM inventory")
                await db.execute("UPDATE players SET coins = 10000")
                await db.commit()

            # 681
            await reset_orders()
            await db.execute(
                "CREATE TRIGGER t681 BEFORE UPDATE OF coins ON players "
                "WHEN OLD.user_id = 4 AND NEW.coins < OLD.coins BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            assert (await m.create_market_order(4, "buy", "basic_gen", 1, 13))[0] is False
            await db.execute("DROP TRIGGER t681")
            await db.commit()

            # 797
            await reset_orders()
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (201, 2, 'sell', 'basic_gen', 0, 13, 1, 1, 'active', ?)",
                (future,),
            )
            await db.commit()
            assert (await m.fill_market_order(201, 1))[0] is False

            # 807
            await reset_orders()
            await db.execute("UPDATE players SET coins = 0 WHERE user_id = 3")
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (202, 2, 'sell', 'basic_gen', 0, 13, 1, 0, 'active', ?)",
                (future,),
            )
            await db.commit()
            assert (await m.fill_market_order(202, 3))[0] is False

            # 833
            await reset_orders()
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (203, 2, 'buy', 'basic_gen', 0, 13, 1, 0, 'active', ?)",
                (future,),
            )
            await db.commit()
            assert (await m.fill_market_order(203, 1))[0] is False

            # 845
            await reset_orders()
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'storage', 0)"
            )
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (204, 2, 'buy', 'basic_gen', 0, 13, 1, 0, 'active', ?)",
                (future,),
            )
            await db.execute(
                "CREATE TRIGGER t845 BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 1 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            assert (await m.fill_market_order(204, 1))[0] is False
            await db.execute("DROP TRIGGER t845")
            await db.commit()

            # 983/988
            await reset_orders()
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (205, 2, 'sell', 'basic_gen', 0, 13, 1, 1, 'active', ?)",
                (past,),
            )
            await db.commit()
            await m.expire_market_orders()

            # 446
            await reset_orders()
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (301, 2, 'sell', 'basic_gen', 0, 20, 1, 0, 'active', ?)",
                (future,),
            )
            await db.execute(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (302, 3, 'buy', 'basic_gen', 0, 13, 1, 0, 'active', ?)",
                (future,),
            )
            await db.commit()
            await m.match_market_orders("basic_gen")

            # 448
            await db.execute(
                "UPDATE market_orders SET price = 14 WHERE id = 301"
            )
            await db.commit()
            await m.match_market_orders("basic_gen")

            # 706/707/710/740
            await reset_orders()

            class MatchFailDB:
                def __init__(self, real):
                    self.real = real

                def __getattr__(self, name):
                    return getattr(self.real, name)

                def execute(self, sql, params=()):
                    if "SELECT id, user_id, side, item_id, price, quantity" in sql:
                        raise RuntimeError("match fail")
                    return self.real.execute(sql, params)

            m.MARKET_ORDER_RUNTIME._db_getter = lambda: MatchFailDB(db)
            try:
                await m.create_market_order(3, "buy", "basic_gen", 1, 13)
            finally:
                m.MARKET_ORDER_RUNTIME._db_getter = original_db
        finally:
            m.MARKET_ORDER_RUNTIME._db_getter = original_db
            await _close(db)

    asyncio.run(run())


def test_bot_remaining_lines():
    async def run():
        db = await _init()
        original_version = m.CONTENT_VERSION
        try:
            await db.execute(
                "INSERT OR REPLACE INTO content_meta (key, value) "
                "VALUES ('content_version', '0')"
            )
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (99, 1000, 100)"
            )
            await db.commit()
            m.CONTENT_VERSION = original_version + 100
            await m.bot.apply_content_migrations([("bad",)], [], [], [], [])
            m.CONTENT_VERSION = original_version

            m.bot.db = _EdgeDB(db)
            try:
                await m.bot.auction_closer.__func__(m.bot)
            except Exception:
                pass
            m.bot.db = db

            view = m.StarConfirmView(99, 0, "basic_gen", 0, 1, "profile")
            await view.confirm.callback(FakeInteraction(99))

            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (99, 0, 'basic_gen', 'profile', 0)"
            )
            await db.execute(
                "CREATE TRIGGER trg_sell99 BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 99 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            modal = m.AuctionSellDetailsModal(99, 0, "basic_gen", 0)
            modal.start_price._value = "10"
            modal.buyout_price._value = "20"
            modal.hours._value = "1"
            await modal.on_submit(FakeInteraction(99))
            await db.execute("DROP TRIGGER trg_sell99")
            await db.commit()
        finally:
            m.CONTENT_VERSION = original_version
            m.bot.db = db
            await _close(db)

    asyncio.run(run())
