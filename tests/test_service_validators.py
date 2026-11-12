import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_service_validators_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_content_and_giveaway_validators():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 100, 10)"
            )
            await db.commit()

            assert m.normalize_content_id(None) is None
            assert m.normalize_content_id("Bad ID") is None
            assert m.normalize_content_id("good_id") == "good_id"
            assert m.normalize_content_name(None) is None
            assert m.normalize_content_name("") is None
            assert m.normalize_content_name("x" * 500) is None
            assert m.normalize_content_name("Test") == "Test"
            assert m.parse_content_int("bad") is None
            assert m.parse_content_int(-1) is None
            assert m.parse_content_int(10**19) is None
            assert m.parse_content_int("10") == 10
            assert m.parse_content_float("bad") is None
            assert m.parse_content_float(-1) is None
            assert m.parse_content_float("1,5") == 1.5
            assert m.format_content_number(1.5) == "1.5"
            assert m.format_content_number(0.0) == "0"
            assert m.format_content_number(None) == "0"
            assert m.is_non_negative_number("1") is True
            assert m.is_non_negative_number("-1") is False
            assert m.is_non_negative_number("x") is False

            for reward_type, info in m.GIVEAWAY_REWARDS.items():
                meta, error = await m.giveaway_validate_reward(
                    reward_type, "bad", "bad"
                )
                assert meta is None and error

            assert m.parse_giveaway_options("0", "24")[2] is not None
            assert m.parse_giveaway_options("1", "0")[2] is not None
            assert m.parse_giveaway_options("1", "999")[2] is not None
            assert m.parse_giveaway_options("bad", "bad")[2] is not None
            winners, hours, error = m.parse_giveaway_options("1", "24")
            assert not error and winners == 1 and hours == 24

            ok, message = await m.create_market_order(
                1, "bad", "basic_gen", 1, 10
            )
            assert not ok and message

            ok, message = await m.create_market_order(
                1, "sell", "missing_item", 1, 10
            )
            assert not ok and message

            active_pet = await m.get_active_pet(1)
            assert active_pet is None
            ok, message, _level, _pet = await m.feed_active_pet(1)
            assert not ok and message

            ok, message = await m.buy_autocollector(1)
            assert not ok and message
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
