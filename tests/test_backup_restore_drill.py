import importlib.util
import pathlib
import sqlite3
import sys

PATH = pathlib.Path(__file__).resolve().parent.parent / "dev" / "check_backup_restore.py"
spec = importlib.util.spec_from_file_location("genmania_restore_check", PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def _make_db(path, players=2):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE players (user_id INTEGER PRIMARY KEY, coins INTEGER)")
    conn.execute("CREATE TABLE inventory (user_id INTEGER, item_id TEXT)")
    conn.execute("CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE guild_settings (guild_id INTEGER PRIMARY KEY)")
    conn.executemany(
        "INSERT INTO players VALUES (?, ?)",
        [(index, index * 100) for index in range(1, players + 1)],
    )
    conn.execute("INSERT INTO items VALUES ('basic_gen', 'Basic')")
    conn.commit()
    conn.execute("PRAGMA user_version = 18")
    conn.commit()
    conn.close()


def test_check_backup_restores_and_counts(tmp_path):
    source = tmp_path / "castle.db"
    _make_db(source, players=3)
    backup = tmp_path / "castle_20260101_000000_test.db"
    src = sqlite3.connect(source)
    dst = sqlite3.connect(backup)
    src.backup(dst)
    src.close()
    dst.close()

    result = m.check_backup(backup)
    assert result["ok"] is True
    assert result["integrity"] == "ok"
    assert result["user_version"] == 18
    assert result["counts"]["players"] == 3
    assert result["counts"]["items"] == 1


def test_find_latest_backup(tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "castle_20260101_000000_old.db").write_bytes(b"old")
    (backups / "castle_20260102_000000_new.db").write_bytes(b"new")
    assert m.find_latest_backup(backups).name.endswith("_new.db")


def test_check_backup_missing_raises(tmp_path):
    try:
        m.check_backup(tmp_path / "missing.db")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("ожидался FileNotFoundError")
