import asyncio
import importlib.util
import pathlib
import sys
import tempfile

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_backup_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        db_path = root / "castle.db"
        backup_dir = root / "backups"
        backup_dir.mkdir()

        bot = m.CastleBot()
        bot.data_dir = root
        bot.db_path = str(db_path)
        bot.backup_dir = backup_dir
        bot.db = await aiosqlite.connect(str(db_path))
        await bot.db.execute("CREATE TABLE test (value TEXT)")
        await bot.db.execute("INSERT INTO test VALUES ('ok')")
        await bot.db.commit()

        backup = await bot.backup_database("test")
        assert backup and backup.exists(), backup
        check = await aiosqlite.connect(str(backup))
        async with check.execute("SELECT value FROM test") as c:
            assert (await c.fetchone())[0] == "ok"
        await check.close()

        # Ротация: оставляем два последних бэкапа.
        old_keep = m.BACKUP_KEEP
        m.BACKUP_KEEP = 2
        try:
            await bot.backup_database("a")
            await bot.backup_database("b")
            await bot.backup_database("c")
        finally:
            m.BACKUP_KEEP = old_keep
        assert len(list(backup_dir.glob("castle_*.db"))) == 2

        await bot.db.close()
        bot.db = None

        # Graceful shutdown: закрывает БД и делает shutdown-бэкап.
        bot2 = m.CastleBot()
        bot2.data_dir = root
        bot2.db_path = str(db_path)
        bot2.backup_dir = backup_dir
        bot2.db = await aiosqlite.connect(str(db_path))
        await bot2.db.execute("CREATE TABLE IF NOT EXISTS test2 (value TEXT)")
        await bot2.db.commit()
        await bot2.close()
        assert bot2.db is None
        assert list(backup_dir.glob("*shutdown*.db"))

        print("BACKUP SMOKE TEST: OK")


def test_smoke():
    asyncio.run(main())


def test_checkpoint_failure_is_best_effort():
    class LockedDB:
        async def execute(self, sql):
            raise m.aiosqlite.OperationalError("database table is locked")

    class OkDB:
        async def execute(self, sql):
            return None

    assert asyncio.run(m.checkpoint_wal_best_effort(LockedDB())) is False
    assert asyncio.run(m.checkpoint_wal_best_effort(OkDB())) is True
