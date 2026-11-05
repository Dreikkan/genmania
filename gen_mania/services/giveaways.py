"""Giveaway reward and participation service."""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable

GIVEAWAY_COLUMNS = (
    "id, guild_id, channel_id, message_id, creator_id, title, "
    "reward_type, reward_id, amount, winners_count, status, "
    "created_at, ends_at, winner_ids, scope"
)


class GiveawayRuntime:
    """Адаптер между bot.py и сервисом розыгрышей."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._clan_getter: Callable[[], Callable] = lambda: None
        self._compensation_getter: Callable[[], Callable] = lambda: None
        self._status_sync_getter: Callable[[], Callable] = lambda: None
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._price_formatter: Callable[[int], str] = str
        self.rewards: dict = {}
        self.pet_types: dict = {}
        self.status_bonuses: dict = {}
        self.status_names: dict = {}
        self.status_durations = ()
        self.status_duration_labels: dict = {}
        self.max_coins = 0
        self.max_gems = 0
        self.max_items = 0
        self.max_catalysts = 0
        self.pet_max_level = 10
        self.clan_max_level = 21
        self.max_winners = 10
        self.min_hours = 1
        self.max_hours = 168
        self.scope_server = "server"
        self.scope_global = "global"
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        clan_getter: Callable[[], Callable],
        compensation_getter: Callable[[], Callable],
        status_sync_getter: Callable[[], Callable],
        emoji_getter: Callable[[], Callable],
        price_formatter: Callable[[int], str],
        rewards: dict,
        pet_types: dict,
        status_bonuses: dict,
        status_names: dict,
        status_durations,
        status_duration_labels: dict,
        max_coins: int,
        max_gems: int,
        max_items: int,
        max_catalysts: int,
        pet_max_level: int,
        clan_max_level: int,
        max_winners: int,
        min_hours: int,
        max_hours: int,
        scope_server: str,
        scope_global: str,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._clan_getter = clan_getter
        self._compensation_getter = compensation_getter
        self._status_sync_getter = status_sync_getter
        self._emoji_getter = emoji_getter
        self._price_formatter = price_formatter
        self.rewards = rewards
        self.pet_types = pet_types
        self.status_bonuses = status_bonuses
        self.status_names = status_names
        self.status_durations = status_durations
        self.status_duration_labels = status_duration_labels
        self.max_coins = max_coins
        self.max_gems = max_gems
        self.max_items = max_items
        self.max_catalysts = max_catalysts
        self.pet_max_level = pet_max_level
        self.clan_max_level = clan_max_level
        self.max_winners = max_winners
        self.min_hours = min_hours
        self.max_hours = max_hours
        self.scope_server = scope_server
        self.scope_global = scope_global
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    async def get_clan(self, user_id: int):
        return await self._clan_getter()(user_id)

    async def grant_compensation(self, *args, **kwargs):
        return await self._compensation_getter()(*args, **kwargs)

    async def sync_status_bonus(self, user_id: int):
        return await self._status_sync_getter()(user_id)

    def emoji(self, key: str):
        return self._emoji_getter()(key)

    def format_price(self, value: int) -> str:
        return self._price_formatter(value)


def make_giveaway_layer(runtime: GiveawayRuntime):
    """Возвращает giveaway-функции, привязанные к runtime."""

    async def get_giveaway(giveaway_id: int):
        async with runtime.db.execute(
            f"SELECT {GIVEAWAY_COLUMNS} FROM giveaways WHERE id = ?",
            (giveaway_id,),
        ) as c:
            return await c.fetchone()

    def giveaway_scope(giveaway) -> str:
        """Возвращает scope розыгрыша с fallback для старых строк."""
        if not giveaway:
            return runtime.scope_server
        try:
            scope = giveaway[14]
        except (IndexError, TypeError):
            scope = None
        return scope or runtime.scope_server

    def is_global_giveaway(giveaway) -> bool:
        return giveaway_scope(giveaway) == runtime.scope_global

    async def giveaway_validate_reward(
        reward_type: str, reward_id: str | None, amount
    ) -> tuple[dict | None, str]:
        info = runtime.rewards.get(reward_type)
        if not info:
            return None, "❌ Неизвестный тип награды."
        reward_id = (reward_id or "").strip().lower()
        try:
            amount_int = int(str(amount).strip())
        except (TypeError, ValueError):
            return None, "❌ Количество должно быть числом."

        summary = ""

        if reward_type == "coins":
            if not 1 <= amount_int <= runtime.max_coins:
                return (
                    None,
                    f"❌ Монет: от 1 до "
                    f"{runtime.format_price(runtime.max_coins)}.",
                )
            summary = (
                f"{runtime.emoji('_coin')} "
                f"**{runtime.format_price(amount_int)}** монет"
            )
        elif reward_type == "gems":
            if not 1 <= amount_int <= runtime.max_gems:
                return (
                    None,
                    f"❌ Гемов: от 1 до "
                    f"{runtime.format_price(runtime.max_gems)}.",
                )
            summary = (
                f"{runtime.emoji('_gem')} "
                f"**{runtime.format_price(amount_int)}** гемов"
            )
        elif reward_type == "catalysts":
            if not 1 <= amount_int <= runtime.max_catalysts:
                return (
                    None,
                    f"❌ Катализаторов: от 1 до "
                    f"{runtime.max_catalysts}.",
                )
            summary = (
                f"{runtime.emoji('_catalyst')} **{amount_int}** "
                "катализаторов"
            )
        elif reward_type == "generator":
            if not 1 <= amount_int <= runtime.max_items:
                return (
                    None,
                    f"❌ Предметов: от 1 до {runtime.max_items}.",
                )
            async with runtime.db.execute(
                "SELECT name, emoji FROM items WHERE id = ?", (reward_id,)
            ) as c:
                item = await c.fetchone()
            if not item:
                return None, "❌ Генератор с таким ID не найден."
            summary = (
                f"{item[1] or runtime.emoji('_generators')} "
                f"**{item[0]}** ×{amount_int}"
            )
        elif reward_type == "pet":
            pet = runtime.pet_types.get(reward_id)
            if not pet:
                return None, "❌ Питомец с таким ID не найден."
            amount_int = 1
            summary = f"{pet['emoji']} **{pet['name']}**"
        elif reward_type == "pet_level":
            pet = runtime.pet_types.get(reward_id)
            if not pet:
                return None, "❌ Питомец с таким ID не найден."
            if not 1 <= amount_int <= runtime.pet_max_level:
                return (
                    None,
                    f"❌ Уровней: от 1 до {runtime.pet_max_level}.",
                )
            summary = (
                f"{pet['emoji']} **{pet['name']}** +{amount_int} ур."
            )
        elif reward_type == "status":
            if reward_id not in runtime.status_bonuses:
                return None, "❌ Статус: vip / gold / platinum / diamond."
            if amount_int not in runtime.status_durations:
                return None, "❌ Срок статуса: 1, 3, 7 или 30 дней."
            summary = (
                f"{runtime.emoji('_' + reward_id)} "
                f"**{runtime.status_names[reward_id]}** "
                f"на {runtime.status_duration_labels[amount_int]}"
            )
        elif reward_type == "clan_level":
            if not 1 <= amount_int <= runtime.clan_max_level:
                return (
                    None,
                    f"❌ Уровней клана: от 1 до {runtime.clan_max_level}.",
                )
            summary = (
                f"{runtime.emoji('_clan')} "
                f"**+{amount_int} ур. клана**"
            )

        return {
            "reward_type": reward_type,
            "reward_id": reward_id,
            "amount": amount_int,
            "summary": summary,
            "info": info,
        }, ""

    def parse_giveaway_options(winners, duration_hours):
        """Валидирует число победителей и длительность розыгрыша."""
        try:
            winners_int = int(str(winners).strip())
            hours_int = int(str(duration_hours).strip())
        except (TypeError, ValueError):
            return (
                None,
                None,
                "❌ Победители и длительность должны быть числами.",
            )
        if not 1 <= winners_int <= runtime.max_winners:
            return (
                None,
                None,
                f"❌ Победителей: от 1 до {runtime.max_winners}.",
            )
        if not runtime.min_hours <= hours_int <= runtime.max_hours:
            return (
                None,
                None,
                f"❌ Длительность: от {runtime.min_hours} "
                f"до {runtime.max_hours} часов.",
            )
        return winners_int, hours_int, ""

    async def grant_pet_reward(
        user_id: int, pet_id: str, levels: int = 0
    ) -> int:
        if pet_id not in runtime.pet_types:
            return 0
        async with runtime.transaction():
            async with runtime.db.execute(
                "SELECT level FROM user_pets_v2 "
                "WHERE user_id = ? AND pet_id = ?",
                (user_id, pet_id),
            ) as c:
                row = await c.fetchone()
            if row:
                current_level = row[0] or 1
                if current_level >= runtime.pet_max_level:
                    return 0
                gain = max(1, levels)
                new_level = min(
                    runtime.pet_max_level, current_level + gain
                )
                await runtime.db.execute(
                    "UPDATE user_pets_v2 SET level = ? "
                    "WHERE user_id = ? AND pet_id = ?",
                    (new_level, user_id, pet_id),
                )
            else:
                new_level = min(runtime.pet_max_level, 1 + levels)
                await runtime.db.execute(
                    "INSERT INTO user_pets_v2 "
                    "(user_id, pet_id, level, last_fed) "
                    "VALUES (?, ?, ?, NULL)",
                    (user_id, pet_id, new_level),
                )
        return new_level

    async def grant_status_reward(
        user_id: int, status_id: str, days: int
    ) -> bool:
        if (
            status_id not in runtime.status_bonuses
            or days not in runtime.status_durations
        ):
            return False
        now = datetime.datetime.now()
        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT expires_at FROM player_upgrades "
                    "WHERE user_id = ? AND upgrade_id = ?",
                    (user_id, status_id),
                ) as c:
                    row = await c.fetchone()
                base = now
                if row and row[0]:
                    try:
                        current = datetime.datetime.fromisoformat(row[0])
                    except (TypeError, ValueError):
                        current = None
                    if current and current > now:
                        base = current
                new_expiry = base + datetime.timedelta(days=days)
                await runtime.db.execute(
                    """
                    INSERT INTO player_upgrades
                        (user_id, upgrade_id, level, purchased_at, expires_at)
                    VALUES (?, ?, 1, CURRENT_TIMESTAMP, ?)
                    ON CONFLICT(user_id, upgrade_id) DO UPDATE SET
                        expires_at = excluded.expires_at,
                        purchased_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, status_id, new_expiry.isoformat()),
                )
                await runtime.sync_status_bonus(user_id)
        except Exception:
            runtime.logger.exception(
                "Не удалось выдать статус %s игроку %s", status_id, user_id
            )
            return False
        return True

    async def grant_clan_levels(clan_id: int, levels: int) -> int | None:
        async with runtime.transaction():
            async with runtime.db.execute(
                "SELECT level FROM clans WHERE id = ?", (clan_id,)
            ) as c:
                row = await c.fetchone()
            if not row:
                return None
            current_level = row[0] or 1
            if current_level >= runtime.clan_max_level:
                return None
            new_level = min(
                runtime.clan_max_level, current_level + levels
            )
            bonus = min(0.20, (new_level - 1) * 0.01)
            await runtime.db.execute(
                "UPDATE clans SET level = ?, bonus = ? WHERE id = ?",
                (new_level, bonus, clan_id),
            )
        return new_level

    async def join_giveaway(
        giveaway_id: int, user_id: int, guild_id: int | None
    ) -> tuple[bool, str]:
        """Записывает игрока в розыгрыш с проверкой scope и правил."""
        async with runtime.transaction():
            giveaway = await get_giveaway(giveaway_id)
            if not giveaway or giveaway[10] != "active":
                return False, "❌ Розыгрыш уже завершён."
            scope = giveaway_scope(giveaway)
            if scope == runtime.scope_global:
                if guild_id is None:
                    return False, "❌ Участвовать можно только на сервере."
            elif guild_id != giveaway[1]:
                return (
                    False,
                    "❌ Этот розыгрыш проводится на другом сервере.",
                )

            ends_at = giveaway[12]
            try:
                ends_dt = datetime.datetime.fromisoformat(ends_at)
            except (TypeError, ValueError):
                ends_dt = None
            if ends_dt and ends_dt <= datetime.datetime.now():
                return False, "❌ Время розыгрыша истекло."

            if giveaway[4] == user_id:
                return False, "❌ Нельзя участвовать в своём розыгрыше."
            if (
                giveaway[6] == "clan_level"
                and not await runtime.get_clan(user_id)
            ):
                return (
                    False,
                    "❌ Для этой награды нужно состоять в клане.",
                )

            async with runtime.db.execute(
                "SELECT 1 FROM players WHERE user_id = ?", (user_id,)
            ) as c:
                if not await c.fetchone():
                    return False, "❌ Сначала зарегистрируйся в игре."

            async with runtime.db.execute(
                "SELECT 1 FROM giveaway_entries "
                "WHERE giveaway_id = ? AND user_id = ?",
                (giveaway_id, user_id),
            ) as c:
                if await c.fetchone():
                    return False, "❌ Ты уже участвуешь."

            await runtime.db.execute(
                "INSERT INTO giveaway_entries (giveaway_id, user_id) "
                "VALUES (?, ?)",
                (giveaway_id, user_id),
            )
        return True, "✅ Ты участвуешь в розыгрыше. Удачи!"

    async def giveaway_grant_reward(winner_id: int, giveaway) -> bool:
        reward_type = giveaway[6]
        reward_id = giveaway[7]
        amount = giveaway[8] or 0
        if reward_type == "coins":
            cur = await runtime.db.execute(
                "UPDATE players SET coins = coins + ? WHERE user_id = ?",
                (amount, winner_id),
            )
            return cur.rowcount > 0
        if reward_type == "gems":
            cur = await runtime.db.execute(
                "UPDATE players SET gems = gems + ? WHERE user_id = ?",
                (amount, winner_id),
            )
            return cur.rowcount > 0
        if reward_type == "catalysts":
            cur = await runtime.db.execute(
                "UPDATE players SET catalysts = catalysts + ? "
                "WHERE user_id = ?",
                (amount, winner_id),
            )
            return cur.rowcount > 0
        if reward_type == "generator":
            await runtime.grant_compensation(
                winner_id, reward_id, amount
            )
            return True
        if reward_type == "pet":
            return await grant_pet_reward(winner_id, reward_id, 0) > 0
        if reward_type == "pet_level":
            return await grant_pet_reward(winner_id, reward_id, amount) > 0
        if reward_type == "status":
            return await grant_status_reward(
                winner_id, reward_id, amount
            )
        if reward_type == "clan_level":
            clan = await runtime.get_clan(winner_id)
            if not clan:
                return False
            return (
                await grant_clan_levels(clan[0], amount) is not None
            )
        return False

    return (
        get_giveaway,
        giveaway_scope,
        is_global_giveaway,
        giveaway_validate_reward,
        parse_giveaway_options,
        grant_pet_reward,
        grant_status_reward,
        grant_clan_levels,
        join_giveaway,
        giveaway_grant_reward,
    )
