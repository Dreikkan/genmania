"""User notification preferences and DM delivery."""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Callable

import discord


class NotificationRuntime:
    """Адаптер между bot.py и сервисом уведомлений."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self._bot_getter: Callable[[], Any] = lambda: None
        self.notification_types: dict = {}
        self.cooldown_hours: dict = {}
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        commit_getter: Callable[[], Callable],
        bot_getter: Callable[[], Any],
        notification_types: dict,
        cooldown_hours: dict,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._commit_getter = commit_getter
        self._bot_getter = bot_getter
        self.notification_types = notification_types
        self.cooldown_hours = cooldown_hours
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    @property
    def bot(self):
        return self._bot_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    async def commit(self) -> None:
        commit = self._commit_getter()
        if commit is not None:
            await commit()


def make_notification_layer(runtime: NotificationRuntime):
    """Возвращает notification-функции, привязанные к runtime."""

    async def get_notifications(user_id: int) -> dict:
        """Возвращает настройки уведомлений; по умолчанию включены."""
        async with runtime.db.execute(
            "SELECT notif_type, enabled, last_sent "
            "FROM user_notifications WHERE user_id = ?",
            (user_id,),
        ) as c:
            rows = await c.fetchall()

        result = {
            t: (1, None) for t in runtime.notification_types
        }
        for ntype, enabled, last_sent in rows:
            result[ntype] = (enabled, last_sent)
        return result

    async def set_notification(
        user_id: int, notif_type: str, enabled: bool
    ):
        """Включает/выключает уведомление. Создаёт запись, если её нет."""
        if notif_type not in runtime.notification_types:
            return
        await runtime.db.execute(
            """
            INSERT INTO user_notifications
                (user_id, notif_type, enabled)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, notif_type) DO UPDATE SET enabled = ?
            """,
            (user_id, notif_type, int(enabled), int(enabled)),
        )
        await runtime.commit()

    async def can_send_notification(
        user_id: int, notif_type: str
    ) -> bool:
        """Проверяет, включено ли уведомление и прошёл ли кулдаун."""
        async with runtime.db.execute(
            "SELECT enabled, last_sent FROM user_notifications "
            "WHERE user_id = ? AND notif_type = ?",
            (user_id, notif_type),
        ) as c:
            row = await c.fetchone()

        if not row:
            return True

        enabled, last_sent = row
        if not enabled:
            return False

        if last_sent:
            last = datetime.datetime.fromisoformat(last_sent)
            cooldown = runtime.cooldown_hours.get(notif_type, 24)
            if (
                datetime.datetime.now() - last
            ).total_seconds() < cooldown * 3600:
                return False
        return True

    async def mark_notification_sent(
        user_id: int, notif_type: str
    ):
        """Отмечает, что уведомление отправлено."""
        now_iso = datetime.datetime.now().isoformat()
        async with runtime.transaction():
            await runtime.db.execute(
                """
                INSERT INTO user_notifications
                    (user_id, notif_type, enabled, last_sent)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, notif_type)
                DO UPDATE SET last_sent = ?
                """,
                (user_id, notif_type, now_iso, now_iso),
            )

    async def send_dm_notification(
        user_id: int,
        notif_type: str,
        text: str,
        embed=None,
    ) -> bool:
        """Пытается отправить ЛС. False при Forbidden/NotFound."""
        try:
            user = runtime.bot.get_user(user_id)
            if user is None:
                user = await runtime.bot.fetch_user(user_id)
            if user is None:
                return False

            if embed:
                await user.send(embed=embed)
            else:
                await user.send(text)
            await mark_notification_sent(user_id, notif_type)
            # мягкий throttle, чтобы не ловить rate limit
            await asyncio.sleep(0.25)
            return True
        except discord.Forbidden:
            title = runtime.notification_types.get(
                notif_type, (notif_type, "")
            )[0]
            body = text or (
                embed.description if embed else ""
            )
            async with runtime.transaction():
                await runtime.db.execute(
                    "DELETE FROM notification_fallback "
                    "WHERE user_id = ? AND notif_type = ?",
                    (user_id, notif_type),
                )
                await runtime.db.execute(
                    "INSERT INTO notification_fallback "
                    "(user_id, notif_type, title, body) "
                    "VALUES (?, ?, ?, ?)",
                    (user_id, notif_type, title, body[:1000]),
                )
            return False
        except discord.NotFound:
            return False
        except discord.HTTPException:
            return False

    return (
        get_notifications,
        set_notification,
        can_send_notification,
        mark_notification_sent,
        send_dm_notification,
    )
