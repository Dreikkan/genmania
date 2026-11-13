"""Shared formatting helpers: short numbers and Russian plurals."""
from __future__ import annotations

import math

SHORT_NUMBER_SUFFIXES = (
    "", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc"
)


def format_short_number(value: int | float) -> str:
    """Короткий формат: 1 500 -> 1.5K, 2 000 000 -> 2M."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return str(value)
    sign = "-" if number < 0 else ""
    number = abs(number)
    if number < 1000:
        if number.is_integer():
            return sign + str(int(number))
        return sign + f"{number:.2f}".rstrip("0").rstrip(".")
    tier = min(
        int(math.log10(number) // 3),
        len(SHORT_NUMBER_SUFFIXES) - 1,
    )
    scaled = number / (1000 ** tier)
    if scaled >= 999.5 and tier < len(SHORT_NUMBER_SUFFIXES) - 1:
        tier += 1
        scaled = number / (1000 ** tier)
    if scaled >= 100:
        text = f"{scaled:.0f}"
    else:
        text = f"{scaled:.1f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{sign}{text}{SHORT_NUMBER_SUFFIXES[tier]}"


def format_content_number(value) -> str:
    """Формат для редактора контента (точнее для малых чисел)."""
    number = value if value is not None else 0
    try:
        numeric = float(number)
    except (TypeError, ValueError):
        return str(number)
    if math.isfinite(numeric) and abs(numeric) >= 1000:
        sign = "-" if numeric < 0 else ""
        scaled_value = abs(numeric)
        tier = min(
            int(math.log10(scaled_value) // 3),
            len(SHORT_NUMBER_SUFFIXES) - 1,
        )
        scaled = scaled_value / (1000 ** tier)
        if scaled >= 999.5 and tier < len(SHORT_NUMBER_SUFFIXES) - 1:
            tier += 1
            scaled = scaled_value / (1000 ** tier)
        text = f"{scaled:.0f}" if scaled >= 100 else f"{scaled:.1f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return f"{sign}{text}{SHORT_NUMBER_SUFFIXES[tier]}"
    if isinstance(value, float):
        text = f"{value:.8f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value if value is not None else 0)


def format_content_input(value) -> str:
    """Точное число для prefill редактируемых полей."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return str(value)
    text = f"{number:.10f}".rstrip("0").rstrip(".")
    return text or "0"


def plural_ru(value, one: str, few: str, many: str) -> str:
    """Русская плюрализация: 1 предмет / 2 предмета / 5 предметов."""
    try:
        number = abs(int(value))
    except (TypeError, ValueError):
        return many
    number %= 100
    if 11 <= number <= 14:
        return many
    number %= 10
    if number == 1:
        return one
    if 2 <= number <= 4:
        return few
    return many


__all__ = [
    "SHORT_NUMBER_SUFFIXES",
    "format_short_number",
    "format_content_number",
    "format_content_input",
    "plural_ru",
]
