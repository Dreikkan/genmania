"""Quest and achievement progression service."""
from __future__ import annotations

import datetime
import json
import logging
import random
from typing import Any, Callable


class ProgressRuntime:
    """Адаптер между bot.py и сервисом прогрессии."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self._clan_getter: Callable[[], Callable] = lambda: None
        self._pets_getter: Callable[[], Callable] = lambda: None
        self._compensation_getter: Callable[[], Callable] = lambda: None
        self._quest_progress_getter: Callable[[], Callable] = lambda: None
        self._achievements_getter: Callable[[], Callable] = lambda: None
        self._season_xp_getter: Callable[[], Callable] = lambda: None
        self._season_xp_amount_getter: Callable[[], Callable] = lambda: None
        self._onboarding_getter: Callable[[], Callable] = lambda: None
        self._log_clan_getter: Callable[[], Callable] = lambda: None
        self._add_clan_xp_getter: Callable[[], Callable] = lambda: None
        self._today_str_getter: Callable[[], Callable] = lambda: None
        self._clan_quests_getter: Callable[[], Any] = lambda: ()
        self._reward_scale_getter: Callable[[], Callable] = (
            lambda: lambda points: 1.0
        )
        self.story_quests: dict = {}
        self.quest_pool: dict = {}
        self.daily_rewards: dict = {}
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        commit_getter: Callable[[], Callable],
        clan_getter: Callable[[], Callable],
        pets_getter: Callable[[], Callable],
        compensation_getter: Callable[[], Callable],
        quest_progress_getter: Callable[[], Callable],
        achievements_getter: Callable[[], Callable],
        season_xp_getter: Callable[[], Callable],
        season_xp_amount_getter: Callable[[], Callable],
        onboarding_getter: Callable[[], Callable],
        log_clan_getter: Callable[[], Callable],
        add_clan_xp_getter: Callable[[], Callable],
        today_str_getter: Callable[[], Callable],
        reward_scale_getter: Callable[[], Callable],
        story_quests: dict,
        quest_pool: dict,
        daily_rewards: dict,
        clan_quests_getter: Callable[[], Any],
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._commit_getter = commit_getter
        self._clan_getter = clan_getter
        self._pets_getter = pets_getter
        self._compensation_getter = compensation_getter
        self._quest_progress_getter = quest_progress_getter
        self._achievements_getter = achievements_getter
        self._season_xp_getter = season_xp_getter
        self._season_xp_amount_getter = season_xp_amount_getter
        self._onboarding_getter = onboarding_getter
        self._log_clan_getter = log_clan_getter
        self._add_clan_xp_getter = add_clan_xp_getter
        self._today_str_getter = today_str_getter
        self._clan_quests_getter = clan_quests_getter
        self._reward_scale_getter = reward_scale_getter
        self.story_quests = story_quests
        self.quest_pool = quest_pool
        self.daily_rewards = daily_rewards
        self.logger = logger

    @property
    def clan_quests(self):
        return self._clan_quests_getter()

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

    async def get_user_pets(self, user_id: int):
        return await self._pets_getter()(user_id)

    async def grant_compensation(self, *args, **kwargs):
        return await self._compensation_getter()(*args, **kwargs)

    async def update_quest_progress(self, *args, **kwargs) -> None:
        await self._quest_progress_getter()(*args, **kwargs)

    async def check_achievements(self, *args, **kwargs):
        return await self._achievements_getter()(*args, **kwargs)

    async def add_season_xp(self, *args, **kwargs) -> None:
        await self._season_xp_getter()(*args, **kwargs)

    def season_xp_amount(self, action: str, multiplier: int = 1):
        return self._season_xp_amount_getter()(action, multiplier)

    async def complete_onboarding_step(self, *args, **kwargs):
        return await self._onboarding_getter()(*args, **kwargs)

    async def log_clan(self, *args, **kwargs) -> None:
        await self._log_clan_getter()(*args, **kwargs)

    async def add_clan_xp(self, *args, **kwargs):
        return await self._add_clan_xp_getter()(*args, **kwargs)

    def today_str(self) -> str:
        return self._today_str_getter()()

    def reward_scale(self, prestige_points: int) -> float:
        return self._reward_scale_getter()(prestige_points)


def make_progress_layer(runtime: ProgressRuntime):
    """Возвращает quest/achievement-функции, привязанные к runtime."""

    async def update_story_quests(
        user_id: int, action_type: str, amount: int = 1
    ):
        """Обновляет прогресс сюжетных квестов при действиях."""
        completed_count = 0
        async with runtime.transaction():
            async with runtime.db.execute(
                "SELECT quest_id, progress FROM player_quests "
                "WHERE user_id = ?",
                (user_id,),
            ) as c:
                rows = await c.fetchall()
            progress_map = {r[0]: r[1] for r in rows}

            for qid, (
                name,
                desc,
                target,
                q_type,
                reward,
            ) in runtime.story_quests.items():
                if q_type != action_type:
                    continue
                current = progress_map.get(qid, 0)
                if current >= target:
                    continue

                new_val = min(current + amount, target)
                await runtime.db.execute(
                    "INSERT INTO player_quests "
                    "(user_id, quest_id, progress, completed) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(user_id, quest_id) DO UPDATE SET "
                    "progress = ?, completed = ?",
                    (
                        user_id,
                        qid,
                        new_val,
                        int(new_val >= target),
                        new_val,
                        int(new_val >= target),
                    ),
                )
                # Если квест только что выполнен — даём награду
                if new_val >= target and current < target:
                    completed_count += 1
                    await runtime.db.execute(
                        "UPDATE players SET gems = gems + ?, "
                        "total_gems_earned = total_gems_earned + ? "
                        "WHERE user_id = ?",
                        (reward, reward, user_id),
                    )
        if completed_count:
            await runtime.add_season_xp(
                user_id,
                runtime.season_xp_amount("story_quest", completed_count),
                action="story_quest",
            )

    async def sync_story_achievements(user_id: int):
        """Синхронизирует 'achievements'-квесты с реальным количеством."""
        async with runtime.db.execute(
            "SELECT COUNT(*) FROM player_achievements WHERE user_id = ?",
            (user_id,),
        ) as c:
            count = (await c.fetchone())[0]

        for qid, (
            name,
            desc,
            target,
            q_type,
            reward,
        ) in runtime.story_quests.items():
            if q_type != "achievements":
                continue

            async with runtime.db.execute(
                "SELECT progress, completed FROM player_quests "
                "WHERE user_id = ? AND quest_id = ?",
                (user_id, qid),
            ) as c:
                row = await c.fetchone()

            current_progress = row[0] if row else 0
            already_completed = row[1] if row else 0

            if already_completed:
                continue

            new_progress = min(count, target)
            completed = int(new_progress >= target)

            await runtime.db.execute(
                "INSERT INTO player_quests "
                "(user_id, quest_id, progress, completed) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, quest_id) DO UPDATE SET "
                "progress = ?, completed = ?",
                (
                    user_id,
                    qid,
                    new_progress,
                    completed,
                    new_progress,
                    completed,
                ),
            )

            # Награда при первом выполнении
            if completed and current_progress < target:
                await runtime.db.execute(
                    "UPDATE players SET gems = gems + ?, "
                    "total_gems_earned = total_gems_earned + ? "
                    "WHERE user_id = ?",
                    (reward, reward, user_id),
                )

        await runtime.commit()

    async def claim_daily(user_id: int) -> dict:
        async with runtime.transaction():
            async with runtime.db.execute(
                "SELECT last_daily, streak_days, prestige_points "
                "FROM players WHERE user_id = ?",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            if not row:
                return {"ok": False, "reason": "Профиль не найден."}

            last_daily, streak, prestige_points = row
            now = datetime.datetime.now()
            today = now.date()

            if last_daily:
                last_date = datetime.datetime.fromisoformat(
                    last_daily
                ).date()
                delta = (today - last_date).days
                if delta == 0:
                    return {
                        "ok": False,
                        "reason": (
                            "Ты уже забирал награду сегодня. "
                            "Возвращайся завтра!"
                        ),
                    }
                new_streak = (
                    streak + 1 if delta == 1 and streak < 30 else 1
                )
            else:
                new_streak = 1

            coins, gems, item_id = runtime.daily_rewards[new_streak]
            scale = runtime.reward_scale(prestige_points or 0)
            coins = int(coins * scale)
            gems = int(gems * scale)

            await runtime.db.execute(
                "UPDATE players SET coins = coins + ?, gems = gems + ?, "
                "total_coins_earned = total_coins_earned + ?, "
                "lifetime_production = lifetime_production + ?, "
                "total_gems_earned = total_gems_earned + ?, "
                "last_daily = ?, streak_days = ? WHERE user_id = ?",
                (
                    coins,
                    gems,
                    coins,
                    coins,
                    gems,
                    now.isoformat(),
                    new_streak,
                    user_id,
                ),
            )

            item_name = None
            if item_id:
                item_name, _ = await runtime.grant_compensation(
                    user_id, item_id, 1
                )

            await runtime.update_quest_progress(
                user_id, "claim_daily"
            )
            await runtime.check_achievements(user_id)
            await runtime.add_season_xp(
                user_id,
                runtime.season_xp_amount("daily"),
                action="daily",
            )
            onboarding = await runtime.complete_onboarding_step(
                user_id, "claim_daily"
            )

            return {
                "ok": True,
                "day": new_streak,
                "coins": coins,
                "gems": gems,
                "item": item_name,
                "streak": new_streak,
                "onboarding": onboarding,
            }

    async def check_achievements(user_id: int):
        async with runtime.db.execute(
            """
            SELECT total_crafts, total_successes, gems, coins, catalysts,
                   (SELECT COUNT(*) FROM inventory inv
                    JOIN items i ON inv.item_id = i.id
                    WHERE inv.user_id = ? AND i.income_gems_per_hour > 0),
                   prestige_points
            FROM players WHERE user_id = ?
            """,
            (user_id, user_id),
        ) as c:
            row = await c.fetchone()
        if not row:
            return []

        (
            total_crafts,
            total_successes,
            gems,
            coins,
            catalysts,
            gem_gens,
            prestige_points,
        ) = row

        # Считаем звёздные достижения
        async with runtime.db.execute(
            """
            SELECT
                MAX(stars) AS max_stars,
                SUM(CASE WHEN stars >= 3 THEN 1 ELSE 0 END) AS stars_3_count,
                SUM(CASE WHEN stars >= 1 THEN 1 ELSE 0 END) AS stars_1_count
            FROM inventory
            WHERE user_id = ? AND location = 'profile'
            """,
            (user_id,),
        ) as c:
            star_row = await c.fetchone()

        max_stars = star_row[0] or 0
        stars_3_count = star_row[1] or 0
        stars_1_count = star_row[2] or 0

        async with runtime.db.execute(
            "SELECT achievement_id FROM player_achievements "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            unlocked = {r[0] for r in await c.fetchall()}

        async with runtime.db.execute(
            "SELECT COALESCE(SUM(catalyst_used), 0) FROM craft_log "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            catalysts_used_total = (await c.fetchone())[0] or 0

        conditions = {
            "first_craft": total_crafts >= 1,
            "craft_10": total_crafts >= 10,
            "craft_50": total_crafts >= 50,
            "success_10": total_successes >= 10,
            "success_50": total_successes >= 50,
            "fail_5": (total_crafts - total_successes) >= 5,
            "first_gem_gen": gem_gens >= 1,
            "rich_1000": coins >= 1000,
            "rich_10000": coins >= 10000,
            "catalyst_10": catalysts_used_total >= 10,
            "star_1": stars_1_count >= 1,
            "star_3": max_stars >= 3,
            "star_3x3": stars_3_count >= 3,
            "star_5": max_stars >= 5,
        }

        newly_unlocked = []
        async with runtime.transaction():
            for ach_id, ok in conditions.items():
                if ok and ach_id not in unlocked:
                    async with runtime.db.execute(
                        "SELECT reward_gems, name, emoji "
                        "FROM achievements WHERE id = ?",
                        (ach_id,),
                    ) as c:
                        ach_row = await c.fetchone()
                    if not ach_row:
                        continue
                    reward_gems, name, emoji = ach_row
                    reward_gems = max(
                        1,
                        int(
                            reward_gems
                            * runtime.reward_scale(prestige_points or 0)
                        ),
                    )

                    cur = await runtime.db.execute(
                        "INSERT OR IGNORE INTO player_achievements "
                        "(user_id, achievement_id) VALUES (?, ?)",
                        (user_id, ach_id),
                    )
                    if cur.rowcount == 0:
                        continue
                    await runtime.db.execute(
                        "UPDATE players SET gems = gems + ?, "
                        "total_gems_earned = total_gems_earned + ? "
                        "WHERE user_id = ?",
                        (reward_gems, reward_gems, user_id),
                    )
                    newly_unlocked.append(
                        (emoji, name, reward_gems)
                    )

        if newly_unlocked:
            await sync_story_achievements(user_id)
            await runtime.add_season_xp(
                user_id,
                runtime.season_xp_amount(
                    "achievement_unlock", len(newly_unlocked)
                ),
                action="achievement_unlock",
            )
        return newly_unlocked

    async def get_or_create_daily_quests(user_id: int):
        today = runtime.today_str()

        async with runtime.db.execute(
            "SELECT daily_quest_date, daily_quest_progress, "
            "daily_quest_claimed FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            return [], {}, []

        date, progress_json, claimed_json = row

        if date != today:
            has_clan = bool(await runtime.get_clan(user_id))
            pets = await runtime.get_user_pets(user_id)

            async with runtime.db.execute(
                "SELECT 1 FROM bank_deposits "
                "WHERE user_id = ? LIMIT 1",
                (user_id,),
            ) as c:
                has_deposit = bool(await c.fetchone())
            async with runtime.db.execute(
                "SELECT 1 FROM auctions WHERE status = 'active' LIMIT 1"
            ) as c:
                has_auction = bool(await c.fetchone())
            async with runtime.db.execute(
                "SELECT 1 FROM inventory WHERE user_id = ? "
                "AND location = 'storage' LIMIT 1",
                (user_id,),
            ) as c:
                has_storage = bool(await c.fetchone())
            async with runtime.db.execute(
                "SELECT 1 FROM inventory WHERE user_id = ? LIMIT 1",
                (user_id,),
            ) as c:
                has_items = bool(await c.fetchone())

            pool = list(runtime.quest_pool.keys())
            if not has_clan:
                pool.remove("donate_clan")
            if not pets:
                pool.remove("feed_pet")
            if not has_deposit:
                pool.remove("close_deposit")
            if not has_auction:
                pool.remove("bid_auction")
            if not has_storage:
                pool.remove("sell_3")
            if not has_items:
                for quest_id in (
                    "star_up_1",
                    "star_fail_1",
                    "sell_auction",
                ):
                    pool.remove(quest_id)
            if len(pool) < 3:
                pool = list(runtime.quest_pool.keys())

            chosen = random.sample(pool, 3)
            progress = {q: 0 for q in chosen}
            claimed: list[str] = []

            await runtime.db.execute(
                "UPDATE players SET daily_quest_date = ?, "
                "daily_quest_progress = ?, daily_quest_claimed = ? "
                "WHERE user_id = ?",
                (
                    today,
                    json.dumps(progress),
                    json.dumps(claimed),
                    user_id,
                ),
            )
            await runtime.commit()
            return chosen, progress, claimed

        progress = json.loads(progress_json or "{}")
        claimed = json.loads(claimed_json or "[]")
        return list(progress.keys()), progress, claimed

    async def update_quest_progress(
        user_id: int, quest_id: str, amount: int = 1
    ):
        async with runtime.transaction():
            quests, progress, claimed = (
                await get_or_create_daily_quests(user_id)
            )
            if quest_id not in progress or quest_id in claimed:
                return

            progress[quest_id] = min(
                progress[quest_id] + amount,
                runtime.quest_pool[quest_id][1],
            )
            await runtime.db.execute(
                "UPDATE players SET daily_quest_progress = ? "
                "WHERE user_id = ?",
                (json.dumps(progress), user_id),
            )

    async def get_or_create_clan_quests(clan_id: int):
        week_key = str(datetime.date.today().isocalendar()[:2])
        async with runtime.db.execute(
            "SELECT id, quest_type, progress, target, reward, "
            "completed, week_start FROM clan_quests WHERE clan_id = ?",
            (clan_id,),
        ) as c:
            rows = await c.fetchall()

        if rows and all((r[6] or "") == week_key for r in rows):
            return [r[:6] for r in rows]

        # Новая неделя (или первый запуск) — пересоздаём квесты.
        await runtime.db.execute(
            "DELETE FROM clan_quests WHERE clan_id = ?", (clan_id,)
        )
        for qt, desc, target, reward in runtime.clan_quests:
            await runtime.db.execute(
                "INSERT INTO clan_quests "
                "(clan_id, quest_type, target, reward, week_start) "
                "VALUES (?, ?, ?, ?, ?)",
                (clan_id, qt, target, reward, week_key),
            )
        await runtime.commit()

        async with runtime.db.execute(
            "SELECT id, quest_type, progress, target, reward, "
            "completed, week_start FROM clan_quests WHERE clan_id = ?",
            (clan_id,),
        ) as c:
            rows = await c.fetchall()
        return [r[:6] for r in rows]

    async def update_clan_quest(
        clan_id: int, quest_type: str, amount: int = 1
    ):
        async with runtime.db.execute(
            "SELECT id, progress, target, reward, completed "
            "FROM clan_quests WHERE clan_id = ? AND quest_type = ?",
            (clan_id, quest_type),
        ) as c:
            row = await c.fetchone()
        if not row or row[4]:
            return
        qid, prog, target, reward, _ = row
        prog = min(prog + amount, target)
        completed = prog >= target
        await runtime.db.execute(
            "UPDATE clan_quests SET progress = ?, completed = ? "
            "WHERE id = ?",
            (prog, int(completed), qid),
        )
        if completed:
            await runtime.db.execute(
                "UPDATE clans SET treasury = treasury + ? WHERE id = ?",
                (reward, clan_id),
            )
            await runtime.log_clan(
                clan_id,
                "quest_complete",
                f"Тип: {quest_type}, +{reward} в сундук",
            )
            await runtime.add_clan_xp(clan_id, 50)
        await runtime.commit()

    return (
        update_story_quests,
        sync_story_achievements,
        claim_daily,
        check_achievements,
        get_or_create_daily_quests,
        update_quest_progress,
        get_or_create_clan_quests,
        update_clan_quest,
    )
