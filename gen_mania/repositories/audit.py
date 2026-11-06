"""Admin audit log repository."""
from __future__ import annotations

import logging
from typing import Any, Callable


class AuditRuntime:
    """Адаптер между bot.py и журналом админ-действий."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self._guild_context_getter: Callable[[], Any] = lambda: None
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        commit_getter: Callable[[], Callable],
        guild_context_getter: Callable[[], Any],
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._commit_getter = commit_getter
        self._guild_context_getter = guild_context_getter
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    async def commit(self) -> None:
        commit = self._commit_getter()
        if commit is not None:
            await commit()

    def current_guild_id(self):
        return self._guild_context_getter()


def make_audit_layer(runtime: AuditRuntime):
    """Возвращает функции записи и чтения admin_log."""

    async def log_admin_action(
        admin_id: int,
        target_id: int,
        action: str,
        details: str = "",
        guild_id: int | None = None,
    ):
        if guild_id is None:
            guild_id = runtime.current_guild_id()
        await runtime.db.execute(
            "INSERT INTO admin_log "
            "(admin_id, target_id, guild_id, action, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (admin_id, target_id, guild_id, action, details),
        )
        await runtime.commit()

    async def get_admin_logs_page(
        guild_id: int | None,
        page: int = 0,
        page_size: int = 10,
    ):
        where = ""
        params: list = []
        if guild_id:
            where = "WHERE guild_id = ? OR guild_id IS NULL"
            params.append(guild_id)

        async with runtime.db.execute(
            f"SELECT COUNT(*) FROM admin_log {where}", params
        ) as c:
            total = (await c.fetchone())[0]

        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))

        async with runtime.db.execute(
            f"SELECT admin_id, target_id, action, details, timestamp, "
            f"guild_id FROM admin_log {where} "
            f"ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, page_size, page * page_size),
        ) as c:
            rows = await c.fetchall()

        return rows, total, page, total_pages

    return log_admin_action, get_admin_logs_page
