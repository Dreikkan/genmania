import asyncio
import importlib.util
import pathlib
import sys
import tempfile
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_backup_reset_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    async def defer(self, *args, **kwargs):
        return None


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(id=user_id, name="Tester")
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()


def test_backup_and_user_reset():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            db_path = tmp_path / "castle.db"
            backup_dir = tmp_path / "backups"
            backup_dir.mkdir()
            db = await aiosqlite.connect(str(db_path))
            m._DB_WRITE_LOCK = asyncio.Lock()
            m._DB_TX_OWNER = None
            m.bot.db = db
            m.bot.db_path = db_path
            m.bot.backup_dir = backup_dir
            try:
                await m.bot.init_db()
                await db.execute(
                    "INSERT INTO players (user_id, coins, gems) "
                    "VALUES (1, 1000, 10)"
                )
                await db.commit()

                backup = await m.bot.backup_database("test")
                assert backup is not None
                assert backup.exists()

                interaction = FakeInteraction(1)
                modal = m.UserResetModal(1)
                modal.confirm._value = "СБРОСИТЬ"
                await modal.on_submit(interaction)
                assert interaction.followup.sent

                async with db.execute(
                    "SELECT coins, gems, grid_size "
                    "FROM players WHERE user_id = 1"
                ) as c:
                    coins, gems, grid_size = await c.fetchone()
                assert coins == m.DEFAULT_START_COINS
                assert gems == 0
                assert grid_size == 9
            finally:
                await db.close()
                m.bot.db = None
                m.bot.db_path = None
                m.bot.backup_dir = None
                m._DB_TX_OWNER = None

    asyncio.run(run())
