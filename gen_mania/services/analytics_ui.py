"""Detailed player analytics embed."""
from __future__ import annotations

import logging
from typing import Any, Callable


class AnalyticsUiRuntime:
    """Адаптер между bot.py и аналитикой."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._accessibility_getter: Callable[[], Callable] = lambda: None
        self._status_bonus_getter: Callable[[], Callable] = lambda: None
        self._income_getter: Callable[[], Callable] = lambda: None
        self._power_getter: Callable[[], Callable] = lambda: None
        self._sets_getter: Callable[[], Callable] = lambda: None
        self._season_getter: Callable[[], Callable] = lambda: None
        self._pet_getter: Callable[[], Callable] = lambda: None
        self._titles_getter: Callable[[], Callable] = lambda: None
        self._prestige_getter: Callable[[], Callable] = lambda: None
        self._collection_getter: Callable[[], Callable] = lambda: None
        self._bonus_line_getter: Callable[[], Callable] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self.pet_types: dict = {}
        self.titles: dict = {}
        self.castle = "⚡"
        self.season_levels = 30
        self.collection_bonus = 0.005
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        accessibility_getter: Callable[[], Callable],
        status_bonus_getter: Callable[[], Callable],
        income_getter: Callable[[], Callable],
        power_getter: Callable[[], Callable],
        sets_getter: Callable[[], Callable],
        season_getter: Callable[[], Callable],
        pet_getter: Callable[[], Callable],
        titles_getter: Callable[[], Callable],
        prestige_getter: Callable[[], Callable],
        collection_getter: Callable[[], Callable],
        bonus_line_getter: Callable[[], Callable],
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        pet_types: dict,
        titles: dict,
        castle: str,
        season_levels: int,
        collection_bonus: float,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._accessibility_getter = accessibility_getter
        self._status_bonus_getter = status_bonus_getter
        self._income_getter = income_getter
        self._power_getter = power_getter
        self._sets_getter = sets_getter
        self._season_getter = season_getter
        self._pet_getter = pet_getter
        self._titles_getter = titles_getter
        self._prestige_getter = prestige_getter
        self._collection_getter = collection_getter
        self._bonus_line_getter = bonus_line_getter
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self.pet_types = pet_types
        self.titles = titles
        self.castle = castle
        self.season_levels = season_levels
        self.collection_bonus = collection_bonus
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    async def is_accessibility_mode(self, user_id: int):
        return await self._accessibility_getter()(user_id)

    async def get_status_bonus(self, user_id: int):
        return await self._status_bonus_getter()(user_id)

    async def get_income(self, user_id: int):
        return await self._income_getter()(user_id)

    async def get_power(self, user_id: int):
        return await self._power_getter()(user_id)

    async def get_sets(self, user_id: int):
        return await self._sets_getter()(user_id)

    async def get_season(self, user_id: int):
        return await self._season_getter()(user_id)

    async def get_active_pet(self, user_id: int):
        return await self._pet_getter()(user_id)

    async def get_unlocked_titles(self, user_id: int):
        return await self._titles_getter()(user_id)

    async def get_prestige_points(self, user_id: int):
        return await self._prestige_getter()(user_id)

    async def get_collection_count(self, user_id: int):
        return await self._collection_getter()(user_id)

    async def get_bonus_line(self, user_id: int):
        return await self._bonus_line_getter()(user_id)

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    async def fix_emojis(self, embed):
        return await self._emoji_fixer(embed)


def make_analytics_ui_layer(runtime: AnalyticsUiRuntime):
    """Возвращает ``build_analytics_embed``, привязанный к runtime."""

    async def build_analytics_embed(interaction):
        user_id = interaction.user.id
        compact = await runtime.is_accessibility_mode(user_id)

        async with runtime.db.execute(
            """
            SELECT coins, gems, catalysts, total_crafts,
                   total_successes, grid_size, title
            FROM players WHERE user_id = ?
            """,
            (user_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            embed = runtime.embed(
                title="❌ Профиль не найден", color=0xe74c3c
            )
            return await runtime.fix_emojis(embed)

        (
            coins,
            gems,
            catalysts,
            crafts,
            successes,
            grid_size,
            title,
        ) = row
        successes = successes or 0
        crafts = crafts or 0
        winrate = (successes / crafts * 100) if crafts > 0 else 0.0

        per_sec_coins, per_sec_gems = await runtime.get_income(user_id)
        income_coins_h = per_sec_coins * 3600
        income_gems_h = per_sec_gems * 3600

        async with runtime.db.execute(
            """
            SELECT COUNT(*),
                   SUM(CASE WHEN i.income_per_hour > 0
                            THEN 1 ELSE 0 END),
                   MAX(i.price)
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND inv.location = 'profile'
            """,
            (user_id,),
        ) as c:
            gens_total, gens_income, best_price = await c.fetchone()
        gens_total = gens_total or 0
        gens_income = gens_income or 0
        best_price = best_price or 0

        avg_income = (
            (income_coins_h / gens_income) if gens_income > 0 else 0
        )
        power = await runtime.get_power(user_id)
        set_details = await runtime.get_sets(user_id)
        season_data = await runtime.get_season(user_id)

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM market_orders "
            "WHERE user_id = ? AND status = 'active'",
            (user_id,),
        ) as c:
            active_orders = (await c.fetchone())[0] or 0
        async with runtime.db.execute(
            "SELECT amount, due_time FROM bank_loans "
            "WHERE user_id = ? AND COALESCE(status, 'active') = 'active'",
            (user_id,),
        ) as c:
            loan_row = await c.fetchone()

        async with runtime.db.execute(
            "SELECT COUNT(*), MAX(level) FROM user_pets_v2 "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            pet_count, pet_max = await c.fetchone()
        pet_count = pet_count or 0
        pet_max = pet_max or 0
        active_pet = await runtime.get_active_pet(user_id)
        active_pet_str = "нет"
        if active_pet:
            pid, lvl = active_pet
            pt = runtime.pet_types.get(pid)
            if pt:
                active_pet_str = (
                    f"{pt['emoji']} {pt['name']} (ур. {lvl})"
                )

        unlocked_titles = await runtime.get_unlocked_titles(user_id)

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM duel_history "
            "WHERE winner_id = ?",
            (user_id,),
        ) as c:
            duel_wins = (await c.fetchone())[0] or 0
        async with runtime.db.execute(
            "SELECT COUNT(*) FROM duel_history "
            "WHERE loser_id = ?",
            (user_id,),
        ) as c:
            duel_losses = (await c.fetchone())[0] or 0
        duel_total = duel_wins + duel_losses
        duel_wr = (
            (duel_wins / duel_total * 100) if duel_total > 0 else 0.0
        )

        async with runtime.db.execute(
            "SELECT progress FROM player_quests "
            "WHERE user_id = ? AND quest_id = 'q_raid_1'",
            (user_id,),
        ) as c:
            r = await c.fetchone()
            raid_wins = r[0] if r else 0

        async with runtime.db.execute(
            "SELECT amount, interest_rate, end_time "
            "FROM bank_deposits WHERE user_id = ?",
            (user_id,),
        ) as c:
            deposit = await c.fetchone()
        deposit_str = "нет"
        if deposit:
            amt, rate, end = deposit
            deposit_str = f"🪙 {amt} ({int(rate * 100)}%)"

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM tax_log WHERE user_id = ?",
            (user_id,),
        ) as c:
            tax_count = (await c.fetchone())[0] or 0

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM auctions WHERE seller_id = ?",
            (user_id,),
        ) as c:
            auction_sold = (await c.fetchone())[0] or 0

        async with runtime.db.execute(
            "SELECT lifetime_production, total_gems_earned "
            "FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            tce, tge = await c.fetchone()

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM player_achievements "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            ach_count = (await c.fetchone())[0] or 0

        prestige_points = await runtime.get_prestige_points(user_id)
        collection_count = await runtime.get_collection_count(user_id)

        embed = runtime.embed(
            title=f"📈 Аналитика — {interaction.user.name}",
            description="Подробная статистика твоего прогресса.",
            color=0x3498db,
        )
        if not compact:
            embed.set_thumbnail(
                url=interaction.user.display_avatar.url
            )

        embed.add_field(
            name="📊 Всего заработано",
            value=f"🪙 {tce or 0}\n💎 {tge or 0}",
            inline=True,
        )

        total_bonus_line = await runtime.get_bonus_line(user_id)
        embed.add_field(
            name="💰 Доход",
            value=(
                f"🪙 {income_coins_h:.2f}/час\n"
                f"💎 {income_gems_h:.4f}/час\n"
                f"{total_bonus_line}"
            ),
            inline=True,
        )

        embed.add_field(
            name=f"{runtime.castle} Энергостанция",
            value=(
                f"Генераторов: **{gens_total}**\n"
                f"Доходных: **{gens_income}**\n"
                f"Средний: 🪙 {avg_income:.2f}/час\n"
                f"Сетка: **{grid_size}**\n"
                f"⚔️ Мощь: **{power}**"
            ),
            inline=True,
        )

        embed.add_field(
            name="🧩 Коллекция и сеты",
            value=(
                f"Коллекция: **{collection_count}**\n"
                f"Бонус коллекции: "
                f"**+{collection_count * runtime.collection_bonus * 100:.1f}%**\n"
                f"Сеты: **+{int(set_details['total'] * 100)}%**\n"
                f"Сезон: **{season_data['level']}/"
                f"{runtime.season_levels}**"
            ),
            inline=True,
        )

        embed.add_field(
            name="⚗️ Синтез",
            value=(
                f"Попыток: **{crafts}**\n"
                f"Успехов: **{successes}**\n"
                f"Винрейт: **{winrate:.1f}%**\n"
                f"Катализаторов: **{catalysts}**"
            ),
            inline=True,
        )

        embed.add_field(
            name="🐾 Питомцы",
            value=(
                f"Куплено: **{pet_count}**\n"
                f"Лучший ур.: **{pet_max}**\n"
                f"Активный: {active_pet_str}"
            ),
            inline=True,
        )

        embed.add_field(
            name="🏅 Титулы",
            value=(
                f"Активный: **{title or 'Новичок'}**\n"
                f"Открыто: **{len(unlocked_titles)}/"
                f"{len(runtime.titles)}**"
            ),
            inline=True,
        )

        embed.add_field(
            name="⚔️ PvP",
            value=(
                f"Дуэли: **{duel_wins}W / {duel_losses}L** "
                f"({duel_wr:.1f}%)\n"
                f"Рейды (победы): **{raid_wins}**"
            ),
            inline=True,
        )

        loan_text = "нет"
        if loan_row:
            loan_text = (
                f"🪙 {loan_row[0]} до {str(loan_row[1])[:10]}"
            )
        embed.add_field(
            name="🏦 Экономика",
            value=(
                f"Вклад: {deposit_str}\n"
                f"Кредит: {loan_text}\n"
                f"Активных ордеров: **{active_orders}**\n"
                f"Налогов: **{tax_count}**\n"
                f"Лотов продано: **{auction_sold}**"
            ),
            inline=True,
        )

        embed.add_field(
            name="🏆 Прогресс",
            value=(
                f"Достижений: **{ach_count}**\n"
                f"Престиж: **{prestige_points}** очк.\n"
                f"Коллекция: **{collection_count}**\n"
                f"Гемов: **{gems}**\n"
                f"Монет: **{coins}**"
            ),
            inline=True,
        )
        return await runtime.fix_emojis(embed)

    return build_analytics_embed
