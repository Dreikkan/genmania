"""Pets and autocollector service."""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable

from .market import parse_market_datetime


class PetRuntime:
    """Адаптер между bot.py и сервисом питомцев."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self.pet_types: dict = {}
        self.pet_max_level = 10
        self.feed_cost_coins = 1000
        self.feed_cost_gems = 5
        self.feed_xp = 1
        self.feed_cooldown_hours = 4
        self.autocollect_price_gems = 100
        self.autocollect_max_level = 5
        self.autocollect_levels: dict = {}
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        pet_types: dict,
        pet_max_level: int,
        feed_cost_coins: int,
        feed_cost_gems: int,
        feed_xp: int,
        feed_cooldown_hours: int,
        autocollect_price_gems: int,
        autocollect_max_level: int,
        autocollect_levels: dict,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self.pet_types = pet_types
        self.pet_max_level = pet_max_level
        self.feed_cost_coins = feed_cost_coins
        self.feed_cost_gems = feed_cost_gems
        self.feed_xp = feed_xp
        self.feed_cooldown_hours = feed_cooldown_hours
        self.autocollect_price_gems = autocollect_price_gems
        self.autocollect_max_level = autocollect_max_level
        self.autocollect_levels = autocollect_levels
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()


def make_pet_layer(runtime: PetRuntime):
    """Возвращает pet/autocollector-функции, привязанные к runtime."""

    async def get_active_pet(user_id: int):
        """Возвращает (pet_id, level) активного питомца или None."""
        async with runtime.db.execute(
            "SELECT active_pet FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        if not row or not row[0]:
            return None
        pet_id = row[0]
        async with runtime.db.execute(
            "SELECT level FROM user_pets_v2 "
            "WHERE user_id = ? AND pet_id = ?",
            (user_id, pet_id),
        ) as c:
            r = await c.fetchone()
        if not r:
            return None
        return pet_id, r[0]

    def pet_effect_bonus(
        pet_id: str | None, level: int, effect_type: str
    ) -> float:
        """Бонус питомца по типу эффекта без обращения к БД."""
        ptype = runtime.pet_types.get(pet_id or "")
        if not ptype:
            return 0.0
        per_level = 0.0
        if ptype.get("effect") == effect_type:
            per_level += ptype.get("per_level", 0.0)
        per_level += ptype.get("extra_effects", {}).get(
            effect_type, 0.0
        )
        return per_level * max(0, int(level or 0))

    async def get_pet_bonus(user_id: int, effect_type: str) -> float:
        """Суммарный бонус активного питомца для эффекта."""
        pet = await get_active_pet(user_id)
        if not pet:
            return 0.0
        pet_id, level = pet
        return pet_effect_bonus(pet_id, level, effect_type)

    async def feed_active_pet(
        user_id: int,
    ) -> tuple[bool, str, int, str]:
        """Кормит активного питомца с проверкой внутри транзакции."""
        pet_id = ""
        new_level = 0
        try:
            async with runtime.transaction():
                pet = await get_active_pet(user_id)
                if not pet:
                    raise ValueError("❌ У тебя нет активного питомца.")
                pet_id, level = pet
                ptype = runtime.pet_types.get(pet_id)
                if not ptype:
                    raise ValueError("❌ Питомец не найден.")
                if level >= runtime.pet_max_level:
                    raise ValueError(
                        f"❌ {ptype['emoji']} {ptype['name']} "
                        "уже максимального уровня."
                    )

                async with runtime.db.execute(
                    "SELECT last_fed FROM user_pets_v2 "
                    "WHERE user_id = ? AND pet_id = ?",
                    (user_id, pet_id),
                ) as c:
                    row = await c.fetchone()
                last_fed = row[0] if row else None
                now = datetime.datetime.now()
                last = parse_market_datetime(last_fed)
                if last:
                    left = (
                        runtime.feed_cooldown_hours * 3600
                        - (now - last).total_seconds()
                    )
                    if left > 0:
                        hours = int(left // 3600)
                        minutes = int((left % 3600) // 60)
                        raise ValueError(
                            f"⏳ Питомец не голоден. Подожди "
                            f"{hours}ч {minutes}м."
                        )

                cur = await runtime.db.execute(
                    "UPDATE players SET coins = coins - ?, "
                    "gems = gems - ? WHERE user_id = ? "
                    "AND coins >= ? AND gems >= ?",
                    (
                        runtime.feed_cost_coins,
                        runtime.feed_cost_gems,
                        user_id,
                        runtime.feed_cost_coins,
                        runtime.feed_cost_gems,
                    ),
                )
                if cur.rowcount == 0:
                    raise ValueError(
                        f"❌ Нужно 🪙 {runtime.feed_cost_coins} и "
                        f"💎 {runtime.feed_cost_gems}."
                    )
                cur = await runtime.db.execute(
                    "UPDATE user_pets_v2 SET level = level + ?, "
                    "last_fed = ? WHERE user_id = ? AND pet_id = ? "
                    "AND level < ?",
                    (
                        runtime.feed_xp,
                        now.isoformat(),
                        user_id,
                        pet_id,
                        runtime.pet_max_level,
                    ),
                )
                if cur.rowcount == 0:
                    raise ValueError(
                        "❌ Питомец уже максимального уровня."
                    )
                new_level = min(
                    runtime.pet_max_level, level + runtime.feed_xp
                )
        except ValueError as exc:
            return False, str(exc), 0, ""
        return (
            True,
            f"🍖 {ptype['emoji']} {ptype['name']} покормлен! "
            f"Уровень: **{new_level}/{runtime.pet_max_level}**.",
            new_level,
            pet_id,
        )

    async def get_autocollector(user_id: int):
        """Возвращает (level, last_auto) или None."""
        async with runtime.db.execute(
            "SELECT level, last_auto FROM autocollectors "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            return await c.fetchone()

    async def buy_autocollector(user_id: int) -> tuple[bool, str]:
        """Покупка автосборщика. Возвращает (успех, сообщение)."""
        existing = await get_autocollector(user_id)
        if existing:
            return False, "❌ У тебя уже есть автосборщик."

        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT 1 FROM autocollectors WHERE user_id = ?",
                    (user_id,),
                ) as c:
                    if await c.fetchone():
                        raise ValueError(
                            "У тебя уже есть автосборщик."
                        )

                cur = await runtime.db.execute(
                    "UPDATE players SET gems = gems - ? "
                    "WHERE user_id = ? AND gems >= ?",
                    (
                        runtime.autocollect_price_gems,
                        user_id,
                        runtime.autocollect_price_gems,
                    ),
                )
                if cur.rowcount == 0:
                    raise ValueError(
                        f"Нужно 💎 {runtime.autocollect_price_gems}."
                    )

                await runtime.db.execute(
                    "INSERT INTO autocollectors "
                    "(user_id, level, last_auto) VALUES (?, 1, ?)",
                    (user_id, datetime.datetime.now().isoformat()),
                )
        except ValueError as e:
            return False, f"❌ {e}"

        interval = runtime.autocollect_levels[1][1]
        return True, (
            f"✅ Автосборщик куплен за 💎 "
            f"{runtime.autocollect_price_gems}! "
            f"Теперь доход собирается раз в {interval} ч."
        )

    async def upgrade_autocollector(
        user_id: int,
    ) -> tuple[bool, str]:
        """Улучшение автосборщика на следующий уровень."""
        existing = await get_autocollector(user_id)
        if not existing:
            return (
                False,
                "❌ У тебя нет автосборщика. Сначала купи его.",
            )

        level, _ = existing
        if level >= runtime.autocollect_max_level:
            return (
                False,
                f"❌ Автосборщик уже максимального уровня "
                f"({runtime.autocollect_max_level}).",
            )

        next_level = level + 1
        price, interval = runtime.autocollect_levels[next_level]

        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT level FROM autocollectors "
                    "WHERE user_id = ?",
                    (user_id,),
                ) as c:
                    row = await c.fetchone()
                if not row or row[0] != level:
                    raise ValueError(
                        "Данные изменились, попробуй снова."
                    )

                cur = await runtime.db.execute(
                    "UPDATE players SET gems = gems - ? "
                    "WHERE user_id = ? AND gems >= ?",
                    (price, user_id, price),
                )
                if cur.rowcount == 0:
                    raise ValueError(f"Нужно 💎 {price}.")

                await runtime.db.execute(
                    "UPDATE autocollectors SET level = ? "
                    "WHERE user_id = ?",
                    (next_level, user_id),
                )
        except ValueError as e:
            return False, f"❌ {e}"

        return True, (
            f"✅ Автосборщик улучшен до {next_level} ур.! "
            f"Теперь собирает раз в {interval} ч."
        )

    async def get_user_pets(user_id: int) -> list:
        """Список (pet_id, level, last_fed) всех питомцев."""
        async with runtime.db.execute(
            "SELECT pet_id, level, last_fed FROM user_pets_v2 "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            return await c.fetchall()

    return (
        get_active_pet,
        pet_effect_bonus,
        get_pet_bonus,
        feed_active_pet,
        get_autocollector,
        buy_autocollector,
        upgrade_autocollector,
        get_user_pets,
    )
