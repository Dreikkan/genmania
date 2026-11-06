"""Holiday advent calendar state, opening and embed."""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable


class AdventRuntime:
    """Адаптер между bot.py и сервисом адвента."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._grant_item_getter: Callable[[], Callable] = lambda: None
        self._achievements_getter: Callable[[], Callable] = lambda: None
        self._parse_time_getter: Callable[[], Callable] = lambda: None
        self._event_getter: Callable[[], Callable] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self.rewards: dict = {}
        self.page_size = 6
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        grant_item_getter: Callable[[], Callable],
        achievements_getter: Callable[[], Callable],
        parse_time_getter: Callable[[], Callable],
        event_getter: Callable[[], Callable],
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        rewards: dict,
        page_size: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._grant_item_getter = grant_item_getter
        self._achievements_getter = achievements_getter
        self._parse_time_getter = parse_time_getter
        self._event_getter = event_getter
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self.rewards = rewards
        self.page_size = page_size
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    async def grant_item(self, *args, **kwargs):
        return await self._grant_item_getter()(*args, **kwargs)

    async def check_achievements(self, user_id: int):
        return await self._achievements_getter()(user_id)

    def parse_db_time(self, value):
        return self._parse_time_getter()(value)

    def active_event(self):
        return self._event_getter()()

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    async def fix_emojis(self, embed):
        return await self._emoji_fixer(embed)


def make_advent_layer(runtime: AdventRuntime):
    """Возвращает функции адвента, привязанные к runtime."""

    async def get_advent_state(user_id: int) -> tuple:
        """Возвращает (last_opened_day, last_opened_date, event_key)."""
        async with runtime.db.execute(
            "SELECT last_opened_day, last_opened_date, event_key "
            "FROM advent_state WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            return 0, None, None
        return row[0] or 0, row[1], row[2]

    async def get_advent_opened(user_id: int) -> set:
        """Возвращает set открытых дней текущего события."""
        event, _day = runtime.active_event()
        if not event:
            return set()
        _last_day, _last_date, event_key = await get_advent_state(
            user_id
        )
        if event_key != event["key"]:
            return set()
        async with runtime.db.execute(
            "SELECT day FROM advent_progress WHERE user_id = ?",
            (user_id,),
        ) as c:
            return {r[0] for r in await c.fetchall()}

    async def can_open_advent_today(user_id: int) -> tuple[bool, str]:
        """Проверяет, можно ли открыть окошко сегодня."""
        event, _day = runtime.active_event()
        if not event:
            return (
                False,
                "Сейчас нет активного праздничного календаря.",
            )
        last_day, last_date, event_key = await get_advent_state(
            user_id
        )
        if event_key == event["key"] and last_day >= event["days"]:
            return (
                False,
                f"{event['emoji']} Все окошки события уже открыты!",
            )
        last = runtime.parse_db_time(last_date)
        if last and (
            datetime.date.today() - last.date()
        ).days < 1:
            return (
                False,
                "⏳ Ты уже открывал окошко сегодня. "
                "Возвращайся завтра!",
            )
        return True, ""

    async def open_advent_day(user_id: int, day: int) -> tuple:
        """Открывает окошко активного праздничного события."""
        event, _current_day = runtime.active_event()
        if not event:
            return (
                False,
                "🎄 Сейчас нет активного праздничного календаря.",
                {},
            )
        if day < 1 or day > event["days"]:
            return (
                False,
                f"❌ В этом событии доступны дни 1–{event['days']}.",
                {},
            )

        try:
            async with runtime.transaction():
                (
                    last_day,
                    last_date,
                    event_key,
                ) = await get_advent_state(user_id)
                if event_key != event["key"]:
                    await runtime.db.execute(
                        "DELETE FROM advent_progress "
                        "WHERE user_id = ?",
                        (user_id,),
                    )
                    last_day = 0
                    last_date = None

                if last_day >= event["days"]:
                    raise ValueError(
                        f"❌ {event['emoji']} Все окошки события "
                        "уже открыты!"
                    )
                last_date_value = runtime.parse_db_time(last_date)
                if last_date_value:
                    if (
                        datetime.date.today()
                        - last_date_value.date()
                    ).days < 1:
                        raise ValueError(
                            "⏳ Ты уже открывал окошко сегодня. "
                            "Возвращайся завтра!"
                        )
                async with runtime.db.execute(
                    "SELECT 1 FROM advent_progress "
                    "WHERE user_id = ? AND day = ?",
                    (user_id, day),
                ) as c:
                    if await c.fetchone():
                        raise ValueError(
                            "❌ Это окошко уже открыто."
                        )
                if day != last_day + 1:
                    raise ValueError(
                        f"❌ Сейчас можно открыть только окошко "
                        f"**{last_day + 1}**."
                    )

                coins, gems, item_id = runtime.rewards[day]
                await runtime.db.execute(
                    "UPDATE players SET coins = coins + ?, "
                    "gems = gems + ?, "
                    "total_coins_earned = total_coins_earned + ?, "
                    "lifetime_production = lifetime_production + ?, "
                    "total_gems_earned = total_gems_earned + ? "
                    "WHERE user_id = ?",
                    (coins, gems, coins, coins, gems, user_id),
                )

                item_name = None
                if item_id:
                    item_name, _ = await runtime.grant_item(
                        user_id, item_id, 1
                    )

                today_str = datetime.date.today().isoformat()
                await runtime.db.execute(
                    "INSERT INTO advent_progress (user_id, day) "
                    "VALUES (?, ?)",
                    (user_id, day),
                )
                await runtime.db.execute(
                    """
                    INSERT INTO advent_state
                        (user_id, last_opened_day, last_opened_date,
                         event_key)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        last_opened_day = ?,
                        last_opened_date = ?,
                        event_key = ?
                    """,
                    (
                        user_id,
                        day,
                        today_str,
                        event["key"],
                        day,
                        today_str,
                        event["key"],
                    ),
                )
        except ValueError as exc:
            return False, str(exc), {}

        await runtime.check_achievements(user_id)

        return (
            True,
            f"🎁 Окошко **{day}** открыто!",
            {
                "day": day,
                "coins": coins,
                "gems": gems,
                "item": item_name,
            },
        )

    async def build_advent_embed(interaction, page: int = 0):
        event, _current_day = runtime.active_event()
        if not event:
            embed = runtime.embed(
                title="🎄 Праздничный календарь",
                description=(
                    "Сейчас нет активного события. Календарь "
                    "открывается на праздники: зимние праздники, "
                    "Хэллоуин, майские, 23 февраля и 8 Марта."
                ),
                color=0xE74C3C,
            )
            return await runtime.fix_emojis(embed)
        event_days = event["days"]
        user_id = interaction.user.id
        opened = await get_advent_opened(user_id)
        last_day, _last_date, event_key = await get_advent_state(
            user_id
        )
        if event_key != event["key"]:
            last_day = 0

        can_today, reason = await can_open_advent_today(user_id)
        next_day = last_day + 1
        total_pages = max(
            1,
            (event_days + runtime.page_size - 1)
            // runtime.page_size,
        )
        page = max(0, min(page, total_pages - 1))
        start_day = page * runtime.page_size + 1
        end_day = min(
            start_day + runtime.page_size - 1, event_days
        )

        embed = runtime.embed(
            title=f"{event['emoji']} {event['name']}",
            description=(
                f"Открыто: **{len(opened)}/{event_days}**\n"
                f"Следующее окошко: "
                f"**{next_day if next_day <= event_days else '—'}**\n"
                + (
                    "✅ Можно открыть!"
                    if can_today
                    else f"⏳ {reason}"
                )
            ),
            color=0xE74C3C,
        )

        lines = []
        for day in range(start_day, end_day + 1):
            if day in opened:
                lines.append(f"✅ **{day}**")
            elif day == next_day and can_today:
                lines.append(f"🎁 **{day}**")
            else:
                lines.append(f"🔒 {day}")

        grid = ""
        for i in range(0, len(lines), 6):
            grid += "  ".join(lines[i:i + 6]) + "\n"
        embed.add_field(
            name=f"Окошки {start_day}–{end_day}",
            value=grid or "—",
            inline=False,
        )

        if next_day <= event_days:
            c, g, it = runtime.rewards.get(
                next_day, (50, 1, None)
            )
            reward_str = f"🪙 {c} | 💎 {g}"
            if it:
                reward_str += f" | 🎁 {it}"
            embed.add_field(
                name=f"Награда за окошко {next_day}",
                value=reward_str,
                inline=False,
            )

        embed.set_footer(
            text=f"Страница {page + 1}/{total_pages}"
        )
        return await runtime.fix_emojis(embed)

    return (
        get_advent_state,
        get_advent_opened,
        can_open_advent_today,
        open_advent_day,
        build_advent_embed,
    )
