import importlib.util
import pathlib
import sys

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_economy_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_start_coins_cover_first_generator():
    price, _ = m.generator_price_income(1)
    assert m.DEFAULT_START_COINS >= m.round_price(price)


def test_generator_payback_stays_reasonable():
    # Самый дорогой обычный генератор должен окупаться быстрее 30 дней.
    for tier in range(1, m.GENERATOR_TIER_COUNT - 2):
        price, income = m.generator_price_income(tier)
        payback_hours = m.round_price(price) / income
        assert payback_hours <= 24 * 30, (tier, payback_hours)


def test_craft_is_slot_positive():
    # 3 копии -> 1 следующего тира без звезды: доход на слот растёт.
    for tier in range(1, 27):
        _, source_income = m.generator_price_income(tier)
        _, result_income = m.generator_price_income(tier + 1)
        ratio = result_income / source_income
        assert ratio > 1.0, (tier, ratio)


def test_star_upgrades_have_positive_expected_value():
    for star in range(1, 6):
        low_mult = 1 + m.STAR_BONUS[star - 1]
        high_mult = 1 + m.STAR_BONUS[star]
        chance = m.STAR_UPGRADE[star]["chance"]
        # При провале одна копия остаётся на прежней звезде.
        expected = chance * high_mult + (1 - chance) * low_mult
        assert expected >= 2 * low_mult, (star, expected, 2 * low_mult)


def test_passive_cap_removed():
    # До 2 часов лимит не мешает активной игре.
    assert m.cap_passive_income(1_000_000, 3600, 100_000) == 1_000_000
    assert m.cap_passive_income(1_000_000, 7200, 100_000) == 1_000_000
    # Оффлайн-потолок удалён: накопление не обрезается.
    assert m.cap_passive_income(1_000_000, 7201, 100_000) == 1_000_000


def test_content_version_includes_balance_change():
    assert m.CONTENT_VERSION >= 5
