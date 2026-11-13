"""Admin grant/take currency modals."""
from __future__ import annotations

import logging
from typing import Any, Callable

import discord


class AdminValuesRuntime:
    """Адаптер между модалками и bot.py."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._log_getter: Callable[[], Callable] = lambda: None
        self._top_exclusion_getter: Callable[[], Callable] = lambda: None
        self.max_resource = 10**12
        self.default_start_coins = 8
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        log_getter: Callable[[], Callable],
        top_exclusion_getter: Callable[[], Callable],
        max_resource: int,
        default_start_coins: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._log_getter = log_getter
        self._top_exclusion_getter = top_exclusion_getter
        self.max_resource = max_resource
        self.default_start_coins = default_start_coins
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        return self._transaction_getter()()

    async def log(self, *args, **kwargs):
        await self._log_getter()(*args, **kwargs)

    async def enforce_top_exclusion(self, *args, **kwargs):
        await self._top_exclusion_getter()(*args, **kwargs)


def make_admin_values_layer(runtime: AdminValuesRuntime):
    class AdminGrantValuesModal(discord.ui.Modal, title="Начислить"):
        user_id: discord.ui.TextInput = discord.ui.TextInput(
            label="ID пользователя",
            placeholder="123456789",
            required=True,
        )
        amount: discord.ui.TextInput = discord.ui.TextInput(
            label="Количество", default="100", required=True
        )

        def __init__(
            self,
            author_id: int,
            currency: str,
            target_id: int | None = None,
        ):
            super().__init__()
            self.author_id = author_id
            self.currency = currency
            if target_id is not None:
                self.user_id.default = str(target_id)

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            if self.currency not in ("coins", "gems"):
                return await interaction.followup.send(
                    "❌ Неверная валюта.", ephemeral=True
                )
            try:
                uid = int(self.user_id.value)
                amount = int(self.amount.value)
                if amount <= 0 or amount > runtime.max_resource:
                    raise ValueError
            except ValueError:
                return await interaction.followup.send(
                    f"❌ ID и количество: 1-{runtime.max_resource}.",
                    ephemeral=True,
                )
            async with runtime.transaction():
                async with runtime.db.execute(
                    "SELECT 1 FROM players WHERE user_id = ?", (uid,)
                ) as c:
                    exists = await c.fetchone()
                if not exists:
                    await runtime.db.execute(
                        "INSERT OR IGNORE INTO players "
                        "(user_id, coins, last_gem_collected, last_tax_time) "
                        "VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                        (uid, runtime.default_start_coins),
                    )
                await runtime.db.execute(
                    f"UPDATE players SET {self.currency} = "
                    f"{self.currency} + ? WHERE user_id = ?",
                    (amount, uid),
                )
            await runtime.log(
                self.author_id,
                uid,
                "grant",
                f"{self.currency} +{amount}",
            )
            await runtime.enforce_top_exclusion(
                interaction, uid, f"self_grant:{self.currency}"
            )
            unit = "🪙" if self.currency == "coins" else "💎"
            await interaction.followup.send(
                f"✅ Начислено {amount} {unit} <@{uid}>.",
                ephemeral=True,
            )

    class AdminTakeValuesModal(discord.ui.Modal, title="Забрать"):
        user_id: discord.ui.TextInput = discord.ui.TextInput(
            label="ID пользователя",
            placeholder="123456789",
            required=True,
        )
        amount: discord.ui.TextInput = discord.ui.TextInput(
            label="Количество", default="100", required=True
        )

        def __init__(
            self,
            author_id: int,
            currency: str,
            target_id: int | None = None,
        ):
            super().__init__()
            self.author_id = author_id
            self.currency = currency
            if target_id is not None:
                self.user_id.default = str(target_id)

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            if self.currency not in ("coins", "gems"):
                return await interaction.followup.send(
                    "❌ Неверная валюта.", ephemeral=True
                )
            try:
                uid = int(self.user_id.value)
                amount = int(self.amount.value)
                if amount <= 0 or amount > runtime.max_resource:
                    raise ValueError
            except ValueError:
                return await interaction.followup.send(
                    f"❌ ID и количество: 1-{runtime.max_resource}.",
                    ephemeral=True,
                )
            try:
                async with runtime.transaction():
                    async with runtime.db.execute(
                        f"SELECT {self.currency} FROM players "
                        "WHERE user_id = ?",
                        (uid,),
                    ) as c:
                        row = await c.fetchone()
                    if not row:
                        raise ValueError("Игрок не найден.")
                    if row[0] < amount:
                        raise ValueError(f"У игрока только {row[0]}.")
                    cur = await runtime.db.execute(
                        f"UPDATE players SET {self.currency} = "
                        f"{self.currency} - ? WHERE user_id = ? "
                        f"AND {self.currency} >= ?",
                        (amount, uid, amount),
                    )
                    if cur.rowcount == 0:
                        raise ValueError("Баланс изменился, попробуй снова.")
            except ValueError as exc:
                return await interaction.followup.send(
                    f"❌ {exc}", ephemeral=True
                )
            await runtime.log(
                self.author_id,
                uid,
                "take",
                f"{self.currency} -{amount}",
            )
            unit = "🪙" if self.currency == "coins" else "💎"
            await interaction.followup.send(
                f"✅ Забрано {amount} {unit} у <@{uid}>.",
                ephemeral=True,
            )

    return AdminGrantValuesModal, AdminTakeValuesModal
