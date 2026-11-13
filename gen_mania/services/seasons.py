"""Season and battle-pass progression service."""
from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Callable


class SeasonRuntime:
    """Адаптер между bot.py и сезонным сервисом."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self._settings_getter: Callable[[], Callable] = lambda: None
        self._achievements_getter: Callable[[], Callable] = lambda: None
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._today_str_getter: Callable[[], Callable] = lambda: None
        self._weekend_mult_getter: Callable[[], float] = lambda: 1.0
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self.month_names = ()
        self.xp_actions: dict = {}
        self.xp_base = 300
        self.xp_step = 90
        self.levels = 30
        self.premium_cost_gems = 500
        self.coin = "🪙"
        self.gem = "💎"
        self.season_total_xp_text = ""
        self.season_xp_help_lines: tuple = ()
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        commit_getter: Callable[[], Callable],
        settings_getter: Callable[[], Callable],
        achievements_getter: Callable[[], Callable],
        emoji_getter: Callable[[], Callable],
        today_str_getter: Callable[[], Callable],
        weekend_mult_getter: Callable[[], float],
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        season_total_xp_text: str,
        season_xp_help_lines: tuple,
        month_names,
        xp_actions: dict,
        xp_base: int,
        xp_step: int,
        levels: int,
        premium_cost_gems: int,
        coin: str,
        gem: str,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._commit_getter = commit_getter
        self._settings_getter = settings_getter
        self._achievements_getter = achievements_getter
        self._emoji_getter = emoji_getter
        self._today_str_getter = today_str_getter
        self._weekend_mult_getter = weekend_mult_getter
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self.month_names = month_names
        self.xp_actions = xp_actions
        self.xp_base = xp_base
        self.xp_step = xp_step
        self.levels = levels
        self.premium_cost_gems = premium_cost_gems
        self.coin = coin
        self.gem = gem
        self.season_total_xp_text = season_total_xp_text
        self.season_xp_help_lines = season_xp_help_lines
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

    async def get_settings(self, guild_id: int):
        return await self._settings_getter()(guild_id)

    async def check_achievements(self, user_id: int):
        return await self._achievements_getter()(user_id)

    def emoji(self, key: str):
        return self._emoji_getter()(key)

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    async def fix_emojis(self, embed):
        return await self._emoji_fixer(embed)

    def today_str(self) -> str:
        return self._today_str_getter()()

    @property
    def weekend_mult(self) -> float:
        return self._weekend_mult_getter()


def make_season_layer(runtime: SeasonRuntime):
    """Возвращает season-функции, привязанные к runtime."""

    def current_season_id() -> str:
        return datetime.date.today().strftime("%Y-%m")

    def current_season_name() -> str:
        today = datetime.date.today()
        return f"{runtime.month_names[today.month - 1]} {today.year}"

    def season_days_left() -> int:
        today = datetime.date.today()
        if today.month == 12:
            last_day = datetime.date(today.year, 12, 31)
        else:
            last_day = (
                datetime.date(today.year, today.month + 1, 1)
                - datetime.timedelta(days=1)
            )
        return max(0, (last_day - today).days + 1)

    def season_event_multiplier() -> float:
        return (
            runtime.weekend_mult
            if datetime.date.today().weekday() >= 5
            else 1.0
        )

    def season_event_label() -> str | None:
        if season_event_multiplier() > 1:
            return "Выходные: +50% сезонного XP"
        return None

    def season_xp_for_next_level(level: int) -> int:
        return runtime.xp_base + max(0, level) * runtime.xp_step

    def season_level_from_xp(xp: int) -> tuple[int, int]:
        xp = max(0, int(xp or 0))
        level = 0
        remaining = xp
        while level < runtime.levels:
            need = season_xp_for_next_level(level)
            if remaining < need:
                break
            remaining -= need
            level += 1
        return level, remaining

    def season_progress_bar(
        remaining: int, needed: int, width: int = 10
    ) -> str:
        if needed <= 0:
            return "▰" * width
        filled = max(0, min(width, int(width * remaining / needed)))
        return "▰" * filled + "▱" * (width - filled)

    def season_reward(level: int, premium: bool = False) -> dict:
        """Награды выровнены по стоимости уровней (+100 XP за уровень)."""
        coins = 150 + level * 55
        gems = 0
        catalysts = 0
        if premium:
            # Итого 220 премиум-гемов за 30 уровней.
            gems = 2 + level // 3 + (1 if level >= 16 else 0)
            if level % 5 == 0:
                catalysts = 1
        else:
            if level % 5 == 0:
                gems = 5 + level // 5
            if level % 10 == 0:
                catalysts = 1
        return {
            "coins": coins,
            "gems": gems,
            "catalysts": catalysts,
        }

    def season_reward_text(
        level: int, premium: bool = False
    ) -> str:
        reward = season_reward(level, premium)
        parts = [f"🪙 {reward['coins']}"]
        if reward["gems"]:
            parts.append(f"💎 {reward['gems']}")
        if reward["catalysts"]:
            parts.append(f"🧪 {reward['catalysts']}")
        return " | ".join(parts)

    def _parse_season_claimed(raw) -> set[int]:
        try:
            return {int(value) for value in json.loads(raw or "[]")}
        except Exception:
            return set()

    async def get_season_data(user_id: int) -> dict:
        season_id = current_season_id()
        await runtime.db.execute(
            "INSERT OR IGNORE INTO season_progress "
            "(user_id, season_id, updated_at) VALUES (?, ?, ?)",
            (
                user_id,
                season_id,
                datetime.datetime.now().isoformat(),
            ),
        )
        await runtime.commit()

        async with runtime.db.execute(
            "SELECT xp, premium, claimed_free, claimed_premium "
            "FROM season_progress WHERE user_id = ? AND season_id = ?",
            (user_id, season_id),
        ) as c:
            row = await c.fetchone()

        xp, premium, free_json, premium_json = row or (
            0,
            0,
            "[]",
            "[]",
        )
        xp = xp or 0
        premium = bool(premium)
        claimed_free = _parse_season_claimed(free_json)
        claimed_premium = _parse_season_claimed(premium_json)
        level, remaining = season_level_from_xp(xp)
        needed = (
            season_xp_for_next_level(level)
            if level < runtime.levels
            else 0
        )

        return {
            "season_id": season_id,
            "season_name": current_season_name(),
            "xp": xp,
            "level": level,
            "remaining": remaining,
            "needed": needed,
            "premium": premium,
            "days_left": season_days_left(),
            "claimed_free": claimed_free,
            "claimed_premium": claimed_premium,
            "claimable_free": [
                lvl
                for lvl in range(1, level + 1)
                if lvl not in claimed_free
            ],
            "claimable_premium": (
                [
                    lvl
                    for lvl in range(1, level + 1)
                    if lvl not in claimed_premium
                ]
                if premium
                else []
            ),
        }

    async def add_season_xp(
        user_id: int,
        base_amount: int,
        guild_id: int | None = None,
        action: str = "other",
    ) -> int:
        """Начисляет сезонный XP с лимитами на транзакцию и день."""
        if base_amount <= 0:
            return 0
        config = runtime.xp_actions.get(
            action, runtime.xp_actions["other"]
        )
        if guild_id:
            settings = await runtime.get_settings(guild_id)
            if not settings.get("battlepass_enabled", True):
                return 0
        base_amount = min(int(base_amount), int(config["per_tx"]))
        amount = max(
            1, int(round(base_amount * season_event_multiplier()))
        )
        season_id = current_season_id()
        day = runtime.today_str()
        now = datetime.datetime.now().isoformat()
        try:
            async with runtime.transaction():
                await runtime.db.execute(
                    "INSERT OR IGNORE INTO season_progress "
                    "(user_id, season_id, updated_at) VALUES (?, ?, ?)",
                    (user_id, season_id, now),
                )
                async with runtime.db.execute(
                    "SELECT xp FROM season_xp_log "
                    "WHERE user_id = ? AND season_id = ? AND day = ? "
                    "AND action = ?",
                    (user_id, season_id, day, action),
                ) as c:
                    row = await c.fetchone()
                used = (row[0] if row else 0) or 0
                allowed = min(
                    amount, max(0, int(config["daily"]) - used)
                )
                if allowed <= 0:
                    return 0
                await runtime.db.execute(
                    "UPDATE season_progress SET xp = xp + ?, "
                    "updated_at = ? WHERE user_id = ? AND season_id = ?",
                    (allowed, now, user_id, season_id),
                )
                await runtime.db.execute(
                    "INSERT INTO season_xp_log "
                    "(user_id, season_id, day, action, xp) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(user_id, season_id, day, action) "
                    "DO UPDATE SET xp = xp + excluded.xp",
                    (user_id, season_id, day, action, allowed),
                )
        except Exception:
            runtime.logger.exception(
                "Не удалось начислить сезонный XP пользователю %s",
                user_id,
            )
            return 0
        return allowed

    async def buy_season_premium(user_id: int) -> tuple[bool, str]:
        season_id = current_season_id()
        now = datetime.datetime.now().isoformat()
        try:
            async with runtime.transaction():
                await runtime.db.execute(
                    "INSERT OR IGNORE INTO season_progress "
                    "(user_id, season_id, updated_at) VALUES (?, ?, ?)",
                    (user_id, season_id, now),
                )
                async with runtime.db.execute(
                    "SELECT premium FROM season_progress "
                    "WHERE user_id = ? AND season_id = ?",
                    (user_id, season_id),
                ) as c:
                    row = await c.fetchone()
                if row and row[0]:
                    raise ValueError(
                        "Премиум-пропуск уже активен."
                    )

                cur = await runtime.db.execute(
                    "UPDATE players SET gems = gems - ? "
                    "WHERE user_id = ? AND gems >= ?",
                    (
                        runtime.premium_cost_gems,
                        user_id,
                        runtime.premium_cost_gems,
                    ),
                )
                if cur.rowcount == 0:
                    raise ValueError(
                        f"Нужно {runtime.gem} "
                        f"{runtime.premium_cost_gems}."
                    )

                await runtime.db.execute(
                    "UPDATE season_progress SET premium = 1, "
                    "updated_at = ? WHERE user_id = ? AND season_id = ?",
                    (now, user_id, season_id),
                )
        except ValueError as e:
            return False, f"❌ {e}"
        return True, (
            f"{runtime.emoji('_approve')} Премиум-пропуск активирован! "
            f"Открыты премиум-награды сезона "
            f"«{current_season_name()}»."
        )

    async def claim_season_rewards(
        user_id: int,
    ) -> tuple[bool, str, dict]:
        season_id = current_season_id()
        now = datetime.datetime.now().isoformat()
        totals = {
            "coins": 0,
            "gems": 0,
            "catalysts": 0,
            "levels": 0,
        }
        try:
            async with runtime.transaction():
                await runtime.db.execute(
                    "INSERT OR IGNORE INTO season_progress "
                    "(user_id, season_id, updated_at) VALUES (?, ?, ?)",
                    (user_id, season_id, now),
                )
                async with runtime.db.execute(
                    "SELECT xp, premium, claimed_free, claimed_premium "
                    "FROM season_progress "
                    "WHERE user_id = ? AND season_id = ?",
                    (user_id, season_id),
                ) as c:
                    row = await c.fetchone()
                if not row:
                    raise ValueError(
                        "Сезонный прогресс не найден."
                    )

                xp, premium, free_json, premium_json = row
                level, _ = season_level_from_xp(xp or 0)
                premium = bool(premium)
                claimed_free = _parse_season_claimed(free_json)
                claimed_premium = _parse_season_claimed(
                    premium_json
                )

                free_levels = [
                    lvl
                    for lvl in range(1, level + 1)
                    if lvl not in claimed_free
                ]
                premium_levels = (
                    [
                        lvl
                        for lvl in range(1, level + 1)
                        if lvl not in claimed_premium
                    ]
                    if premium
                    else []
                )

                if not free_levels and not premium_levels:
                    raise ValueError("Нет наград для получения.")

                for lvl in free_levels:
                    reward = season_reward(lvl, premium=False)
                    for key in ("coins", "gems", "catalysts"):
                        totals[key] += reward[key]
                    totals["levels"] += 1
                for lvl in premium_levels:
                    reward = season_reward(lvl, premium=True)
                    for key in ("coins", "gems", "catalysts"):
                        totals[key] += reward[key]
                    totals["levels"] += 1

                await runtime.db.execute(
                    "UPDATE players SET coins = coins + ?, "
                    "gems = gems + ?, catalysts = catalysts + ?, "
                    "total_coins_earned = total_coins_earned + ?, "
                    "lifetime_production = lifetime_production + ?, "
                    "total_gems_earned = total_gems_earned + ? "
                    "WHERE user_id = ?",
                    (
                        totals["coins"],
                        totals["gems"],
                        totals["catalysts"],
                        totals["coins"],
                        totals["coins"],
                        totals["gems"],
                        user_id,
                    ),
                )

                new_free = claimed_free | set(free_levels)
                new_premium = claimed_premium | set(
                    premium_levels
                )
                await runtime.db.execute(
                    "UPDATE season_progress SET claimed_free = ?, "
                    "claimed_premium = ?, updated_at = ? "
                    "WHERE user_id = ? AND season_id = ?",
                    (
                        json.dumps(sorted(new_free)),
                        json.dumps(sorted(new_premium)),
                        now,
                        user_id,
                        season_id,
                    ),
                )
        except ValueError as e:
            return False, f"❌ {e}", totals

        try:
            await runtime.check_achievements(user_id)
        except Exception:
            runtime.logger.exception(
                "Не удалось проверить достижения после наград сезона"
            )
        parts = [
            f"{runtime.coin} {totals['coins']}",
            f"{runtime.gem} {totals['gems']}",
        ]
        if totals["catalysts"]:
            parts.append(
                f"{runtime.emoji('_catalyst')} "
                f"{totals['catalysts']}"
            )
        message = (
            f"{runtime.emoji('_approve')} Получено наград: "
            f"**{totals['levels']}**\n" + " | ".join(parts)
        )
        return True, message, totals

    async def build_season_embed(user_id: int):
        data = await get_season_data(user_id)
        level = data["level"]

        if level >= runtime.levels:
            progress_text = (
                f"Уровень **{runtime.levels}/{runtime.levels}** — "
                f"максимум\nВсего XP: **{data['xp']}**"
            )
        else:
            bar = season_progress_bar(
                data["remaining"], data["needed"]
            )
            progress_text = (
                f"Уровень **{level}/{runtime.levels}**\n"
                f"`{bar}` {data['remaining']}/{data['needed']} XP\n"
                f"Всего XP: **{data['xp']}**"
            )

        embed = runtime.embed(
            title=(
                f"{runtime.emoji('_advent')} Сезон: "
                f"{data['season_name']}"
            ),
            description=(
                f"До конца сезона: **{data['days_left']} дн.**\n"
                f"Уровень 1 — {runtime.xp_base} XP, каждый следующий "
                f"+{runtime.xp_step} XP.\n"
                f"Всего до {runtime.levels} уровня — "
                f"**{runtime.season_total_xp_text} XP**."
            ),
            color=0x9B59B6,
        )
        embed.add_field(
            name="Прогресс", value=progress_text, inline=False
        )

        event = season_event_label()
        if event:
            embed.add_field(name="Событие", value=event, inline=False)

        embed.add_field(
            name="XP за действия и лимиты",
            value="\n".join(runtime.season_xp_help_lines),
            inline=False,
        )

        next_levels = list(
            range(
                data["level"] + 1,
                min(data["level"] + 5, runtime.levels) + 1,
            )
        )
        if next_levels:
            free_text = "\n".join(
                f"Ур. {lvl}: {season_reward_text(lvl)}"
                for lvl in next_levels
            )
            premium_text = "\n".join(
                f"Ур. {lvl}: {season_reward_text(lvl, premium=True)}"
                for lvl in next_levels
            )
        else:
            free_text = "Максимальный уровень достигнут."
            premium_text = free_text

        embed.add_field(
            name="Бесплатные награды", value=free_text, inline=True
        )
        embed.add_field(
            name="Премиум-награды",
            value=premium_text,
            inline=True,
        )

        if data["premium"]:
            pass_text = f"{runtime.emoji('_approve')} Активен"
        else:
            pass_text = (
                f"Не куплен — {runtime.gem} "
                f"{runtime.premium_cost_gems}"
            )

        claimable = (
            len(data["claimable_free"])
            + len(data["claimable_premium"])
        )
        if claimable:
            pass_text += (
                f"\nК получению: "
                f"**{len(data['claimable_free'])}** бесплатных"
            )
            if data["premium"]:
                pass_text += (
                    f" + **{len(data['claimable_premium'])}** премиум"
                )

        embed.add_field(
            name="Премиум-пропуск", value=pass_text, inline=False
        )
        embed.set_footer(
            text=(
                f"Сезон {data['season_id']} · "
                f"уровень = {runtime.xp_base} + "
                f"{runtime.xp_step}×(ур.-1) XP"
            )
        )
        return await runtime.fix_emojis(embed), data

    return (
        current_season_id,
        current_season_name,
        season_days_left,
        season_event_multiplier,
        season_event_label,
        season_xp_for_next_level,
        season_level_from_xp,
        season_progress_bar,
        season_reward,
        season_reward_text,
        _parse_season_claimed,
        get_season_data,
        add_season_xp,
        buy_season_premium,
        claim_season_rewards,
        build_season_embed,
    )
