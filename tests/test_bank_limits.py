import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_bank_limits_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_bank_limits_scale_with_income():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000), (2, 1000)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (1, 0, 'basic_gen', 'profile')"
            )
            await db.commit()

            per_sec_coins, _ = await m.get_per_second_income(1)
            income_hour = per_sec_coins * 3600
            max_deposit, max_loan = await m.get_bank_limits(1)
            assert max_deposit == max(
                m.BANK_MAX_DEPOSIT,
                int(income_hour * m.BANK_DEPOSIT_INCOME_HOURS),
            )
            assert max_loan == max(
                m.BANK_LOAN_MAX,
                int(income_hour * m.BANK_LOAN_INCOME_HOURS),
            )

            empty_deposit, empty_loan = await m.get_bank_limits(2)
            assert empty_deposit == m.BANK_MAX_DEPOSIT
            assert empty_loan == m.BANK_LOAN_MAX
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_loan_is_limited_by_income_cap():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour) "
                "VALUES ('big_relic', 'Большой залог', 10000000, 0)"
            )
            await db.execute("INSERT INTO players (user_id, coins) VALUES (1, 0)")
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (1, 0, 'big_relic', 'profile')"
            )
            await db.commit()

            ok, message = await m.take_bank_loan(1, "big_relic", 0, 30000)
            assert ok is False
            assert "Сумма кредита" in message, message
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_tax_rate_falls_back_to_default():
    async def run():
        db = await _init()
        try:
            assert await m.get_tax_rate_for_user(1) == m.DEFAULT_TAX_RATE
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
