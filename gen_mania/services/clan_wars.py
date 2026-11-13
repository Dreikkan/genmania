"""Clan war declaration and attack service."""
from __future__ import annotations

import datetime
import logging
import random
from typing import Any, Callable


class ClanWarRuntime:
    """Адаптер между bot.py и сервисом клановых войн."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._active_war_getter: Callable[[], Callable] = lambda: None
        self._clan_power_getter: Callable[[], Callable] = lambda: None
        self._clan_level_getter: Callable[[], Callable] = lambda: None
        self._combat_power_getter: Callable[[], Callable] = lambda: None
        self._log_clan_getter: Callable[[], Callable] = lambda: None
        self._add_clan_xp_getter: Callable[[], Callable] = lambda: None
        self._clan_quest_getter: Callable[[], Callable] = lambda: None
        self._parse_time_getter: Callable[[], Callable] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self.declare_cost = 500
        self.reward = 1000
        self.reward_per_level = 0
        self.cooldown_hours = 24
        self.attack_cooldown_hours = 1
        self.damage_rate = 0.15
        self.war_duration_hours = 24
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        active_war_getter: Callable[[], Callable],
        clan_power_getter: Callable[[], Callable],
        clan_level_getter: Callable[[], Callable],
        combat_power_getter: Callable[[], Callable],
        log_clan_getter: Callable[[], Callable],
        add_clan_xp_getter: Callable[[], Callable],
        clan_quest_getter: Callable[[], Callable],
        parse_time_getter: Callable[[], Callable],
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        declare_cost: int,
        reward: int,
        reward_per_level: int,
        cooldown_hours: int,
        attack_cooldown_hours: int,
        damage_rate: float,
        war_duration_hours: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._active_war_getter = active_war_getter
        self._clan_power_getter = clan_power_getter
        self._clan_level_getter = clan_level_getter
        self._combat_power_getter = combat_power_getter
        self._log_clan_getter = log_clan_getter
        self._add_clan_xp_getter = add_clan_xp_getter
        self._clan_quest_getter = clan_quest_getter
        self._parse_time_getter = parse_time_getter
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self.declare_cost = declare_cost
        self.reward = reward
        self.reward_per_level = reward_per_level
        self.cooldown_hours = cooldown_hours
        self.attack_cooldown_hours = attack_cooldown_hours
        self.damage_rate = damage_rate
        self.war_duration_hours = war_duration_hours
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    async def get_active_clan_war(self, clan_id: int):
        return await self._active_war_getter()(clan_id)

    async def get_clan_power(self, clan_id: int):
        return await self._clan_power_getter()(clan_id)

    async def get_clan_level_info(self, clan_id: int):
        return await self._clan_level_getter()(clan_id)

    async def get_combat_power(self, user_id: int):
        return await self._combat_power_getter()(user_id)

    async def log_clan(self, *args, **kwargs) -> None:
        await self._log_clan_getter()(*args, **kwargs)

    async def add_clan_xp(self, *args, **kwargs):
        return await self._add_clan_xp_getter()(*args, **kwargs)

    async def update_clan_quest(self, *args, **kwargs) -> None:
        await self._clan_quest_getter()(*args, **kwargs)

    def parse_db_time(self, value):
        return self._parse_time_getter()(value)

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    async def fix_emojis(self, embed):
        return await self._emoji_fixer(embed)


def make_clan_war_layer(runtime: ClanWarRuntime):
    """Возвращает clan war-функции, привязанные к runtime."""

    async def start_clan_war(clan_id: int, enemy_id: int) -> int:
        if clan_id == enemy_id:
            raise ValueError("Нельзя объявить войну самому себе.")
        async with runtime.transaction():
            if await runtime.get_active_clan_war(clan_id):
                raise ValueError(
                    "У твоего клана уже есть активная война."
                )
            if await runtime.get_active_clan_war(enemy_id):
                raise ValueError(
                    "У этого клана уже есть активная война."
                )
            async with runtime.db.execute(
                "SELECT end_time FROM clan_wars "
                "WHERE (clan1_id = ? OR clan2_id = ?) "
                "AND status = 'finished' "
                "ORDER BY end_time DESC LIMIT 1",
                (clan_id, clan_id),
            ) as c:
                last_war = await c.fetchone()
            if last_war and last_war[0]:
                last_end = runtime.parse_db_time(last_war[0])
                if last_end:
                    elapsed = (
                        datetime.datetime.now() - last_end
                    ).total_seconds()
                    if elapsed < runtime.cooldown_hours * 3600:
                        left = int(
                            (
                                runtime.cooldown_hours * 3600 - elapsed
                            )
                            // 60
                        )
                        raise ValueError(
                            f"⏳ Новая война доступна через {left} мин."
                        )
            async with runtime.db.execute(
                "SELECT treasury FROM clans WHERE id = ?", (clan_id,)
            ) as c:
                row = await c.fetchone()
            if not row:
                raise ValueError("Клан не найден.")
            if (row[0] or 0) < runtime.declare_cost:
                raise ValueError(
                    f"Нужно 🪙 {runtime.declare_cost} в сундуке "
                    "для объявления войны."
                )
            async with runtime.db.execute(
                "SELECT 1 FROM clans WHERE id = ?", (enemy_id,)
            ) as c:
                if not await c.fetchone():
                    raise ValueError("Клан-противник не найден.")

            p1 = await runtime.get_clan_power(clan_id)
            p2 = await runtime.get_clan_power(enemy_id)
            hp1 = max(100, int(p1 * 0.5))
            hp2 = max(100, int(p2 * 0.5))

            await runtime.db.execute(
                "UPDATE clans SET treasury = treasury - ? WHERE id = ?",
                (runtime.declare_cost, clan_id),
            )
            cursor = await runtime.db.execute(
                """
                INSERT INTO clan_wars
                (clan1_id, clan2_id, start_time, status,
                 clan1_hp, clan2_hp, clan1_max_hp, clan2_max_hp,
                 clan1_damage, clan2_damage)
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?, 0, 0)
                """,
                (
                    clan_id,
                    enemy_id,
                    datetime.datetime.now().isoformat(),
                    hp1,
                    hp2,
                    hp1,
                    hp2,
                ),
            )
            war_id = cursor.lastrowid

        await runtime.log_clan(
            clan_id, "war_declared", f"Против клана {enemy_id}"
        )
        await runtime.log_clan(
            enemy_id, "war_declared", f"Война с кланом {clan_id}"
        )
        return war_id

    async def attack_clan_war(
        war_id: int, user_id: int
    ) -> tuple[bool, str, bool]:
        damage = 0
        new_enemy_hp = 0
        finished = False
        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT clan_id FROM clan_members "
                    "WHERE user_id = ? LIMIT 1",
                    (user_id,),
                ) as c:
                    member = await c.fetchone()
                if not member:
                    raise ValueError("❌ Ты не в клане.")
                clan_id = member[0]

                async with runtime.db.execute(
                    """
                    SELECT id, clan1_id, clan2_id, status, start_time,
                           clan1_hp, clan2_hp, clan1_max_hp, clan2_max_hp,
                           clan1_damage, clan2_damage
                    FROM clan_wars WHERE id = ?
                    """,
                    (war_id,),
                ) as c:
                    war = await c.fetchone()
                if not war:
                    raise ValueError("❌ Война не найдена.")
                (
                    _,
                    c1,
                    c2,
                    status,
                    start_time,
                    c1_hp,
                    c2_hp,
                    c1_max,
                    c2_max,
                    c1_dmg,
                    c2_dmg,
                ) = war
                c1_hp = c1_hp or 0
                c2_hp = c2_hp or 0
                c1_dmg = c1_dmg or 0
                c2_dmg = c2_dmg or 0
                if status != "active":
                    raise ValueError("❌ Война уже завершена.")
                start = runtime.parse_db_time(start_time)
                if start and (
                    datetime.datetime.now() - start
                ).total_seconds() > runtime.war_duration_hours * 3600:
                    raise ValueError("❌ Время войны истекло.")
                if clan_id not in (c1, c2):
                    raise ValueError(
                        "❌ Твой клан не участвует в этой войне."
                    )

                async with runtime.db.execute(
                    """
                    SELECT timestamp FROM clan_war_attacks
                    WHERE war_id = ? AND attacker_id = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (war_id, user_id),
                ) as c:
                    last_attack = await c.fetchone()
                now = datetime.datetime.now()
                if last_attack and last_attack[0]:
                    last = runtime.parse_db_time(last_attack[0])
                    if last:
                        left = (
                            runtime.attack_cooldown_hours * 3600
                            - (now - last).total_seconds()
                        )
                        if left > 0:
                            raise ValueError(
                                f"⏳ Атака будет доступна через "
                                f"{int(left // 60)} мин."
                            )

                power = await runtime.get_combat_power(user_id)
                if power <= 0:
                    raise ValueError(
                        "❌ У тебя нет генераторов на энергостанции."
                    )

                level, _, _ = await runtime.get_clan_level_info(clan_id)
                reward = runtime.reward + max(
                    0, level - 1
                ) * runtime.reward_per_level
                level_mult = 1 + max(0, level - 1) * 0.01
                damage = max(
                    1,
                    int(
                        power
                        * runtime.damage_rate
                        * random.uniform(0.8, 1.2)
                        * level_mult
                    ),
                )

                if clan_id == c1:
                    new_enemy_hp = max(0, c2_hp - damage)
                    own_damage = c1_dmg + damage
                    await runtime.db.execute(
                        "UPDATE clan_wars SET clan2_hp = ?, "
                        "clan1_damage = ? "
                        "WHERE id = ? AND status = 'active'",
                        (new_enemy_hp, own_damage, war_id),
                    )
                else:
                    new_enemy_hp = max(0, c1_hp - damage)
                    own_damage = c2_dmg + damage
                    await runtime.db.execute(
                        "UPDATE clan_wars SET clan1_hp = ?, "
                        "clan2_damage = ? "
                        "WHERE id = ? AND status = 'active'",
                        (new_enemy_hp, own_damage, war_id),
                    )

                await runtime.db.execute(
                    "INSERT INTO clan_war_attacks "
                    "(war_id, attacker_id, attacker_clan_id, damage, "
                    "timestamp) VALUES (?, ?, ?, ?, ?)",
                    (
                        war_id,
                        user_id,
                        clan_id,
                        damage,
                        now.isoformat(),
                    ),
                )

                finished = new_enemy_hp <= 0
                if finished:
                    await runtime.db.execute(
                        "UPDATE clan_wars SET status = 'finished', "
                        "winner_id = ?, end_time = ? "
                        "WHERE id = ? AND status = 'active'",
                        (clan_id, now.isoformat(), war_id),
                    )
                    await runtime.db.execute(
                        "UPDATE clans SET treasury = treasury + ? "
                        "WHERE id = ?",
                        (reward, clan_id),
                    )
        except ValueError as exc:
            return False, str(exc), False

        if finished:
            await runtime.log_clan(
                clan_id, "war_win", f"Война #{war_id}, урон {damage}"
            )
            await runtime.add_clan_xp(clan_id, 200)
            await runtime.update_clan_quest(clan_id, "war", 1)
            return (
                True,
                f"🏆 Победа! Урон {damage}. "
                f"Клан получает 🪙 {reward} в сундук.",
                True,
            )

        return (
            True,
            f"⚔️ Удар на **{damage}** урона. "
            f"У врага осталось **{new_enemy_hp}** HP.",
            False,
        )

    async def build_clan_war_embed(interaction, war, clan_id: int):
        (
            war_id,
            c1,
            c2,
            start_time,
            c1_hp,
            c2_hp,
            c1_max,
            c2_max,
            c1_dmg,
            c2_dmg,
        ) = war

        async with runtime.db.execute(
            "SELECT id, name FROM clans WHERE id IN (?, ?)",
            (c1, c2),
        ) as c:
            names = {r[0]: r[1] for r in await c.fetchall()}

        own_id = clan_id
        enemy_id = c2 if clan_id == c1 else c1
        own_name = names.get(own_id, f"Клан {own_id}")
        enemy_name = names.get(enemy_id, f"Клан {enemy_id}")

        if clan_id == c1:
            own_hp, own_max = c1_hp or 0, c1_max or 1
            enemy_hp, enemy_max = c2_hp or 0, c2_max or 1
            own_dmg, enemy_dmg = c1_dmg or 0, c2_dmg or 0
        else:
            own_hp, own_max = c2_hp or 0, c2_max or 1
            enemy_hp, enemy_max = c1_hp or 0, c1_max or 1
            own_dmg, enemy_dmg = c2_dmg or 0, c1_dmg or 0

        def hp_bar(current: int, maximum: int) -> str:
            pct = max(
                0.0, min(1.0, current / max(1, maximum))
            )
            filled = int(pct * 10)
            return "🟩" * filled + "⬛" * (10 - filled)

        end = datetime.datetime.fromisoformat(
            start_time
        ) + datetime.timedelta(hours=runtime.war_duration_hours)
        left = max(
            0,
            int(
                (
                    end - datetime.datetime.now()
                ).total_seconds()
            ),
        )
        hours = left // 3600
        minutes = (left % 3600) // 60

        embed = runtime.embed(
            title=f"⚔️ Клановая война #{war_id}",
            description=(
                f"**{own_name}** против **{enemy_name}**\n"
                f"До конца: **{hours} ч {minutes} мин**"
            ),
            color=0xE74C3C,
        )
        embed.add_field(
            name=f"🏰 {own_name}",
            value=(
                f"HP: **{own_hp}/{own_max}**\n"
                f"{hp_bar(own_hp, own_max)}\n"
                f"Урон: **{own_dmg}**"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"🏴 {enemy_name}",
            value=(
                f"HP: **{enemy_hp}/{enemy_max}**\n"
                f"{hp_bar(enemy_hp, enemy_max)}\n"
                f"Урон: **{enemy_dmg}**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Правила",
            value=(
                f"• Одна атака раз в "
                f"**{runtime.attack_cooldown_hours} ч**\n"
                f"• Урон — около "
                f"**{int(runtime.damage_rate * 100)}%** мощи\n"
                f"• Победитель забирает 🪙 "
                f"**{runtime.reward}** + "
                f"**{runtime.reward_per_level}** за уровень клана"
            ),
            inline=False,
        )
        return await runtime.fix_emojis(embed)

    return start_clan_war, attack_clan_war, build_clan_war_embed
