"""Status purchase, bonus and expiry service."""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable

import aiosqlite


class StatusRuntime:
    """Адаптер между bot.py и сервисом статусов."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self._remove_role_getter: Callable[[], Callable] = lambda: None
        self._price_getter: Callable[[str, int], int | None] = (
            lambda status_id, days: None
        )
        self.bonuses: dict = {}
        self.durations = ()
        self.names: dict = {}
        self.order = ()
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        commit_getter: Callable[[], Callable],
        remove_role_getter: Callable[[], Callable],
        price_getter: Callable[[str, int], int | None],
        bonuses: dict,
        durations,
        names: dict,
        order,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._commit_getter = commit_getter
        self._remove_role_getter = remove_role_getter
        self._price_getter = price_getter
        self.bonuses = bonuses
        self.durations = durations
        self.names = names
        self.order = order
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    async def commit(self) -> None:
        commit = self._commit_getter()
        if commit is not None:
            await commit()

    async def remove_status_role(self, *args, **kwargs) -> None:
        await self._remove_role_getter()(*args, **kwargs)

    def status_price(self, status_id: str, days: int):
        return self._price_getter(status_id, days)


def make_status_layer(runtime: StatusRuntime):
    """Возвращает status-функции, привязанные к runtime."""

    def status_rank(upgrade_id: str) -> int:
        """Ранг статуса в линейке; -1 для не-статуса."""
        try:
            return runtime.order.index(upgrade_id)
        except ValueError:
            return -1

    def best_status_bonus(status_ids) -> float:
        """Бонус лучшего статуса из набора."""
        best = 0.0
        for status_id in status_ids:
            bonus = runtime.bonuses.get(status_id, 0.0)
            if bonus > best:
                best = bonus
        return best

    def format_status_expiry(value) -> str:
        if not value:
            return "бессрочно"
        try:
            parsed = datetime.datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return str(value)
        return parsed.strftime("%d.%m.%Y %H:%M")

    async def get_active_statuses(
        user_id: int,
    ) -> dict[str, str | None]:
        """Активные статусы пользователя: id -> expires_at."""
        now_iso = datetime.datetime.now().isoformat()
        statuses = tuple(runtime.bonuses)
        placeholders = ",".join("?" for _ in statuses)
        try:
            async with runtime.db.execute(
                f"SELECT upgrade_id, expires_at FROM player_upgrades "
                f"WHERE user_id = ? "
                f"AND upgrade_id IN ({placeholders}) "
                f"AND (expires_at IS NULL "
                f"OR datetime(expires_at) > datetime(?))",
                (user_id, *statuses, now_iso),
            ) as c:
                rows = await c.fetchall()
            return {row[0]: row[1] for row in rows}
        except aiosqlite.OperationalError:
            # Совместимость со старыми схемами без expires_at.
            try:
                async with runtime.db.execute(
                    f"SELECT upgrade_id FROM player_upgrades "
                    f"WHERE user_id = ? "
                    f"AND upgrade_id IN ({placeholders})",
                    (user_id, *statuses),
                ) as c:
                    rows = await c.fetchall()
                return {row[0]: None for row in rows}
            except aiosqlite.OperationalError:
                return {}

    async def get_status_bonus(user_id: int) -> float:
        statuses = await get_active_statuses(user_id)
        return best_status_bonus(statuses.keys())

    async def sync_status_bonus(user_id: int) -> float:
        bonus = await get_status_bonus(user_id)
        await runtime.db.execute(
            "UPDATE players SET income_bonus = ? WHERE user_id = ?",
            (bonus, user_id),
        )
        await runtime.commit()
        return bonus

    async def purchase_status(
        user_id: int, status_id: str, days: int
    ) -> tuple[bool, str]:
        if status_id not in runtime.bonuses:
            return False, "❌ Неизвестный статус."
        if days not in runtime.durations:
            return False, "❌ Неверный срок статуса."
        price = runtime.status_price(status_id, days)
        if price is None:
            return False, "❌ Неверная цена статуса."
        name = runtime.names.get(status_id, status_id)

        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT gems FROM players WHERE user_id = ?",
                    (user_id,),
                ) as c:
                    row = await c.fetchone()
                if not row:
                    raise ValueError("❌ Профиль не найден.")
                gems = row[0] or 0
                if gems < price:
                    raise ValueError(
                        f"❌ Нужно 💎 {price}, у тебя {gems}."
                    )

                active = await get_active_statuses(user_id)
                owned_rank = max(
                    (status_rank(item) for item in active),
                    default=-1,
                )
                if status_rank(status_id) < owned_rank:
                    best = max(active, key=status_rank)
                    raise ValueError(
                        f"❌ У тебя активен "
                        f"**{runtime.names.get(best, best)}**. "
                        "Статус ниже по линейке покупать нельзя."
                    )

                now = datetime.datetime.now()
                async with runtime.db.execute(
                    "SELECT expires_at FROM player_upgrades "
                    "WHERE user_id = ? AND upgrade_id = ?",
                    (user_id, status_id),
                ) as c:
                    current = await c.fetchone()
                base = now
                if current and current[0]:
                    try:
                        current_expiry = (
                            datetime.datetime.fromisoformat(
                                current[0]
                            )
                        )
                    except (TypeError, ValueError):
                        current_expiry = None
                    if current_expiry and current_expiry > now:
                        base = current_expiry
                new_expiry = base + datetime.timedelta(days=days)

                cur = await runtime.db.execute(
                    "UPDATE players SET gems = gems - ? "
                    "WHERE user_id = ? AND gems >= ?",
                    (price, user_id, price),
                )
                if cur.rowcount == 0:
                    raise ValueError(
                        "❌ Недостаточно гемов (баланс изменился)."
                    )

                await runtime.db.execute(
                    """
                    INSERT INTO player_upgrades
                        (user_id, upgrade_id, level, purchased_at,
                         expires_at)
                    VALUES (?, ?, 1, CURRENT_TIMESTAMP, ?)
                    ON CONFLICT(user_id, upgrade_id) DO UPDATE SET
                        expires_at = excluded.expires_at,
                        purchased_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, status_id, new_expiry.isoformat()),
                )
                await sync_status_bonus(user_id)
        except ValueError as exc:
            return False, str(exc)

        return True, (
            f"✅ **{name}** активирован до "
            f"`{format_status_expiry(new_expiry.isoformat())}`. "
            f"Списано 💎 {price}."
        )

    async def expire_statuses() -> list[tuple[int, str]]:
        """Удаляет истёкшие статусы и пересчитывает income_bonus."""
        now_iso = datetime.datetime.now().isoformat()
        statuses = tuple(runtime.bonuses)
        placeholders = ",".join("?" for _ in statuses)
        async with runtime.transaction():
            async with runtime.db.execute(
                f"SELECT user_id, upgrade_id FROM player_upgrades "
                f"WHERE upgrade_id IN ({placeholders}) "
                f"AND expires_at IS NOT NULL "
                f"AND datetime(expires_at) <= datetime(?)",
                (*statuses, now_iso),
            ) as c:
                expired = await c.fetchall()
            if not expired:
                return []
            await runtime.db.execute(
                f"DELETE FROM player_upgrades "
                f"WHERE upgrade_id IN ({placeholders}) "
                f"AND expires_at IS NOT NULL "
                f"AND datetime(expires_at) <= datetime(?)",
                (*statuses, now_iso),
            )
            for user_id in {row[0] for row in expired}:
                await sync_status_bonus(user_id)

        for user_id, status_id in expired:
            await runtime.remove_status_role(user_id, status_id)
        return expired

    return (
        status_rank,
        best_status_bonus,
        format_status_expiry,
        get_active_statuses,
        get_status_bonus,
        sync_status_bonus,
        purchase_status,
        expire_statuses,
    )
