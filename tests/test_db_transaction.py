import asyncio
import importlib.util
import pathlib
import sys
import tempfile

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_tx_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def run_checks(db):
    await m.bot.init_db()
    assert db.in_transaction is False

    settings = await m.get_settings(1)
    assert settings["start_coins"] == m.DEFAULT_START_COINS
    assert db.in_transaction is False

    await m.save_setting(1, "bot_name", "TX Test")
    assert db.in_transaction is False
    settings = await m.get_settings(1)
    assert settings["bot_name"] == "TX Test"

    # COMMIT
    async with m.db_transaction():
        await db.execute(
            "INSERT INTO content_meta (key, value) VALUES ('tx_commit', '1')"
        )
    assert db.in_transaction is False
    async with db.execute(
        "SELECT COUNT(*) FROM content_meta WHERE key = 'tx_commit'"
    ) as c:
        assert (await c.fetchone())[0] == 1

    # ROLLBACK
    try:
        async with m.db_transaction():
            await db.execute(
                "INSERT INTO content_meta (key, value) VALUES ('tx_rollback', '1')"
            )
            raise RuntimeError("rollback")
    except RuntimeError:
        pass
    assert db.in_transaction is False
    async with db.execute(
        "SELECT COUNT(*) FROM content_meta WHERE key = 'tx_rollback'"
    ) as c:
        assert (await c.fetchone())[0] == 0

    # Nested SAVEPOINT: inner rollback does not kill outer
    async with m.db_transaction():
        await db.execute(
            "INSERT INTO content_meta (key, value) VALUES ('tx_outer', '1')"
        )
        try:
            async with m.db_transaction():
                await db.execute(
                    "INSERT INTO content_meta (key, value) VALUES ('tx_inner', '1')"
                )
                raise RuntimeError("inner")
        except RuntimeError:
            pass
    assert db.in_transaction is False
    async with db.execute(
        "SELECT key FROM content_meta WHERE key IN ('tx_outer', 'tx_inner') ORDER BY key"
    ) as c:
        assert [r[0] for r in await c.fetchall()] == ["tx_outer"]

    # commit_if_needed() внутри managed tx не коммитит раньше времени
    try:
        async with m.db_transaction():
            await db.execute(
                "INSERT INTO content_meta (key, value) VALUES ('tx_early', '1')"
            )
            await m.commit_if_needed()
            raise RuntimeError("late rollback")
    except RuntimeError:
        pass
    async with db.execute(
        "SELECT COUNT(*) FROM content_meta WHERE key = 'tx_early'"
    ) as c:
        assert (await c.fetchone())[0] == 0


async def run_backup_check():
    path = pathlib.Path(tempfile.gettempdir()) / "gen_mania_tx_backup_test.db"
    if path.exists():
        path.unlink()
    db = await aiosqlite.connect(str(path))
    m.bot.db = db
    try:
        await m.bot.init_db()
        await m.get_settings(1)
        assert db.in_transaction is False

        # Оставляем открытую транзакцию: бэкап должен её закоммитить.
        await db.execute(
            "INSERT INTO content_meta (key, value) VALUES ('tx_backup_pending', '1')"
        )
        assert db.in_transaction is True

        bot = m.CastleBot.__new__(m.CastleBot)
        bot.db = db
        bot.db_path = str(path)
        bot.backup_dir = path.parent / "gen_mania_tx_backups"
        bot.backup_dir.mkdir(exist_ok=True)
        result = await bot.backup_database("tx_test")
        assert result is not None
        assert pathlib.Path(result).exists()
        assert db.in_transaction is False

        check = await aiosqlite.connect(str(result))
        try:
            async with check.execute(
                "SELECT value FROM content_meta WHERE key = 'tx_backup_pending'"
            ) as c:
                assert (await c.fetchone())[0] == "1"
        finally:
            await check.close()
    finally:
        await db.close()
        m.bot.db = None


async def main():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    try:
        await run_checks(db)
    finally:
        await db.close()
        m.bot.db = None
    await run_backup_check()
    print("DB TRANSACTION TEST: OK")


def test_db_transactions_and_backups():
    asyncio.run(main())


def test_db_transaction_survives_implicit_transaction_race():
    """Сырой DML между проверкой in_transaction и BEGIN не должен ронять tx."""

    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        original_execute = db.execute
        injected = False
        try:
            await m.bot.init_db()

            async def flaky_execute(sql, *args, **kwargs):
                nonlocal injected
                if sql == "BEGIN IMMEDIATE" and not injected:
                    injected = True
                    # Имитируем сырой DML из другой корутины: он открывает
                    # неявную транзакцию прямо перед BEGIN IMMEDIATE.
                    await original_execute(
                        "INSERT INTO content_meta (key, value) "
                        "VALUES ('race', '1')"
                    )
                return await original_execute(sql, *args, **kwargs)

            db.execute = flaky_execute
            async with m.db_transaction():
                await db.execute(
                    "INSERT INTO content_meta (key, value) "
                    "VALUES ('after', '1')"
                )
            async with original_execute(
                "SELECT key FROM content_meta "
                "WHERE key IN ('race', 'after') ORDER BY key"
            ) as cursor:
                assert [row[0] for row in await cursor.fetchall()] == [
                    "after",
                    "race",
                ]
        finally:
            db.execute = original_execute
            await db.close()
            m.bot.db = None

    asyncio.run(run())
