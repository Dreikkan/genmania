"""Тексты приветствия нового участника и подстановка плейсхолдеров."""
from __future__ import annotations

from typing import Any

DEFAULT_WELCOME_TITLE = "Добро пожаловать! / Welcome!"

DEFAULT_WELCOME_TEXT_RU = (
    "**{member}**, добро пожаловать в **Gen Mania**! "
    "Покупайте генераторы, заполняйте энергостанцию, собирайте доход и развивайте клан. "
    "В этом вам помогут титулы, питомцы и квесты. Начинайте с команды **/меню**. "
    "Стартовый баланс {start_coins} монет, но у нас есть вступительное задание "
    '"Первые шаги", в котором вы получите дополнительный начальный доход. Желаем удачи!'
)

DEFAULT_WELCOME_TEXT_EN = (
    "**{member}**, welcome to **Gen Mania**! "
    "Buy generators, fill your power station, collect income and grow your clan. "
    "Titles, pets and quests will help you. Start with the **/меню** command. "
    "Your starting balance is {start_coins} coins, but we have an introductory quest "
    '"First Steps" that gives you extra starting income. Good luck!'
)


def format_welcome_text(template: Any, member: Any, settings: dict) -> str:
    """Подставляет данные участника и настройки сервера в шаблон."""
    text = str(template or "")
    if not text:
        return ""
    guild = getattr(member, "guild", None)
    replacements = {
        "{member}": str(getattr(member, "mention", "")),
        "{name}": str(
            getattr(member, "display_name", None)
            or getattr(member, "name", "")
        ),
        "{server}": str(getattr(guild, "name", "")),
        "{start_coins}": str(int(settings.get("start_coins") or 0)),
        "{currency}": str(settings.get("currency_coins") or "монеты"),
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text.strip()
