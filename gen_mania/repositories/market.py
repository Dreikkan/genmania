"""Market price history repository."""
from __future__ import annotations

import logging
from typing import Any, Callable


class MarketRuntime:
    """Адаптер между bot.py и репозиторием рынка."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        commit_getter: Callable[[], Callable],
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._commit_getter = commit_getter
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    async def commit(self) -> None:
        commit = self._commit_getter()
        if commit is not None:
            await commit()


def make_market_layer(runtime: MarketRuntime):
    """Возвращает market-функции, привязанные к runtime."""

    async def record_market_price(
        item_id: str,
        price: int,
        demand: int = 0,
        supply: int = 0,
        commit: bool = True,
    ):
        await runtime.db.execute(
            "INSERT INTO market_history (item_id, price, demand, supply) "
            "VALUES (?, ?, ?, ?)",
            (item_id, int(price), int(demand), int(supply)),
        )
        await runtime.db.execute(
            "DELETE FROM market_history WHERE item_id = ? AND id NOT IN ("
            "SELECT id FROM market_history WHERE item_id = ? "
            "ORDER BY id DESC LIMIT 50)",
            (item_id, item_id),
        )
        if commit:
            await runtime.commit()

    return (record_market_price,)
