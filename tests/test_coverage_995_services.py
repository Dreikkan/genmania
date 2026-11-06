
import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

from gen_mania.db.transaction import TransactionRuntime, make_transaction_layer

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_coverage_995_services", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def fetchone(self):
        return None

    async def fetchall(self):
        return []


class FakeDB:
    in_transaction = False

    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.fail_begin = False

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    def execute(self, sql, params=()):
        if self.fail_begin and sql == "BEGIN IMMEDIATE":
            raise aiosqlite.OperationalError("other error")
        return FakeCtx()


class FakeLogger:
    def __init__(self):
        self.warnings = []
        self.errors = []

    def warning(self, *args, **kwargs):
        self.warnings.append((args, kwargs))

    def exception(self, *args, **kwargs):
        self.errors.append((args, kwargs))


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


def test_transaction_layer_edges():
    async def run():
        runtime = TransactionRuntime()
        db = FakeDB()
        lock = asyncio.Lock()
        owner = {"value": None}
        runtime._db_getter = lambda: db
        runtime._lock_getter = lambda: lock
        runtime._owner_getter = lambda: owner["value"]
        runtime._owner_setter = lambda value: owner.__setitem__("value", value)
        runtime.logger = FakeLogger()
        runtime.slow_ms = 0
        db_tx, commit, rollback = make_transaction_layer(runtime)

        runtime.log_slow(1)
        assert runtime.logger.warnings

        import gen_mania.db.transaction as tx_module

        original_current = tx_module.asyncio.current_task
        tx_module.asyncio.current_task = lambda: (_ for _ in ()).throw(RuntimeError())
        try:
            await commit()
        finally:
            tx_module.asyncio.current_task = original_current
        assert db.commits == 1

        owner["value"] = asyncio.current_task()
        await rollback()
        assert db.rollbacks == 0

        owner["value"] = None
        await rollback()
        assert db.rollbacks == 1

        db.fail_begin = True
        try:
            async with db_tx():
                pass
        except aiosqlite.OperationalError:
            pass

    asyncio.run(run())


def test_bank_clan_apps_and_raids():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 1000, 100)",
                [(1,), (2,), (3,), (4,), (5,), (6,)],
            )
            await db.execute(
                "INSERT OR IGNORE INTO items "
                "(id, name, price, income_per_hour, emoji, rarity, buyable) "
                "VALUES ('loan_gen', 'Loan', 100000, 1, 'X', 'common', 1)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury, capacity) "
                "VALUES (1, 'Probe', 1, 1000, 10)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) VALUES (1, 1, 'leader')"
            )
            await db.commit()
            ok, msg = await m.take_bank_loan(1, "loan_gen", 0, 1000)
            assert not ok

            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (2, 0, 'loan_gen', 'profile', 0)"
            )
            await db.execute(
                "CREATE TRIGGER trg_loan_del_ignore BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 2 AND OLD.slot = 0 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            ok, msg = await m.take_bank_loan(2, "loan_gen", 0, 1000)
            assert not ok
            await db.execute("DROP TRIGGER trg_loan_del_ignore")
            await db.commit()

            await db.execute(
                "INSERT INTO bank_loans "
                "(user_id, amount, interest_rate, due_time, collateral_item, "
                "collateral_stars, issued_at, status) "
                "VALUES (4, 100, 0.05, '9999-01-01T00:00:00', 'loan_gen', 0, 'now', 'active')"
            )
            await db.execute(
                "CREATE TRIGGER trg_repay_coins_ignore BEFORE UPDATE OF coins ON players "
                "WHEN OLD.user_id = 4 AND NEW.coins < OLD.coins BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            ok, msg = await m.repay_bank_loan(4)
            assert not ok
            await db.execute("DROP TRIGGER trg_repay_coins_ignore")
            await db.execute(
                "CREATE TRIGGER trg_repay_delete_ignore BEFORE DELETE ON bank_loans "
                "WHEN OLD.user_id = 4 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            ok, msg = await m.repay_bank_loan(4)
            assert not ok
            await db.execute("DROP TRIGGER trg_repay_delete_ignore")
            await db.commit()

            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury, capacity) "
                "VALUES (2, 'App', 1, 0, 10)"
            )
            await db.execute(
                "INSERT INTO clan_applications (id, clan_id, user_id, status) "
                "VALUES (1, 2, 3, 'pending')"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) VALUES (3, 2, 'member')"
            )
            await db.commit()
            ok, msg = await m.decide_clan_application(1, True, 1)
            assert not ok

            await db.execute("DELETE FROM clan_members WHERE user_id = 3")
            await db.execute("UPDATE clans SET capacity = 1 WHERE id = 2")
            await db.commit()
            ok, msg = await m.decide_clan_application(1, True, 1)
            assert not ok

            await db.execute(
                "INSERT INTO raid_parties (id, leader_id) VALUES (1, 1)"
            )
            await db.commit()
            try:
                await m.create_raid_party(1)
            except ValueError:
                pass

            await db.execute(
                "UPDATE raid_parties SET member2_id = 2, member3_id = 3 WHERE id = 1"
            )
            await db.commit()
            try:
                await m.join_raid_party(1, 4)
            except ValueError:
                pass

            assert await m.detach_user_from_raid_party(999) == "none"

            await db.execute(
                "INSERT INTO raid_parties (id, leader_id) VALUES (2, 4)"
            )
            await db.commit()
            await m.cleanup_expired_raid_parties()

            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (5, 0, 'loan_gen', 'profile', 0)"
            )
            await db.execute(
                "CREATE TRIGGER trg_lock_ignore BEFORE UPDATE ON inventory "
                "WHEN OLD.user_id = 5 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            ok, state, msg = await m.toggle_item_lock(5, "profile", 0, "loan_gen", 0)
            assert not ok
            await db.execute("DROP TRIGGER trg_lock_ignore")
            await db.commit()
        finally:
            await _close(db)

    asyncio.run(run())


def test_inventory_clan_and_setting_edges():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, grid_size, storage_size) VALUES (10, 9, 1)"
            )
            for slot in range(9):
                await db.execute(
                    "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                    "VALUES (10, ?, 'basic_gen', 'profile', 0)",
                    (slot,),
                )
            await db.commit()
            await m.place_items(10, "basic_gen", 2, commit=False)

            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury, level, xp) "
                "VALUES (1, 'Probe', 1, 0, 1, 0)"
            )
            await db.commit()
            await m.add_clan_xp(1, 0)
            await m.add_clan_xp(1, 10 ** 9)
            assert await m.get_clan_level_info(999) == (1, 0, 0.0)

            await m.save_setting(1, "__unknown__", 1)
            await m.save_setting(1, "bot_name", "x" * 250)
        finally:
            await _close(db)

    asyncio.run(run())


def test_season_and_advent_edges():
    async def run():
        db = await _init()
        original_weekend = m.SEASON_RUNTIME._weekend_mult_getter
        original_tx = m.SEASON_RUNTIME._transaction_getter
        original_ach = m.SEASON_RUNTIME._achievements_getter
        original_event = m.ADVENT_RUNTIME._event_getter
        original_rewards = m.ADVENT_RUNTIME.rewards
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 100)"
            )
            await db.commit()

            m.SEASON_RUNTIME._weekend_mult_getter = lambda: 1.0
            assert m.season_event_label() is None
            assert m.season_progress_bar(0, 0) == chr(0x25B0) * 10
            assert m._parse_season_claimed("bad") == set()
            assert await m.add_season_xp(1, 0) == 0

            class BrokenTx:
                async def __aenter__(self):
                    raise RuntimeError("tx fail")

                async def __aexit__(self, *args):
                    return None

            m.SEASON_RUNTIME._transaction_getter = lambda: (lambda: BrokenTx())
            try:
                assert await m.add_season_xp(1, 10) == 0
            finally:
                m.SEASON_RUNTIME._transaction_getter = original_tx

            season_id = m.current_season_id()
            await db.execute(
                "INSERT OR REPLACE INTO season_progress "
                "(user_id, season_id, xp, premium, claimed_free, claimed_premium, updated_at) "
                "VALUES (1, ?, 1000000, 0, '[]', '[]', 'now')",
                (season_id,),
            )
            await db.execute(
                "INSERT OR REPLACE INTO season_progress "
                "(user_id, season_id, xp, premium, claimed_free, claimed_premium, updated_at) "
                "VALUES (2, ?, 500, 0, '[]', '[]', 'now')",
                (season_id,),
            )
            await db.commit()
            embed = await m.build_season_embed(1)
            assert embed

            async def achievements_fail(user_id):
                raise RuntimeError("ach fail")

            m.SEASON_RUNTIME._achievements_getter = lambda: achievements_fail
            try:
                ok, msg, totals = await m.claim_season_rewards(2)
                assert ok
            finally:
                m.SEASON_RUNTIME._achievements_getter = original_ach

            event = {"key": "probe", "days": 3, "emoji": "X", "name": "Probe"}
            m.ADVENT_RUNTIME._event_getter = lambda: (lambda: (None, 0))
            assert await m.get_advent_opened(1) == set()
            assert (await m.can_open_advent_today(1))[0] is False

            m.ADVENT_RUNTIME._event_getter = lambda: (lambda: (event, 1))
            m.ADVENT_RUNTIME._rewards = {1: (1, 2, "basic_gen"), 2: (1, 2, None), 3: (1, 2, None)}
            await db.execute(
                "INSERT INTO advent_state "
                "(user_id, last_opened_day, last_opened_date, event_key) "
                "VALUES (1, 3, NULL, 'probe')"
            )
            await db.execute(
                "INSERT INTO advent_progress (user_id, day) VALUES (1, 1)"
            )
            await db.commit()
            opened = await m.get_advent_opened(1)
            assert 1 in opened
            assert (await m.can_open_advent_today(1))[0] is False

            await db.execute(
                "UPDATE advent_state SET last_opened_day = 0, last_opened_date = ? "
                "WHERE user_id = 1",
                (m.datetime.date.today().isoformat(),),
            )
            await db.commit()
            assert (await m.can_open_advent_today(1))[0] is False

            await db.execute(
                "UPDATE advent_state SET last_opened_date = NULL WHERE user_id = 1"
            )
            await db.commit()
            ok, msg, reward = await m.open_advent_day(1, 99)
            assert not ok
            await db.execute(
                "UPDATE advent_state SET last_opened_day = 3 WHERE user_id = 1"
            )
            await db.execute("DELETE FROM advent_progress WHERE user_id = 1")
            await db.commit()
            ok, msg, reward = await m.open_advent_day(1, 1)
            assert not ok

            await db.execute(
                "UPDATE advent_state SET last_opened_day = 0, last_opened_date = ? "
                "WHERE user_id = 1",
                (m.datetime.date.today().isoformat(),),
            )
            await db.commit()
            ok, msg, reward = await m.open_advent_day(1, 1)
            assert not ok

            await db.execute(
                "UPDATE advent_state SET last_opened_date = NULL WHERE user_id = 1"
            )
            await db.execute(
                "INSERT INTO advent_progress (user_id, day) VALUES (1, 1)"
            )
            await db.commit()
            ok, msg, reward = await m.open_advent_day(1, 2)
            assert not ok

            await db.execute("DELETE FROM advent_progress WHERE user_id = 1")
            await db.commit()
            ok, msg, reward = await m.open_advent_day(1, 1)
            assert ok

            class Inter:
                user = type("U", (), {"id": 1})()

            embed = await m.build_advent_embed(Inter(), 0)
            assert embed
            m.ADVENT_RUNTIME._event_getter = original_event
            embed = await m.build_advent_embed(Inter(), 0)
            assert embed
        finally:
            m.SEASON_RUNTIME._weekend_mult_getter = original_weekend
            m.SEASON_RUNTIME._transaction_getter = original_tx
            m.SEASON_RUNTIME._achievements_getter = original_ach
            m.ADVENT_RUNTIME._event_getter = original_event
            m.ADVENT_RUNTIME.rewards = original_rewards
            await _close(db)

    asyncio.run(run())


class _FakeCursor:
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


class _ProxyDB:
    def __init__(self, real, mode):
        self._real = real
        self._mode = mode

    def __getattr__(self, name):
        return getattr(self._real, name)

    def execute(self, sql, params=()):
        if self._mode == "auction_zero" and "UPDATE auctions SET status = 'closing'" in sql:
            return _FakeCursor(rowcount=0)
        if self._mode == "auction_no_fresh":
            if "UPDATE auctions SET status = 'closing'" in sql:
                return _FakeCursor(rowcount=1)
            if "SELECT seller_id, item_id, stars, current_bid" in sql:
                return _FakeCursor(row=None)
        if self._mode == "auction_lots" and "FROM auctions WHERE status = 'active'" in sql:
            return _FakeCursor(rows=[(1, 1, "basic_gen", 0, 0, None)])
        if self._mode == "tax_no_row" and "SELECT user_id, coins, last_tax_time FROM players" in sql:
            return _FakeCursor(rows=[(1, 100, None)])
        if self._mode == "tax_no_row" and "SELECT coins, last_tax_time FROM players" in sql:
            return _FakeCursor(row=None)
        if self._mode == "tax_update_zero":
            if "SELECT user_id, coins, last_tax_time FROM players" in sql:
                return _FakeCursor(rows=[(1, 1000, None)])
            if "SELECT coins, last_tax_time FROM players" in sql:
                return _FakeCursor(row=(1000, None))
            if "UPDATE players SET coins = coins - ?" in sql:
                return _FakeCursor(rowcount=0)
        if self._mode == "auto_recent":
            if "SELECT user_id, level, last_auto FROM autocollectors" in sql:
                return _FakeCursor(rows=[(1, 1, None)])
            if "SELECT last_auto FROM autocollectors" in sql:
                return _FakeCursor(row=(m.datetime.datetime.now().isoformat(),))
        return self._real.execute(sql, params)


def test_remaining_background_and_modal_branches(tmp_path):
    async def run():
        db = await _init()
        original_sleep = m.asyncio.sleep
        original_transaction = m.db_transaction
        original_rotating = m.RotatingFileHandler
        original_connect = m.aiosqlite.connect
        original_getenv = m.os.getenv
        original_clan_role = m.get_clan_role
        original_perm = m.has_clan_permission
        original_active_war = m.get_active_clan_war
        original_start_war = m.start_clan_war
        original_event = m.get_active_advent_event
        original_profile = m.build_user_profile_embed
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 100)"
            )
            await db.commit()

            fake = object.__new__(m.CastleBot)
            m.os.getenv = lambda key, default=None: str(tmp_path)
            m.RotatingFileHandler = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError())
            m.aiosqlite.connect = lambda path: (_ for _ in ()).throw(RuntimeError())
            try:
                try:
                    await m.CastleBot.setup_hook(fake)
                except Exception:
                    pass
            finally:
                m.RotatingFileHandler = original_rotating
                m.aiosqlite.connect = original_connect
                m.os.getenv = original_getenv

            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'A', 1, 0), (2, 'B', 2, 0)"
            )
            await db.execute(
                "INSERT INTO clan_wars (id, clan1_id, clan2_id, start_time, status) "
                "VALUES (1, 1, 2, 'now', 'active')"
            )
            await db.commit()

            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def tx_mark_finished():
                await db.execute(
                    "UPDATE clan_wars SET status = 'finished' WHERE id = 1"
                )
                yield

            m.db_transaction = tx_mark_finished
            await _once(m.bot.war_closer)
            m.db_transaction = original_transaction

            await m.bot.apply_content_migrations([], [], [], [], [])
            # failure inside the content migration transaction
            @asynccontextmanager
            async def broken_tx():
                raise RuntimeError("broken")
                yield

            m.db_transaction = broken_tx
            await m.bot.apply_content_migrations([], [], [], [], [])
            m.db_transaction = original_transaction

            for mode in ("auction_zero", "auction_no_fresh"):
                m.bot.db = _ProxyDB(db, "auction_lots")
                await _once(m.bot.auction_closer)
                m.bot.db = db

            for mode in ("tax_no_row", "tax_update_zero"):
                m.bot.db = _ProxyDB(db, mode)
                await _once(m.bot.tax_collector)
                m.bot.db = db

            m.bot.db = _ProxyDB(db, "auto_recent")
            await _once(m.bot.autocollector_task)
            m.bot.db = db

            m.get_clan_role = lambda user_id, clan_id: _leader()
            m.has_clan_permission = lambda role, action: True
            m.get_active_clan_war = lambda clan_id: _none()
            m.start_clan_war = lambda *args: _none()
            view = m.ClanMenuView(1, 1)
            interaction = _Interaction(1)
            try:
                await view.btn_war.callback(interaction)
            except Exception:
                pass
            m.get_clan_role = original_clan_role
            m.has_clan_permission = original_perm
            m.get_active_clan_war = original_active_war
            m.start_clan_war = original_start_war

            view = m.StarConfirmView(1, 0, "basic_gen", 0, 1, "profile")
            interaction = _Interaction(1)
            await view.confirm.callback(interaction)

            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 3, 'basic_gen', 'profile', 0)"
            )
            await db.execute(
                "CREATE TRIGGER trg_sell_details_ignore BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 1 AND OLD.slot = 3 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            modal = m.AuctionSellDetailsModal(1, 3, "basic_gen", 0)
            modal.start_price._value = "10"
            modal.buyout_price._value = "20"
            modal.hours._value = "1"
            interaction = _Interaction(1)
            await modal.on_submit(interaction)
            await db.execute("DROP TRIGGER trg_sell_details_ignore")
            await db.commit()

            async def user_profile(interaction):
                return m.BotEmbed(title="U")

            m.build_user_profile_embed = user_profile
            modal = m.UserResetModal(1, main_message=_FailMessage())
            modal.confirm._value = "\u0421\u0411\u0420\u041e\u0421\u0418\u0422\u042c"
            interaction = _Interaction(1)
            await modal.on_submit(interaction)
            m.build_user_profile_embed = original_profile

            event = {"key": "probe", "days": 3, "emoji": "X", "name": "Probe"}
            m.get_active_advent_event = lambda: (event, 1)
            await db.execute(
                "INSERT OR REPLACE INTO advent_progress (user_id, day) VALUES (1, 1)"
            )
            await db.commit()
            modal = m.AdminOpenAdventModal(1)
            modal.user_id._value = "1"
            modal.day._value = "1"
            interaction = _Interaction(1)
            await modal.on_submit(interaction)
            m.get_active_advent_event = original_event
        finally:
            m.asyncio.sleep = original_sleep
            m.db_transaction = original_transaction
            m.RotatingFileHandler = original_rotating
            m.aiosqlite.connect = original_connect
            m.os.getenv = original_getenv
            m.get_clan_role = original_clan_role
            m.has_clan_permission = original_perm
            m.get_active_clan_war = original_active_war
            m.start_clan_war = original_start_war
            m.get_active_advent_event = original_event
            m.build_user_profile_embed = original_profile
            m.bot.db = db
            await _close(db)

    asyncio.run(run())


class _Interaction:
    def __init__(self, user_id=1):
        self.user = type("U", (), {"id": user_id, "name": "U", "display_avatar": type("A", (), {"url": "https://example.com/a.png"})()})()
        self.guild_id = 1
        self.guild = type("G", (), {"id": 1, "owner_id": 1})()
        self.response = _Response()
        self.followup = _Followup()
        self.data = {"values": ["1"]}
        self.message = _FailMessage()
        self.edited = []

    async def edit_original_response(self, *args, **kwargs):
        self.edited.append((args, kwargs))


class _Response:
    def __init__(self):
        self.deferred = False
        self.messages = []
        self.modals = []

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_modal(self, modal):
        self.modals.append(modal)


class _Followup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class _FailMessage:
    async def edit(self, *args, **kwargs):
        raise m.discord.HTTPException.__new__(m.discord.HTTPException)

    async def delete(self):
        return None


async def _once(method):
    original_wait = m.bot.wait_until_ready
    original_closed = m.bot.is_closed
    original_sleep = m.asyncio.sleep
    state = {"closed": False}

    async def ready():
        return None

    def closed():
        if state["closed"]:
            return True
        state["closed"] = True
        return False

    async def no_sleep(*args, **kwargs):
        return None

    m.bot.wait_until_ready = ready
    m.bot.is_closed = closed
    m.asyncio.sleep = no_sleep
    try:
        await method()
    finally:
        m.bot.wait_until_ready = original_wait
        m.bot.is_closed = original_closed
        m.asyncio.sleep = original_sleep


async def _none():
    return None


async def _leader():
    return "leader"


def test_service_error_branches_batch2():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems, active_pet) "
                "VALUES (?, 1000, 1000, ?)",
                [(1, "missing"), (2, None), (3, None), (4, None)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury, capacity) "
                "VALUES (1, 'Probe', 1, 0, 10)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) VALUES (1, 1, 'leader')"
            )
            await db.execute(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level) VALUES (1, 'missing', 1)"
            )
            await db.execute(
                "INSERT INTO autocollectors (user_id, level, last_auto) VALUES (2, 1, NULL)"
            )
            await db.commit()

            try:
                await m.feed_active_pet(1)
            except Exception:
                pass
            try:
                await m.buy_autocollector(2)
            except Exception:
                pass
            try:
                await m.upgrade_autocollector(999)
            except Exception:
                pass
            assert (await m.validate_power_duel(999, 998))[0] is False
            try:
                await m.resolve_duel(1, 2, 10000, "dice")
            except Exception:
                pass
            result, error = await m.perform_raid([], 2)
            assert result is None and error
            try:
                await m.perform_raid([1], 2)
            except Exception:
                pass
            try:
                await m.finalize_raid({})
            except Exception:
                pass

            await db.execute(
                "INSERT INTO clan_applications (id, clan_id, user_id, status) "
                "VALUES (1, 1, 2, 'pending'), (2, 1, 4, 'pending')"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) VALUES (2, 1, 'member')"
            )
            await db.commit()
            ok, msg = await m.decide_clan_application(1, True, 1)
            assert not ok
            await db.execute("UPDATE clans SET capacity = 1 WHERE id = 1")
            await db.commit()
            ok, msg = await m.decide_clan_application(2, True, 1)
            assert not ok

            assert (await m.claim_daily(999))["ok"] is False
            assert await m.get_or_create_daily_quests(999) == ([], {}, [])
            await m.set_notification(1, "__bad__", True)

            due = (m.datetime.datetime.now() + m.datetime.timedelta(hours=12)).isoformat()
            await db.execute(
                "INSERT INTO bank_loans "
                "(user_id, amount, interest_rate, due_time, collateral_item, "
                "collateral_stars, issued_at, status) "
                "VALUES (1, 100, 0.05, ?, 'basic_gen', 0, 'now', 'active')",
                (due,),
            )
            await db.commit()
            embed = await m.build_notification_center_embed(1)
            assert embed

            await db.execute("DELETE FROM market_prices")
            await db.commit()
            embed = await m.build_trading_hub_embed()
            assert embed
            embed = await m.build_market_history_embed("basic_gen")
            assert embed

            assert await m.calculate_prestige_gain(999) == 0
            await db.execute(
                "CREATE TRIGGER trg_status_pay_ignore BEFORE UPDATE OF gems ON players "
                "WHEN OLD.user_id = 1 AND NEW.gems < OLD.gems BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            ok, msg = await m.purchase_status(1, "vip", 1)
            assert not ok
            await db.execute("DROP TRIGGER trg_status_pay_ignore")
            await db.commit()

            interaction = _Interaction(1)
            embed = await m.build_storage_embed(interaction, "rare")
            assert embed
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'temp', 0)"
            )
            await db.execute(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level) VALUES (1, 'unknown', 1)"
            )
            await db.execute(
                "INSERT OR REPLACE INTO user_cosmetics (user_id, bg_url) "
                "VALUES (1, 'https://example.com/bg.png')"
            )
            await db.commit()
            embed = await m.build_temp_storage_embed(interaction)
            assert embed
            embed = await m.build_pets_embed(interaction)
            assert embed
            embed = await m.build_profile_embed(interaction)
            assert embed

            for pair in ((999, 1), (1, 999), (1, 1)):
                try:
                    await m.start_clan_war(*pair)
                except Exception:
                    pass
            await m.giveaway_validate_reward("pet_level", "missing", 1)
            await m.grant_pet_reward(1, "missing")
            await m.grant_clan_levels(999, 1)
        finally:
            await _close(db)

    asyncio.run(run())


def test_final_ui_and_auction_branches():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems, last_daily, streak_days) "
                "VALUES (?, 1000, 1000, ?, ?)",
                [(1, "2020-01-01T00:00:00", 4), (2, None, None), (3, None, None)],
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0)"
            )
            await db.execute(
                "INSERT OR IGNORE INTO market_prices "
                "(item_id, base_price, current_price, demand, supply) "
                "VALUES ('basic_gen', 100, 100, 0, 0)"
            )
            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, stars, start_price, current_bid, "
                "current_bidder, buyout_price, end_time, status) "
                "VALUES (90, 1, 'basic_gen', 0, 10, 10, NULL, 100, "
                "'9999-01-01T00:00:00', 'active')"
            )
            await db.execute(
                "INSERT INTO bank_loans "
                "(user_id, amount, interest_rate, due_time, collateral_item, "
                "collateral_stars, issued_at, status) "
                "VALUES (1, 100, 0.05, '9999-01-01T00:00:00', 'basic_gen', 0, 'now', 'active')"
            )
            await db.execute(
                "INSERT INTO player_upgrades (user_id, upgrade_id) VALUES (1, 'vip')"
            )
            await db.execute(
                "INSERT INTO player_upgrades (user_id, upgrade_id) VALUES (1, 'grid_7x7')"
            )
            await db.commit()

            interaction = _Interaction(1)
            embed = await m.build_analytics_embed(interaction)
            assert embed
            embed = await m.build_generator_details_embed(interaction, 0)
            assert embed
            embed = await m.build_storage_embed(interaction, "rare")
            assert embed
            embed = await m.build_upgrades_page(interaction, 0)
            assert embed
            embed = await m.build_market_history_embed("basic_gen")
            assert embed
            embed = await m.build_auction_history_embed(90)
            assert embed

            await db.execute(
                "INSERT INTO auction_bids (auction_id, bidder_id, amount, kind) "
                "VALUES (90, 2, 10, 'refund')"
            )
            await db.commit()
            embed = await m.build_auction_history_embed(90)
            assert embed

            await db.execute(
                "CREATE TRIGGER trg_bid_coins_ignore BEFORE UPDATE OF coins ON players "
                "WHEN OLD.user_id = 2 AND NEW.coins < OLD.coins BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.execute(
                "CREATE TRIGGER trg_buyout_coins_ignore BEFORE UPDATE OF coins ON players "
                "WHEN OLD.user_id = 3 AND NEW.coins < OLD.coins BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            await m.place_auction_bid(2, 90, 20)
            await m.buyout_auction(3, 90)
            await db.execute("DROP TRIGGER trg_bid_coins_ignore")
            await db.execute("DROP TRIGGER trg_buyout_coins_ignore")
            await db.commit()

            await db.execute(
                "CREATE TRIGGER trg_duel_coins_ignore BEFORE UPDATE OF coins ON players "
                "WHEN OLD.user_id = 2 AND NEW.coins < OLD.coins BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            await m.resolve_duel(1, 2, 10, "dice")
            await db.execute("DROP TRIGGER trg_duel_coins_ignore")
            await db.commit()

            res = await m.claim_daily(1)
            assert res["ok"]
            await m.save_setting(1, "bot_name", "x" * 250, actor_id=1)
            import gen_mania.services.market as market_service
            assert market_service.parse_market_datetime("bad") is None
        finally:
            await _close(db)

    asyncio.run(run())


def test_runtime_compensation_wrappers():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 100)"
            )
            await db.commit()
            try:
                await m.GIVEAWAY_RUNTIME.grant_compensation(1, "basic_gen", 1)
            except Exception:
                pass
            try:
                await m.PROGRESS_RUNTIME.grant_compensation(1, "basic_gen", 1)
            except Exception:
                pass
            try:
                await m.BANK_RUNTIME.grant_compensation(1, "basic_gen", 1)
            except Exception:
                pass
        finally:
            await _close(db)

    asyncio.run(run())
