"""PvP duel and cooldown service."""
from __future__ import annotations

import datetime
import logging
import random
from typing import Any, Callable


class PvpRuntime:
    """Адаптер между bot.py и PvP-сервисом."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._parse_time_getter: Callable[[], Callable] = lambda: None
        self._combat_power_getter: Callable[[], Callable] = lambda: None
        self._quest_getter: Callable[[], Callable] = lambda: None
        self._story_quest_getter: Callable[[], Callable] = lambda: None
        self._achievements_getter: Callable[[], Callable] = lambda: None
        self._season_xp_getter: Callable[[], Callable] = lambda: None
        self._season_xp_amount_getter: Callable[[], Callable] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._raid_cooldown_getter: Callable[[], Callable] = lambda: None
        self._format_cooldown_getter: Callable[[], Callable] = lambda: None
        self.duel_cooldown_seconds = 300
        self.espionage_cooldown_seconds = 300
        self.duel_max_bet_pct = 0.10
        self.duel_power_tolerance = 0.15
        self.duel_power_variance = 0.15
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        parse_time_getter: Callable[[], Callable],
        combat_power_getter: Callable[[], Callable],
        quest_getter: Callable[[], Callable],
        story_quest_getter: Callable[[], Callable],
        achievements_getter: Callable[[], Callable],
        season_xp_getter: Callable[[], Callable],
        season_xp_amount_getter: Callable[[], Callable],
        embed_factory: Callable[..., Any],
        emoji_getter: Callable[[], Callable],
        raid_cooldown_getter: Callable[[], Callable],
        format_cooldown_getter: Callable[[], Callable],
        duel_cooldown_seconds: int,
        espionage_cooldown_seconds: int,
        duel_max_bet_pct: float,
        duel_power_tolerance: float,
        duel_power_variance: float,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._parse_time_getter = parse_time_getter
        self._combat_power_getter = combat_power_getter
        self._quest_getter = quest_getter
        self._story_quest_getter = story_quest_getter
        self._achievements_getter = achievements_getter
        self._season_xp_getter = season_xp_getter
        self._season_xp_amount_getter = season_xp_amount_getter
        self._embed_factory = embed_factory
        self._emoji_getter = emoji_getter
        self._raid_cooldown_getter = raid_cooldown_getter
        self._format_cooldown_getter = format_cooldown_getter
        self.duel_cooldown_seconds = duel_cooldown_seconds
        self.espionage_cooldown_seconds = espionage_cooldown_seconds
        self.duel_max_bet_pct = duel_max_bet_pct
        self.duel_power_tolerance = duel_power_tolerance
        self.duel_power_variance = duel_power_variance
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    def parse_db_time(self, value):
        return self._parse_time_getter()(value)

    async def get_combat_power(self, user_id: int):
        return await self._combat_power_getter()(user_id)

    async def update_quest_progress(self, *args, **kwargs) -> None:
        await self._quest_getter()(*args, **kwargs)

    async def update_story_quests(self, *args, **kwargs) -> None:
        await self._story_quest_getter()(*args, **kwargs)

    async def check_achievements(self, *args, **kwargs) -> None:
        await self._achievements_getter()(*args, **kwargs)

    async def add_season_xp(self, *args, **kwargs) -> None:
        await self._season_xp_getter()(*args, **kwargs)

    def season_xp_amount(self, action: str):
        return self._season_xp_amount_getter()(action)

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    def emoji(self, key: str):
        return self._emoji_getter()(key)

    async def get_raid_cooldown_seconds(self, user_id: int):
        return await self._raid_cooldown_getter()(user_id)

    def format_cooldown(self, seconds: int) -> str:
        return self._format_cooldown_getter()(seconds)


def make_pvp_layer(runtime: PvpRuntime):
    """Возвращает PvP-функции, привязанные к runtime."""

    async def get_duel_cooldown_seconds(user_id: int) -> int:
        """Сколько секунд осталось до следующей дуэли."""
        async with runtime.db.execute(
            "SELECT last_duel_time FROM duel_cooldowns WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        last = runtime.parse_db_time(row[0]) if row else None
        if not last:
            return 0
        return max(
            0,
            int(
                runtime.duel_cooldown_seconds
                - (datetime.datetime.now() - last).total_seconds()
            ),
        )

    async def set_duel_cooldown(
        user_id: int, when: datetime.datetime | None = None
    ):
        stamp = (when or datetime.datetime.now()).isoformat()
        await runtime.db.execute(
            "INSERT INTO duel_cooldowns (user_id, last_duel_time) "
            "VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET last_duel_time = ?",
            (user_id, stamp, stamp),
        )

    async def get_espionage_cooldown_seconds(user_id: int) -> int:
        async with runtime.db.execute(
            "SELECT last_espionage_time FROM espionage_cooldowns "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        last = runtime.parse_db_time(row[0]) if row else None
        if not last:
            return 0
        return max(
            0,
            int(
                runtime.espionage_cooldown_seconds
                - (datetime.datetime.now() - last).total_seconds()
            ),
        )

    async def set_espionage_cooldown(user_id: int):
        stamp = datetime.datetime.now().isoformat()
        await runtime.db.execute(
            "INSERT INTO espionage_cooldowns (user_id, last_espionage_time) "
            "VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_espionage_time = ?",
            (user_id, stamp, stamp),
        )

    def power_duel_allowed(
        challenger_power: int, opponent_power: int
    ) -> bool:
        """Проверяет ±15% мощи без ошибок округления float."""
        if challenger_power <= 0 or opponent_power <= 0:
            return False
        percent = int(round(runtime.duel_power_tolerance * 100))
        return (
            challenger_power * (100 - percent)
            <= opponent_power * 100
            <= challenger_power * (100 + percent)
        )

    async def validate_power_duel(
        challenger_id: int, opponent_id: int
    ) -> tuple[bool, str]:
        p1 = await runtime.get_combat_power(challenger_id)
        p2 = await runtime.get_combat_power(opponent_id)
        if p1 <= 0 or p2 <= 0:
            return False, "У одного из игроков нет генераторов для дуэли."
        if not power_duel_allowed(p1, p2):
            return False, (
                "❌ Для power-дуэли нужен противник в диапазоне "
                f"±{int(runtime.duel_power_tolerance * 100)}% твоей мощи."
            )
        return True, ""

    async def resolve_duel(
        challenger_id: int,
        opponent_id: int,
        bet: int,
        mode: str,
        guild_id: int | None = None,
    ) -> tuple[bool, str]:
        """Проводит дуэль после согласия обеих сторон."""
        try:
            async with runtime.transaction():
                for uid in (challenger_id, opponent_id):
                    cooldown = await get_duel_cooldown_seconds(uid)
                    if cooldown > 0:
                        minutes = max(1, int(cooldown // 60) + 1)
                        raise ValueError(
                            f"Кулдаун дуэли ещё ~{minutes} мин."
                        )

                async with runtime.db.execute(
                    "SELECT coins FROM players WHERE user_id = ?",
                    (challenger_id,),
                ) as c:
                    c1_row = await c.fetchone()
                async with runtime.db.execute(
                    "SELECT coins FROM players WHERE user_id = ?",
                    (opponent_id,),
                ) as c:
                    c2_row = await c.fetchone()

                c1 = (c1_row[0] if c1_row else 0) or 0
                c2 = (c2_row[0] if c2_row else 0) or 0
                if c1 < bet or c2 < bet:
                    raise ValueError(
                        "У кого-то не хватает монет на ставку."
                    )
                max_bet = max(
                    1, int(min(c1, c2) * runtime.duel_max_bet_pct)
                )
                if bet > max_bet:
                    raise ValueError(
                        f"Ставка не больше "
                        f"{int(runtime.duel_max_bet_pct * 100)}% "
                        f"баланса (максимум {max_bet})."
                    )

                if mode == "dice":
                    r1, r2 = random.randint(1, 100), random.randint(1, 100)
                    winner = challenger_id if r1 > r2 else opponent_id
                    text = f"🎲 Выпало: {r1} против {r2}"
                else:
                    p1 = await runtime.get_combat_power(challenger_id)
                    p2 = await runtime.get_combat_power(opponent_id)
                    if p1 <= 0 or p2 <= 0:
                        raise ValueError(
                            "У одного из игроков нет генераторов для дуэли."
                        )
                    if not power_duel_allowed(p1, p2):
                        raise ValueError(
                            "Для power-дуэли нужен противник в диапазоне "
                            f"±{int(runtime.duel_power_tolerance * 100)}% "
                            "мощи."
                        )
                    r1 = int(
                        p1
                        * random.uniform(
                            1 - runtime.duel_power_variance,
                            1 + runtime.duel_power_variance,
                        )
                    )
                    r2 = int(
                        p2
                        * random.uniform(
                            1 - runtime.duel_power_variance,
                            1 + runtime.duel_power_variance,
                        )
                    )
                    winner = challenger_id if r1 > r2 else opponent_id
                    text = f"⚔️ Мощь: {p1}→{r1} против {p2}→{r2}"

                cur1 = await runtime.db.execute(
                    "UPDATE players SET coins = coins - ? "
                    "WHERE user_id = ? AND coins >= ?",
                    (bet, challenger_id, bet),
                )
                cur2 = await runtime.db.execute(
                    "UPDATE players SET coins = coins - ? "
                    "WHERE user_id = ? AND coins >= ?",
                    (bet, opponent_id, bet),
                )
                if cur1.rowcount == 0 or cur2.rowcount == 0:
                    raise ValueError(
                        "У кого-то не хватает монет на ставку."
                    )

                await runtime.db.execute(
                    "UPDATE players SET coins = coins + ? WHERE user_id = ?",
                    (bet * 2, winner),
                )
                loser = (
                    opponent_id
                    if winner == challenger_id
                    else challenger_id
                )
                await runtime.db.execute(
                    "INSERT INTO duel_history "
                    "(winner_id, loser_id, bet, type) VALUES (?, ?, ?, ?)",
                    (winner, loser, bet, mode),
                )
                await set_duel_cooldown(
                    challenger_id, datetime.datetime.now()
                )
                await set_duel_cooldown(
                    opponent_id, datetime.datetime.now()
                )
        except ValueError as e:
            return False, f"❌ {e}"

        await runtime.update_quest_progress(challenger_id, "duel_1")
        await runtime.update_quest_progress(opponent_id, "duel_1")
        if winner == challenger_id:
            await runtime.update_story_quests(
                challenger_id, "duel_win", 1
            )
        else:
            await runtime.update_story_quests(opponent_id, "duel_win", 1)

        await runtime.check_achievements(challenger_id)
        await runtime.check_achievements(opponent_id)

        loser = opponent_id if winner == challenger_id else challenger_id
        await runtime.add_season_xp(
            winner,
            runtime.season_xp_amount("duel_win"),
            guild_id,
            action="duel_win",
        )
        await runtime.add_season_xp(
            loser,
            runtime.season_xp_amount("duel_loss"),
            guild_id,
            action="duel_loss",
        )

        winner_name = f"<@{winner}>"
        msg = (
            f"{text}\n\n"
            f"🏆 Победитель: {winner_name}\n"
            f"Банк: 🪙 **{bet * 2}**\n"
            f"⏳ Следующая дуэль через "
            f"{runtime.duel_cooldown_seconds // 60} мин."
        )
        return True, msg

    async def build_battle_log_embed(
        user_id: int, filter_type: str = "all"
    ):
        events = []
        if filter_type in ("all", "duel"):
            async with runtime.db.execute(
                "SELECT winner_id, loser_id, bet, type, timestamp "
                "FROM duel_history WHERE winner_id = ? "
                "OR loser_id = ? ORDER BY id DESC LIMIT 10",
                (user_id, user_id),
            ) as c:
                for winner, loser, bet, mode, ts in await c.fetchall():
                    won = winner == user_id
                    opponent = loser if won else winner
                    events.append(
                        (
                            runtime.parse_db_time(ts)
                            or datetime.datetime.min,
                            f"{'🏆' if won else '💥'} Дуэль ({mode}) "
                            f"против <@{opponent}> · "
                            f"ставка 🪙 {bet}",
                        )
                    )
        if filter_type in ("all", "raid"):
            async with runtime.db.execute(
                "SELECT target_id, amount, timestamp "
                "FROM raid_loot_log WHERE user_id = ? "
                "ORDER BY id DESC LIMIT 10",
                (user_id,),
            ) as c:
                for target, amount, ts in await c.fetchall():
                    events.append(
                        (
                            runtime.parse_db_time(ts)
                            or datetime.datetime.min,
                            f"🏰 Рейд: украдено 🪙 {amount} "
                            f"у <@{target}>",
                        )
                    )

        events.sort(key=lambda item: item[0], reverse=True)
        filter_labels = {
            "all": "все",
            "duel": "дуэли",
            "raid": "рейды",
        }
        description = (
            f"Последние 10 событий · режим: "
            f"{filter_labels.get(filter_type, filter_type)}."
        )
        raid_cd = await runtime.get_raid_cooldown_seconds(user_id)
        duel_cd = await get_duel_cooldown_seconds(user_id)
        cooldown_parts = []
        if raid_cd:
            cooldown_parts.append(
                f"Рейд: **{runtime.format_cooldown(raid_cd)}**"
            )
        if duel_cd:
            cooldown_parts.append(
                f"Дуэль: **{runtime.format_cooldown(duel_cd)}**"
            )
        if cooldown_parts:
            description += "\n" + " · ".join(cooldown_parts)
        embed = runtime.embed(
            title=f"{runtime.emoji('_history')} Боевой журнал",
            description=description,
            color=0xE74C3C,
        )
        if not events:
            embed.description = (
                "Пока нет боёв. Начни с рейда или дуэли в PvP-хабе."
            )
            return embed
        for timestamp, text in events[:10]:
            embed.add_field(
                name=text[:256],
                value=f"`{timestamp.strftime('%d.%m %H:%M')}`",
                inline=False,
            )
        return embed

    return (
        get_duel_cooldown_seconds,
        set_duel_cooldown,
        get_espionage_cooldown_seconds,
        set_espionage_cooldown,
        power_duel_allowed,
        validate_power_duel,
        resolve_duel,
        build_battle_log_embed,
    )
