"""Inventory repository.

This layer owns only inventory SQL and slot maintenance. UI filters,
selling and crafting rules remain in ``bot.py``.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import aiosqlite


class InventoryRuntime:
    """Адаптер между bot.py и репозиторием инвентаря."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self._grid_size_getter: Callable[[], Callable] = lambda: None
        self._storage_size_getter: Callable[[], Callable] = lambda: None
        self._place_items_getter: Callable[[], Callable] = lambda: None
        self._temp_storage_size_getter: Callable[[], int] = lambda: 6
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        commit_getter: Callable[[], Callable],
        grid_size_getter: Callable[[], Callable],
        storage_size_getter: Callable[[], Callable],
        place_items_getter: Callable[[], Callable],
        temp_storage_size_getter: Callable[[], int],
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._commit_getter = commit_getter
        self._grid_size_getter = grid_size_getter
        self._storage_size_getter = storage_size_getter
        self._place_items_getter = place_items_getter
        self._temp_storage_size_getter = temp_storage_size_getter
        self.logger = logger

    @property
    def temp_storage_size(self) -> int:
        return self._temp_storage_size_getter()

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

    async def get_grid_size(self, user_id: int):
        return await self._grid_size_getter()(user_id)

    async def get_storage_size(self, user_id: int):
        return await self._storage_size_getter()(user_id)

    async def place_items(self, *args, **kwargs):
        return await self._place_items_getter()(*args, **kwargs)


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

    async def _place_items_unlocked(
        user_id: int,
        item_id: str,
        quantity: int,
        commit: bool = True,
        stars: int = 0,
    ) -> tuple[int, int, int]:
        grid_size = await runtime.get_grid_size(user_id)
        storage_size = await runtime.get_storage_size(user_id)
        temp_size = runtime.temp_storage_size

        async with runtime.db.execute(
            "SELECT slot FROM inventory "
            "WHERE user_id = ? AND location = 'profile'",
            (user_id,),
        ) as c:
            used_profile = {r[0] for r in await c.fetchall()}
        free_profile = [
            s for s in range(grid_size) if s not in used_profile
        ]

        async with runtime.db.execute(
            "SELECT slot FROM inventory "
            "WHERE user_id = ? AND location = 'storage'",
            (user_id,),
        ) as c:
            used_storage = {r[0] for r in await c.fetchall()}
        free_storage = [
            s for s in range(storage_size) if s not in used_storage
        ]

        async with runtime.db.execute(
            "SELECT slot FROM inventory "
            "WHERE user_id = ? AND location = 'temp'",
            (user_id,),
        ) as c:
            used_temp = {r[0] for r in await c.fetchall()}
        free_temp = [
            s for s in range(temp_size) if s not in used_temp
        ]

        total_free = (
            len(free_profile) + len(free_storage) + len(free_temp)
        )
        if total_free < quantity:
            raise ValueError(
                f"Не хватает места: свободно {total_free} "
                f"(энергостанция + хранилище + временное), "
                f"нужно {quantity}."
            )

        to_profile = min(quantity, len(free_profile))
        remaining = quantity - to_profile
        to_storage = min(remaining, len(free_storage))
        to_temp = remaining - to_storage

        for i in range(to_profile):
            await runtime.db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (?, ?, ?, 'profile', ?)",
                (user_id, free_profile[i], item_id, stars),
            )
        for i in range(to_storage):
            await runtime.db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (?, ?, ?, 'storage', ?)",
                (user_id, free_storage[i], item_id, stars),
            )
        for i in range(to_temp):
            await runtime.db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (?, ?, ?, 'temp', ?)",
                (user_id, free_temp[i], item_id, stars),
            )
        await runtime.db.execute(
            "INSERT OR IGNORE INTO player_collection "
            "(user_id, item_id) VALUES (?, ?)",
            (user_id, item_id),
        )
        try:
            await runtime.db.execute(
                "INSERT OR IGNORE INTO player_star_collection "
                "(user_id, item_id, stars) VALUES (?, ?, ?)",
                (user_id, item_id, stars),
            )
        except aiosqlite.OperationalError:
            # Старые схемы могут не иметь таблицы звёздной коллекции.
            pass
        if commit:
            await runtime.commit()
        return to_profile, to_storage, to_temp

    async def place_items(
        user_id: int,
        item_id: str,
        quantity: int,
        commit: bool = True,
        stars: int = 0,
    ) -> tuple[int, int, int]:
        async with runtime.transaction():
            return await _place_items_unlocked(
                user_id,
                item_id,
                quantity,
                commit=commit,
                stars=stars,
            )

    async def grant_item_or_compensation(
        user_id: int,
        item_id: str,
        quantity: int = 1,
        stars: int = 0,
    ) -> tuple[str, int]:
        """Выдаёт предмет. Если места нет — отправляет его в почту."""
        async with runtime.db.execute(
            "SELECT name FROM items WHERE id = ?", (item_id,)
        ) as c:
            row = await c.fetchone()
        name = row[0] if row else item_id

        try:
            await runtime.place_items(
                user_id,
                item_id,
                quantity,
                commit=False,
                stars=stars,
            )
            await runtime.commit()
            return name, 0
        except ValueError:
            await runtime.db.execute(
                "INSERT INTO mailbox "
                "(user_id, item_id, quantity, stars, reason) "
                "VALUES (?, ?, ?, ?, 'no_space')",
                (user_id, item_id, quantity, stars),
            )
            await runtime.commit()
            return (
                f"{name} (нет места — отправлен в почту)",
                0,
            )

    return (
        _reslot_inventory,
        sort_inventory,
        sort_inventory_by,
        get_inventory_rows,
        toggle_item_lock,
        place_items,
        _place_items_unlocked,
        grant_item_or_compensation,
    )
