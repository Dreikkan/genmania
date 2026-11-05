import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_pvp_targets_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _add_power(db, user_id, price, coins):
    await db.execute(
        "INSERT INTO items (id, name, price, income_per_hour) VALUES (?, ?, ?, 0)",
        (f"gen_{user_id}", f"Generator {user_id}", price),
    )
    await db.execute(
        "INSERT INTO players (user_id, coins) VALUES (?, ?)",
        (user_id, coins),
    )
    await db.execute(
        "INSERT INTO inventory (user_id, slot, item_id, location) "
        "VALUES (?, 0, ?, 'profile')",
        (user_id, f"gen_{user_id}"),
    )


def test_target_board_filters_by_mode_and_power():
    async def run():
        db = await _init()
        try:
            # Зритель: 100 мощи. Цели: 100, 110, 120, 20.
            await _add_power(db, 1, 100, 1000)
            await _add_power(db, 2, 100, 5000)
            await _add_power(db, 3, 110, 4000)
            await _add_power(db, 4, 120, 3000)
            await _add_power(db, 5, 20, 2000)
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (6, 900)"
            )
            await db.commit()

            raid_targets = await m.get_pvp_targets(1, "raid")
            raid_ids = [target["user_id"] for target in raid_targets]
            assert raid_ids == [2, 3, 4], raid_ids
            assert all(target["power"] >= 25 for target in raid_targets)

            duel_targets = await m.get_pvp_targets(1, "duel")
            duel_ids = [target["user_id"] for target in duel_targets]
            assert duel_ids == [2, 3], duel_ids
            for target in duel_targets:
                assert 85 <= target["power"] <= 115, target
            assert 1 not in duel_ids and 5 not in duel_ids and 6 not in duel_ids

            duel_embed = await m.build_pvp_targets_embed(1, "duel")
            assert "±15%" in duel_embed.description, duel_embed.description
            assert "Целей найдено: **2**" in duel_embed.description

            raid_embed = await m.build_pvp_targets_embed(1, "raid")
            assert "25%" in raid_embed.description, raid_embed.description
            assert "Целей найдено: **3**" in raid_embed.description
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_target_board_shows_shield_and_cooldowns():
    async def run():
        db = await _init()
        try:
            await _add_power(db, 1, 100, 1000)
            await _add_power(db, 2, 100, 2000)
            now = datetime.datetime.now()
            await db.execute(
                "INSERT INTO raid_cooldowns (user_id, last_raid_time, "
                "last_attacked_time) VALUES (2, ?, ?)",
                (
                    (now - datetime.timedelta(minutes=10)).isoformat(),
                    (now - datetime.timedelta(hours=1)).isoformat(),
                ),
            )
            await db.execute(
                "INSERT INTO duel_cooldowns (user_id, last_duel_time) "
                "VALUES (2, ?)",
                ((now - datetime.timedelta(seconds=60)).isoformat(),),
            )
            await db.commit()

            targets = await m.get_pvp_targets(1, "raid")
            assert len(targets) == 1
            target = targets[0]
            assert target["shield"] > 0
            assert target["raid_cd"] > 0
            assert target["duel_cd"] > 0

            embed = await m.build_pvp_targets_embed(1, "raid")
            value = embed.fields[0].value
            assert "Щит" in value and "Рейд:" in value and "Дуэль:" in value
            assert "готов" not in value.split("Щит")[1].split("\n")[0]
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_target_board_empty_state_and_limit():
    async def run():
        db = await _init()
        try:
            await _add_power(db, 1, 100, 1000)
            await db.execute("INSERT INTO players (user_id, coins) VALUES (2, 500)")
            await db.commit()

            targets = await m.get_pvp_targets(1, "raid")
            assert targets == []
            embed = await m.build_pvp_targets_embed(1, "raid")
            assert "Подходящих целей нет" in embed.description

            # 12 равных целей: доска обязана ограничиться десятью.
            for user_id in range(10, 22):
                await _add_power(db, user_id, 100, 10000 - user_id)
            await db.commit()
            targets = await m.get_pvp_targets(1, "duel")
            assert len(targets) == 10, len(targets)
            assert len({target["user_id"] for target in targets}) == 10
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_last_targets_for_rematch():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO duel_history (winner_id, loser_id, bet, type) "
                "VALUES (1, 2, 100, 'dice'), (3, 1, 200, 'power')"
            )
            await db.execute(
                "INSERT INTO raid_loot_log (user_id, target_id, amount) "
                "VALUES (1, 4, 100), (1, 5, 200)"
            )
            await db.commit()

            assert await m.get_last_duel_opponent(1) == 3
            assert await m.get_last_duel(1) == (3, "power")
            assert await m.get_last_raid_target(1) == 5
            assert await m.get_last_duel_opponent(9) is None
            assert await m.get_last_duel(9) is None
            assert await m.get_last_raid_target(9) is None
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_battle_log_filters():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO duel_history (winner_id, loser_id, bet, type) "
                "VALUES (1, 2, 100, 'dice')"
            )
            await db.execute(
                "INSERT INTO raid_loot_log (user_id, target_id, amount) "
                "VALUES (1, 3, 500)"
            )
            await db.commit()

            all_embed = await m.build_battle_log_embed(1, "all")
            all_names = "\n".join(field.name for field in all_embed.fields)
            assert "Дуэль" in all_names and "Рейд" in all_names

            duel_embed = await m.build_battle_log_embed(1, "duel")
            duel_names = "\n".join(field.name for field in duel_embed.fields)
            assert "Дуэль" in duel_names and "Рейд" not in duel_names
            assert "дуэли" in duel_embed.description

            raid_embed = await m.build_battle_log_embed(1, "raid")
            raid_names = "\n".join(field.name for field in raid_embed.fields)
            assert "Рейд" in raid_names and "Дуэль" not in raid_names
            assert "рейды" in raid_embed.description
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
