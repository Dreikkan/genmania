"""Storage and temporary storage embeds."""
from __future__ import annotations

import logging
from typing import Any, Callable

from ..formatting import plural_ru


class StorageUiRuntime:
    """Адаптер между bot.py и UI хранилища."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self._price_formatter: Callable[[int], str] = str
        self._settings_getter: Callable[[], Callable] = lambda: None
        self._storage_size_getter: Callable[[], Callable] = lambda: None
        self._star_emoji_getter: Callable[[], Callable] = lambda: None
        self._filter_rows: Callable = lambda rows, mode: rows
        self._sell_price: Callable[[int, int], int] = lambda price, stars: 0
        self.storage_filters: dict = {}
        self.sell_allowed_rarities: set = set()
        self.temp_storage_size = 100
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        price_formatter: Callable[[int], str],
        settings_getter: Callable[[], Callable],
        storage_size_getter: Callable[[], Callable],
        star_emoji_getter: Callable[[], Callable],
        filter_rows: Callable,
        sell_price: Callable[[int, int], int],
        storage_filters: dict,
        sell_allowed_rarities: set,
        temp_storage_size: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self._price_formatter = price_formatter
        self._settings_getter = settings_getter
        self._storage_size_getter = storage_size_getter
        self._star_emoji_getter = star_emoji_getter
        self._filter_rows = filter_rows
        self._sell_price = sell_price
        self.storage_filters = storage_filters
        self.sell_allowed_rarities = sell_allowed_rarities
        self.temp_storage_size = temp_storage_size
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    async def fix_emojis(self, embed):
        return await self._emoji_fixer(embed)

    def format_price(self, value: int) -> str:
        return self._price_formatter(value)

    async def get_settings(self, guild_id: int):
        return await self._settings_getter()(guild_id)

    async def get_storage_size(self, user_id: int):
        return await self._storage_size_getter()(user_id)

    async def get_star_emoji(
        self, item_id: str, stars: int, emoji: str
    ):
        return await self._star_emoji_getter()(item_id, stars, emoji)

    def filter_rows(self, rows, filter_mode: str):
        return self._filter_rows(rows, filter_mode)

    def sell_price(self, price: int, stars: int = 0) -> int:
        return self._sell_price(price, stars)


def make_storage_ui_layer(runtime: StorageUiRuntime):
    """Возвращает storage-embed-функции, привязанные к runtime."""

    async def build_storage_embed(interaction, filter_mode: str = "all"):
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        settings = await runtime.get_settings(guild_id)
        grid_size = await runtime.get_storage_size(user_id)
        filter_mode = (
            filter_mode
            if filter_mode in runtime.storage_filters
            else "all"
        )

        async with runtime.db.execute(
            """
            SELECT inv.slot, i.id, i.emoji, inv.stars, i.price, i.rarity,
                   COALESCE(inv.is_locked, 0)
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND inv.location = 'storage'
            """,
            (user_id,),
        ) as c:
            rows = await c.fetchall()

        custom = settings["custom_emojis"]
        visible_rows = runtime.filter_rows(rows, filter_mode)
        zero_star = sum(1 for row in rows if (row[3] or 0) == 0)
        starred = len(rows) - zero_star
        locked_count = sum(1 for row in rows if row[6])
        sellable = [
            row
            for row in rows
            if (row[3] or 0) == 0
            and row[5] in runtime.sell_allowed_rarities
            and not row[6]
        ]
        sell_total = sum(
            runtime.sell_price(row[4], 0) for row in sellable
        )

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM inventory "
            "WHERE user_id = ? AND location = 'temp'",
            (user_id,),
        ) as c:
            temp_count = (await c.fetchone())[0] or 0

        storage_emoji = custom.get("_storage", "🎒")
        width = max(1, int(grid_size ** 0.5))
        embed = runtime.embed(
            title=f"{storage_emoji} Хранилище {interaction.user.name}",
            color=0x808080,
        )
        embed.description = (
            f"Слотов: **{grid_size}** | "
            f"Временное: **{temp_count}/{runtime.temp_storage_size}**\n"
            f"0★: **{zero_star}** | Со звёздами: **{starred}** | "
            f"🔒 Заблокировано: **{locked_count}**\n"
        )
        if sellable:
            embed.description += (
                f"Быстрая продажа 0★: **{len(sellable)}** "
                f"{plural_ru(len(sellable), 'штука', 'штуки', 'штук')} за "
                f"🪙 **{runtime.format_price(sell_total)}**\n"
            )
        else:
            embed.description += (
                "Быстрая продажа 0★: нет подходящих предметов\n"
            )
        embed.description += (
            f"Фильтр: **{runtime.storage_filters[filter_mode]}** · "
            f"Показано **{len(visible_rows)}/{len(rows)}**\n"
            "-# Звёздные, epic+ и предметы из энергостанции "
            "не входят в быструю продажу."
        )
        if rows and not visible_rows:
            embed.description += "\n\nПо выбранному фильтру ничего нет."
        if not rows:
            embed.description += (
                "\n\nХранилище пусто. Перемести сюда предметы "
                "из энергостанции, чтобы освободить слоты."
            )

        visible_items = {}
        for (
            slot,
            item_id,
            default_emoji,
            stars,
            _price,
            _rarity,
            _locked,
        ) in visible_rows:
            emoji = custom.get(item_id, default_emoji)
            emoji = await runtime.get_star_emoji(
                item_id, stars, emoji
            )
            visible_items[slot] = emoji
        for start in range(0, grid_size, width):
            row_items = [
                visible_items.get(slot, "⬛")
                for slot in range(
                    start, min(start + width, grid_size)
                )
            ]
            embed.add_field(
                name="\u200b", value="  ".join(row_items), inline=False
            )
        return await runtime.fix_emojis(embed)

    async def build_temp_storage_embed(interaction):
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        settings = await runtime.get_settings(guild_id)
        custom = settings["custom_emojis"]

        async with runtime.db.execute(
            """
            SELECT inv.slot, i.id, i.emoji, inv.stars
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND inv.location = 'temp'
            """,
            (user_id,),
        ) as c:
            rows = await c.fetchall()

        items = {}
        for slot, item_id, default_emoji, stars in rows:
            emoji = custom.get(item_id, default_emoji)
            emoji = await runtime.get_star_emoji(
                item_id, stars, emoji
            )
            items[slot] = emoji

        width = 10
        embed = runtime.embed(
            title=f"📦 Временное хранилище — {interaction.user.name}",
            description=(
                f"Занято: **{len(rows)}/{runtime.temp_storage_size}**\n"
                "Сюда попадают предметы, которым не хватило слотов "
                "на энергостанции и хранилище."
                + (
                    "\n\nВременное хранилище пусто."
                    if not rows
                    else ""
                )
            ),
            color=0x808080,
        )
        for start in range(0, runtime.temp_storage_size, width):
            row_items = [
                items.get(slot, "⬛")
                for slot in range(start, start + width)
            ]
            embed.add_field(
                name="\u200b", value="  ".join(row_items), inline=False
            )
        return await runtime.fix_emojis(embed)

    return build_storage_embed, build_temp_storage_embed
