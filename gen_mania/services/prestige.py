"""Prestige progression and rebirth service."""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable

import aiosqlite


class PrestigeRuntime:
    """Адаптер между bot.py и сервисом престижа."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._settings_getter: Callable[[], Callable] = lambda: None
        self._release_bids_getter: Callable[[], Callable] = lambda: None
        self._statuses_getter: Callable[[], Callable] = lambda: None
        self._status_bonus_getter: Callable[[], Callable] = lambda: None
        self._season_xp_getter: Callable[[], Callable] = lambda: None
        self._season_xp_amount_getter: Callable[[], Callable] = lambda: None
        self._prestige_points_getter: Callable[[], Callable] = lambda: None
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self._price_formatter: Callable[[int], str] = str
        self.default_start_coins = 8
        self.max_start_coins = 100
        self.base_requirement = 150_000
        self.step_requirement = 50_000
        self.bonus_per_point = 0.05
        self.bonus_cap = 5.0
        self.start_grid = 9
        self.storage_size = 36
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        settings_getter: Callable[[], Callable],
        release_bids_getter: Callable[[], Callable],
        statuses_getter: Callable[[], Callable],
        status_bonus_getter: Callable[[], Callable],
        season_xp_getter: Callable[[], Callable],
        season_xp_amount_getter: Callable[[], Callable],
        prestige_points_getter: Callable[[], Callable],
        emoji_getter: Callable[[], Callable],
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        price_formatter: Callable[[int], str],
        default_start_coins: int,
        max_start_coins: int,
        base_requirement: int,
        step_requirement: int,
        bonus_per_point: float,
        bonus_cap: float,
        start_grid: int,
        storage_size: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._settings_getter = settings_getter
        self._release_bids_getter = release_bids_getter
        self._statuses_getter = statuses_getter
        self._status_bonus_getter = status_bonus_getter
        self._season_xp_getter = season_xp_getter
        self._season_xp_amount_getter = season_xp_amount_getter
        self._prestige_points_getter = prestige_points_getter
        self._emoji_getter = emoji_getter
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self._price_formatter = price_formatter
        self.default_start_coins = default_start_coins
        self.max_start_coins = max_start_coins
        self.base_requirement = base_requirement
        self.step_requirement = step_requirement
        self.bonus_per_point = bonus_per_point
        self.bonus_cap = bonus_cap
        self.start_grid = start_grid
        self.storage_size = storage_size
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    async def get_settings(self, guild_id: int):
        return await self._settings_getter()(guild_id)

    async def release_bids(self, user_id: int):
        return await self._release_bids_getter()(user_id)

    async def get_active_statuses(self, user_id: int):
        return await self._statuses_getter()(user_id)

    def best_status_bonus(self, statuses):
        return self._status_bonus_getter()(statuses)

    async def add_season_xp(self, *args, **kwargs) -> None:
        await self._season_xp_getter()(*args, **kwargs)

    def season_xp_amount(self, action: str):
        return self._season_xp_amount_getter()(action)

    async def get_prestige_points(self, user_id: int):
        return await self._prestige_points_getter()(user_id)

    def emoji(self, key: str):
        return self._emoji_getter()(key)

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    async def fix_emojis(self, embed):
        return await self._emoji_fixer(embed)

    def format_price(self, value: int) -> str:
        return self._price_formatter(value)


def make_prestige_layer(runtime: PrestigeRuntime):
    """Возвращает prestige-функции, привязанные к runtime."""

    def prestige_point_cost(points_earned: int) -> int:
        """Стоимость следующего очка с учётом уже полученных."""
        return (
            runtime.base_requirement
            + max(0, int(points_earned)) * runtime.step_requirement
        )

    def prestige_gain_from_lifetime(
        lifetime: int, existing_points: int
    ) -> int:
        """Сколько новых очков даёт текущее производство.

        Стоимость очков — арифметическая прогрессия, поэтому считаем
        сумму через формулу и бинарный поиск, без цикла по каждому очку.
        """
        budget = max(0, int(lifetime or 0))
        points = max(0, int(existing_points or 0))
        if budget < prestige_point_cost(points):
            return 0

        def total_cost(count: int) -> int:
            return (
                count * runtime.base_requirement
                + runtime.step_requirement
                * (count * points + count * (count - 1) // 2)
            )

        high = 1
        while total_cost(high) <= budget:
            high *= 2
        low = 0
        while low + 1 < high:
            middle = (low + high) // 2
            if total_cost(middle) <= budget:
                low = middle
            else:
                high = middle
        return low

    def prestige_points_from_lifetime(total: int) -> int:
        """Сколько всего очков заработано при данном производстве."""
        return prestige_gain_from_lifetime(total, 0)

    async def calculate_prestige_gain(user_id: int) -> int:
        async with runtime.db.execute(
            "SELECT lifetime_production, prestige_points "
            "FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            return 0
        total, points = row
        return prestige_gain_from_lifetime(total or 0, points or 0)

    async def do_prestige(
        user_id: int, guild_id: int | None = None
    ) -> tuple[bool, str, int, int]:
        settings = (
            await runtime.get_settings(guild_id)
            if guild_id
            else {"start_coins": runtime.default_start_coins}
        )
        start_coins = min(
            int(settings["start_coins"]), runtime.max_start_coins
        )
        points = await runtime.get_prestige_points(user_id)
        released_bids = 0

        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT lifetime_production, prestige_points "
                    "FROM players WHERE user_id = ?",
                    (user_id,),
                ) as c:
                    row = await c.fetchone()
                if not row:
                    raise ValueError("Профиль не найден.")

                total, points = row
                points = points or 0
                gain = prestige_gain_from_lifetime(
                    total or 0, points
                )
                if gain <= 0:
                    need = prestige_point_cost(points) - (total or 0)
                    raise ValueError(
                        f"Нужно ещё 🪙 {max(0, need)} производства для "
                        f"следующего очка."
                    )

                for label, sql in (
                    (
                        "вклад",
                        "SELECT 1 FROM bank_deposits WHERE user_id = ?",
                    ),
                    (
                        "кредит",
                        "SELECT 1 FROM bank_loans WHERE user_id = ? "
                        "AND COALESCE(status, 'active') = 'active'",
                    ),
                    (
                        "ордера",
                        "SELECT 1 FROM market_orders WHERE user_id = ? "
                        "AND status = 'active'",
                    ),
                    (
                        "аукционы",
                        "SELECT 1 FROM auctions WHERE seller_id = ? "
                        "AND status = 'active'",
                    ),
                    (
                        "почту",
                        "SELECT 1 FROM mailbox WHERE user_id = ?",
                    ),
                ):
                    try:
                        async with runtime.db.execute(
                            sql, (user_id,)
                        ) as c:
                            if await c.fetchone():
                                raise ValueError(
                                    f"Сначала закрой {label}: "
                                    "перерождение не должно терять "
                                    "активные обязательства."
                                )
                    except aiosqlite.OperationalError:
                        # Очень старые/упрощённые схемы могут не иметь
                        # соответствующей таблицы.
                        continue

                # Снимаем ставки игрока на чужих лотах.
                released_bids, _refunded = await runtime.release_bids(
                    user_id
                )

                # Закрываем активные лоты игрока и возвращаем ставки.
                async with runtime.db.execute(
                    "SELECT id, current_bidder, current_bid FROM auctions "
                    "WHERE seller_id = ? AND status = 'active'",
                    (user_id,),
                ) as c:
                    lots = await c.fetchall()
                for aid, bidder, bid in lots:
                    if bidder and bid:
                        await runtime.db.execute(
                            "UPDATE players SET coins = coins + ? "
                            "WHERE user_id = ?",
                            (bid, bidder),
                        )
                    await runtime.db.execute(
                        "DELETE FROM auction_bids WHERE auction_id = ?",
                        (aid,),
                    )
                    await runtime.db.execute(
                        "DELETE FROM auctions WHERE id = ?", (aid,)
                    )

                now_iso = datetime.datetime.now().isoformat()
                try:
                    await runtime.db.execute(
                        "DELETE FROM player_upgrades WHERE user_id = ? "
                        "AND upgrade_id IN "
                        "('vip','gold','platinum','diamond') "
                        "AND expires_at IS NOT NULL "
                        "AND datetime(expires_at) <= datetime(?)",
                        (user_id, now_iso),
                    )
                except aiosqlite.OperationalError:
                    # Совместимость с очень старыми/упрощёнными схемами.
                    pass
                active_statuses = await runtime.get_active_statuses(
                    user_id
                )
                status_bonus = runtime.best_status_bonus(
                    active_statuses.keys()
                )

                await runtime.db.execute(
                    """
                    UPDATE players SET
                        coins = ?,
                        grid_size = ?,
                        storage_size = ?,
                        income_bonus = ?,
                        catalysts = 0,
                        lifetime_production = 0,
                        prestige_points = prestige_points + ?,
                        daily_quest_date = NULL,
                        daily_quest_progress = '{}',
                        daily_quest_claimed = '[]',
                        last_collected = CURRENT_TIMESTAMP,
                        last_gem_collected = CURRENT_TIMESTAMP,
                        last_tax_time = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    """,
                    (
                        start_coins,
                        runtime.start_grid,
                        runtime.storage_size,
                        status_bonus,
                        gain,
                        user_id,
                    ),
                )

                await runtime.db.execute(
                    "DELETE FROM inventory WHERE user_id = ?",
                    (user_id,),
                )
                await runtime.db.execute(
                    "DELETE FROM market_orders WHERE user_id = ?",
                    (user_id,),
                )
                # Сетки сбрасываются вместе с энергостанцией, а активные
                # временные статусы сохраняются до своего expires_at.
                await runtime.db.execute(
                    "DELETE FROM player_upgrades WHERE user_id = ? "
                    "AND (upgrade_id IS NULL OR upgrade_id NOT IN "
                    "('vip','gold','platinum','diamond'))",
                    (user_id,),
                )
                await runtime.db.execute(
                    "DELETE FROM bank_deposits WHERE user_id = ?",
                    (user_id,),
                )
                await runtime.db.execute(
                    "DELETE FROM bank_loans WHERE user_id = ?",
                    (user_id,),
                )
                for pity_table in ("craft_pity", "star_pity"):
                    try:
                        await runtime.db.execute(
                            f"DELETE FROM {pity_table} WHERE user_id = ?",
                            (user_id,),
                        )
                    except aiosqlite.OperationalError:
                        continue
        except ValueError as e:
            return False, f"❌ {e}", 0, points

        await runtime.add_season_xp(
            user_id,
            runtime.season_xp_amount("prestige"),
            guild_id,
            action="prestige",
        )
        new_points = points + gain
        bid_note = ""
        if released_bids:
            bid_note = (
                f"\n🏛️ Сняты активные ставки на аукционах: "
                f"**{released_bids}**."
            )
        return (
            True,
            f"{runtime.emoji('_rebirth')} Перерождение завершено! "
            f"Получено **{gain}** очков престижа.\n"
            f"Всего очков: **{new_points}** "
            f"(+{int(min(new_points * runtime.bonus_per_point, runtime.bonus_cap) * 100)}% "
            f"к доходу)."
            f"{bid_note}",
            gain,
            new_points,
        )

    async def build_prestige_embed(interaction):
        user_id = interaction.user.id
        async with runtime.db.execute(
            "SELECT lifetime_production, prestige_points "
            "FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()

        total, points = row if row else (0, 0)
        total = total or 0
        points = points or 0
        gain = prestige_gain_from_lifetime(total, points)
        next_need = (
            max(0, prestige_point_cost(points) - total)
            if gain <= 0
            else 0
        )
        bonus_pct = int(
            min(
                points * runtime.bonus_per_point,
                runtime.bonus_cap,
            )
            * 100
        )

        embed = runtime.embed(
            title="🔁 Перерождение",
            description=(
                "Сбрось текущую энергостанцию и начни заново — "
                "но уже с постоянным бонусом к доходу.\n"
                "Это основной долгосрочный цикл игры."
            ),
            color=0x9B59B6,
        )
        embed.add_field(
            name="Очки престижа",
            value=f"**{points}**",
            inline=True,
        )
        embed.add_field(
            name="Бонус к доходу",
            value=f"**+{bonus_pct}%**",
            inline=True,
        )
        embed.add_field(
            name="Доступно сейчас",
            value=f"**+{gain}** очков",
            inline=True,
        )
        embed.add_field(
            name="Всего заработано",
            value=f"🪙 {runtime.format_price(total)}",
            inline=True,
        )
        embed.add_field(
            name="До следующего очка",
            value=f"🪙 {runtime.format_price(next_need)}",
            inline=True,
        )
        embed.add_field(
            name="Что сбросится",
            value=(
                "монеты, инвентарь, сетка, катализаторы, улучшения, "
                "ежедневные квесты. Вклад, кредит и активные ордера "
                "нужно закрыть заранее."
            ),
            inline=False,
        )
        embed.add_field(
            name="Что останется",
            value=(
                "гемы, питомцы, титулы, статусы "
                "VIP/Gold/Platinum/Diamond, достижения, клан, "
                "косметика, сюжетные квесты, статистика"
            ),
            inline=False,
        )
        embed.set_footer(
            text=(
                "Стоимость: 1-е очко "
                f"{runtime.format_price(runtime.base_requirement)}, "
                "дальше +"
                f"{runtime.format_price(runtime.step_requirement)}; "
                f"макс. бонус +{int(runtime.bonus_cap * 100)}%"
            )
        )
        return await runtime.fix_emojis(embed)

    return (
        prestige_point_cost,
        prestige_gain_from_lifetime,
        prestige_points_from_lifetime,
        calculate_prestige_gain,
        do_prestige,
        build_prestige_embed,
    )
