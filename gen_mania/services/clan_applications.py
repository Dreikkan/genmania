"""Clan application submission and review service."""
from __future__ import annotations

import logging
from typing import Any, Callable

import aiosqlite


class ClanApplicationRuntime:
    """Адаптер между bot.py и сервисом клановых заявок."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self._clan_getter: Callable[[], Callable] = lambda: None
        self._capacity_getter: Callable[[], Callable] = lambda: None
        self._member_count_getter: Callable[[], Callable] = lambda: None
        self._role_getter: Callable[[], Callable] = lambda: None
        self._log_getter: Callable[[], Callable] = lambda: None
        self._permission_getter: Callable[[], Callable] = lambda: None
        self._story_quest_getter: Callable[[], Callable] = lambda: None
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        commit_getter: Callable[[], Callable],
        clan_getter: Callable[[], Callable],
        capacity_getter: Callable[[], Callable],
        member_count_getter: Callable[[], Callable],
        role_getter: Callable[[], Callable],
        log_getter: Callable[[], Callable],
        permission_getter: Callable[[], Callable],
        story_quest_getter: Callable[[], Callable],
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._commit_getter = commit_getter
        self._clan_getter = clan_getter
        self._capacity_getter = capacity_getter
        self._member_count_getter = member_count_getter
        self._role_getter = role_getter
        self._log_getter = log_getter
        self._permission_getter = permission_getter
        self._story_quest_getter = story_quest_getter
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

    async def get_clan(self, user_id: int):
        return await self._clan_getter()(user_id)

    async def get_capacity(self, clan_id: int):
        return await self._capacity_getter()(clan_id)

    async def get_member_count(self, clan_id: int):
        return await self._member_count_getter()(clan_id)

    async def get_role(self, user_id: int, clan_id: int):
        return await self._role_getter()(user_id, clan_id)

    async def log_clan(self, *args, **kwargs) -> None:
        await self._log_getter()(*args, **kwargs)

    def has_permission(self, role: str, action: str) -> bool:
        return self._permission_getter()(role, action)

    async def update_story_quests(self, *args, **kwargs) -> None:
        await self._story_quest_getter()(*args, **kwargs)


def make_clan_application_layer(runtime: ClanApplicationRuntime):
    """Возвращает clan application-функции, привязанные к runtime."""

    async def apply_to_clan(
        user_id: int, clan_id: int
    ) -> tuple[bool, str]:
        if await runtime.get_clan(user_id):
            return False, "Ты уже в клане."
        async with runtime.db.execute(
            "SELECT name FROM clans WHERE id = ?", (clan_id,)
        ) as c:
            clan = await c.fetchone()
        if not clan:
            return False, "Клан уже не существует."
        capacity = await runtime.get_capacity(clan_id)
        members = await runtime.get_member_count(clan_id)
        if members >= capacity:
            return False, "Клан заполнен. Нужно расширить состав."
        async with runtime.db.execute(
            "SELECT status FROM clan_applications "
            "WHERE clan_id = ? AND user_id = ?",
            (clan_id, user_id),
        ) as c:
            row = await c.fetchone()
        if row and row[0] == "pending":
            return False, "Заявка уже отправлена."
        await runtime.db.execute(
            "INSERT INTO clan_applications (clan_id, user_id, status) "
            "VALUES (?, ?, 'pending') "
            "ON CONFLICT(clan_id, user_id) DO UPDATE SET "
            "status = 'pending', created_at = CURRENT_TIMESTAMP",
            (clan_id, user_id),
        )
        await runtime.commit()
        await runtime.log_clan(
            clan_id, "application", f"<@{user_id}>"
        )
        return True, f"Заявка в клан **{clan[0]}** отправлена."

    async def decide_clan_application(
        app_id: int, approve: bool, actor_id: int
    ) -> tuple[bool, str]:
        async with runtime.db.execute(
            "SELECT clan_id, user_id, status "
            "FROM clan_applications WHERE id = ?",
            (app_id,),
        ) as c:
            app = await c.fetchone()
        if not app:
            return False, "Заявка не найдена."
        clan_id, target_id, status = app
        if status != "pending":
            return False, "Заявка уже обработана."
        role = await runtime.get_role(actor_id, clan_id)
        if not runtime.has_permission(role, "invite"):
            return False, "Недостаточно прав."
        if approve:
            try:
                async with runtime.transaction():
                    async with runtime.db.execute(
                        "SELECT status FROM clan_applications "
                        "WHERE id = ?",
                        (app_id,),
                    ) as c:
                        fresh = await c.fetchone()
                    if not fresh or fresh[0] != "pending":
                        raise ValueError(
                            "Заявка уже обработана."
                        )
                    if await runtime.get_clan(target_id):
                        raise ValueError(
                            "Игрок уже состоит в клане."
                        )
                    capacity = await runtime.get_capacity(clan_id)
                    members = await runtime.get_member_count(clan_id)
                    if members >= capacity:
                        raise ValueError(
                            "Клан заполнен. Нужно расширить состав."
                        )
                    await runtime.db.execute(
                        "INSERT INTO clan_members "
                        "(user_id, clan_id, role) "
                        "VALUES (?, ?, 'member')",
                        (target_id, clan_id),
                    )
                    await runtime.db.execute(
                        "UPDATE clan_applications SET status = 'accepted' "
                        "WHERE id = ?",
                        (app_id,),
                    )
                    await runtime.db.execute(
                        "DELETE FROM clan_invites "
                        "WHERE target_id = ?",
                        (target_id,),
                    )
            except (
                ValueError,
                aiosqlite.IntegrityError,
            ) as exc:
                msg = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "Игрок уже состоит в клане."
                )
                return False, msg
            await runtime.log_clan(
                clan_id, "join", f"<@{target_id}> (заявка)"
            )
            await runtime.update_story_quests(
                target_id, "clan_join", 1
            )
            return True, f"✅ <@{target_id}> принят в клан."
        await runtime.db.execute(
            "UPDATE clan_applications SET status = 'declined' "
            "WHERE id = ?",
            (app_id,),
        )
        await runtime.commit()
        await runtime.log_clan(
            clan_id, "application_declined", f"<@{target_id}>"
        )
        return True, f"❌ Заявка <@{target_id}> отклонена."

    return apply_to_clan, decide_clan_application
