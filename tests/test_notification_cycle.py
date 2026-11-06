import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_notification_cycle_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeUser:
    def __init__(self, uid, sent):
        self.id = uid
        self._sent = sent

    async def send(self, text=None, embed=None):
        self._sent.append((self.id, text, embed))


def test_notification_cycle_covers_all_events():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            now = datetime.datetime.now()
            yesterday = (now - datetime.timedelta(days=1)).isoformat()
            await db.execute(
                "INSERT INTO players "
                "(user_id, active_pet, last_daily, streak_days) "
                "VALUES (1, 'cat', ?, 3), (2, NULL, ?, 0)",
                (yesterday, yesterday),
            )
            await db.execute(
                "INSERT INTO user_pets_v2 "
                "(user_id, pet_id, level, last_fed) "
                "VALUES (1, 'cat', 1, ?)",
                (
                    (
                        now - datetime.timedelta(hours=10)
                    ).isoformat(),
                ),
            )
            await db.execute(
                "INSERT INTO auctions "
                "(seller_id, item_id, current_bidder, current_bid, "
                "end_time, status) "
                "VALUES (1, 'basic_gen', 2, 100, ?, 'active')",
                (
                    (
                        now + datetime.timedelta(minutes=30)
                    ).isoformat(),
                ),
            )
            await db.execute(
                "INSERT INTO autocollectors "
                "(user_id, level, last_auto) VALUES (1, 1, ?)",
                (
                    (
                        now - datetime.timedelta(hours=5)
                    ).isoformat(),
                ),
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id) "
                "VALUES (1, 'Alpha', 1), (2, 'Beta', 2)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 2, 'leader')"
            )
            await db.execute(
                "INSERT INTO clan_wars "
                "(clan1_id, clan2_id, start_time, status) "
                "VALUES (1, 2, ?, 'active')",
                (now.isoformat(),),
            )
            await db.commit()

            sent = []
            original_get_user = m.bot.get_user
            m.bot.get_user = lambda uid: FakeUser(uid, sent)
            try:
                count = await m.run_notification_cycle()
                assert count >= 6, count
                assert len(sent) == count
                again = await m.run_notification_cycle()
                assert again == 0, again
            finally:
                m.bot.get_user = original_get_user
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
