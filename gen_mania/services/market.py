"""Pure market pricing helpers.

No database or Discord imports: these functions are safe to reuse in
tests, UI and background jobs.
"""
from __future__ import annotations

import datetime

SHOP_MARKET_MIN_RATIO = 0.80
SHOP_MARKET_MAX_RATIO = 1.20
MARKET_MIN_RATIO = 0.50
MARKET_MAX_RATIO = 2.00


def calculate_market_buy_prices(
    price: int, base_price: int, qty: int
) -> tuple[int, int]:
    """Средняя цена покупки и новая цена после покупки.

    Покупка пачки не должна идти целиком по старой цене: иначе можно
    купить 100 предметов, поднять цену до 2× и продать по 70% от неё.
    """
    new_price = min(
        int(base_price * 2) if base_price else int(price * 2),
        max(1, int(price * (1 + 0.01 * qty))),
    )
    avg_price = max(1, int((int(price) + int(new_price)) / 2))
    return avg_price, new_price


def market_price_bounds(item_price: int, buyable: bool) -> tuple[int, int]:
    """Допустимый коридор биржевой цены.

    Для магазинных генераторов биржа не может уйти дальше ±20% от
    фиксированной цены магазина. Для epic+ коридор шире — 50–200%.
    """
    base = max(1, int(item_price or 1))
    if buyable:
        return (
            max(1, int(base * SHOP_MARKET_MIN_RATIO)),
            max(1, int(base * SHOP_MARKET_MAX_RATIO)),
        )
    return (
        max(1, int(base * MARKET_MIN_RATIO)),
        max(1, int(base * MARKET_MAX_RATIO)),
    )


def market_order_price_bounds(item_price: int, buyable: bool) -> tuple[int, int]:
    """Границы цены в ордере.

    Для магазинных генераторов верхняя граница — цена магазина, чтобы
    нельзя было скупить товар в магазине и перепродать дороже.
    """
    low, high = market_price_bounds(item_price, buyable)
    if buyable:
        high = max(low, int(item_price or high))
    return low, high


def clamp_market_price(price, item_price: int, buyable: bool) -> int:
    low, high = market_price_bounds(item_price, buyable)
    value = int(price or item_price or 1)
    return min(high, max(low, value))


def market_sparkline(prices: list[int]) -> str:
    if not prices:
        return "—"
    chars = "▁▂▃▄▅▆▇█"
    low = min(prices)
    high = max(prices)
    if high == low:
        return chars[3] * len(prices)
    return "".join(
        chars[min(7, max(0, int((price - low) / (high - low) * 7)))]
        for price in prices
    )


def parse_market_datetime(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
