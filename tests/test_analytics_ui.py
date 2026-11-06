import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_analytics_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_analytics_embed_contains_core_sections():
    async def run():
        m._DB_WRITE_LOCK = asyncio.Lock()
        m._DB_TX_OWNER = None
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players "
                "(user_id, coins, gems, total_crafts, total_successes, "
                "grid_size, title) VALUES (1, 100, 10, 2, 1, 9, 'Новичок')"
            )
            await db.commit()
            interaction = SimpleNamespace(
                user=SimpleNamespace(
                    id=1,
                    name="Tester",
                    display_avatar=SimpleNamespace(
                        url="https://example.com/a.png"
                    ),
                ),
                guild_id=1,
            )
            embed = await m.build_analytics_embed(interaction)
            assert "Аналитика" in embed.title
            names = [field.name for field in embed.fields]
            assert any("Всего заработано" in name for name in names)
            assert any("Доход" in name for name in names)
            assert any("Прогресс" in name for name in names)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
