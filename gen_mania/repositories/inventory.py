"""Inventory repository.

This layer owns only inventory SQL and slot maintenance. UI filters,
selling and crafting rules remain in ``bot.py``.
"""
from __future__ import annotations

import logging
from typing import Any, Callable


class InventoryRuntime:
    """Адаптер между bot.py и репозиторием инвентаря."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        commit_getter: Callable[[], Callable],
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._commit_getter = commit_getter
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


def make_inventory_layer(runtime: InventoryRuntime):
    """Возвращает inventory-функции, привязанные к runtime."""

    async def _reslot_inventory(user_id: int, location: str, rows: list):
        """Переставляет предметы по слотам через временные отрицательные."""
        if not rows:
            return

        for idx, row in enumerate(rows):
            old_slot = row[0]
            await runtime.db.execute(
                "UPDATE inventory SET slot = ? "
                "WHERE user_id = ? AND location = ? AND slot = ?",
                (-(idx + 1), user_id, location, old_slot),
            )

        for new_slot, row in enumerate(rows):
            await runtime.db.execute(
                "UPDATE inventory SET slot = ? "
                "WHERE user_id = ? AND location = ? AND slot = ?",
                (new_slot, user_id, location, -(new_slot + 1)),
            )
        await runtime.commit()

    async def sort_inventory(user_id: int, location: str):
        async with runtime.db.execute(
            """
            SELECT inv.slot, inv.item_id, inv.stars, i.price
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND inv.location = ?
            ORDER BY i.price DESC, inv.stars DESC
            """,
            (user_id, location),
        ) as c:
            rows = await c.fetchall()

        await _reslot_inventory(user_id, location, rows)

    async def sort_inventory_by(user_id: int, location: str, sort_type: str):
        """Сортирует инвентарь по выбранному критерию."""
        async with runtime.db.execute(
            """
            SELECT inv.slot, inv.item_id, inv.stars, i.price,
                   i.income_per_hour, i.rarity
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND inv.location = ?
            """,
            (user_id, location),
        ) as c:
            rows = await c.fetchall()

        if not rows:
            return

        rarity_order = {
            "common": 1,
            "uncommon": 2,
            "rare": 3,
            "epic": 4,
            "legendary": 5,
            "mythic": 6,
        }

        if sort_type == "price_desc":
            rows.sort(key=lambda r: r[3], reverse=True)
        elif sort_type == "price_asc":
            rows.sort(key=lambda r: r[3])
        elif sort_type == "stars_desc":
            rows.sort(key=lambda r: (r[2], r[3]), reverse=True)
        elif sort_type == "stars_asc":
            rows.sort(key=lambda r: (r[2], r[3]))
        elif sort_type == "income_desc":
            rows.sort(key=lambda r: r[4], reverse=True)
        elif sort_type == "rarity_desc":
            rows.sort(
                key=lambda r: (rarity_order.get(r[5], 0), r[3]),
                reverse=True,
            )
        else:
            rows.sort(key=lambda r: (r[3], r[2]), reverse=True)

        await _reslot_inventory(user_id, location, rows)

    async def get_inventory_rows(user_id: int, location: str):
        async with runtime.db.execute(
            """
            SELECT inv.slot, inv.item_id, i.name, i.emoji, inv.stars, i.price,
                   i.rarity, COALESCE(inv.is_locked, 0)
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND inv.location = ?
            ORDER BY inv.slot ASC
            """,
            (user_id, location),
        ) as c:
            return await c.fetchall()

    async def toggle_item_lock(
        user_id: int,
        location: str,
        slot: int,
        item_id: str,
        stars: int,
    ) -> tuple[bool, int, str]:
        """Переключает блокировку предмета. Возвращает (ok, state, message)."""
        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT COALESCE(is_locked, 0) FROM inventory "
                    "WHERE user_id = ? AND location = ? AND slot = ? "
                    "AND item_id = ? AND stars = ?",
                    (user_id, location, slot, item_id, stars),
                ) as c:
                    row = await c.fetchone()
                if not row:
                    raise ValueError("Предмет не найден.")
                new_state = 0 if row[0] else 1
                cur = await runtime.db.execute(
                    "UPDATE inventory SET is_locked = ? "
                    "WHERE user_id = ? AND location = ? AND slot = ? "
                    "AND item_id = ? AND stars = ?",
                    (new_state, user_id, location, slot, item_id, stars),
                )
                if cur.rowcount == 0:
                    raise ValueError("Предмет уже перемещён.")
        except ValueError as e:
            return False, 0, f"❌ {e}"
        return True, new_state, ""

    return (
        _reslot_inventory,
        sort_inventory,
        sort_inventory_by,
        get_inventory_rows,
        toggle_item_lock,
    )
