"""Tests for the dashboard push-sync module."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path

import aiosqlite
import discord

from gen_mania import dashboard_sync
from gen_mania.dashboard_sync import DashboardSync

SCHEMA = """
CREATE TABLE players (user_id INTEGER PRIMARY KEY, coins INTEGER DEFAULT 0, gems INTEGER DEFAULT 0, prestige_points INTEGER DEFAULT 0, last_collected TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_gem_collected TIMESTAMP DEFAULT CURRENT_TIMESTAMP, lifetime_production INTEGER DEFAULT 0, top_excluded INTEGER DEFAULT 0, total_crafts INTEGER DEFAULT 0);
CREATE TABLE inventory (user_id INTEGER, slot INTEGER, item_id TEXT, location TEXT DEFAULT 'profile', stars INTEGER DEFAULT 0, PRIMARY KEY (user_id, location, slot));
CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT, price INTEGER, rarity TEXT DEFAULT 'common');
CREATE TABLE clans (id INTEGER PRIMARY KEY, name TEXT, treasury INTEGER DEFAULT 0, level INTEGER DEFAULT 1, capacity INTEGER DEFAULT 10);
CREATE TABLE clan_members (user_id INTEGER PRIMARY KEY, clan_id INTEGER, role TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE clan_inventory (clan_id INTEGER, slot INTEGER, item_id TEXT, stars INTEGER DEFAULT 0, PRIMARY KEY (clan_id, slot));
CREATE TABLE clan_wars (id INTEGER PRIMARY KEY, winner_id INTEGER);
CREATE TABLE guild_settings (guild_id INTEGER PRIMARY KEY, start_coins INTEGER, currency_coins TEXT, currency_gems TEXT, tax_rate REAL, admin_role_id INTEGER);
CREATE TABLE market_prices (item_id TEXT PRIMARY KEY, base_price INTEGER, current_price INTEGER, demand INTEGER, supply INTEGER);
CREATE TABLE market_history (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT, price INTEGER, demand INTEGER, supply INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE market_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, side TEXT, item_id TEXT, price INTEGER, quantity INTEGER, filled INTEGER, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE bank_deposits (user_id INTEGER PRIMARY KEY, amount INTEGER);
CREATE TABLE bank_loans (user_id INTEGER PRIMARY KEY, amount INTEGER, status TEXT DEFAULT 'active');
CREATE TABLE tax_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, tax_type TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE admin_log (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, target_id INTEGER, guild_id INTEGER, action TEXT, details TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE onboarding_progress (user_id INTEGER, step TEXT, completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""


class FakeUser:
    def __init__(self, user_id: int, name: str):
        self.id = user_id
        self.name = name
        self.global_name = name
        self.display_name = name


class FakeMember(FakeUser):
    def __init__(self, user_id: int, name: str, status: discord.Status):
        super().__init__(user_id, name)
        self.status = status
        self.joined_at = dt.datetime.now(dt.timezone.utc)


class FakeGuild:
    def __init__(self, guild_id: int, name: str, members: list[FakeMember]):
        self.id = guild_id
        self.name = name
        self.members = members
        self.member_count = len(members)
        self.owner = members[0]
        self.me = members[0]
        self.features = {"COMMUNITY"}
        self.preferred_locale = "ru"
        self.premium_subscription_count = 5


class FakeBot:
    def __init__(self, db, data_dir: Path, guilds=None, users=None, closed=False):
        self.db = db
        self.data_dir = data_dir
        self.backup_dir = data_dir / "backups"
        self.db_path = str(data_dir / "castle.db")
        self.guilds = guilds or []
        self.latency = 0.042
        self.background_tasks = []
        self._users = users or {}
        self._closed = closed

    async def wait_until_ready(self):
        return None

    def is_closed(self):
        return self._closed

    def get_user(self, user_id):
        return self._users.get(user_id)


async def make_bot(tmp_path: Path, *, with_data: bool = True):
    db = await aiosqlite.connect(":memory:")
    await db.executescript(SCHEMA)
    if with_data:
        await db.executemany(
            "INSERT INTO players (user_id, coins, gems, prestige_points, lifetime_production) VALUES (?, ?, ?, ?, ?)",
            [(1, 5000, 50, 3, 9000), (2, 2500, 20, 1, 4500)],
        )
        await db.executemany(
            "INSERT INTO items (id, name, price, rarity) VALUES (?, ?, ?, ?)",
            [("gen_1", "Генератор", 1000, "rare"), ("cat_1", "Катализатор", 500, "common")],
        )
        await db.executemany(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) VALUES (?, ?, ?, ?, ?)",
            [(1, 1, "gen_1", "profile", 2), (1, 2, "cat_1", "profile", 0), (2, 1, "gen_1", "profile", 1)],
        )
        await db.execute("INSERT INTO clans (id, name, treasury) VALUES (1, '420 SQUAD', 12000)")
        await db.execute("INSERT INTO clan_members (user_id, clan_id, role) VALUES (1, 1, 'leader')")
        await db.execute("INSERT INTO clan_inventory (clan_id, slot, item_id, stars) VALUES (1, 1, 'gen_1', 1)")
        await db.execute("INSERT INTO clan_wars (winner_id) VALUES (1)")
        await db.execute("INSERT INTO guild_settings (guild_id, start_coins, currency_coins, currency_gems, tax_rate, admin_role_id) VALUES (1, 500, 'монеты', 'гемы', 0.05, 123)")
        await db.execute("INSERT INTO market_prices (item_id, base_price, current_price, demand, supply) VALUES ('gen_1', 1000, 1200, 10, 20)")
        await db.executemany("INSERT INTO market_history (item_id, price) VALUES ('gen_1', ?)", [(1000,), (1200,)])
        await db.execute("INSERT INTO market_orders (user_id, side, item_id, price, quantity, filled, status) VALUES (1, 'buy', 'gen_1', 1200, 3, 3, 'filled')")
        await db.execute("INSERT INTO bank_deposits (user_id, amount) VALUES (1, 8000)")
        await db.execute("INSERT INTO tax_log (user_id, amount, tax_type) VALUES (1, 500, 'income')")
        await db.execute("INSERT INTO admin_log (admin_id, target_id, action, details) VALUES (1, 2, 'grant_coins', '+1000')")
        await db.execute("INSERT INTO onboarding_progress (user_id, step) VALUES (2, 'buy_generator')")
        await db.commit()

    users = {1: FakeUser(1, "Vortex"), 2: FakeUser(2, "Kira")}
    members = [
        FakeMember(1, "Vortex", discord.Status.online),
        FakeMember(2, "Kira", discord.Status.idle),
    ]
    guilds = [FakeGuild(1, "420 SQUAD", members)]
    return db, FakeBot(db, tmp_path, guilds=guilds, users=users)


def test_helpers_and_init(monkeypatch):
    assert dashboard_sync._iso(None) == ""
    assert dashboard_sync._iso(123)
    assert dashboard_sync._iso("2026-01-01") == "2026-01-01T00:00:00+00:00"
    assert dashboard_sync._percent(110, 100) == 10.0
    assert dashboard_sync._percent(110, 0) == 0.0
    monkeypatch.setenv("DASHBOARD_SYNC_INTERVAL", "bad")
    assert dashboard_sync._env_int("DASHBOARD_SYNC_INTERVAL", 300, 60, 3600) == 300
    monkeypatch.setenv("DASHBOARD_SYNC_INTERVAL", "5")
    assert dashboard_sync._env_int("DASHBOARD_SYNC_INTERVAL", 300, 60, 3600) == 60
    monkeypatch.setenv("DASHBOARD_SYNC_INTERVAL", "99999")
    assert dashboard_sync._env_int("DASHBOARD_SYNC_INTERVAL", 300, 60, 3600) == 3600

    monkeypatch.delenv("DASHBOARD_SYNC_URL", raising=False)
    monkeypatch.delenv("DASHBOARD_SYNC_TOKEN", raising=False)
    bot = FakeBot(None, Path("."))
    assert DashboardSync(bot).enabled is False

    monkeypatch.setenv("DASHBOARD_SYNC_URL", "http://example.test/api/ingest.php")
    monkeypatch.setenv("DASHBOARD_SYNC_TOKEN", "short")
    assert DashboardSync(bot).enabled is False

    monkeypatch.setenv("DASHBOARD_SYNC_TOKEN", "0123456789abcdef")
    sync = DashboardSync(bot)
    assert sync.enabled is True


def test_collect_builds_live_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_SYNC_URL", "https://example.test/api/ingest.php")
    monkeypatch.setenv("DASHBOARD_SYNC_TOKEN", "0123456789abcdef")

    async def run():
        db, bot = await make_bot(tmp_path)
        try:
            payload = await DashboardSync(bot).collect()
            assert payload["stats"]["players"] == 2
            assert payload["stats"]["coins"] == 7500
            assert payload["stats"]["generators"] == 3
            assert payload["stats"]["online"] == 2
            assert payload["stats"]["servers"] == 1
            assert payload["stats"]["db_tables"] > 0
            assert payload["top_players"][0]["name"] == "Vortex"
            assert payload["top_players"][0]["clan"] == "420 SQUAD"
            assert payload["servers"][0]["name"] == "420 SQUAD"
            assert payload["servers"][0]["online"] == 2
            assert payload["top_clans"][0]["power"] == 4000
            assert payload["market"][0]["change"] == 20.0
            assert payload["transactions"][0]["amount"] == -3600
            assert payload["logs"][0]["type"] == "grant"
            assert payload["settings"]["tax_rate"] == 5.0
            assert payload["admin_user_ids"] == [1]
            assert payload["admin_guilds"] == {"1": ["1"]}
            assert payload["guild_settings"][0]["guild_id"] == 1
            assert payload["guild_settings"][0]["start_coins"] == 500
            assert payload["guild_settings"][0]["guild_name"] == "420 SQUAD"
            assert len(payload["activity"]["labels"]) == 30
            assert len(payload["economy"]["weekly"]["values"]) == 7
            assert payload["economy"]["split"][0]["value"] > 0
            json.dumps(payload)
            assert (tmp_path / "dashboard_history.json").exists()
        finally:
            await db.close()

    asyncio.run(run())


def test_collect_empty_database(tmp_path):
    async def run():
        db, bot = await make_bot(tmp_path, with_data=False)
        try:
            payload = await DashboardSync(bot).collect()
            assert payload["stats"]["players"] == 0
            assert payload["top_players"] == []
            assert payload["top_clans"] == []
            assert payload["market"] == []
            assert payload["transactions"] == []
            assert payload["logs"][0]["type"] == "system"
            assert payload["settings"]["start_coins"] == 8
            assert payload["economy"]["split"][0]["value"] == 100
        finally:
            await db.close()

    asyncio.run(run())


def test_history_and_growth(tmp_path):
    sync = DashboardSync(FakeBot(None, tmp_path))
    today = dt.datetime.now(dt.timezone.utc).date()
    days = []
    for offset in range(10, -1, -1):
        day = today - dt.timedelta(days=offset)
        days.append(
            {
                "date": day.isoformat(),
                "players": 100 + (10 - offset),
                "servers": 5,
                "online": 40,
                "coins": 1000 + (10 - offset) * 10,
                "gems": 100,
                "generators": 20,
                "production": 500 + (10 - offset) * 50,
                "market_volume": 0,
            }
        )
    sync.history_path.write_text(json.dumps({"days": days}), encoding="utf-8")
    stats = sync._history_entry(
        {"players": 200, "servers": 5, "online": 50, "coins": 2000, "gems": 100, "generators": 30, "lifetime_production": 1000, "market_volume": 0}
    )
    days = sync._record_history(stats)
    activity, weekly, growth = sync._history_series(days)
    assert len(activity["labels"]) == 30
    assert len(weekly["labels"]) == 7
    assert growth["players"] > 0
    assert sync._read_history()
    assert sync._health({"latency": 42, "db_size_bytes": 0})[0]["value"] == "42 ms"
    assert sync._latest_backup() == ""


def test_push_success_and_error(tmp_path, monkeypatch):
    sync = DashboardSync(FakeBot(None, tmp_path))
    sync.url = "https://example.test/api/ingest.php"
    sync.token = "0123456789abcdef"

    class FakeResponse:
        def __init__(self, status):
            self.status = status

        async def text(self):
            return "ok" if self.status == 200 else "boom"

    class FakePost:
        def __init__(self, response):
            self.response = response

        async def __aenter__(self):
            return self.response

        async def __aexit__(self, *_args):
            return None

    class FakeSession:
        status = 200

        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def post(self, *_args, **_kwargs):
            return FakePost(FakeResponse(self.status))

    monkeypatch.setattr(dashboard_sync.aiohttp, "ClientSession", FakeSession)
    asyncio.run(sync.push({"stats": {}}))
    FakeSession.status = 500
    try:
        asyncio.run(sync.push({"stats": {}}))
    except RuntimeError as exc:
        assert "ingest вернул 500" in str(exc)
    else:
        raise AssertionError("push должен падать при статусе 500")


def test_run_disabled_and_enabled(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHBOARD_SYNC_URL", raising=False)
    monkeypatch.delenv("DASHBOARD_SYNC_TOKEN", raising=False)
    bot = FakeBot(None, tmp_path)
    asyncio.run(DashboardSync(bot).run())

    monkeypatch.setenv("DASHBOARD_SYNC_URL", "https://example.test/api/ingest.php")
    monkeypatch.setenv("DASHBOARD_SYNC_TOKEN", "0123456789abcdef")
    sync = DashboardSync(bot)
    calls = {"collect": 0, "push": 0, "closed": 0}

    async def collect():
        calls["collect"] += 1
        return {"stats": {}}

    async def push(_payload):
        calls["push"] += 1

    original_closed = bot.is_closed

    def is_closed():
        calls["closed"] += 1
        return calls["closed"] > 1

    bot.is_closed = is_closed
    sync.collect = collect
    sync.push = push

    async def no_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(dashboard_sync.asyncio, "sleep", no_sleep)
    asyncio.run(sync.run())
    bot.is_closed = original_closed
    assert calls["collect"] == 1
    assert calls["push"] == 1


def test_iso_and_empty_history(tmp_path):
    assert dashboard_sync._iso(dt.datetime(2026, 1, 1, 12, 0)) == "2026-01-01T12:00:00+00:00"
    assert dashboard_sync._iso(dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)) == "2026-01-01T12:00:00+00:00"
    assert dashboard_sync._iso(dt.date(2026, 1, 1)) == "2026-01-01"
    assert dashboard_sync._iso("not-a-date") == "not-a-date"

    sync = DashboardSync(FakeBot(None, tmp_path))
    activity, weekly, growth = sync._history_series([])
    assert len(activity["labels"]) == 30
    assert all(value == 0 for value in activity["coins_earned"])
    assert len(weekly["labels"]) == 7
    assert growth == {"players": 0.0, "servers": 0.0, "coins": 0.0, "gems": 0.0, "generators": 0.0}


def test_fetch_errors_and_files(tmp_path):
    class BrokenDB:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    sync = DashboardSync(FakeBot(BrokenDB(), tmp_path))

    async def run():
        assert await sync._fetchone("SELECT 1") is None
        assert await sync._fetchall("SELECT 1") == []

    asyncio.run(run())

    (tmp_path / "castle.db").write_bytes(b"x" * 1024)
    (tmp_path / "castle.db-wal").write_bytes(b"y" * 1024)
    assert sync._db_size() == 2048
    sync.bot.backup_dir.mkdir(exist_ok=True)
    backup = sync.bot.backup_dir / "castle_20260101_000000.db"
    backup.write_bytes(b"backup")
    assert sync._latest_backup()


def test_settings_interval_branches(tmp_path, monkeypatch):
    sync = DashboardSync(FakeBot(None, tmp_path))

    async def run():
        for hours, expected in ((1, "1 час"), (6, "6 часов"), (12, "12 часов"), (24, "24 часа"), (48, "24 часа")):
            monkeypatch.setattr(dashboard_sync, "BACKUP_INTERVAL_HOURS", hours)
            settings = await sync._collect_settings()
            assert settings["backup_interval"] == expected

    asyncio.run(run())


def test_run_handles_collect_error(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_SYNC_URL", "https://example.test/api/ingest.php")
    monkeypatch.setenv("DASHBOARD_SYNC_TOKEN", "0123456789abcdef")
    bot = FakeBot(None, tmp_path)
    sync = DashboardSync(bot)
    calls = {"closed": 0}

    async def collect():
        raise RuntimeError("boom")

    def is_closed():
        calls["closed"] += 1
        return calls["closed"] > 1

    bot.is_closed = is_closed
    sync.collect = collect

    async def no_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(dashboard_sync.asyncio, "sleep", no_sleep)
    asyncio.run(sync.run())
    assert sync._last_error is not None


def test_apply_pending_settings(tmp_path):
    applied = []

    async def apply(update):
        applied.append(update)
        return {"ok": True, "applied": ["start_coins"], "guild_id": update.get("guild_id")}

    sync = DashboardSync(FakeBot(None, tmp_path), apply_settings=apply)
    update = {
        "revision": "abc123",
        "guild_id": 1,
        "settings": {"start_coins": 10},
    }
    asyncio.run(sync._apply_pending_settings({"settings_update": update}))
    assert applied and applied[0]["revision"] == "abc123"
    assert sync._applied_settings_revision == "abc123"
    assert sync.applied_revision_path.read_text(encoding="utf-8") == "abc123"

    async def reject(_update):
        return {"ok": False, "error": "no fields"}

    sync.apply_settings = reject
    asyncio.run(
        sync._apply_pending_settings(
            {"settings_update": {"revision": "def456", "settings": {"x": 1}}}
        )
    )
    assert sync._applied_settings_revision == "abc123"


def test_display_name_fallbacks(tmp_path):
    sync = DashboardSync(FakeBot(None, tmp_path))
    assert sync._display_name(999, {}) == ("Игрок 999", "999")
    assert sync._display_name(1, {1: FakeMember(1, "Vortex", discord.Status.online)}) == ("Vortex", "Vortex")
