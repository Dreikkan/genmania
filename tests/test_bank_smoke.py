import asyncio
import datetime
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_bank_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

SCHEMA = """
CREATE TABLE players (
    user_id INTEGER PRIMARY KEY,
    coins INTEGER DEFAULT 0,
    gems INTEGER DEFAULT 0,
    total_coins_earned INTEGER DEFAULT 0,
    total_gems_earned INTEGER DEFAULT 0,
    grid_size INTEGER DEFAULT 9,
    storage_size INTEGER DEFAULT 36,
    income_bonus REAL DEFAULT 0,
    daily_quest_date TEXT DEFAULT NULL,
    daily_quest_progress TEXT DEFAULT '{}',
    daily_quest_claimed TEXT DEFAULT '[]'
);
CREATE TABLE items (
    id TEXT PRIMARY KEY,
    name TEXT,
    price INTEGER DEFAULT 100,
    emoji TEXT DEFAULT '📦',
    rarity TEXT DEFAULT 'common'
);
CREATE TABLE inventory (
    user_id INTEGER,
    slot INTEGER,
    item_id TEXT,
    location TEXT DEFAULT 'profile',
    stars INTEGER DEFAULT 0,
    is_locked INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, location, slot)
);
CREATE TABLE player_collection (
    user_id INTEGER,
    item_id TEXT,
    PRIMARY KEY (user_id, item_id)
);
CREATE TABLE bank_deposits (
    user_id INTEGER PRIMARY KEY,
    amount INTEGER,
    interest_rate REAL DEFAULT 0.05,
    start_time TIMESTAMP,
    end_time TIMESTAMP
);
CREATE TABLE bank_loans (
    user_id INTEGER PRIMARY KEY,
    amount INTEGER,
    interest_rate REAL DEFAULT 0.10,
    due_time TIMESTAMP,
    collateral_item TEXT DEFAULT NULL,
    collateral_stars INTEGER DEFAULT 0,
    issued_at TIMESTAMP DEFAULT NULL,
    status TEXT DEFAULT 'active'
);
CREATE TABLE bank_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    kind TEXT DEFAULT 'deposit',
    details TEXT DEFAULT NULL
);
"""


async def main():
    db = await aiosqlite.connect(":memory:")
    try:
        await run_checks(db)
    finally:
        await db.close()


async def run_checks(db):
    await db.executescript(SCHEMA)
    await db.execute(
        "INSERT INTO items (id, name, price) VALUES ('basic_gen', 'Базовый', 1000)"
    )
    await db.execute(
        "INSERT INTO players (user_id, coins) VALUES (1, 0)"
    )
    await db.execute(
        "INSERT INTO inventory (user_id, slot, item_id, location) "
        "VALUES (1, 0, 'basic_gen', 'profile')"
    )
    await db.commit()
    m.bot.db = db

    # Сложный процент: 1000 под 2% в день на 7 дней.
    start = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
    end = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
    await db.execute(
        "INSERT INTO bank_deposits "
        "(user_id, amount, interest_rate, start_time, end_time) "
        "VALUES (1, 1000, ?, ?, ?)",
        (m.BANK_DAILY_RATE * 7, start, end),
    )
    await db.commit()
    expected = int(1000 * ((1 + m.BANK_DAILY_RATE) ** 7))
    assert await m.calculate_deposit_interest(1) == expected

    # Кредит под залог: 400 из максимума 500.
    ok, msg = await m.take_bank_loan(1, "basic_gen", 0, 400)
    assert ok, msg
    async with db.execute("SELECT coins FROM players WHERE user_id = 1") as c:
        assert (await c.fetchone())[0] == 400
    async with db.execute(
        "SELECT COUNT(*) FROM inventory WHERE user_id = 1"
    ) as c:
        assert (await c.fetchone())[0] == 0
    loan = await m.get_loan(1)
    assert loan and m.loan_total_due(loan) == 440

    # Не хватает на погашение.
    ok, msg = await m.repay_bank_loan(1)
    assert not ok and "Нужно" in msg, (ok, msg)

    # Погашение возвращает залог.
    await db.execute("UPDATE players SET coins = 1000 WHERE user_id = 1")
    await db.commit()
    ok, msg = await m.repay_bank_loan(1)
    assert ok, msg
    async with db.execute("SELECT coins FROM players WHERE user_id = 1") as c:
        assert (await c.fetchone())[0] == 560
    async with db.execute(
        "SELECT COUNT(*) FROM inventory WHERE user_id = 1 AND item_id = 'basic_gen'"
    ) as c:
        assert (await c.fetchone())[0] == 1
    assert await m.get_loan(1) is None

    # Просроченный кредит: залог не возвращается.
    ok, msg = await m.take_bank_loan(1, "basic_gen", 0, 100)
    assert ok, msg
    await db.execute(
        "UPDATE bank_loans SET due_time = ? WHERE user_id = 1",
        ((datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat(),),
    )
    await db.commit()
    await m.expire_bank_loans()
    assert await m.get_loan(1) is None
    async with db.execute(
        "SELECT COUNT(*) FROM inventory WHERE user_id = 1 AND item_id = 'basic_gen'"
    ) as c:
        assert (await c.fetchone())[0] == 0

    # История и экран банка.
    embed, has_deposit, has_loan = await m.build_bank_embed(1)
    assert "Банк" in embed.title
    assert has_deposit and not has_loan
    history = await m.build_bank_history_embed(1)
    assert "История банка" in history.title

    print("BANK SMOKE TEST: OK")


def test_smoke():
    asyncio.run(main())
