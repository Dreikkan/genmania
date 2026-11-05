import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_health_metrics_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._tax_rate_cache.clear()
    m._top_cache.clear()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems) VALUES (1, 100, 100)"
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._tax_rate_cache.clear()
    m._top_cache.clear()


def test_metrics_registry_snapshot():
    registry = m.MetricsRegistry()
    registry.record_command("menu", 10)
    registry.record_command("menu", 30)
    registry.record_command_error("ValueError")
    registry.record_db_tx(5)
    registry.record_db_tx(150)
    registry.record_background_error("tax_collector")

    snapshot = registry.snapshot()
    assert snapshot["commands_total"] == 3
    assert snapshot["command_errors"] == 1
    assert snapshot["command_avg_ms"] == 20.0
    assert snapshot["command_p95_ms"] == 30.0
    assert snapshot["commands_by_name"] == {"menu": 2}
    assert snapshot["command_errors_by_type"] == {"ValueError": 1}
    assert snapshot["db_tx_total"] == 2
    assert snapshot["db_tx_errors"] == 0
    assert snapshot["slow_db_tx"] == 1
    assert snapshot["background_errors"] == 1
    assert snapshot["background_errors_by_task"] == {
        "tax_collector": 1
    }


def test_db_transaction_records_metrics():
    async def run():
        db = await _init()
        try:
            before = m.METRICS.db_tx_total
            async with m.db_transaction():
                await db.execute(
                    "UPDATE players SET coins = coins + 1 WHERE user_id = 1"
                )
            assert m.METRICS.db_tx_total == before + 1
        finally:
            await _close(db)

    asyncio.run(run())


def test_health_snapshot_and_background_errors():
    async def run():
        db = await _init()
        try:
            snapshot = await m.bot.build_health_snapshot(deep=True)
            assert snapshot["db_quick_check"] == "ok"
            assert snapshot["guilds"] >= 0
            assert snapshot["db_size_bytes"] >= 0
            assert isinstance(snapshot["tasks"], list)
            assert snapshot["tasks_alive"] == 0

            before = m.METRICS.background_errors_by_task.get(
                "health_test_boom", 0
            )

            async def boom():
                raise RuntimeError("boom")

            task = m.bot._spawn_background("health_test_boom", boom())
            await task
            assert (
                m.METRICS.background_errors_by_task["health_test_boom"]
                == before + 1
            )
        finally:
            await _close(db)

    asyncio.run(run())
