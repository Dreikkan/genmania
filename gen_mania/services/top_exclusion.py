"""Top leaderboard exclusion for self-granted admin rewards."""
from __future__ import annotations

import logging
from typing import Any, Callable

import discord


class TopExclusionRuntime:
    """Адаптер между bot.py и сервисом исключения из топов."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self._cache_clear: Callable[[], None] = lambda: None
        self._audit_getter: Callable[[], Callable] = lambda: None
        self.notice = ""
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        commit_getter: Callable[[], Callable],
        cache_clear: Callable[[], None],
        audit_getter: Callable[[], Callable],
        notice: str,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._commit_getter = commit_getter
        self._cache_clear = cache_clear
        self._audit_getter = audit_getter
        self.notice = notice
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    async def commit(self) -> None:
        commit = self._commit_getter()
        if commit is not None:
            await commit()

    def clear_cache(self) -> None:
        self._cache_clear()

    async def log_admin_action(self, *args, **kwargs) -> None:
        await self._audit_getter()(*args, **kwargs)


def make_top_exclusion_layer(runtime: TopExclusionRuntime):
    """Возвращает ``enforce_top_exclusion``, привязанный к runtime."""

    async def enforce_top_exclusion(
        interaction: discord.Interaction,
        target_id: int,
        reason: str,
    ) -> bool:
        """Исключает админа/владельца из топов после выдачи себе."""
        if target_id != interaction.user.id:
            return False
        cur = await runtime.db.execute(
            "UPDATE players SET top_excluded = 1 "
            "WHERE user_id = ? AND COALESCE(top_excluded, 0) = 0",
            (target_id,),
        )
        await runtime.commit()
        runtime.clear_cache()
        if cur.rowcount == 0:
            return False
        await runtime.log_admin_action(
            target_id,
            target_id,
            "top_exclusion",
            reason,
            guild_id=getattr(interaction, "guild_id", None),
        )
        try:
            await interaction.followup.send(
                runtime.notice, ephemeral=True
            )
        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
        ):
            pass
        return True

    return enforce_top_exclusion
