import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_notifications_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._DB_TX_OWNER = None


def test_notification_preferences_and_throttle():
    async def run():
        db = await _init()
        try:
            notif_type = next(iter(m.NOTIFICATION_TYPES))
            defaults = await m.get_notifications(1)
            assert defaults[notif_type] == (1, None)

            await m.set_notification(1, notif_type, False)
            disabled = await m.get_notifications(1)
            assert disabled[notif_type][0] == 0
            assert await m.can_send_notification(1, notif_type) is False

            await m.set_notification(1, notif_type, True)
            assert await m.can_send_notification(1, notif_type) is True

            await m.mark_notification_sent(1, notif_type)
            assert await m.can_send_notification(1, notif_type) is False

            before = await m.get_notifications(1)
            assert before[notif_type][1] is not None
        finally:
            await _close(db)

    asyncio.run(run())


def test_dm_notification_marks_sent():
    async def run():
        db = await _init()
        original_get_user = m.bot.get_user
        try:
            class FakeUser:
                def __init__(self):
                    self.messages = []

                async def send(self, *args, **kwargs):
                    self.messages.append((args, kwargs))

            fake = FakeUser()
            m.bot.get_user = lambda user_id: fake
            notif_type = next(iter(m.NOTIFICATION_TYPES))
            ok = await m.send_dm_notification(1, notif_type, "hello")
            assert ok is True
            assert fake.messages
            assert (await m.get_notifications(1))[notif_type][1] is not None
        finally:
            m.bot.get_user = original_get_user
            await _close(db)

    asyncio.run(run())
