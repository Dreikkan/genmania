#!/usr/bin/env python3
"""Быстрая проверка dev-базы без запуска Discord-бота."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "castle.db"


def main() -> int:
    if not DB_PATH.exists():
        print(f"❌ Нет базы: {DB_PATH}")
        return 1

    connection = sqlite3.connect(DB_PATH)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        players = connection.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        print(f"✅ DB: {DB_PATH}")
        print(f"✅ size: {DB_PATH.stat().st_size} bytes")
        print(f"✅ integrity: {integrity}")
        print(f"✅ schema user_version: {schema_version}")
        print(f"✅ tables: {tables}")
        print(f"✅ players: {players}")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
