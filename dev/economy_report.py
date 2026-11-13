"""Экономический отчёт по базе Gen Mania.

Запуск:
    python dev/economy_report.py
    python dev/economy_report.py path/to/castle.db
    python dev/economy_report.py --json
"""
from __future__ import annotations

import datetime
import json
import os
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gen_mania.formatting import format_short_number  # noqa: E402


def _connect(path: Path):
    uri = path.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _fmt(value) -> str:
    number = int(value or 0)
    text = f"{number:,}".replace(",", " ")
    if abs(number) >= 1_000_000:
        text += f" ({format_short_number(number)})"
    return text


def _sum(conn, sql: str, params=()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int((row[0] if row and row[0] is not None else 0) or 0)


def build_report(db_path: Path) -> dict:
    db_path = Path(db_path)
    conn = _connect(db_path)
    try:
        now = datetime.datetime.now()
        players = []
        if _table_exists(conn, "players"):
            cols = _columns(conn, "players")
            wanted = [
                "user_id", "coins", "gems", "lifetime_production",
                "prestige_points", "last_collected", "last_tax_time",
            ]
            selected = [name for name in wanted if name in cols]
            rows = conn.execute(
                f"SELECT {', '.join(selected)} FROM players"
            ).fetchall()
            for row in rows:
                data = dict(zip(selected, row))
                players.append(data)

        coins = [int(p.get("coins") or 0) for p in players]
        gems = [int(p.get("gems") or 0) for p in players]
        active_24h = 0
        active_7d = 0
        for player in players:
            last = _parse_dt(player.get("last_collected"))
            if last:
                age = (now - last).total_seconds()
                if age <= 86400:
                    active_24h += 1
                if age <= 7 * 86400:
                    active_7d += 1

        top_coins = sorted(coins, reverse=True)[:10]
        top_share = (
            sum(top_coins) / sum(coins) * 100 if sum(coins) else 0.0
        )

        income = {}
        if _table_exists(conn, "items") and _table_exists(conn, "inventory"):
            income = {
                "coins_hour": _sum(
                    conn,
                    "SELECT SUM(i.income_per_hour * 3600) "
                    "FROM inventory inv JOIN items i ON i.id = inv.item_id "
                    "WHERE inv.location = 'profile'",
                ),
                "gems_hour": _sum(
                    conn,
                    "SELECT SUM(i.income_gems_per_hour * 3600) "
                    "FROM inventory inv JOIN items i ON i.id = inv.item_id "
                    "WHERE inv.location = 'profile'",
                ),
            }

        inventory = {}
        if _table_exists(conn, "inventory"):
            for location in ("profile", "storage", "temp"):
                inventory[location] = _sum(
                    conn,
                    "SELECT COUNT(*) FROM inventory WHERE location = ?",
                    (location,),
                )

        deposits = {"count": 0, "amount": 0, "matured": 0}
        if _table_exists(conn, "bank_deposits"):
            rows = conn.execute(
                "SELECT amount, interest_rate, end_time FROM bank_deposits"
            ).fetchall()
            deposits["count"] = len(rows)
            deposits["amount"] = sum(int(r[0] or 0) for r in rows)
            for _amount, _rate, end_time in rows:
                end = _parse_dt(end_time)
                if end and end <= now:
                    deposits["matured"] += 1

        loans = {
            "count": 0,
            "principal": 0,
            "debt": 0,
            "overdue": 0,
        }
        if _table_exists(conn, "bank_loans"):
            cols = _columns(conn, "bank_loans")
            status_sql = (
                "AND COALESCE(status, 'active') = 'active'"
                if "status" in cols
                else ""
            )
            rows = conn.execute(
                "SELECT amount, interest_rate, due_time FROM bank_loans "
                f"WHERE 1 = 1 {status_sql}"
            ).fetchall()
            loans["count"] = len(rows)
            for amount, rate, due_time in rows:
                amount = int(amount or 0)
                loans["principal"] += amount
                loans["debt"] += int(amount * (1 + (rate or 0)))
                due = _parse_dt(due_time)
                if due and due <= now:
                    loans["overdue"] += 1

        market = {
            "buy_orders": 0,
            "sell_orders": 0,
            "reserved_coins": 0,
            "escrow_items": 0,
        }
        if _table_exists(conn, "market_orders"):
            rows = conn.execute(
                "SELECT side, price, quantity, filled FROM market_orders "
                "WHERE status = 'active'"
            ).fetchall()
            for side, price, quantity, filled in rows:
                remaining = max(
                    0, int(quantity or 0) - int(filled or 0)
                )
                if side == "buy":
                    market["buy_orders"] += 1
                    market["reserved_coins"] += int(price or 0) * remaining
                else:
                    market["sell_orders"] += 1
                    market["escrow_items"] += remaining

        auctions = {"active": 0, "bids": 0, "buyout_lots": 0}
        if _table_exists(conn, "auctions"):
            rows = conn.execute(
                "SELECT current_bid, start_price, buyout_price "
                "FROM auctions WHERE status = 'active'"
            ).fetchall()
            auctions["active"] = len(rows)
            auctions["bids"] = sum(
                int(bid or start or 0) for bid, start, _buyout in rows
            )
            auctions["buyout_lots"] = sum(
                1 for _bid, _start, buyout in rows if buyout
            )

        taxes = {"day": 0, "day_count": 0, "total": 0}
        if _table_exists(conn, "tax_log"):
            cutoff = now - datetime.timedelta(days=1)
            rows = conn.execute(
                "SELECT amount, timestamp FROM tax_log"
            ).fetchall()
            for amount, timestamp in rows:
                amount = int(amount or 0)
                taxes["total"] += amount
                parsed = _parse_dt(timestamp)
                if parsed and parsed >= cutoff:
                    taxes["day"] += amount
                    taxes["day_count"] += 1

        clans = {"count": 0, "treasury": 0}
        if _table_exists(conn, "clans"):
            clans["count"] = _sum(conn, "SELECT COUNT(*) FROM clans")
            clans["treasury"] = _sum(
                conn, "SELECT COALESCE(SUM(treasury), 0) FROM clans"
            )

        season = {"players": 0, "premium": 0, "avg_xp": 0}
        if _table_exists(conn, "season_progress"):
            season_id = now.strftime("%Y-%m")
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(premium), 0), "
                "COALESCE(AVG(xp), 0) FROM season_progress "
                "WHERE season_id = ?",
                (season_id,),
            ).fetchone()
            season["players"] = int(row[0] or 0)
            season["premium"] = int(row[1] or 0)
            season["avg_xp"] = int(row[2] or 0)

        autocollectors = {}
        if _table_exists(conn, "autocollectors"):
            for level, count in conn.execute(
                "SELECT level, COUNT(*) FROM autocollectors "
                "GROUP BY level ORDER BY level"
            ).fetchall():
                autocollectors[int(level or 1)] = int(count)

        lifetime = sum(
            int(p.get("lifetime_production") or 0) for p in players
        )
        prestige = sum(
            int(p.get("prestige_points") or 0) for p in players
        )

        return {
            "db": str(db_path),
            "db_size_bytes": db_path.stat().st_size,
            "players": len(players),
            "active_24h": active_24h,
            "active_7d": active_7d,
            "coins": {
                "total": sum(coins),
                "avg": sum(coins) / len(coins) if coins else 0,
                "median": statistics.median(coins) if coins else 0,
                "top10": top_coins,
                "top10_share_pct": top_share,
            },
            "gems": {
                "total": sum(gems),
                "avg": sum(gems) / len(gems) if gems else 0,
                "median": statistics.median(gems) if gems else 0,
            },
            "lifetime_production": lifetime,
            "prestige_points": prestige,
            "income": income,
            "inventory": inventory,
            "deposits": deposits,
            "loans": loans,
            "market": market,
            "auctions": auctions,
            "taxes": taxes,
            "clans": clans,
            "season": season,
            "autocollectors": autocollectors,
        }
    finally:
        conn.close()


def print_report(report: dict) -> None:
    print("=== Экономика Gen Mania ===")
    print(f"БД: {report['db']}")
    print(f"Размер: {_fmt(report['db_size_bytes'])} байт")
    print(
        f"Игроки: {_fmt(report['players'])} · "
        f"активны 24ч: {_fmt(report['active_24h'])} · "
        f"7д: {_fmt(report['active_7d'])}"
    )
    print(
        f"Монеты: {_fmt(report['coins']['total'])} · "
        f"среднее: {_fmt(report['coins']['avg'])} · "
        f"медиана: {_fmt(report['coins']['median'])}"
    )
    print(
        f"Топ-10 монет: {_fmt(report['coins']['top10_share_pct'])}% "
        f"от всех монет"
    )
    print(
        f"Гемы: {_fmt(report['gems']['total'])} · "
        f"среднее: {_fmt(report['gems']['avg'])}"
    )
    print(
        f"Всего произведено: {_fmt(report['lifetime_production'])} · "
        f"престиж: {_fmt(report['prestige_points'])} очков"
    )
    income = report["income"]
    print(
        f"Доход/час: 🪙 {_fmt(income.get('coins_hour', 0))} · "
        f"💎 {_fmt(income.get('gems_hour', 0))}"
    )
    inv = report["inventory"]
    print(
        f"Инвентарь: станция {_fmt(inv.get('profile', 0))} · "
        f"хранилище {_fmt(inv.get('storage', 0))} · "
        f"временное {_fmt(inv.get('temp', 0))}"
    )
    dep = report["deposits"]
    print(
        f"Вклады: {_fmt(dep['count'])} на {_fmt(dep['amount'])} · "
        f"истекло: {_fmt(dep['matured'])}"
    )
    loan = report["loans"]
    print(
        f"Кредиты: {_fmt(loan['count'])} · тело {_fmt(loan['principal'])} · "
        f"к возврату {_fmt(loan['debt'])} · просрочено {_fmt(loan['overdue'])}"
    )
    market = report["market"]
    print(
        f"Биржа: buy {_fmt(market['buy_orders'])} / "
        f"sell {_fmt(market['sell_orders'])} · "
        f"резерв {_fmt(market['reserved_coins'])} монет · "
        f"эскроу {_fmt(market['escrow_items'])} предметов"
    )
    auction = report["auctions"]
    print(
        f"Аукционы: активных {_fmt(auction['active'])} · "
        f"ставки {_fmt(auction['bids'])} · buyout-лотов "
        f"{_fmt(auction['buyout_lots'])}"
    )
    taxes = report["taxes"]
    print(
        f"Налоги за 24ч: {_fmt(taxes['day'])} с "
        f"{_fmt(taxes['day_count'])} игроков · всего "
        f"{_fmt(taxes['total'])}"
    )
    clans = report["clans"]
    print(
        f"Кланы: {_fmt(clans['count'])} · сундуки "
        f"{_fmt(clans['treasury'])}"
    )
    season = report["season"]
    print(
        f"Сезон {datetime.datetime.now():%Y-%m}: "
        f"{_fmt(season['players'])} игроков · премиум "
        f"{_fmt(season['premium'])} · средний XP {_fmt(season['avg_xp'])}"
    )
    if report["autocollectors"]:
        levels = ", ".join(
            f"{level}: {count}"
            for level, count in report["autocollectors"].items()
        )
        print(f"Автосборщики: {levels}")


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    args = [arg for arg in argv[1:] if arg != "--json"]
    if args:
        db_path = Path(args[0])
    else:
        data_dir = Path(os.getenv("DATA_DIR", "data"))
        db_path = data_dir / "castle.db"

    if not db_path.exists():
        print(f"База не найдена: {db_path}")
        return 1

    report = build_report(db_path)
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
