import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_pvp_hub_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_cooldown_format():
    assert m.format_cooldown(0) == "готово"
    assert m.format_cooldown(30) == "1 мин."
    assert m.format_cooldown(3600) == "1 ч 0 мин."


def test_pvp_hub_and_battle_log():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, raid_wins) "
                "VALUES (1, 1000, 3), (2, 1000, 0)"
            )
            await db.execute(
                "INSERT INTO raid_cooldowns (user_id, last_raid_time, "
                "last_attacked_time) VALUES (1, ?, ?)",
                (
                    (datetime.datetime.now() - datetime.timedelta(minutes=10)).isoformat(),
                    (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat(),
                ),
            )
            await db.execute(
                "INSERT INTO duel_history (winner_id, loser_id, bet, type) "
                "VALUES (1, 2, 100, 'dice')"
            )
            await db.execute(
                "INSERT INTO raid_loot_log (user_id, target_id, amount, date) "
                "VALUES (1, 2, 300, ?)",
                (m.today_str(),),
            )
            await db.commit()

            hub = await m.build_pvp_hub_embed(1)
            assert "PvP-хаб" in hub.title
            text = hub.description or ""
            assert "Рейд" in text and "Дуэль" in text
            assert "Щит" in text

            log = await m.build_battle_log_embed(1)
            assert "Дуэль" in log.title or "боевой" in log.title.lower()
            entries = "\n".join(field.name for field in log.fields)
            assert "Дуэль" in entries
            assert "Рейд" in entries

            hub_view = m.PvPHubView(1)
            hub_labels = [
                child.label
                for child in hub_view.children
                if isinstance(child, m.discord.ui.Button)
            ]
            assert "Цели" in hub_labels, hub_labels
            assert "История" in hub_labels, hub_labels

            log_view = m.BattleLogView(1, "all", 2, 3)
            filters = [
                child
                for child in log_view.children
                if isinstance(child, m.discord.ui.Select)
            ]
            assert filters, "фильтр истории не добавлен"
            values = [option.value for option in filters[0].options]
            assert values == ["all", "duel", "raid"], values
            assert log_view.btn_duel_rematch.disabled is False
            assert log_view.btn_raid_rematch.disabled is False
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
