"""Guild access snapshots (owner, roles, permissions)."""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

import discord


class GuildAccessRuntime:
    """Адаптер между bot.py и сервисом доступа к серверам."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._settings_getter: Callable[[], Callable] = lambda: None
        self._role_admin_predicate: Callable[[Any], bool] = (
            lambda role: False
        )
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        settings_getter: Callable[[], Callable],
        role_admin_predicate: Callable[[Any], bool],
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._settings_getter = settings_getter
        self._role_admin_predicate = role_admin_predicate
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    async def get_settings(self, guild_id: int):
        return await self._settings_getter()(guild_id)

    def role_is_admin(self, role) -> bool:
        return self._role_admin_predicate(role)


def make_guild_access_layer(runtime: GuildAccessRuntime):
    """Возвращает функции снимка доступа, привязанные к runtime."""

    async def sync_guild_access(guild, reason: str = "join"):
        """Считывает владельца, роли и права бота при заходе на сервер."""
        guild_id = getattr(guild, "id", None)
        if guild_id is None:
            return None
        try:
            async with runtime.transaction():
                await runtime.db.execute(
                    "INSERT OR IGNORE INTO guild_settings "
                    "(guild_id) VALUES (?)",
                    (guild_id,),
                )
        except Exception:
            runtime.logger.exception(
                "GUILD_ACCESS: не удалось создать настройки %s",
                guild_id,
            )
        try:
            settings = await runtime.get_settings(guild_id)
        except Exception:
            settings = {}

        owner_id = getattr(guild, "owner_id", None)
        owner = getattr(guild, "owner", None)
        if owner is None and owner_id is not None:
            fetch_member = getattr(guild, "fetch_member", None)
            if fetch_member is not None:
                try:
                    owner = await fetch_member(owner_id)
                except (
                    discord.NotFound,
                    discord.Forbidden,
                    discord.HTTPException,
                    AttributeError,
                    TypeError,
                ):
                    owner = None
        owner_name = (
            getattr(owner, "display_name", None)
            or getattr(owner, "name", None)
            or ""
        )

        roles = list(getattr(guild, "roles", ()) or ())
        roles_data = [
            {
                "id": getattr(role, "id", None),
                "name": str(getattr(role, "name", "")),
                "position": int(getattr(role, "position", 0) or 0),
                "administrator": runtime.role_is_admin(role),
                "permissions": int(
                    getattr(
                        getattr(role, "permissions", None),
                        "value",
                        0,
                    )
                    or 0
                ),
            }
            for role in roles
        ]
        admin_role_ids = [
            item["id"]
            for item in roles_data
            if item["administrator"] and item["id"] is not None
        ]
        admin_role_id = settings.get("admin_role_id")
        admin_role_name = next(
            (
                item["name"]
                for item in roles_data
                if item["id"] == admin_role_id
            ),
            None,
        )
        bot_member = getattr(guild, "me", None)
        bot_permissions = int(
            getattr(
                getattr(bot_member, "guild_permissions", None),
                "value",
                0,
            )
            or 0
        )
        member_count = int(getattr(guild, "member_count", 0) or 0)

        try:
            async with runtime.transaction():
                await runtime.db.execute(
                    """
                    INSERT INTO guild_access
                        (guild_id, owner_id, owner_name, admin_role_id,
                         admin_role_name, admin_role_ids, roles_json,
                         member_count, bot_permissions, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                            CURRENT_TIMESTAMP)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        owner_id = excluded.owner_id,
                        owner_name = excluded.owner_name,
                        admin_role_id = excluded.admin_role_id,
                        admin_role_name = excluded.admin_role_name,
                        admin_role_ids = excluded.admin_role_ids,
                        roles_json = excluded.roles_json,
                        member_count = excluded.member_count,
                        bot_permissions = excluded.bot_permissions,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        guild_id,
                        owner_id,
                        owner_name,
                        admin_role_id,
                        admin_role_name,
                        json.dumps(admin_role_ids),
                        json.dumps(roles_data, ensure_ascii=False),
                        member_count,
                        bot_permissions,
                    ),
                )
        except Exception:
            runtime.logger.exception(
                "GUILD_ACCESS: не удалось сохранить снимок %s",
                guild_id,
            )

        snapshot = {
            "guild_id": guild_id,
            "owner_id": owner_id,
            "owner_name": owner_name,
            "admin_role_id": admin_role_id,
            "admin_role_name": admin_role_name,
            "admin_role_ids": admin_role_ids,
            "role_count": len(roles_data),
            "member_count": member_count,
            "bot_permissions": bot_permissions,
        }
        runtime.logger.info(
            "GUILD_ACCESS: guild=%s owner=%s admin_roles=%s roles=%s "
            "reason=%s",
            guild_id,
            owner_id,
            admin_role_ids,
            len(roles_data),
            reason,
        )
        return snapshot

    return sync_guild_access
