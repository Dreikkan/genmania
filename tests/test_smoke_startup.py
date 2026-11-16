"""Смоук-тест: бот поднимается на чистой папке data и готов к работе.

Юнит-тесты проверяют отдельные функции, но не проверяют, что процесс
стартует: миграции на пустой БД, прогрев кэшей, запуск фоновых задач.
Именно это обычно ломается при обновлении на хостинге.
"""
import asyncio
import importlib.util
import os
import pathlib
import sys
import tempfile

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_smoke_startup", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class AsyncNoop:
    def __init__(self, result=None):
        self.result = result

    async def __call__(self, *args, **kwargs):
        return self.result


async def _run():
    data_dir = tempfile.mkdtemp(prefix="genmania-smoke-")
    old_data_dir = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = data_dir
    for name in ("DASHBOARD_SYNC_URL", "DASHBOARD_GAME_URL", "DISCORD_TOKEN"):
        os.environ.pop(name, None)

    bot = m.CastleBot()
    bot.tree.sync = AsyncNoop()
    bot.load_application_emojis = AsyncNoop()
    bot.restore_giveaway_views = AsyncNoop()

    try:
        await bot.setup_hook()

        # 1. Миграции отработали на пустой базе.
        assert bot.db is not None
        async with bot.db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
        ) as cursor:
            tables = int((await cursor.fetchone())[0])
        assert tables >= 30, f"таблиц слишком мало: {tables}"

        async with bot.db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name IN ('players', 'inventory', 'clans', 'user_pets_v2')"
        ) as cursor:
            names = {row[0] for row in await cursor.fetchall()}
        assert names == {"players", "inventory", "clans", "user_pets_v2"}

        # 2. Фоновые задачи созданы и живы.
        assert len(bot.background_tasks) >= 15
        await asyncio.sleep(0.2)
        dead = [
            task.get_name()
            for task in bot.background_tasks
            if task.done() and not task.cancelled()
        ]
        assert dead == [], f"фоновые задачи завершились: {dead}"

        # 3. Health-снимок строится на реальной базе.
        snapshot = await bot.build_health_snapshot(deep=True)
        assert snapshot["db_quick_check"] == "ok"
        assert snapshot["db_size_bytes"] > 0
        assert snapshot["tasks_alive"] >= 15
        assert snapshot["gateway_status"] in {"ok", "warning", "error", "unknown"}

        # 4. Повторный запуск на той же папке не проходит из-за lock-файла.
        second = m.CastleBot()
        try:
            second.data_dir = pathlib.Path(data_dir)
            second._instance_lock = m.InstanceLock(second.data_dir / "bot.lock")
            assert second._instance_lock.acquire() is False
        finally:
            second._instance_lock and second._instance_lock.release()
    finally:
        for task in bot.background_tasks:
            task.cancel()
        await asyncio.gather(*bot.background_tasks, return_exceptions=True)
        bot._release_instance_lock()
        if bot.db is not None:
            await bot.db.close()
        if old_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = old_data_dir


def test_bot_starts_on_fresh_data_dir():
    asyncio.run(_run())
