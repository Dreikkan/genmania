"""Проверка восстановления последнего бэкапа Gen Mania.

Запуск:
    python dev/check_backup_restore.py
    python dev/check_backup_restore.py path/to/castle_....db
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

KEY_TABLES = ("players", "inventory", "items", "guild_settings")


def find_latest_backup(backup_dir: Path) -> Path | None:
    if not backup_dir.exists():
        return None
    backups = sorted(
        backup_dir.glob("castle_*.db"),
        key=lambda path: path.name,
        reverse=True,
    )
    return backups[0] if backups else None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def check_backup(backup_path: Path) -> dict:
    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError(f"Бэкап не найден: {backup_path}")

    with tempfile.TemporaryDirectory(prefix="genmania_restore_") as tmp:
        restored_path = Path(tmp) / "restored.db"
        source = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
        target = sqlite3.connect(restored_path)
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()

        check = sqlite3.connect(restored_path)
        try:
            integrity = check.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
            user_version = check.execute(
                "PRAGMA user_version"
            ).fetchone()[0]
            counts = {}
            for table in KEY_TABLES:
                if _table_exists(check, table):
                    counts[table] = check.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
        finally:
            check.close()

    return {
        "ok": integrity == "ok",
        "integrity": integrity,
        "user_version": user_version,
        "counts": counts,
        "path": str(backup_path),
    }


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        backup_path = Path(argv[1])
    else:
        data_dir = Path(os.getenv("DATA_DIR", "data"))
        backup_path = find_latest_backup(data_dir / "backups")
        if backup_path is None:
            print(f"Бэкапы не найдены в {data_dir / 'backups'}")
            return 1

    result = check_backup(backup_path)
    print(f"Бэкап: {result['path']}")
    print(f"integrity_check: {result['integrity']}")
    print(f"user_version: {result['user_version']}")
    for table, count in result["counts"].items():
        print(f"{table}: {count}")
    if not result["ok"]:
        print("РЕЗУЛЬТАТ: FAIL")
        return 1
    print("РЕЗУЛЬТАТ: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
