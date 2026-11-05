import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_season_notif_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_advent_events_are_not_only_december():
    import datetime as _dt

    halloween, day = m.get_active_advent_event(_dt.date(2026, 10, 25))
    assert halloween and halloween["key"] == "halloween", halloween
    assert 1 <= day <= halloween["days"]

    winter, _ = m.get_active_advent_event(_dt.date(2026, 12, 25))
    assert winter and winter["key"] == "winter", winter

    none_event, _ = m.get_active_advent_event(_dt.date(2026, 6, 1))
    assert none_event is None

    china, _ = m.get_active_advent_event(_dt.date(2026, 10, 3))
    assert china and china["key"] == "china", china

    america, _ = m.get_active_advent_event(_dt.date(2026, 7, 4))
    assert america and america["key"] == "america", america

    kazakhstan, _ = m.get_active_advent_event(_dt.date(2026, 3, 21))
    assert kazakhstan and kazakhstan["key"] == "kazakhstan_nauryz", kazakhstan


def test_season_preview_pages():
    async def run():
        db = await _init()
        try:
            await db.execute("INSERT INTO players (user_id) VALUES (1)")
            await db.commit()
            first, pages = await m.build_season_preview_embed(1, 0)
            assert pages == 6, pages
            assert "все уровни" in first.title.lower()
            assert len(first.fields) == 5
            last, pages2 = await m.build_season_preview_embed(1, 5)
            assert pages2 == 6
            assert "Ур. 30" in last.fields[-1].name
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_notification_center_events():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, active_pet, last_daily) "
                "VALUES (1, 'cat', NULL)"
            )
            await db.execute(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level, last_fed) "
                "VALUES (1, 'cat', 1, NULL)"
            )
            await db.execute(
                "INSERT INTO bank_loans (user_id, amount, interest_rate, due_time, status) "
                "VALUES (1, 1000, 0.1, ?, 'active')",
                ((datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat(),),
            )
            await db.commit()

            embed = await m.build_notification_center_embed(1)
            assert "Дейли" in embed.description, embed.description
            assert "Питомец" in embed.description, embed.description
            assert "Кредит" in embed.description, embed.description
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
