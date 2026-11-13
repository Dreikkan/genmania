import datetime
import importlib.util
import pathlib
import sqlite3
import sys

PATH = pathlib.Path(__file__).resolve().parent.parent / "dev" / "economy_report.py"
spec = importlib.util.spec_from_file_location("genmania_economy_report", PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def _build_db(path):
    now = datetime.datetime.now()
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE players (
            user_id INTEGER PRIMARY KEY,
            coins INTEGER,
            gems INTEGER,
            lifetime_production INTEGER,
            prestige_points INTEGER,
            last_collected TIMESTAMP,
            last_tax_time TIMESTAMP
        );
        CREATE TABLE items (
            id TEXT PRIMARY KEY,
            income_per_hour REAL,
            income_gems_per_hour REAL
        );
        CREATE TABLE inventory (
            user_id INTEGER,
            item_id TEXT,
            location TEXT
        );
        CREATE TABLE bank_deposits (
            user_id INTEGER PRIMARY KEY,
            amount INTEGER,
            interest_rate REAL,
            end_time TIMESTAMP
        );
        CREATE TABLE bank_loans (
            user_id INTEGER PRIMARY KEY,
            amount INTEGER,
            interest_rate REAL,
            due_time TIMESTAMP,
            status TEXT
        );
        CREATE TABLE market_orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            side TEXT,
            price INTEGER,
            quantity INTEGER,
            filled INTEGER,
            status TEXT
        );
        CREATE TABLE auctions (
            id INTEGER PRIMARY KEY,
            current_bid INTEGER,
            start_price INTEGER,
            buyout_price INTEGER,
            status TEXT
        );
        CREATE TABLE tax_log (
            id INTEGER PRIMARY KEY,
            amount INTEGER,
            timestamp TIMESTAMP
        );
        CREATE TABLE clans (
            id INTEGER PRIMARY KEY,
            treasury INTEGER
        );
        CREATE TABLE season_progress (
            user_id INTEGER,
            season_id TEXT,
            xp INTEGER,
            premium INTEGER
        );
        CREATE TABLE autocollectors (
            user_id INTEGER PRIMARY KEY,
            level INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, 100, 5, 1000, 1, now.isoformat(), now.isoformat()),
            (
                2,
                200,
                10,
                2000,
                2,
                (now - datetime.timedelta(days=3)).isoformat(),
                now.isoformat(),
            ),
            (
                3,
                300,
                15,
                3000,
                3,
                (now - datetime.timedelta(days=10)).isoformat(),
                now.isoformat(),
            ),
        ],
    )
    conn.executemany(
        "INSERT INTO items VALUES (?, ?, ?)",
        [("basic_gen", 2 / 3600, 0.1 / 3600)],
    )
    conn.executemany(
        "INSERT INTO inventory VALUES (?, ?, ?)",
        [
            (1, "basic_gen", "profile"),
            (2, "basic_gen", "storage"),
            (3, "basic_gen", "temp"),
        ],
    )
    conn.executemany(
        "INSERT INTO bank_deposits VALUES (?, ?, ?, ?)",
        [
            (1, 100, 0.01, (now - datetime.timedelta(days=1)).isoformat()),
            (2, 200, 0.02, (now + datetime.timedelta(days=2)).isoformat()),
        ],
    )
    conn.executemany(
        "INSERT INTO bank_loans VALUES (?, ?, ?, ?, ?)",
        [
            (1, 100, 0.25, (now - datetime.timedelta(days=1)).isoformat(), "active"),
            (2, 100, 0.25, (now + datetime.timedelta(days=1)).isoformat(), "active"),
        ],
    )
    conn.executemany(
        "INSERT INTO market_orders VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, 1, "buy", 200, 2, 0, "active"),
            (2, 2, "sell", 100, 3, 0, "active"),
        ],
    )
    conn.execute(
        "INSERT INTO auctions VALUES (1, 150, 100, 500, 'active')"
    )
    conn.executemany(
        "INSERT INTO tax_log VALUES (?, ?, ?)",
        [
            (1, 10, now.isoformat()),
            (2, 15, (now - datetime.timedelta(days=2)).isoformat()),
        ],
    )
    conn.execute("INSERT INTO clans VALUES (1, 500)")
    season_id = now.strftime("%Y-%m")
    conn.executemany(
        "INSERT INTO season_progress VALUES (?, ?, ?, ?)",
        [(1, season_id, 200, 0), (2, season_id, 400, 1)],
    )
    conn.executemany(
        "INSERT INTO autocollectors VALUES (?, ?)",
        [(1, 1), (2, 1), (3, 3)],
    )
    conn.commit()
    conn.close()


def test_economy_report(tmp_path):
    db_path = tmp_path / "castle.db"
    _build_db(db_path)
    report = m.build_report(db_path)

    assert report["players"] == 3
    assert report["active_24h"] == 1
    assert report["active_7d"] == 2
    assert report["coins"]["total"] == 600
    assert report["coins"]["top10"] == [300, 200, 100]
    assert report["income"]["coins_hour"] == 2
    assert report["income"]["gems_hour"] == 0
    assert report["inventory"] == {
        "profile": 1,
        "storage": 1,
        "temp": 1,
    }
    assert report["deposits"] == {
        "count": 2,
        "amount": 300,
        "matured": 1,
    }
    assert report["loans"]["count"] == 2
    assert report["loans"]["principal"] == 200
    assert report["loans"]["debt"] == 250
    assert report["loans"]["overdue"] == 1
    assert report["market"] == {
        "buy_orders": 1,
        "sell_orders": 1,
        "reserved_coins": 400,
        "escrow_items": 3,
    }
    assert report["auctions"] == {
        "active": 1,
        "bids": 150,
        "buyout_lots": 1,
    }
    assert report["taxes"]["day"] == 10
    assert report["taxes"]["total"] == 25
    assert report["clans"]["treasury"] == 500
    assert report["season"]["players"] == 2
    assert report["season"]["premium"] == 1
    assert report["autocollectors"] == {1: 2, 3: 1}


def test_economy_report_missing_optional_tables(tmp_path):
    db_path = tmp_path / "minimal.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE players (user_id INTEGER PRIMARY KEY, coins INTEGER)"
    )
    conn.execute("INSERT INTO players VALUES (1, 10)")
    conn.commit()
    conn.close()

    report = m.build_report(db_path)
    assert report["players"] == 1
    assert report["coins"]["total"] == 10
    assert report["deposits"]["count"] == 0
    assert report["market"]["buy_orders"] == 0
