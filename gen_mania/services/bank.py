"""Bank loans and deposits service."""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable


class BankRuntime:
    """Адаптер между bot.py и банковским сервисом."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._limits_getter: Callable[[], Callable] = lambda: None
        self._compensation_getter: Callable[[], Callable] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._price_formatter: Callable[[int], str] = str
        self.ltv = 0.50
        self.loan_min = 100
        self.loan_term_days = 7
        self.loan_interest = 0.10
        self.daily_rate = 0.02
        self.deposit_income_hours = 24
        self.loan_income_hours = 12
        self.coin = "🪙"
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        limits_getter: Callable[[], Callable],
        compensation_getter: Callable[[], Callable],
        embed_factory: Callable[..., Any],
        emoji_getter: Callable[[], Callable],
        price_formatter: Callable[[int], str],
        ltv: float,
        loan_min: int,
        loan_term_days: int,
        loan_interest: float,
        daily_rate: float,
        deposit_income_hours: int,
        loan_income_hours: int,
        coin: str,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._limits_getter = limits_getter
        self._compensation_getter = compensation_getter
        self._embed_factory = embed_factory
        self._emoji_getter = emoji_getter
        self._price_formatter = price_formatter
        self.ltv = ltv
        self.loan_min = loan_min
        self.loan_term_days = loan_term_days
        self.loan_interest = loan_interest
        self.daily_rate = daily_rate
        self.deposit_income_hours = deposit_income_hours
        self.loan_income_hours = loan_income_hours
        self.coin = coin
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    async def get_bank_limits(self, user_id: int) -> tuple[int, int]:
        return await self._limits_getter()(user_id)

    async def grant_compensation(self, *args, **kwargs):
        return await self._compensation_getter()(*args, **kwargs)

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    def emoji(self, key: str):
        return self._emoji_getter()(key)

    def format_price(self, value: int) -> str:
        return self._price_formatter(value)


def make_bank_layer(runtime: BankRuntime):
    """Возвращает bank-функции, привязанные к runtime."""

    async def get_deposit(user_id: int):
        async with runtime.db.execute(
            "SELECT amount, interest_rate, start_time, end_time "
            "FROM bank_deposits WHERE user_id = ?",
            (user_id,),
        ) as c:
            return await c.fetchone()

    async def get_loan(user_id: int):
        async with runtime.db.execute(
            "SELECT amount, interest_rate, due_time, collateral_item, "
            "collateral_stars, status FROM bank_loans "
            "WHERE user_id = ? AND COALESCE(status, 'active') = 'active'",
            (user_id,),
        ) as c:
            return await c.fetchone()

    def loan_total_due(loan) -> int:
        if not loan:
            return 0
        amount, rate = loan[0], loan[1]
        return int((amount or 0) * (1 + (rate or 0)))

    async def get_collateral_value(item_id: str, stars: int) -> int:
        async with runtime.db.execute(
            "SELECT price FROM items WHERE id = ?", (item_id,)
        ) as c:
            row = await c.fetchone()
        price = (row[0] if row else 0) or 0
        return int(price * (1 + (stars or 0) * 0.5))

    async def take_bank_loan(
        user_id: int, item_id: str, stars: int, amount: int
    ) -> tuple[bool, str]:
        if await get_loan(user_id):
            return False, "❌ У тебя уже есть активный кредит."
        collateral_value = await get_collateral_value(item_id, stars)
        _, loan_cap = await runtime.get_bank_limits(user_id)
        max_loan = min(loan_cap, int(collateral_value * runtime.ltv))
        if max_loan < runtime.loan_min:
            return False, "❌ Залог слишком дешёвый для кредита."
        if amount < runtime.loan_min or amount > max_loan:
            return (
                False,
                f"❌ Сумма кредита: {runtime.loan_min}–{max_loan}.",
            )

        due = datetime.datetime.now() + datetime.timedelta(
            days=runtime.loan_term_days
        )
        try:
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT slot FROM inventory WHERE user_id = ? "
                    "AND location = 'profile' AND item_id = ? AND stars = ? "
                    "AND COALESCE(is_locked, 0) = 0 LIMIT 1",
                    (user_id, item_id, stars),
                ) as c:
                    row = await c.fetchone()
                if not row:
                    raise ValueError(
                        "Залоговый предмет не найден на энергостанции "
                        "или заблокирован."
                    )
                slot = row[0]

                cur = await runtime.db.execute(
                    "DELETE FROM inventory WHERE user_id = ? "
                    "AND location = 'profile' AND slot = ? AND item_id = ? "
                    "AND stars = ? AND COALESCE(is_locked, 0) = 0",
                    (user_id, slot, item_id, stars),
                )
                if cur.rowcount == 0:
                    raise ValueError("Залоговый предмет уже перемещён.")

                await runtime.db.execute(
                    "INSERT INTO bank_loans "
                    "(user_id, amount, interest_rate, due_time, "
                    "collateral_item, collateral_stars, issued_at, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'active')",
                    (
                        user_id,
                        amount,
                        runtime.loan_interest,
                        due.isoformat(),
                        item_id,
                        stars,
                        datetime.datetime.now().isoformat(),
                    ),
                )
                await runtime.db.execute(
                    "UPDATE players SET coins = coins + ? WHERE user_id = ?",
                    (amount, user_id),
                )
                await runtime.db.execute(
                    "INSERT INTO bank_history (user_id, amount, kind, details) "
                    "VALUES (?, ?, 'loan', ?)",
                    (user_id, amount, f"{item_id} {stars}★"),
                )
        except ValueError as e:
            return False, f"❌ {e}"

        return True, (
            f"✅ Кредит 🪙 **{amount}** выдан под залог "
            f"**{item_id}** ({stars}★).\n"
            f"К возврату до {due.strftime('%d.%m %H:%M')}: "
            f"🪙 {amount + int(amount * runtime.loan_interest)}."
        )

    async def repay_bank_loan(user_id: int) -> tuple[bool, str]:
        try:
            async with runtime.transaction():
                loan = await get_loan(user_id)
                if not loan:
                    raise ValueError("У тебя нет активного кредита.")
                amount, _rate, _due, item_id, stars, _status = loan
                total_due = loan_total_due(loan)

                async with runtime.db.execute(
                    "SELECT coins FROM players WHERE user_id = ?",
                    (user_id,),
                ) as c:
                    row = await c.fetchone()
                coins = (row[0] if row else 0) or 0
                if coins < total_due:
                    raise ValueError(
                        f"Нужно 🪙 {total_due}, у тебя {coins}."
                    )

                cur = await runtime.db.execute(
                    "UPDATE players SET coins = coins - ? "
                    "WHERE user_id = ? AND coins >= ?",
                    (total_due, user_id, total_due),
                )
                if cur.rowcount == 0:
                    raise ValueError(
                        "Недостаточно монет (баланс изменился)."
                    )

                await runtime.grant_compensation(
                    user_id, item_id, 1, stars or 0
                )

                cur = await runtime.db.execute(
                    "DELETE FROM bank_loans "
                    "WHERE user_id = ? AND COALESCE(status, 'active') = 'active'",
                    (user_id,),
                )
                if cur.rowcount == 0:
                    raise ValueError("Кредит уже погашен.")
                await runtime.db.execute(
                    "INSERT INTO bank_history (user_id, amount, kind) "
                    "VALUES (?, ?, 'loan_repay')",
                    (user_id, total_due),
                )
        except ValueError as e:
            return False, f"❌ {e}"

        return True, (
            f"✅ Кредит погашен: 🪙 **{total_due}**. "
            f"Залог **{item_id}** возвращён на энергостанцию или в почту."
        )

    async def expire_bank_loans():
        now = datetime.datetime.now().isoformat()
        async with runtime.db.execute(
            "SELECT user_id, amount, collateral_item, collateral_stars "
            "FROM bank_loans WHERE COALESCE(status, 'active') = 'active' "
            "AND due_time < ?",
            (now,),
        ) as c:
            loans = await c.fetchall()

        async with runtime.transaction():
            for user_id, amount, item_id, stars in loans:
                await runtime.db.execute(
                    "DELETE FROM bank_loans WHERE user_id = ?", (user_id,)
                )
                await runtime.db.execute(
                    "INSERT INTO bank_history "
                    "(user_id, amount, kind, details) "
                    "VALUES (?, ?, 'loan_default', ?)",
                    (user_id, amount, f"{item_id} {stars}★"),
                )

    async def build_bank_embed(user_id: int):
        deposit = await get_deposit(user_id)
        loan = await get_loan(user_id)
        max_deposit, max_loan = await runtime.get_bank_limits(user_id)
        embed = runtime.embed(
            title=f"{runtime.emoji('_bank')} Банк",
            description=(
                f"Вклад: **{int(runtime.daily_rate * 100)}%/день** "
                "(сложный процент).\n"
                f"Кредит: до **{int(runtime.ltv * 100)}%** "
                f"стоимости залога, переплата "
                f"**{int(runtime.loan_interest * 100)}%** за "
                f"{runtime.loan_term_days} дней."
            ),
            color=0x2ECC71,
        )
        embed.add_field(
            name="Лимиты",
            value=(
                f"Вклад: до {runtime.coin} "
                f"**{runtime.format_price(max_deposit)}** "
                f"({runtime.deposit_income_hours} ч дохода)\n"
                f"Кредит: до {runtime.coin} "
                f"**{runtime.format_price(max_loan)}** "
                f"({runtime.loan_income_hours} ч дохода, но не больше "
                f"{int(runtime.ltv * 100)}% залога)"
            ),
            inline=False,
        )

        if deposit:
            amount, rate, start, end = deposit
            start_dt = datetime.datetime.fromisoformat(start)
            end_dt = datetime.datetime.fromisoformat(end)
            days = max(
                1, (end_dt - start_dt).total_seconds() / 86400
            )
            daily_rate = rate / days if days > 0 else 0
            total_value = int(amount * ((1 + daily_rate) ** days))
            if datetime.datetime.now() >= end_dt:
                value_line = (
                    f"К получению: {runtime.coin} **{total_value}** "
                    f"(+{total_value - amount})"
                )
            else:
                value_line = (
                    f"При завершении: {runtime.coin} "
                    f"**{total_value}** (+{total_value - amount})\n"
                    f"Досрочно: {runtime.coin} **{amount}** "
                    "(без процентов)"
                )
            embed.add_field(
                name="Вклад",
                value=(
                    f"Сумма: {runtime.coin} **{amount}**\n"
                    f"Срок: до `{end_dt.strftime('%d.%m %H:%M')}` "
                    f"({days:.0f} дн.)\n{value_line}"
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="Вклад",
                value="Нет активного вклада.",
                inline=False,
            )

        if loan:
            amount, _rate, due, item_id, stars, _status = loan
            total_due = loan_total_due(loan)
            async with runtime.db.execute(
                "SELECT name, emoji FROM items WHERE id = ?",
                (item_id,),
            ) as c:
                item_row = await c.fetchone()
            item_name, item_emoji = item_row or (item_id, "📦")
            embed.add_field(
                name="Кредит",
                value=(
                    f"Получено: {runtime.coin} **{amount}**\n"
                    f"К возврату: {runtime.coin} **{total_due}**\n"
                    f"Срок: до `{str(due)[:16]}`\n"
                    f"Залог: {item_emoji} **{item_name}** "
                    f"({stars or 0}★)"
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="Кредит",
                value="Нет активного кредита.",
                inline=False,
            )

        embed.set_footer(
            text=(
                "Досрочное закрытие вклада возвращает сумму "
                "без процентов."
            )
        )
        return embed, bool(deposit), bool(loan)

    async def build_bank_history_embed(user_id: int):
        async with runtime.db.execute(
            "SELECT amount, kind, details, opened_at "
            "FROM bank_history WHERE user_id = ? "
            "ORDER BY id DESC LIMIT 10",
            (user_id,),
        ) as c:
            rows = await c.fetchall()

        embed = runtime.embed(
            title=f"{runtime.emoji('_history')} История банка",
            color=0x2ECC71,
        )
        if not rows:
            embed.description = "Операций пока нет."
            return embed

        kind_names = {
            "deposit": "вклад открыт",
            "withdraw": "вклад закрыт",
            "loan": "кредит получен",
            "loan_repay": "кредит погашен",
            "loan_default": "кредит просрочен",
        }
        lines = []
        for amount, kind, details, opened_at in rows:
            label = kind_names.get(
                kind or "deposit", kind or "операция"
            )
            extra = f" · {details}" if details else ""
            lines.append(
                f"🪙 **{amount}** — {label}{extra}\n"
                f"`{str(opened_at)[:16]}`"
            )
        embed.description = "\n\n".join(lines)
        return embed

    return (
        get_deposit,
        get_loan,
        loan_total_due,
        get_collateral_value,
        take_bank_loan,
        repay_bank_loan,
        expire_bank_loans,
        build_bank_embed,
        build_bank_history_embed,
    )
