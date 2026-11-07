
import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_coverage_100_part2", BOT_PATH)
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
        self.followup = FakeFollowup(fail_followup)
        self.data = {"values": ["1"]}
        self.message = None
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


class Cursor:
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


def test_progress_advent_seasons_edges():
    async def run():
        db = await _init()
        original_pool = m.PROGRESS_RUNTIME.quest_pool
        original_event = m.ADVENT_RUNTIME._event_getter
        original_rewards = m.ADVENT_RUNTIME.rewards
        original_season_db = m.SEASON_RUNTIME._db_getter
        original_date = None
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, daily_quest_date) "
                "VALUES (10, 10000, 1000, '2000-01-01')"
            )
            await db.commit()
            await db.execute("DELETE FROM achievements")
            await db.commit()
            assert await m.check_achievements(10) == []

            await db.execute(
                "INSERT INTO achievements (id, name, description, reward_gems, emoji) "
                "VALUES ('rich_10000', 'Rich', 'x', 1, 'X')"
            )
            await db.execute(
                "CREATE TRIGGER trg_ach100 BEFORE INSERT ON player_achievements "
                "WHEN NEW.user_id = 10 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            await m.check_achievements(10)
            await db.execute("DROP TRIGGER trg_ach100")
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
                await m.get_or_create_daily_quests(10)
            finally:
                m.PROGRESS_RUNTIME.quest_pool = original_pool

            event = {"key": "probe", "days": 4, "emoji": "X", "name": "Probe"}
            m.ADVENT_RUNTIME._event_getter = lambda: (lambda: (event, 1))
            m.ADVENT_RUNTIME._rewards = {
                1: (1, 2, "basic_gen"),
                2: (1, 2, None),
                3: (1, 2, "basic_gen"),
                4: (1, 2, None),
            }
            await db.execute(
                "INSERT INTO advent_state "
                "(user_id, last_opened_day, last_opened_date, event_key) "
                "VALUES (10, 0, NULL, 'probe')"
            )
            await db.execute(
                "INSERT INTO advent_progress (user_id, day) VALUES (10, 1)"
            )
            await db.commit()
            ok, msg, reward = await m.open_advent_day(10, 1)
            assert not ok

            await db.execute("DELETE FROM advent_progress WHERE user_id = 10")
            await db.commit()
            ok, msg, reward = await m.open_advent_day(10, 1)
            assert ok

            await db.execute(
                "UPDATE advent_state SET last_opened_day = 2, last_opened_date = NULL "
                "WHERE user_id = 10"
            )
            await db.commit()
            embed = await m.build_advent_embed(FakeInteraction(10), 0)
            assert embed
            m.ADVENT_RUNTIME._event_getter = original_event
            m.ADVENT_RUNTIME.rewards = original_rewards

            # season December branch
            import gen_mania.services.seasons as seasons_module

            original_date = seasons_module.datetime.date

            class FakeDate:
                @classmethod
                def today(cls):
                    return original_date(2026, 12, 15)

                def __new__(cls, *args, **kwargs):
                    return original_date(*args, **kwargs)

            seasons_module.datetime.date = FakeDate
            try:
                m.season_days_left()
            finally:
                seasons_module.datetime.date = original_date

            class NoneRowDB:
                def __init__(self, real):
                    self.real = real

                def __getattr__(self, name):
                    return getattr(self.real, name)

                def execute(self, sql, params=()):
                    if "SELECT xp, premium, claimed_free, claimed_premium" in sql:
                        return Cursor(row=None)
                    return self.real.execute(sql, params)

            m.SEASON_RUNTIME._db_getter = lambda: NoneRowDB(db)
            try:
                ok, msg, totals = await m.claim_season_rewards(10)
                assert not ok
            finally:
                m.SEASON_RUNTIME._db_getter = original_season_db

            season_id = m.current_season_id()
            await db.execute(
                "INSERT OR REPLACE INTO season_progress "
                "(user_id, season_id, xp, premium, claimed_free, claimed_premium, updated_at) "
                "VALUES (10, ?, 1000000, 0, '[]', '[]', 'now')",
                (season_id,),
            )
            await db.commit()
            ok, msg, totals = await m.claim_season_rewards(10)
            assert ok and totals["catalysts"] > 0
        finally:
            m.PROGRESS_RUNTIME.quest_pool = original_pool
            m.ADVENT_RUNTIME._event_getter = original_event
            m.ADVENT_RUNTIME.rewards = original_rewards
            m.SEASON_RUNTIME._db_getter = original_season_db
            await _close(db)

    asyncio.run(run())


def test_clan_pet_upgrade_raid_and_guide_edges():
    async def run():
        db = await _init()
        original_clan_app_db = m.CLAN_APPLICATION_RUNTIME._db_getter
        original_raid_db = m.RAID_RUNTIME._db_getter
        original_combat = m.RAID_COMBAT_RUNTIME._combat_power_getter
        original_season_xp = m.RAID_COMBAT_RUNTIME._season_xp_amount_getter
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 1000, 1000)",
                [(1,), (2,), (3,), (4,)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'A', 1, 10000), (2, 'B', 2, 10000)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) VALUES (1, 1, 'leader')"
            )
            await db.commit()

            await db.execute(
                "INSERT INTO clan_wars (id, clan1_id, clan2_id, start_time, status) "
                "VALUES (1, 2, 1, 'now', 'active')"
            )
            await db.commit()
            try:
                await m.start_clan_war(1, 2)
            except ValueError:
                pass
            await db.execute("DELETE FROM clan_wars")
            await db.commit()
            try:
                await m.start_clan_war(1, 999)
            except ValueError:
                pass

            await db.execute(
                "INSERT INTO clan_applications (id, clan_id, user_id, status) "
                "VALUES (1, 1, 3, 'pending')"
            )
            await db.commit()

            class AppDB:
                def __init__(self, real):
                    self.real = real
                    self.n = 0

                def __getattr__(self, name):
                    return getattr(self.real, name)

                def execute(self, sql, params=()):
                    if "SELECT clan_id, user_id, status" in sql:
                        return Cursor(row=(1, 3, "pending"))
                    if "SELECT status FROM clan_applications" in sql:
                        return Cursor(row=("accepted",))
                    return self.real.execute(sql, params)

            m.CLAN_APPLICATION_RUNTIME._db_getter = lambda: AppDB(db)
            try:
                await m.decide_clan_application(1, True, 1)
            finally:
                m.CLAN_APPLICATION_RUNTIME._db_getter = original_clan_app_db

            await db.execute(
                "INSERT INTO autocollectors (user_id, level, last_auto) VALUES (1, 1, NULL)"
            )
            await db.commit()
            await m.buy_autocollector(1)
            await db.execute(
                "CREATE TRIGGER trg_auto100 BEFORE UPDATE ON autocollectors "
                "WHEN OLD.user_id = 1 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            await m.upgrade_autocollector(1)
            await db.execute("DROP TRIGGER trg_auto100")
            await db.commit()

            await db.execute(
                "INSERT INTO player_upgrades (user_id, upgrade_id, expires_at) "
                "VALUES (1, 'vip', '9999-01-01T00:00:00')"
            )
            await db.commit()
            for page in range(4):
                await m.build_upgrades_page(FakeInteraction(1), page)
            m.UPGRADES_UI_RUNTIME.format_status_expiry("9999-01-01T00:00:00")

            await db.execute(
                "INSERT INTO raid_parties (id, leader_id, member2_id, member3_id) "
                "VALUES (1, 1, 2, 3)"
            )
            await db.commit()
            try:
                await m.join_raid_party(1, 4)
            except ValueError:
                pass

            async def power(user_id):
                return 1000 if user_id == 1 else 1

            m.RAID_COMBAT_RUNTIME._combat_power_getter = lambda: power
            try:
                try:
                    await m.perform_raid([1], 2)
                except ValueError:
                    pass
                await m.finalize_raid({"members": [1], "success": False})
            finally:
                m.RAID_COMBAT_RUNTIME._combat_power_getter = original_combat

            async def season_fail(action):
                raise RuntimeError("season fail")

            m.RAID_COMBAT_RUNTIME._season_xp_amount_getter = lambda: season_fail
            try:
                await m.finalize_raid({"members": [1], "success": False})
            finally:
                m.RAID_COMBAT_RUNTIME._season_xp_amount_getter = original_season_xp

            for key in m.GUIDE_SECTIONS:
                await m.build_guide_section_page(key, 0)

            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'storage', 0)"
            )
            await db.commit()
            await m.build_storage_embed(FakeInteraction(1), "epic")
        finally:
            m.CLAN_APPLICATION_RUNTIME._db_getter = original_clan_app_db
            m.RAID_RUNTIME._db_getter = original_raid_db
            m.RAID_COMBAT_RUNTIME._combat_power_getter = original_combat
            m.RAID_COMBAT_RUNTIME._season_xp_amount_getter = original_season_xp
            await _close(db)

    asyncio.run(run())


def test_notification_cycle_edges():
    async def run():
        db = await _init()
        original_bot = m.NOTIFICATION_RUNTIME._bot_getter
        original_max = m.NOTIFICATION_RUNTIME.max_sent_per_cycle
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, last_daily, active_pet) "
                "VALUES (1, 1000, ?, 'cat')",
                (m.datetime.datetime.now().isoformat(),),
            )
            await db.execute(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level, last_fed) "
                "VALUES (1, 'cat', 1, '2000-01-01T00:00:00')"
            )
            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, stars, start_price, current_bid, "
                "current_bidder, buyout_price, end_time, status) "
                "VALUES (1, 2, 'basic_gen', 0, 1, 1, 3, NULL, ?, 'active')",
                ((m.datetime.datetime.now() + m.datetime.timedelta(minutes=30)).isoformat(),),
            )
            await db.execute(
                "INSERT INTO clan_wars (id, clan1_id, clan2_id, start_time, status) "
                "VALUES (1, 1, 2, 'now', 'active')"
            )
            await db.commit()

            class User:
                async def send(self, *args, **kwargs):
                    return None

            class NotifyBot:
                def get_user(self, user_id):
                    return User()

                async def fetch_user(self, user_id):
                    return User()

            m.NOTIFICATION_RUNTIME._bot_getter = lambda: NotifyBot()
            m.NOTIFICATION_RUNTIME.max_sent_per_cycle = 1
            await m.run_notification_cycle()

            await db.execute(
                "INSERT INTO user_notifications (user_id, notif_type, enabled) "
                "VALUES (1, 'autocollect', 0)"
            )
            await db.execute(
                "INSERT INTO autocollectors (user_id, level, last_auto) "
                "VALUES (1, 1, '2000-01-01T00:00:00')"
            )
            await db.commit()
            m.NOTIFICATION_RUNTIME.max_sent_per_cycle = 5000
            await m.run_notification_cycle()
        finally:
            m.NOTIFICATION_RUNTIME._bot_getter = original_bot
            m.NOTIFICATION_RUNTIME.max_sent_per_cycle = original_max
            await _close(db)

    asyncio.run(run())
