import asyncio
import importlib.util
import pathlib
import sys

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("genmania_reliability_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_instance_lock_blocks_second_instance(tmp_path):
    first = m.InstanceLock(tmp_path / "bot.lock")
    second = m.InstanceLock(tmp_path / "bot.lock")
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
        second.release()

    third = m.InstanceLock(tmp_path / "bot.lock")
    assert third.acquire() is True
    third.release()


def test_background_watchdog_restarts_after_error():
    bot = m.CastleBot()
    bot._closing = False
    bot.background_restart_delay = 0.01
    bot.background_restart_max = 0.01
    calls = {"count": 0}

    async def flaky():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        await asyncio.sleep(10)

    async def run():
        task = bot._spawn_background("flaky", flaky)
        await asyncio.sleep(0.1)
        assert calls["count"] >= 2
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
