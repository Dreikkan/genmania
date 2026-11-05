"""Managed SQLite transactions and commit/rollback helpers.

``bot.py`` creates its own ``TransactionRuntime`` and binds a transaction
layer to it. This keeps multiple imported bot modules (tests import bot.py
under unique names) isolated from each other.
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Callable

import aiosqlite


class TransactionRuntime:
    """Адаптер между bot.py и транзакционным слоем."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._lock_getter: Callable[[], Any] = asyncio.Lock
        self._owner_getter: Callable[[], Any] = lambda: None
        self._owner_setter: Callable[[Any], None] = lambda owner: None
        self.metrics: Any = None
        self.slow_ms: float = 100.0
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        lock_getter: Callable[[], Any],
        owner_getter: Callable[[], Any],
        owner_setter: Callable[[Any], None],
        metrics: Any,
        slow_ms: float,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._lock_getter = lock_getter
        self._owner_getter = owner_getter
        self._owner_setter = owner_setter
        self.metrics = metrics
        self.slow_ms = slow_ms
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    @property
    def lock(self):
        return self._lock_getter()

    @property
    def owner(self):
        return self._owner_getter()

    def set_owner(self, owner) -> None:
        self._owner_setter(owner)

    def record_db_tx(self, duration_ms: float, ok: bool = True) -> None:
        if self.metrics is not None:
            self.metrics.record_db_tx(duration_ms, ok=ok)

    def log_slow(self, duration_ms: float) -> None:
        if duration_ms >= self.slow_ms:
            self.logger.warning("SLOW_DB_TX: %.1f ms", duration_ms)


def make_transaction_layer(runtime: TransactionRuntime):
    """Возвращает (db_transaction, commit_if_needed, rollback_if_needed)."""

    def _managed_tx_owner_is_self() -> bool:
        try:
            current = asyncio.current_task()
        except RuntimeError:
            return False
        owner = runtime.owner
        return owner is not None and owner is current

    async def commit_if_needed() -> None:
        """Коммитит только вне managed-транзакции текущей задачи."""
        if _managed_tx_owner_is_self():
            return
        if runtime.owner is not None:
            async with runtime.lock:
                await runtime.db.commit()
            return
        await runtime.db.commit()

    async def rollback_if_needed() -> None:
        """Откатывает только вне managed-транзакции текущей задачи."""
        if _managed_tx_owner_is_self():
            return
        if runtime.owner is not None:
            async with runtime.lock:
                await runtime.db.rollback()
            return
        await runtime.db.rollback()

    @asynccontextmanager
    async def db_transaction():
        """Контекстный менеджер для транзакций SQLite.

        Внешняя транзакция сериализуется writer-lock'ом и всегда
        завершается COMMIT/ROLLBACK. Вложенные вызовы используют
        SAVEPOINT.
        """
        current = asyncio.current_task()
        db = runtime.db
        if runtime.owner is current:
            await db.execute("SAVEPOINT gen_mania_sp")
            try:
                yield
                await db.execute("RELEASE SAVEPOINT gen_mania_sp")
            except BaseException:
                await db.execute("ROLLBACK TO SAVEPOINT gen_mania_sp")
                await db.execute("RELEASE SAVEPOINT gen_mania_sp")
                raise
            return

        async with runtime.lock:
            tx_started = time.perf_counter()
            db = runtime.db
            # После исправления get_settings() это не должно срабатывать.
            # Оставляем защиту от старых незакоммиченных DML.
            if db.in_transaction:
                runtime.logger.debug(
                    "Найдена незавершённая транзакция перед BEGIN — коммитим"
                )
                await db.commit()

            # Сырые DML-вызовы вне db_transaction могут открыть неявную
            # транзакцию между проверкой in_transaction и BEGIN. Повторяем
            # BEGIN после коммита, чтобы не падать на гонке.
            for attempt in range(3):
                try:
                    await db.execute("BEGIN IMMEDIATE")
                    break
                except aiosqlite.OperationalError as exc:
                    if (
                        "cannot start a transaction within a transaction"
                        not in str(exc)
                        or attempt == 2
                    ):
                        raise
                    runtime.logger.warning(
                        "db_transaction: гонка с незавершённой транзакцией, "
                        "коммитим и повторяем BEGIN"
                    )
                    await db.commit()
            runtime.set_owner(current)
            tx_ok = True
            try:
                yield
                await db.commit()
            except BaseException:
                tx_ok = False
                await db.rollback()
                raise
            finally:
                runtime.set_owner(None)
                elapsed_ms = (time.perf_counter() - tx_started) * 1000
                runtime.record_db_tx(elapsed_ms, ok=tx_ok)
                runtime.log_slow(elapsed_ms)

    return db_transaction, commit_if_needed, rollback_if_needed
