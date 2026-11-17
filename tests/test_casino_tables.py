"""Тесты чистых правил рулетки и блэкджека."""
import collections

from gen_mania.services.casino_tables import (
    BLACKJACK_DECKS,
    dealer_should_hit,
    hand_value,
    is_blackjack,
    new_shoe,
    roulette_color,
    roulette_payout,
    settle_blackjack,
)


def test_roulette_colors():
    assert roulette_color(0) == "green"
    assert roulette_color(1) == "red"
    assert roulette_color(2) == "black"
    assert roulette_color(36) == "red"


def test_roulette_payouts():
    assert roulette_payout("number", "17", 17, 100) == 3600
    assert roulette_payout("number", "17", 18, 100) == 0
    assert roulette_payout("color", "red", 3, 100) == 200
    assert roulette_payout("color", "red", 4, 100) == 0
    assert roulette_payout("color", "black", 0, 100) == 0
    assert roulette_payout("parity", "even", 12, 100) == 200
    assert roulette_payout("parity", "odd", 12, 100) == 0
    assert roulette_payout("parity", "even", 0, 100) == 0
    assert roulette_payout("range", "low", 18, 100) == 200
    assert roulette_payout("range", "high", 18, 100) == 0
    assert roulette_payout("dozen", "1", 12, 100) == 300
    assert roulette_payout("dozen", "2", 13, 100) == 300
    assert roulette_payout("dozen", "3", 36, 100) == 300
    assert roulette_payout("dozen", "3", 0, 100) == 0
    assert roulette_payout("unknown", "x", 5, 100) == 0
    assert roulette_payout("number", "bad", 5, 100) == 0
    assert roulette_payout("color", "green", 5, 100) == 0
    assert roulette_payout("parity", "zero", 5, 100) == 0
    assert roulette_payout("range", "mid", 5, 100) == 0
    assert roulette_payout("dozen", "zero", 5, 100) == 0
    assert roulette_payout("number", "17", 17, 0) == 0


def test_hand_values_and_blackjack():
    assert hand_value(["AS", "KH"]) == (21, True)
    assert is_blackjack(["AS", "KH"]) is True
    assert is_blackjack(["AS", "5H", "5D"]) is False
    assert hand_value(["AS", "AH", "9D"]) == (21, True)
    assert hand_value(["AS", "AH", "9D", "9C"]) == (20, False)
    assert hand_value(["KS", "QH", "2D"]) == (22, False)
    assert hand_value(["XX", "5S"]) == (5, False)
    assert hand_value([]) == (0, False)
    assert dealer_should_hit(["10S", "6H"]) is True
    assert dealer_should_hit(["10S", "7H"]) is False
    assert dealer_should_hit(["AS", "6H"]) is False


def test_new_shoe_size_and_distribution():
    shoe = new_shoe()
    assert len(shoe) == 52 * BLACKJACK_DECKS
    counts = collections.Counter(shoe)
    assert counts["AS"] == BLACKJACK_DECKS
    assert len(set(shoe)) == 52


def test_settle_blackjack():
    win = settle_blackjack(["10S", "9H"], ["10D", "8C"], 100)
    assert win["result"] == "win"
    assert win["payout"] == 200
    assert win["net"] == 100

    lose = settle_blackjack(["10S", "8H"], ["10D", "9C"], 100)
    assert lose["result"] == "lose"
    assert lose["payout"] == 0
    assert lose["net"] == -100

    push = settle_blackjack(["10S", "9H"], ["10D", "9C"], 100)
    assert push["result"] == "push"
    assert push["payout"] == 100
    assert push["net"] == 0

    natural = settle_blackjack(["AS", "KH"], ["10D", "9C"], 100)
    assert natural["result"] == "blackjack"
    assert natural["payout"] == 250
    assert natural["net"] == 150

    both = settle_blackjack(["AS", "KH"], ["AD", "KC"], 100)
    assert both["result"] == "push"

    dealer_natural = settle_blackjack(["10S", "9H"], ["AD", "KC"], 100)
    assert dealer_natural["result"] == "lose"

    bust = settle_blackjack(["10S", "9H", "5D"], ["10D", "8C"], 200)
    assert bust["result"] == "bust"
    assert bust["payout"] == 0
    assert bust["net"] == -200

    dealer_bust = settle_blackjack(["10S", "8H"], ["10D", "6C", "9S"], 100)
    assert dealer_bust["result"] == "win"
