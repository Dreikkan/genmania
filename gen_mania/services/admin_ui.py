"""Admin panel embeds."""
from __future__ import annotations

import logging
from typing import Any, Callable


class AdminUiRuntime:
    """Адаптер между bot.py и админ-UI."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._price_formatter: Callable[[int], str] = str
        self.start_grid = 9
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        embed_factory: Callable[..., Any],
        emoji_getter: Callable[[], Callable],
        price_formatter: Callable[[int], str],
        start_grid: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._embed_factory = embed_factory
        self._emoji_getter = emoji_getter
        self._price_formatter = price_formatter
        self.start_grid = start_grid
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    def emoji(self, key: str):
        return self._emoji_getter()(key)

    def format_price(self, value: int) -> str:
        return self._price_formatter(value)


def make_admin_ui_layer(runtime: AdminUiRuntime):
    """Возвращает admin-embed-функции, привязанные к runtime."""

    async def build_admin_player_card(user_id: int):
        async with runtime.db.execute(
            "SELECT coins, gems, prestige_points, title, grid_size, "
            "lifetime_production, last_collected, last_tax_time "
            "FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            return runtime.embed(
                title="❌ Игрок не найден",
                description=f"В базе нет профиля <@{user_id}>.",
                color=0xe74c3c,
            )

        (
            coins,
            gems,
            points,
            title,
            grid,
            lifetime,
            last_col,
            last_tax,
        ) = row
        embed = runtime.embed(
            title=f"👤 Карточка игрока — {title or 'Новичок'}",
            description=f"<@{user_id}> · `{user_id}`",
            color=0x3498db,
        )
        embed.add_field(
            name="Баланс",
            value=(
                f"🪙 {runtime.format_price(coins or 0)} | "
                f"💎 {runtime.format_price(gems or 0)}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Прогресс",
            value=(
                f"Престиж: **{points or 0}** · "
                f"Сетка: **{grid or runtime.start_grid}**\n"
                f"Всего произведено: "
                f"**{runtime.format_price(lifetime or 0)}**"
            ),
            inline=False,
        )

        async with runtime.db.execute(
            "SELECT c.name, cm.role FROM clan_members cm "
            "JOIN clans c ON c.id = cm.clan_id "
            "WHERE cm.user_id = ?",
            (user_id,),
        ) as c:
            clan_row = await c.fetchone()
        embed.add_field(
            name="Клан",
            value=(
                f"**{clan_row[0]}** ({clan_row[1]})"
                if clan_row
                else "не состоит в клане"
            ),
            inline=True,
        )

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM market_orders "
            "WHERE user_id = ? AND status = 'active'",
            (user_id,),
        ) as c:
            orders = (await c.fetchone())[0] or 0
        async with runtime.db.execute(
            "SELECT amount, end_time FROM bank_deposits "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            deposit = await c.fetchone()
        async with runtime.db.execute(
            "SELECT amount, due_time FROM bank_loans "
            "WHERE user_id = ? AND COALESCE(status, 'active') = 'active'",
            (user_id,),
        ) as c:
            loan = await c.fetchone()
        embed.add_field(
            name="Обязательства",
            value=(
                f"Ордера: **{orders}**\n"
                f"Вклад: "
                f"{'**' + runtime.format_price(deposit[0]) + '**' if deposit else 'нет'}\n"
                f"Кредит: "
                f"{'**' + runtime.format_price(loan[0]) + '**' if loan else 'нет'}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Активность",
            value=(
                f"Сбор: `{str(last_col)[:16]}`\n"
                f"Налог: `{str(last_tax)[:16]}`"
            ),
            inline=False,
        )
        return embed

    def build_admin_season_embed(enabled: bool):
        status = "включён" if enabled else "отключён"
        color = 0x2ecc71 if enabled else 0xe74c3c
        return runtime.embed(
            title=f"{runtime.emoji('_advent')} Управление баттлпассом",
            description=(
                f"Статус: **{status}**\n\n"
                "Отключение скрывает сезонный экран и блокирует "
                "начисление XP за действия в этом сервере. "
                "Прогресс игроков сохраняется."
            ),
            color=color,
        )

    async def build_admin_market_embed():
        async with runtime.db.execute(
            "SELECT status, COUNT(*) FROM market_orders "
            "GROUP BY status"
        ) as c:
            status_rows = await c.fetchall()
        counts = {
            status: count for status, count in status_rows
        }
        async with runtime.db.execute(
            "SELECT side, COUNT(*) FROM market_orders "
            "WHERE status = 'active' GROUP BY side"
        ) as c:
            side_rows = await c.fetchall()
        sides = {side: count for side, count in side_rows}
        return runtime.embed(
            title=f"{runtime.emoji('_market')} Управление биржей",
            description=(
                f"Активных ордеров: **{counts.get('active', 0)}**\n"
                f"На покупку: **{sides.get('buy', 0)}** · "
                f"На продажу: **{sides.get('sell', 0)}**\n"
                f"Истёкших: **{counts.get('expired', 0)}** · "
                f"Отменённых: **{counts.get('cancelled', 0)}**"
            ),
            color=0x9b59b6,
        )

    return (
        build_admin_player_card,
        build_admin_season_embed,
        build_admin_market_embed,
    )
