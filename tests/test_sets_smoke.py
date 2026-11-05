import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_sets_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


SCHEMA = """
CREATE TABLE players (
    user_id INTEGER PRIMARY KEY,
    grid_size INTEGER DEFAULT 9,
    income_bonus REAL DEFAULT 0,
    gems INTEGER DEFAULT 0,
    coins INTEGER DEFAULT 0
);
CREATE TABLE items (
    id TEXT PRIMARY KEY,
    name TEXT,
    emoji TEXT DEFAULT '📦'
);
CREATE TABLE inventory (
    user_id INTEGER,
    slot INTEGER,
    item_id TEXT,
    location TEXT DEFAULT 'profile',
    stars INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, location, slot)
);
"""


async def main():
    db = await aiosqlite.connect(":memory:")
    try:
        await run_checks(db)
    finally:
        await db.close()


async def run_checks(db):
    # Чистая логика: два металла рядом.
    details = m.compute_set_synergy([(0, "basic_gen"), (1, "copper_gen")], 9)
    assert details["set_counts"]["metals"] == 2
    assert details["set_bonus"] == 0.01
    assert details["adjacency_pairs"] == 1
    assert details["adjacency_bonus"] == 0.005
    assert details["full_rows"] == 0
    assert details["total"] == 0.015

    # Полный ряд из трёх металлов: сет + 2 соседства + этаж.
    details = m.compute_set_synergy(
        [(0, "basic_gen"), (1, "copper_gen"), (2, "bronze_gen")], 9
    )
    assert details["set_bonus"] == 0.01
    assert details["adjacency_pairs"] == 2
    assert details["full_rows"] == 1
    assert abs(details["total"] - 0.03) < 1e-9

    # Шесть разных металлов: полный сет.
    details = m.compute_set_synergy(
        [
            (0, "basic_gen"), (1, "copper_gen"), (2, "bronze_gen"),
            (3, "iron_gen"), (4, "steel_gen"), (5, "silver_gen"),
        ],
        9,
    )
    assert details["set_counts"]["metals"] == 6
    assert details["set_bonus"] == 0.06
    assert details["full_rows"] == 2
    assert details["total"] > 0.10

    # БД: раскладка и экран сетов.
    await db.executescript(SCHEMA)
    await db.execute("INSERT INTO players (user_id, grid_size) VALUES (1, 9)")
    for item_id in ("basic_gen", "copper_gen", "bronze_gen"):
        await db.execute(
            "INSERT INTO items (id, name) VALUES (?, ?)",
            (item_id, item_id),
        )
    for slot, item_id in enumerate(("basic_gen", "copper_gen", "bronze_gen")):
        await db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location) "
            "VALUES (1, ?, ?, 'profile')",
            (slot, item_id),
        )
    await db.commit()
    m.bot.db = db

    details = await m.get_set_synergy_details(1)
    assert details["set_counts"]["metals"] == 3
    assert details["full_rows"] == 1
    assert abs(await m.get_set_bonus(1) - 0.03) < 1e-9

    embed = await m.build_sets_embed(1)
    assert "Сеты генераторов" in embed.title
    names = [field.name for field in embed.fields]
    assert "Наборы" in names and "Синергия" in names

    print("SETS SMOKE TEST: OK")


def test_smoke():
    asyncio.run(main())
