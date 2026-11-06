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
        self._parse_db_time_getter: Callable[[], Callable] = lambda: None
        self._price_formatter: Callable[[int], str] = str
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self._now_getter: Callable[[], Any] = datetime.datetime.now
        self.notification_types: dict = {}
        self.cooldown_hours: dict = {}
        self.pet_max_level = 10
        self.pet_feed_cooldown_hours = 6
        self.autocollect_levels: dict = {}
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        commit_getter: Callable[[], Callable],
        bot_getter: Callable[[], Any],
        parse_db_time_getter: Callable[[], Callable],
        price_formatter: Callable[[int], str],
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        now_getter: Callable[[], Any],
        notification_types: dict,
        cooldown_hours: dict,
        pet_max_level: int,
        pet_feed_cooldown_hours: int,
        autocollect_levels: dict,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._commit_getter = commit_getter
        self._bot_getter = bot_getter
        self._parse_db_time_getter = parse_db_time_getter
        self._price_formatter = price_formatter
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self._now_getter = now_getter
        self.notification_types = notification_types
        self.cooldown_hours = cooldown_hours
        self.pet_max_level = pet_max_level
        self.pet_feed_cooldown_hours = pet_feed_cooldown_hours
        self.autocollect_levels = autocollect_levels
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

    def parse_db_time(self, value):
        return self._parse_db_time_getter()(value)

    def format_price(self, value: int) -> str:
        return self._price_formatter(value)

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    async def fix_emojis(self, embed):
        return await self._emoji_fixer(embed)

    def now(self):
        return self._now_getter()


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

    async def build_notification_center_embed(user_id: int):
        now = runtime.now()
        lines: list[str] = []

        async with runtime.db.execute(
            "SELECT last_daily FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        last_daily = runtime.parse_db_time(row[0]) if row else None
        if not last_daily or last_daily.date() != now.date():
            lines.append(
                "🎁 **Дейли доступен** — забери награду в главном меню."
            )

        async with runtime.db.execute(
            "SELECT up.level, up.last_fed FROM user_pets_v2 up "
            "JOIN players p ON p.active_pet = up.pet_id "
            "WHERE p.user_id = ?",
            (user_id,),
        ) as c:
            pet = await c.fetchone()
        if pet:
            level, last_fed = pet
            fed = runtime.parse_db_time(last_fed)
            if level < runtime.pet_max_level and (
                not fed
                or (now - fed).total_seconds()
                >= runtime.pet_feed_cooldown_hours * 3600
            ):
                lines.append(
                    "🐾 **Питомец голоден** — покорми в «Питомцах»."
                )

        async with runtime.db.execute(
            "SELECT amount, due_time FROM bank_loans "
            "WHERE user_id = ? AND COALESCE(status, 'active') = 'active'",
            (user_id,),
        ) as c:
            loan = await c.fetchone()
        if loan:
            amount, due_time = loan
            due = runtime.parse_db_time(due_time)
            if due:
                left = (due - now).total_seconds()
                if left <= 0:
                    lines.append(
                        "🏦 **Кредит просрочен** — залог может быть "
                        "потерян."
                    )
                elif left <= 24 * 3600:
                    lines.append(
                        f"🏦 **Кредит** {runtime.format_price(amount)} — "
                        f"осталось {max(1, int(left // 3600))} ч."
                    )

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM market_orders WHERE user_id = ? "
            "AND status = 'active' AND expires_at <= ?",
            (user_id, (now + datetime.timedelta(hours=2)).isoformat()),
        ) as c:
            expiring_orders = (await c.fetchone())[0] or 0
        if expiring_orders:
            lines.append(
                f"📋 **Ордера биржи**: {expiring_orders} истекают "
                "в ближайшие 2 ч."
            )

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM auctions WHERE status = 'active' "
            "AND (seller_id = ? OR current_bidder = ?) AND end_time <= ?",
            (
                user_id,
                user_id,
                (now + datetime.timedelta(hours=6)).isoformat(),
            ),
        ) as c:
            ending_auctions = (await c.fetchone())[0] or 0
        if ending_auctions:
            lines.append(
                f"🏛️ **Аукцион**: {ending_auctions} лотов "
                "заканчиваются в ближайшие 6 ч."
            )

        async with runtime.db.execute(
            "SELECT level, last_auto FROM autocollectors "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            autoc = await c.fetchone()
        if autoc:
            level, last_auto = autoc
            interval = runtime.autocollect_levels.get(level, (0, 4))[1]
            last = runtime.parse_db_time(last_auto)
            if (
                not last
                or (now - last).total_seconds() >= interval * 3600
            ):
                lines.append(
                    "🤖 **Автосборщик готов** — доход можно забрать."
                )

        embed = runtime.embed(
            title="🔔 Центр уведомлений",
            description="Актуальные события твоей энергостанции.",
            color=0x3498DB,
        )
        if lines:
            embed.description = "\n\n".join(lines)
        else:
            embed.description = "✅ Всё спокойно: срочных событий нет."
        return await runtime.fix_emojis(embed)

    return (
        get_notifications,
        set_notification,
        can_send_notification,
        mark_notification_sent,
        send_dm_notification,
        build_notification_center_embed,
    )
