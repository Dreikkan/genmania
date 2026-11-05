"""Raid combat and finalization service."""
from __future__ import annotations

import datetime
import logging
import random
from typing import Any, Callable


class RaidCombatRuntime:
    """Адаптер между bot.py и боевым сервисом рейдов."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self._parse_time_getter: Callable[[], Callable] = lambda: None
        self._combat_power_getter: Callable[[], Callable] = lambda: None
        self._pet_bonus_getter: Callable[[], Callable] = lambda: None
        self._title_bonus_getter: Callable[[], Callable] = lambda: None
        self._today_str_getter: Callable[[], Callable] = lambda: None
        self._quest_progress_getter: Callable[[], Callable] = lambda: None
        self._clan_getter: Callable[[], Callable] = lambda: None
        self._clan_quest_getter: Callable[[], Callable] = lambda: None
        self._story_quest_getter: Callable[[], Callable] = lambda: None
        self._achievements_getter: Callable[[], Callable] = lambda: None
        self._season_xp_getter: Callable[[], Callable] = lambda: None
        self._season_xp_amount_getter: Callable[[], Callable] = lambda: None
        self.group_synergy = 0.10
        self.min_target_power_ratio = 0.25
        self.target_shield_hours = 6
        self.daily_loss_cap = 0.25
        self.loot_rate = 0.08
        self.cooldown_seconds = 3600
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        commit_getter: Callable[[], Callable],
        parse_time_getter: Callable[[], Callable],
        combat_power_getter: Callable[[], Callable],
        pet_bonus_getter: Callable[[], Callable],
        title_bonus_getter: Callable[[], Callable],
        today_str_getter: Callable[[], Callable],
        quest_progress_getter: Callable[[], Callable],
        clan_getter: Callable[[], Callable],
        clan_quest_getter: Callable[[], Callable],
        story_quest_getter: Callable[[], Callable],
        achievements_getter: Callable[[], Callable],
        season_xp_getter: Callable[[], Callable],
        season_xp_amount_getter: Callable[[], Callable],
        group_synergy: float,
        min_target_power_ratio: float,
        target_shield_hours: int,
        daily_loss_cap: float,
        loot_rate: float,
        cooldown_seconds: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._commit_getter = commit_getter
        self._parse_time_getter = parse_time_getter
        self._combat_power_getter = combat_power_getter
        self._pet_bonus_getter = pet_bonus_getter
        self._title_bonus_getter = title_bonus_getter
        self._today_str_getter = today_str_getter
        self._quest_progress_getter = quest_progress_getter
        self._clan_getter = clan_getter
        self._clan_quest_getter = clan_quest_getter
        self._story_quest_getter = story_quest_getter
        self._achievements_getter = achievements_getter
        self._season_xp_getter = season_xp_getter
        self._season_xp_amount_getter = season_xp_amount_getter
        self.group_synergy = group_synergy
        self.min_target_power_ratio = min_target_power_ratio
        self.target_shield_hours = target_shield_hours
        self.daily_loss_cap = daily_loss_cap
        self.loot_rate = loot_rate
        self.cooldown_seconds = cooldown_seconds
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

    def parse_db_time(self, value):
        return self._parse_time_getter()(value)

    def today_str(self) -> str:
        return self._today_str_getter()()

    async def get_combat_power(self, user_id: int):
        return await self._combat_power_getter()(user_id)

    async def get_pet_bonus(self, user_id: int, key: str):
        return await self._pet_bonus_getter()(user_id, key)

    async def get_title_bonus(self, user_id: int, key: str):
        return await self._title_bonus_getter()(user_id, key)

    async def update_quest_progress(self, *args, **kwargs) -> None:
        await self._quest_progress_getter()(*args, **kwargs)

    async def get_clan(self, user_id: int):
        return await self._clan_getter()(user_id)

    async def update_clan_quest(self, *args, **kwargs) -> None:
        await self._clan_quest_getter()(*args, **kwargs)

    async def update_story_quests(self, *args, **kwargs) -> None:
        await self._story_quest_getter()(*args, **kwargs)

    async def check_achievements(self, *args, **kwargs):
        return await self._achievements_getter()(*args, **kwargs)

    async def add_season_xp(self, *args, **kwargs) -> None:
        await self._season_xp_getter()(*args, **kwargs)

    def season_xp_amount(self, action: str):
        return self._season_xp_amount_getter()(action)


def make_raid_combat_layer(runtime: RaidCombatRuntime):
    """Возвращает боевые raid-функции, привязанные к runtime."""

    async def perform_raid(attacker_ids: list[int], target_id: int):
        """Проводит рейд. Возвращает (result, error)."""
        members = []
        for uid in attacker_ids:
            if uid not in members:
                members.append(uid)

        if not members:
            return None, "❌ В отряде нет участников."
        if target_id in members:
            return None, "❌ Нельзя атаковать участника своего отряда."

        now = datetime.datetime.now()
        result = {
            "members": members,
            "target_id": target_id,
            "powers": {},
            "team_power": 0,
            "def_power": 0,
            "roll_atk": 0,
            "roll_def": 0,
            "success": False,
            "loot": {},
            "capped": [],
            "target_capped": False,
            "daily": {},
            "synergy_pct": int(
                round(runtime.group_synergy * 100 * (len(members) - 1))
            ),
        }

        try:
            async with runtime.transaction():
                # --- Цель ---
                async with runtime.db.execute(
                    "SELECT coins FROM players WHERE user_id = ?",
                    (target_id,),
                ) as c:
                    target_row = await c.fetchone()
                if not target_row:
                    raise ValueError("❌ Цель не найдена.")
                target_coins = max(0, target_row[0] or 0)
                today = runtime.today_str()
                async with runtime.db.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM raid_loot_log "
                    "WHERE target_id = ? AND date = ?",
                    (target_id, today),
                ) as c:
                    target_lost_today = (await c.fetchone())[0] or 0

                # --- Кулдауны атакующих ---
                placeholders = ",".join("?" for _ in members)
                async with runtime.db.execute(
                    f"SELECT user_id, last_raid_time FROM raid_cooldowns "
                    f"WHERE user_id IN ({placeholders})",
                    members,
                ) as c:
                    cooldown_rows = await c.fetchall()
                cooldowns = {
                    uid: last for uid, last in cooldown_rows
                }

                on_cooldown = []
                for uid in members:
                    last_raid = runtime.parse_db_time(
                        cooldowns.get(uid)
                    )
                    if not last_raid:
                        continue
                    remain = (
                        runtime.cooldown_seconds
                        - (now - last_raid).total_seconds()
                    )
                    if remain > 0:
                        on_cooldown.append(
                            f"<@{uid}> "
                            f"(~{max(1, int(remain // 60) + 1)} мин.)"
                        )
                if on_cooldown:
                    raise ValueError(
                        "❌ Кулдаун рейда: "
                        + ", ".join(on_cooldown)
                        + "."
                    )

                # Щит цели после предыдущей атаки.
                async with runtime.db.execute(
                    "SELECT last_attacked_time FROM raid_cooldowns "
                    "WHERE user_id = ?",
                    (target_id,),
                ) as c:
                    shield_row = await c.fetchone()
                last_attacked = (
                    runtime.parse_db_time(shield_row[0])
                    if shield_row
                    else None
                )
                if last_attacked:
                    shield_left = (
                        runtime.target_shield_hours * 3600
                        - (now - last_attacked).total_seconds()
                    )
                    if shield_left > 0:
                        minutes = max(1, int(shield_left // 60) + 1)
                        raise ValueError(
                            f"❌ У цели действует щит ещё {minutes} мин. "
                            "Её недавно атаковали."
                        )

                # --- Мощь ---
                powers = {}
                for uid in members:
                    power = await runtime.get_combat_power(uid)
                    if power <= 0:
                        raise ValueError(
                            f"❌ У <@{uid}> нет генераторов "
                            "на энергостанции (мощь 0)."
                        )
                    powers[uid] = power

                def_power = await runtime.get_combat_power(target_id)
                if def_power <= 0:
                    raise ValueError(
                        "❌ У цели нет генераторов. Атаковать нечего."
                    )

                team_power = sum(powers.values())
                if len(members) > 1:
                    team_power = int(
                        team_power
                        * (
                            1
                            + runtime.group_synergy
                            * (len(members) - 1)
                        )
                    )
                if def_power < team_power * runtime.min_target_power_ratio:
                    raise ValueError(
                        "❌ Цель слишком слабая для твоего отряда. "
                        "Выбери противника, сопоставимого по силе."
                    )

                roll_atk = random.randint(1, team_power)
                roll_def = random.randint(1, def_power)
                success = roll_atk > roll_def

                # --- Кулдауны после рейда ---
                now_iso = now.isoformat()
                for uid in members:
                    await runtime.db.execute(
                        "INSERT INTO raid_cooldowns "
                        "(user_id, last_raid_time) VALUES (?, ?) "
                        "ON CONFLICT(user_id) DO UPDATE SET "
                        "last_raid_time = ?",
                        (uid, now_iso, now_iso),
                    )
                await runtime.db.execute(
                    "INSERT INTO raid_cooldowns "
                    "(user_id, last_attacked_time) VALUES (?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET "
                    "last_attacked_time = ?",
                    (target_id, now_iso, now_iso),
                )

                # --- Добыча ---
                loot = {}
                capped = []
                daily = {}
                target_capped = False
                if success and target_coins > 0:
                    total_loot = 0
                    target_budget = max(
                        0,
                        int(target_coins * runtime.daily_loss_cap)
                        - target_lost_today,
                    )
                    wanted_by_uid = {}
                    for uid in members:
                        bonus = (
                            await runtime.get_pet_bonus(uid, "raid_loot")
                            + await runtime.get_title_bonus(
                                uid, "raid_loot"
                            )
                        )
                        wanted_by_uid[uid] = (
                            int(
                                target_coins
                                * (runtime.loot_rate + bonus)
                            )
                            // len(members)
                        )

                    total_wanted = sum(wanted_by_uid.values())
                    scale = 1.0
                    if total_wanted > target_budget:
                        scale = (
                            (target_budget / total_wanted)
                            if total_wanted
                            else 0.0
                        )
                        target_capped = True

                    for uid, base_wanted in wanted_by_uid.items():
                        wanted = int(base_wanted * scale)

                        async with runtime.db.execute(
                            "SELECT COALESCE(SUM(amount), 0) "
                            "FROM raid_loot_log "
                            "WHERE user_id = ? AND date = ?",
                            (uid, today),
                        ) as c:
                            used = (await c.fetchone())[0] or 0

                        async with runtime.db.execute(
                            "SELECT coins FROM players "
                            "WHERE user_id = ?",
                            (uid,),
                        ) as c:
                            row = await c.fetchone()
                        my_coins = (row[0] if row else 0) or 0
                        limit = max(1000, my_coins // 2)
                        remaining = max(0, limit - used)
                        actual = min(wanted, remaining)

                        if actual < wanted:
                            capped.append(uid)
                        daily[uid] = (used, limit)
                        if actual > 0:
                            loot[uid] = actual
                            total_loot += actual

                    if total_loot > 0:
                        cur = await runtime.db.execute(
                            "UPDATE players SET coins = coins - ? "
                            "WHERE user_id = ? AND coins >= ?",
                            (total_loot, target_id, total_loot),
                        )
                        if cur.rowcount == 0:
                            raise ValueError(
                                "❌ Кошелёк цели изменился. "
                                "Попробуй рейд ещё раз."
                            )

                        for uid, amount in loot.items():
                            await runtime.db.execute(
                                "UPDATE players SET coins = coins + ?, "
                                "total_coins_earned = "
                                "total_coins_earned + ? "
                                "WHERE user_id = ?",
                                (amount, amount, uid),
                            )
                            await runtime.db.execute(
                                "INSERT INTO raid_loot_log "
                                "(user_id, target_id, amount, date) "
                                "VALUES (?, ?, ?, ?)",
                                (uid, target_id, amount, today),
                            )

                result.update(
                    {
                        "powers": powers,
                        "team_power": team_power,
                        "def_power": def_power,
                        "roll_atk": roll_atk,
                        "roll_def": roll_def,
                        "success": success,
                        "loot": loot,
                        "capped": capped,
                        "target_capped": target_capped,
                        "daily": daily,
                    }
                )
        except ValueError as e:
            return None, str(e)

        return result, None

    async def finalize_raid(result: dict):
        """Обновляет квесты, победы и достижения всех участников."""
        for uid in result["members"]:
            try:
                await runtime.update_quest_progress(uid, "raid_1")

                clan = await runtime.get_clan(uid)
                if clan:
                    await runtime.update_clan_quest(clan[0], "raid", 1)

                if result["success"]:
                    await runtime.update_story_quests(
                        uid, "raid_win", 1
                    )
                    await runtime.db.execute(
                        "UPDATE players SET raid_wins = raid_wins + 1 "
                        "WHERE user_id = ?",
                        (uid,),
                    )
                    await runtime.commit()
                    await runtime.check_achievements(uid)
                await runtime.add_season_xp(
                    uid,
                    runtime.season_xp_amount(
                        "raid_win"
                        if result["success"]
                        else "raid_loss"
                    ),
                    action=(
                        "raid_win"
                        if result["success"]
                        else "raid_loss"
                    ),
                )
            except Exception:
                runtime.logger.exception(
                    "Не удалось обновить прогресс рейда для %s", uid
                )

    return perform_raid, finalize_raid
