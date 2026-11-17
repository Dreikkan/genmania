"""Правила рулетки и блэкджека для веб-казино.

Модуль намеренно не знает про базу и Discord: только чистые функции,
которые легко тестировать.
"""
from __future__ import annotations

import random

RED_NUMBERS = frozenset(
    {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
)

ROULETTE_BET_TYPES = (
    "number",
    "color",
    "parity",
    "range",
    "dozen",
)

BLACKJACK_RANKS = (
    "A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K",
)
BLACKJACK_SUITS = ("S", "H", "D", "C")
BLACKJACK_DECKS = 6


def roulette_color(number: int) -> str:
    if int(number) == 0:
        return "green"
    return "red" if int(number) in RED_NUMBERS else "black"


def roulette_payout(
    bet_type: str,
    bet_value: str,
    number: int,
    amount: int,
) -> int:
    """Сумма возврата игроку. 0 — ставка проиграла."""
    number = int(number)
    amount = int(amount)
    if amount <= 0:
        return 0
    value = str(bet_value or "").strip().lower()

    if bet_type == "number":
        try:
            target = int(value)
        except (TypeError, ValueError):
            return 0
        return amount * 36 if number == target else 0
    if number == 0:
        return 0
    if bet_type == "color":
        return amount * 2 if roulette_color(number) == value else 0
    if bet_type == "parity":
        even = number % 2 == 0
        if value == "even":
            return amount * 2 if even else 0
        if value == "odd":
            return amount * 2 if not even else 0
        return 0
    if bet_type == "range":
        if value == "low":
            return amount * 2 if 1 <= number <= 18 else 0
        if value == "high":
            return amount * 2 if 19 <= number <= 36 else 0
        return 0
    if bet_type == "dozen":
        try:
            dozen = int(value)
        except (TypeError, ValueError):
            return 0
        return amount * 3 if (number - 1) // 12 + 1 == dozen else 0
    return 0


def spin_number(rng: random.Random | None = None) -> int:
    return (rng or random.SystemRandom()).randrange(37)


def card_rank(card: str) -> str:
    return str(card or "")[:-1].upper()


def card_suit(card: str) -> str:
    return str(card or "")[-1:].upper()


def hand_value(cards: list[str]) -> tuple[int, bool]:
    """Возвращает (сумма, мягкая ли рука)."""
    total = 0
    aces = 0
    for card in cards:
        rank = card_rank(card)
        if rank == "A":
            total += 11
            aces += 1
        elif rank in {"10", "J", "Q", "K"}:
            total += 10
        else:
            try:
                total += int(rank)
            except (TypeError, ValueError):
                continue
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


def is_blackjack(cards: list[str]) -> bool:
    return len(cards) == 2 and hand_value(cards)[0] == 21


def dealer_should_hit(cards: list[str]) -> bool:
    """Дилер добирает до 17 и стоит на любых 17, включая мягкие."""
    return hand_value(cards)[0] < 17


def new_shoe(
    decks: int = BLACKJACK_DECKS,
    rng: random.Random | None = None,
) -> list[str]:
    rng = rng or random.SystemRandom()
    cards = [
        rank + suit
        for _ in range(max(1, int(decks)))
        for suit in BLACKJACK_SUITS
        for rank in BLACKJACK_RANKS
    ]
    rng.shuffle(cards)
    return cards


def can_double(cards: list[str]) -> bool:
    return len(cards) == 2


def settle_blackjack(
    player_cards: list[str],
    dealer_cards: list[str],
    stake: int,
) -> dict:
    """Итог раздачи. stake — сумма на столе с учётом удвоения."""
    stake = max(0, int(stake))
    player_total, _player_soft = hand_value(player_cards)
    dealer_total, _dealer_soft = hand_value(dealer_cards)
    player_bj = is_blackjack(player_cards)
    dealer_bj = is_blackjack(dealer_cards)

    if player_bj and dealer_bj:
        result = "push"
        payout = stake
    elif player_bj:
        result = "blackjack"
        payout = int(stake * 2.5)
    elif dealer_bj:
        result = "lose"
        payout = 0
    elif player_total > 21:
        result = "bust"
        payout = 0
    elif dealer_total > 21:
        result = "win"
        payout = stake * 2
    elif player_total > dealer_total:
        result = "win"
        payout = stake * 2
    elif player_total == dealer_total:
        result = "push"
        payout = stake
    else:
        result = "lose"
        payout = 0

    return {
        "result": result,
        "player_total": player_total,
        "dealer_total": dealer_total,
        "player_blackjack": player_bj,
        "dealer_blackjack": dealer_bj,
        "payout": int(payout),
        "net": int(payout) - stake,
        "stake": stake,
    }
