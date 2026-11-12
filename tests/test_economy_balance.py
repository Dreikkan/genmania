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
    # Покупаемые обычные генераторы должны окупаться быстрее 90 дней.
    for tier in range(1, 10):
        price, income = m.generator_price_income(tier)
        payback_hours = m.round_price(price) / income
        assert payback_hours <= 24 * 90, (tier, payback_hours)


def test_craft_is_cheaper_than_buying():
    # 3 копии предыдущего тира должны стоить меньше готового генератора.
    for tier in range(1, 10):
        source_price, _ = m.generator_price_income(tier)
        result_price, _ = m.generator_price_income(tier + 1)
        assert m.round_price(result_price) > (
            m.CRAFT_COST * m.round_price(source_price)
        ), tier


def test_craft_is_slot_positive():
    # 3 копии -> 1 следующего тира без звезды: доход на слот растёт.
    for tier in range(1, 27):
        _, source_income = m.generator_price_income(tier)
        _, result_income = m.generator_price_income(tier + 1)
        ratio = result_income / source_income
        assert ratio > 1.0, (tier, ratio)


def test_synthesis_keeps_total_income():
    # 3 копии должны давать не меньше суммарного дохода, чем 1 результат.
    for tier in range(1, 30):
        _, source_income = m.generator_price_income(tier)
        _, result_income = m.generator_price_income(tier + 1)
        assert result_income >= m.CRAFT_COST * source_income - 1e-9, tier


def test_star_stacking_does_not_beat_tier_progression():
    _, basic_income = m.generator_price_income(1)
    _, steel_income = m.generator_price_income(5)
    assert basic_income * (1 + m.STAR_BONUS[5]) < steel_income


def test_star_upgrades_have_positive_expected_value():
    for star in range(1, 6):
        low_mult = 1 + m.STAR_BONUS[star - 1]
        high_mult = 1 + m.STAR_BONUS[star]
        chance = m.STAR_UPGRADE[star]["chance"]
        # При провале одна копия остаётся на прежней звезде.
        expected = chance * high_mult + (1 - chance) * low_mult
        assert high_mult > low_mult, (star, low_mult, high_mult)
        assert expected > low_mult, (star, expected, low_mult)


def test_passive_cap_removed():
    # До 2 часов лимит не мешает активной игре.
    assert m.cap_passive_income(1_000_000, 3600, 100_000) == 1_000_000
    assert m.cap_passive_income(1_000_000, 7200, 100_000) == 1_000_000
    # Оффлайн-потолок удалён: накопление не обрезается.
    assert m.cap_passive_income(1_000_000, 7201, 100_000) == 1_000_000


def test_content_version_includes_balance_change():
    assert m.CONTENT_VERSION >= 5
