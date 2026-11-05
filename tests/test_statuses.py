import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_statuses_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init(gems=10000):
    m._DB_WRITE_LOCK = asyncio.Lock()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems) VALUES (1, 100, ?)",
        (gems,),
    )
    await db.commit()
    return db


async def _gems(db):
    async with db.execute(
        "SELECT gems, income_bonus FROM players WHERE user_id = 1"
    ) as c:
        return await c.fetchone()


def test_status_price_ladder_rewards_bulk_purchase():
    for status_id in m.STATUS_BONUSES:
        prices = {
            days: m.status_price(status_id, days)
            for days in m.STATUS_DURATIONS
        }
        assert set(prices) == {1, 3, 7, 30}
        assert prices[30] < prices[1] * 30
        daily = {
            days: prices[days] / days for days in m.STATUS_DURATIONS
        }
        assert daily[1] > daily[3] > daily[7] > daily[30]

    assert m.status_price("vip", 1) == 30
    assert m.status_price("vip", 30) == 500
    assert m.status_price("diamond", 1) == 165
    assert m.status_price("diamond", 30) == 2750
    assert m.status_savings_percent("vip", 30) == 44


def test_purchase_extends_and_blocks_lower_status():
    async def run():
        db = await _init()
        try:
            ok, message = await m.purchase_status(1, "vip", 1)
            assert ok, message
            assert await _gems(db) == (9970, 0.15)
            first = await m.get_active_statuses(1)
            assert "vip" in first

            ok, message = await m.purchase_status(1, "vip", 30)
            assert ok, message
            assert await _gems(db) == (9470, 0.15)
            extended = await m.get_active_statuses(1)
            assert extended["vip"] > first["vip"]
            expiry = datetime.datetime.fromisoformat(extended["vip"])
            assert expiry > datetime.datetime.now() + datetime.timedelta(days=30)

            ok, message = await m.purchase_status(1, "gold", 7)
            assert ok, message
            assert await _gems(db) == (9170, 0.25)
            assert set((await m.get_active_statuses(1))) == {"vip", "gold"}

            ok, message = await m.purchase_status(1, "vip", 1)
            assert ok is False
            assert "Gold" in message
            assert await _gems(db) == (9170, 0.25)

            ok, message = await m.purchase_status(1, "diamond", 1)
            assert ok, message
            assert await _gems(db) == (9005, 0.45)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_status_expiry_removes_bonus():
    async def run():
        db = await _init()
        try:
            assert (await m.purchase_status(1, "gold", 3))[0]
            past = (
                datetime.datetime.now() - datetime.timedelta(days=1)
            ).isoformat()
            await db.execute(
                "UPDATE player_upgrades SET expires_at = ? WHERE upgrade_id = 'gold'",
                (past,),
            )
            await db.commit()

            assert await m.get_active_statuses(1) == {}
            assert await m.get_status_bonus(1) == 0.0
            expired = await m.expire_statuses()
            assert (1, "gold") in expired
            assert await _gems(db) == (9850, 0.0)
            async with db.execute(
                "SELECT COUNT(*) FROM player_upgrades WHERE upgrade_id = 'gold'"
            ) as c:
                assert (await c.fetchone())[0] == 0
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_status_purchase_rejects_insufficient_gems():
    async def run():
        db = await _init(gems=10)
        try:
            ok, message = await m.purchase_status(1, "vip", 1)
            assert ok is False
            assert "Нужно" in message
            assert await _gems(db) == (10, 0.0)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_status_duration_view_and_embed():
    async def run():
        db = await _init()
        try:
            embed = await m.build_status_duration_embed("vip", 1)
            text = "\n".join(field.value for field in embed.fields)
            assert "1 день" in embed.fields[0].name
            assert "30 дней" in embed.fields[3].name
            assert "/день" in text
            assert "выгода" in text

            view = m.StatusDurationView(1, "vip", 0)
            labels = [
                child.label
                for child in view.children
                if isinstance(child, m.discord.ui.Button)
            ]
            assert any("1 день" in label for label in labels)
            assert any("3 дня" in label for label in labels)
            assert any("7 дней" in label for label in labels)
            assert any("30 дней" in label for label in labels)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_upgrade_page_shows_status_duration_range():
    async def run():
        db = await _init()
        try:
            interaction = SimpleNamespace(
                user=SimpleNamespace(id=1), guild_id=1
            )
            embed, _ = await m.build_upgrades_page(interaction, 1)
            vip_fields = [
                field for field in embed.fields if "VIP" in field.name
            ]
            assert vip_fields
            assert "1–30 дней" in vip_fields[0].value
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
