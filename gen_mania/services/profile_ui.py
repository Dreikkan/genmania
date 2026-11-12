"""Profile and synthesis statistics embeds."""
from __future__ import annotations

import logging
from typing import Any, Callable


class ProfileUiRuntime:
    """Адаптер между bot.py и UI профиля."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._settings_getter: Callable[[], Callable] = lambda: None
        self._accessibility_getter: Callable[[], Callable] = lambda: None
        self._status_bonus_getter: Callable[[], Callable] = lambda: None
        self._titles_getter: Callable[[], Callable] = lambda: None
        self._pet_getter: Callable[[], Callable] = lambda: None
        self._autocollector_getter: Callable[[], Callable] = lambda: None
        self._combat_power_getter: Callable[[], Callable] = lambda: None
        self._income_getter: Callable[[], Callable] = lambda: None
        self._pet_bonus_getter: Callable[[], Callable] = lambda: None
        self._title_bonus_getter: Callable[[], Callable] = lambda: None
        self._collection_count_getter: Callable[[], Callable] = lambda: None
        self._player_stats_getter: Callable[[], Callable] = lambda: None
        self._star_emoji_getter: Callable[[], Callable] = lambda: None
        self._profile_filter: Callable = lambda rows, mode: rows
        self._clan_getter: Callable[[], Callable] = lambda: None
        self._total_bonus_getter: Callable[[], Callable] = lambda: None
        self._set_details_getter: Callable[[], Callable] = lambda: None
        self._prestige_bonus_getter: Callable[[], Callable] = lambda: None
        self._collection_bonus_getter: Callable[[], Callable] = lambda: None
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self._price_formatter: Callable[[int], str] = str
        self.titles: dict = {}
        self.title_bonuses: dict = {}
        self.btype_names: dict = {}
        self.button_emojis: dict = {}
        self.pet_types: dict = {}
        self.autocollect_levels: dict = {}
        self.storage_filters: dict = {}
        self.set_definitions: dict = {}
        self.item_set: dict = {}
        self.star_bonus: dict = {}
        self.rarity_names: dict = {}
        self.income_hint = ""
        self.page_size = 10
        self.castle = "⚡"
        self.prestige_bonus_per_point = 0.0
        self.prestige_bonus_cap = 0.0
        self.start_grid = 9
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        settings_getter: Callable[[], Callable],
        accessibility_getter: Callable[[], Callable],
        status_bonus_getter: Callable[[], Callable],
        titles_getter: Callable[[], Callable],
        pet_getter: Callable[[], Callable],
        autocollector_getter: Callable[[], Callable],
        combat_power_getter: Callable[[], Callable],
        income_getter: Callable[[], Callable],
        pet_bonus_getter: Callable[[], Callable],
        title_bonus_getter: Callable[[], Callable],
        collection_count_getter: Callable[[], Callable],
        player_stats_getter: Callable[[], Callable],
        star_emoji_getter: Callable[[], Callable],
        profile_filter: Callable,
        clan_getter: Callable[[], Callable],
        total_bonus_getter: Callable[[], Callable],
        set_details_getter: Callable[[], Callable],
        prestige_bonus_getter: Callable[[], Callable],
        collection_bonus_getter: Callable[[], Callable],
        emoji_getter: Callable[[], Callable],
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        price_formatter: Callable[[int], str],
        titles: dict,
        title_bonuses: dict,
        btype_names: dict,
        button_emojis: dict,
        pet_types: dict,
        autocollect_levels: dict,
        storage_filters: dict,
        set_definitions: dict,
        item_set: dict,
        star_bonus: dict,
        rarity_names: dict,
        income_hint: str,
        page_size: int,
        castle: str,
        prestige_bonus_per_point: float,
        prestige_bonus_cap: float,
        start_grid: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._settings_getter = settings_getter
        self._accessibility_getter = accessibility_getter
        self._status_bonus_getter = status_bonus_getter
        self._titles_getter = titles_getter
        self._pet_getter = pet_getter
        self._autocollector_getter = autocollector_getter
        self._combat_power_getter = combat_power_getter
        self._income_getter = income_getter
        self._pet_bonus_getter = pet_bonus_getter
        self._title_bonus_getter = title_bonus_getter
        self._collection_count_getter = collection_count_getter
        self._player_stats_getter = player_stats_getter
        self._star_emoji_getter = star_emoji_getter
        self._profile_filter = profile_filter
        self._clan_getter = clan_getter
        self._total_bonus_getter = total_bonus_getter
        self._set_details_getter = set_details_getter
        self._prestige_bonus_getter = prestige_bonus_getter
        self._collection_bonus_getter = collection_bonus_getter
        self._emoji_getter = emoji_getter
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self._price_formatter = price_formatter
        self.titles = titles
        self.title_bonuses = title_bonuses
        self.btype_names = btype_names
        self.button_emojis = button_emojis
        self.pet_types = pet_types
        self.autocollect_levels = autocollect_levels
        self.storage_filters = storage_filters
        self.set_definitions = set_definitions
        self.item_set = item_set
        self.star_bonus = star_bonus
        self.rarity_names = rarity_names
        self.income_hint = income_hint
        self.page_size = page_size
        self.castle = castle
        self.prestige_bonus_per_point = prestige_bonus_per_point
        self.prestige_bonus_cap = prestige_bonus_cap
        self.start_grid = start_grid
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    async def get_settings(self, guild_id: int):
        return await self._settings_getter()(guild_id)

    async def is_accessibility_mode(self, user_id: int):
        return await self._accessibility_getter()(user_id)

    async def get_status_bonus(self, user_id: int):
        return await self._status_bonus_getter()(user_id)

    async def get_unlocked_titles(self, user_id: int):
        return await self._titles_getter()(user_id)

    async def get_active_pet(self, user_id: int):
        return await self._pet_getter()(user_id)

    async def get_autocollector(self, user_id: int):
        return await self._autocollector_getter()(user_id)

    async def get_combat_power(self, user_id: int):
        return await self._combat_power_getter()(user_id)

    async def get_income(self, user_id: int):
        return await self._income_getter()(user_id)

    async def get_pet_bonus(self, user_id: int, effect_type: str):
        return await self._pet_bonus_getter()(user_id, effect_type)

    async def get_title_bonus(self, user_id: int, effect_type: str):
        return await self._title_bonus_getter()(user_id, effect_type)

    async def get_collection_count(self, user_id: int):
        return await self._collection_count_getter()(user_id)

    async def get_player_stats(self, user_id: int, guild_id: int):
        return await self._player_stats_getter()(user_id, guild_id)

    async def get_star_emoji(self, item_id: str, stars: int, emoji: str):
        return await self._star_emoji_getter()(item_id, stars, emoji)

    def filter_profile_rows(self, rows, filter_mode: str):
        return self._profile_filter(rows, filter_mode)

    async def get_clan(self, user_id: int):
        return await self._clan_getter()(user_id)

    async def get_total_bonus_percent(self, user_id: int):
        return await self._total_bonus_getter()(user_id)

    async def get_set_details(self, user_id: int):
        return await self._set_details_getter()(user_id)

    async def get_prestige_bonus(self, user_id: int):
        return await self._prestige_bonus_getter()(user_id)

    async def get_collection_bonus(self, user_id: int):
        return await self._collection_bonus_getter()(user_id)

    def emoji(self, key: str):
        return self._emoji_getter()(key)

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    def format_price(self, value: int) -> str:
        return self._price_formatter(value)

    async def fix_emojis(self, embed):
        return await self._emoji_fixer(embed)


def make_profile_ui_layer(runtime: ProfileUiRuntime):
    """Возвращает profile-embed-функции, привязанные к runtime."""

    async def build_stats_embed(interaction):
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        custom = (await runtime.get_settings(guild_id))[
            "custom_emojis"
        ]
        stats_emoji = custom.get("_stats", "📊")
        gem = custom.get("_gem", "💎")

        async with runtime.db.execute(
            """
            SELECT COUNT(*), SUM(success), SUM(gems_spent),
                   SUM(catalyst_used)
            FROM craft_log WHERE user_id = ?
            """,
            (user_id,),
        ) as c:
            total, successes, gems_spent, catalysts_used = (
                await c.fetchone()
            )

        if not total:
            embed = runtime.embed(
                title=f"{stats_emoji} Статистика синтеза",
                description="У тебя пока нет ни одного синтеза.",
                color=0x9b59b6,
            )
            return await runtime.fix_emojis(embed)

        successes = successes or 0
        failures = total - successes
        gems_spent = gems_spent or 0
        catalysts_used = catalysts_used or 0
        winrate = (successes / total) * 100

        embed = runtime.embed(
            title=f"{stats_emoji} Статистика — {interaction.user.name}",
            color=0x9b59b6,
        )
        embed.add_field(name="Попыток", value=str(total), inline=True)
        embed.add_field(
            name="✅ Успехов", value=str(successes), inline=True
        )
        embed.add_field(
            name="💥 Провалов", value=str(failures), inline=True
        )
        embed.add_field(
            name="Винрейт", value=f"{winrate:.1f}%", inline=True
        )
        embed.add_field(
            name=f"{gem} Потрачено",
            value=str(gems_spent),
            inline=True,
        )
        embed.add_field(
            name="🧪 Катализаторов",
            value=str(catalysts_used),
            inline=True,
        )
        return await runtime.fix_emojis(embed)

    async def build_user_profile_embed(interaction):
        user_id = interaction.user.id
        compact = await runtime.is_accessibility_mode(user_id)

        async with runtime.db.execute(
            """
            SELECT coins, gems, catalysts, total_crafts,
                   total_successes, grid_size
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

        coins, gems, catalysts, crafts, successes, grid = row
        bonus = await runtime.get_status_bonus(user_id)

        async with runtime.db.execute(
            "SELECT COUNT(*) FROM player_achievements "
            "WHERE user_id = ?",
            (user_id,),
        ) as c:
            ach_count = (await c.fetchone())[0]

        winrate = (
            (successes / crafts * 100) if crafts > 0 else 0.0
        )

        async with runtime.db.execute(
            "SELECT embed_color, bg_url, castle_icon "
            "FROM user_cosmetics WHERE user_id = ?",
            (user_id,),
        ) as c:
            cos = await c.fetchone()
        cos_color = cos[0] if cos and cos[0] else 0x3498db
        cos_bg = cos[1] if cos else None
        cos_icon = cos[2] if cos else None

        embed = runtime.embed(
            title=f"{cos_icon or '👤'} Профиль — {interaction.user.name}",
            description="Подробная информация о твоих успехах.",
            color=cos_color,
        )
        if cos_bg and not compact:
            embed.set_image(url=cos_bg)
        if not compact:
            embed.set_thumbnail(
                url=interaction.user.display_avatar.url
            )

        async with runtime.db.execute(
            "SELECT title FROM players WHERE user_id = ?",
            (user_id,),
        ) as c:
            title_row = await c.fetchone()
        title = (title_row[0] if title_row else None) or "Новичок"

        unlocked_titles = await runtime.get_unlocked_titles(user_id)

        title_id = None
        for tid, (name, _req) in runtime.titles.items():
            if name == title:
                title_id = tid
                break
        bonus_line = ""
        if title_id:
            btype, bval = runtime.title_bonuses.get(
                title_id, (None, 0.0)
            )
            if btype and bval > 0:
                bonus_line = (
                    f"\n+{int(bval * 100)}% "
                    f"{runtime.btype_names.get(btype, btype)}"
                )

        embed.add_field(
            name=(
                f"{runtime.button_emojis.get('_title', '🏅')} "
                "Титул"
            ),
            value=(
                f"{title}{bonus_line}\nОткрыто: "
                f"**{len(unlocked_titles)}/{len(runtime.titles)}**"
            ),
            inline=True,
        )

        pet = await runtime.get_active_pet(user_id)
        if pet:
            pid, lvl = pet
            pt = runtime.pet_types.get(pid)
            if pt:
                embed.add_field(
                    name=f"{pt['emoji']} Питомец",
                    value=f"{pt['name']} (ур. {lvl})",
                    inline=True,
                )
        autoc = await runtime.get_autocollector(user_id)
        if autoc:
            lvl, _ = autoc
            embed.add_field(
                name="🤖 Автосборщик",
                value=(
                    f"Ур. {lvl} (раз в "
                    f"{runtime.autocollect_levels[lvl][1]} ч)"
                ),
                inline=True,
            )
        embed.add_field(
            name=f"{runtime.castle} Энергостанция",
            value=(
                f"Сетка: **{grid}** слотов\n"
                f"Бонус дохода: **+{int(bonus * 100)}%**"
            ),
            inline=True,
        )
        embed.add_field(
            name="💰 Ресурсы",
            value=(
                f"{runtime.button_emojis.get('_coin', '🪙')} "
                f"{runtime.format_price(coins)}\n"
                f"{runtime.button_emojis.get('_gem', '💎')} {gems}\n"
                f"🧪 {catalysts}"
            ),
            inline=True,
        )
        embed.add_field(
            name="🏆 Достижения",
            value=f"**{ach_count}**",
            inline=True,
        )
        embed.add_field(
            name="⚗️ Успешность синтеза",
            value=f"**{winrate:.1f}%**",
            inline=True,
        )
        embed.add_field(
            name="🆔 ID", value=f"`{user_id}`", inline=True
        )

        return await runtime.fix_emojis(embed)

    async def build_public_profile_embed(
        target_id: int, detailed: bool = False
    ):
        async with runtime.db.execute(
            "SELECT coins, gems, title, grid_size, prestige_points "
            "FROM players WHERE user_id = ?",
            (target_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            return runtime.embed(
                title="❌ Игрок не найден",
                description=f"Профиль <@{target_id}> не найден.",
                color=0xe74c3c,
            )

        coins, gems, title, grid_size, prestige = row
        income_bonus = await runtime.get_status_bonus(target_id)
        grid_size = grid_size or runtime.start_grid
        title = title or "Новичок"

        async with runtime.db.execute(
            "SELECT c.name, cm.role FROM clan_members cm "
            "JOIN clans c ON c.id = cm.clan_id WHERE cm.user_id = ?",
            (target_id,),
        ) as c:
            clan_row = await c.fetchone()

        power = await runtime.get_combat_power(target_id)
        per_sec_coins, per_sec_gems = await runtime.get_income(target_id)
        pet = await runtime.get_active_pet(target_id)
        autoc = await runtime.get_autocollector(target_id)

        async with runtime.db.execute(
            "SELECT inv.slot, inv.item_id, i.name, i.emoji, inv.stars, "
            "i.price FROM inventory inv "
            "JOIN items i ON inv.item_id = i.id "
            "WHERE inv.user_id = ? AND inv.location = 'profile'",
            (target_id,),
        ) as c:
            rows = await c.fetchall()

        pet_power = await runtime.get_pet_bonus(
            target_id, "combat_power"
        )
        title_power = await runtime.get_title_bonus(
            target_id, "combat_power"
        )
        combat_mult = 1 + pet_power + title_power

        grid = {}
        power_rows = []
        for slot, item_id, name, emoji, stars, price in rows:
            grid[slot] = emoji
            power_rows.append(
                (
                    name,
                    emoji,
                    stars,
                    int(
                        (price or 0)
                        * (1 + stars * 0.5)
                        * combat_mult
                    ),
                )
            )

        embed = runtime.embed(
            title=(
                f"🕵️ Шпионаж: <@{target_id}>"
                if detailed
                else f"👤 Профиль: <@{target_id}>"
            ),
            description=(
                "Данные разведки: баланс, доход, мощь и энергостанция."
                if detailed
                else "Публичный обзор: титул, клан, доход, коллекция "
                "и энергостанция."
            ),
            color=0x9b59b6 if detailed else 0x3498db,
        )
        embed.add_field(
            name="Основное",
            value=(
                f"Титул: **{title}**\n"
                f"Клан: **{clan_row[0]}** ({clan_row[1]})"
                if clan_row
                else f"Титул: **{title}**\nКлан: не состоит"
            ),
            inline=False,
        )
        if detailed:
            prestige_bonus = int(
                min(
                    (prestige or 0) * runtime.prestige_bonus_per_point,
                    runtime.prestige_bonus_cap,
                )
                * 100
            )
            embed.add_field(
                name="Баланс",
                value=(
                    f"🪙 {runtime.format_price(coins or 0)} | "
                    f"💎 {runtime.format_price(gems or 0)}"
                ),
                inline=True,
            )
            embed.add_field(
                name="Престиж",
                value=(
                    f"**{prestige or 0}** очков · "
                    f"бонус +{prestige_bonus}%"
                ),
                inline=True,
            )
            embed.add_field(
                name="⚔️ Мощь",
                value=f"**{power}**",
                inline=True,
            )
        embed.add_field(
            name="Доход",
            value=(
                f"🪙 {per_sec_coins * 3600:.2f}/час"
                + (
                    f"\n💎 {per_sec_gems * 3600:.4f}/час"
                    if per_sec_gems > 0
                    else ""
                )
            ),
            inline=True,
        )
        if detailed:
            pet_text = "нет"
            if pet:
                pet_type = runtime.pet_types.get(pet[0])
                if pet_type:
                    pet_text = (
                        f"{pet_type['emoji']} {pet_type['name']} "
                        f"(ур. {pet[1]})"
                    )
            embed.add_field(
                name="Активность",
                value=(
                    f"Питомец: {pet_text}\n"
                    f"Автосборщик: "
                    f"{'ур. ' + str(autoc[0]) if autoc else 'нет'}\n"
                    f"Бонус статуса: +{int((income_bonus or 0) * 100)}%"
                ),
                inline=False,
            )

        if detailed and power_rows:
            top = sorted(
                power_rows, key=lambda item: item[3], reverse=True
            )[:5]
            embed.add_field(
                name="Топ генераторов по мощи",
                value="\n".join(
                    f"{emoji} {name} ({stars}★) — **{gen_power}**"
                    for name, emoji, stars, gen_power in top
                ),
                inline=False,
            )

        if not detailed:
            async with runtime.db.execute(
                "SELECT COUNT(*) FROM items "
                "WHERE id LIKE '%\\_gen' ESCAPE '\\'"
            ) as c:
                total_generators = (await c.fetchone())[0] or 0
            collection_count = await runtime.get_collection_count(
                target_id
            )
            async with runtime.db.execute(
                "SELECT COUNT(*) FROM player_achievements "
                "WHERE user_id = ?",
                (target_id,),
            ) as c:
                achievements_count = (await c.fetchone())[0] or 0
            async with runtime.db.execute(
                "SELECT COUNT(*) FROM achievements"
            ) as c:
                achievements_total = (await c.fetchone())[0] or 0
            embed.add_field(
                name=f"{runtime.castle} Энергостанция",
                value=(
                    f"Сетка: **{grid_size}**\n"
                    f"Занято: **{len(rows)}/{grid_size}**"
                ),
                inline=True,
            )
            embed.add_field(
                name="📚 Коллекция",
                value=f"**{collection_count}/{total_generators}**",
                inline=True,
            )
            embed.add_field(
                name="🏆 Достижения",
                value=f"**{achievements_count}/{achievements_total}**",
                inline=True,
            )

        width = max(1, int(grid_size ** 0.5))
        embed.add_field(
            name=f"Энергостанция · сетка {grid_size}",
            value="\n".join(
                "  ".join(
                    grid.get(slot, "⬛")
                    if detailed
                    else ("🟦" if slot in grid else "⬛")
                    for slot in range(
                        start, min(start + width, grid_size)
                    )
                )
                for start in range(0, grid_size, width)
            ),
            inline=False,
        )
        return await runtime.fix_emojis(embed)

    async def build_profile_embed(interaction, filter_mode: str = "all"):
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        settings = await runtime.get_settings(guild_id)
        compact = await runtime.is_accessibility_mode(user_id)
        filter_mode = (
            filter_mode
            if filter_mode in runtime.storage_filters
            else "all"
        )

        grid_size, bonus, gems, coins = await runtime.get_player_stats(
            user_id, guild_id
        )

        async with runtime.db.execute(
            """
            SELECT inv.slot, i.id, i.name, i.emoji, inv.stars, i.price,
                   i.rarity, COALESCE(inv.is_locked, 0)
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND inv.location = 'profile'
            """,
            (user_id,),
        ) as c:
            rows = await c.fetchall()

        custom = settings["custom_emojis"]
        power_rows = []
        for (
            slot,
            item_id,
            item_name,
            default_emoji,
            stars,
            price,
            rarity,
            locked,
        ) in rows:
            emoji = custom.get(item_id, default_emoji)
            emoji = await runtime.get_star_emoji(
                item_id, stars, emoji
            )
            power_rows.append((item_name, emoji, stars, price or 0))

        visible_rows = runtime.filter_profile_rows(rows, filter_mode)
        visible_items = {}
        for (
            slot,
            item_id,
            _item_name,
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

        coin = custom.get("_coin", "🪙")
        gem = custom.get("_gem", "💎")
        castle = custom.get("_castle", "⚡")

        per_sec_coins, per_sec_gems = await runtime.get_income(user_id)
        parts = []
        if per_sec_coins > 0:
            parts.append(f"{coin} {per_sec_coins * 3600:.2f}/час")
        if per_sec_gems > 0:
            parts.append(f"{gem} {per_sec_gems * 3600:.4f}/час")
        income_str = (
            " | ".join(parts)
            if parts
            else "нет генераторов · купи первый в «Магазине»"
        )

        clan_bonus = 0.0
        clan = await runtime.get_clan(user_id)
        if clan:
            clan_bonus = clan[4] or 0.0

        total_pct = await runtime.get_total_bonus_percent(user_id)
        set_details = await runtime.get_set_details(user_id)

        width = max(1, int(grid_size ** 0.5))
        async with runtime.db.execute(
            "SELECT embed_color, bg_url, castle_icon "
            "FROM user_cosmetics WHERE user_id = ?",
            (user_id,),
        ) as c:
            cos = await c.fetchone()
        cos_color = cos[0] if cos and cos[0] else 0x00FF00
        cos_bg = cos[1] if cos else None
        cos_icon = cos[2] if cos else None

        embed = runtime.embed(
            title=(
                f"{cos_icon or castle} Энергостанция "
                f"{interaction.user.name}"
            ),
            color=cos_color,
        )
        if cos_bg and not compact:
            embed.set_image(url=cos_bg)
        if not rows:
            embed.description = (
                "Энергостанция пуста. Купи первый генератор в "
                "«Магазине» — он начнёт приносить доход."
            )
        if not compact:
            embed.set_thumbnail(
                url=interaction.user.display_avatar.url
            )
        embed.add_field(
            name="Кошелёк",
            value=f"{coin} {coins} | {gem} {gems}",
            inline=False,
        )
        embed.add_field(
            name="Доход",
            value=(
                f"{income_str}"
                if compact
                else f"{income_str}\n-# {runtime.income_hint}"
            ),
            inline=False,
        )
        embed.add_field(name="Бонус", value=f"+{total_pct}%", inline=True)
        total_power = await runtime.get_combat_power(user_id)
        combat_pet = await runtime.get_pet_bonus(
            user_id, "combat_power"
        )
        combat_title = await runtime.get_title_bonus(
            user_id, "combat_power"
        )
        combat_mult = 1 + combat_pet + combat_title
        if power_rows:
            top_power = sorted(
                power_rows,
                key=lambda row: int(row[3] * (1 + row[2] * 0.5)),
                reverse=True,
            )[:3]
            power_lines = [
                f"{emoji} {name} ({stars}★) — "
                f"**{int(price * (1 + stars * 0.5) * combat_mult)}**"
                for name, emoji, stars, price in top_power
            ]
            power_value = (
                f"Всего: **{total_power}**\n" + "\n".join(power_lines)
            )
        else:
            power_value = (
                f"Всего: **{total_power}**\n"
                "нет генераторов на энергостанции"
            )
        embed.add_field(
            name="⚔️ Мощь", value=power_value, inline=False
        )
        autoc = await runtime.get_autocollector(user_id)
        if autoc:
            lvl, _ = autoc
            embed.add_field(
                name="🤖 Автосборщик",
                value=(
                    f"Ур. {lvl} (раз в "
                    f"{runtime.autocollect_levels[lvl][1]} ч)"
                ),
                inline=True,
            )
        embed.add_field(
            name="Сетка", value=f"{grid_size} слотов", inline=True
        )
        active_sets = [
            f"{set_def['name']} "
            f"{set_details['set_counts'][set_id]}/"
            f"{len(set_def['items'])}"
            for set_id, set_def in runtime.set_definitions.items()
            if set_details["set_counts"][set_id] > 0
        ]
        embed.add_field(
            name="Сеты",
            value=(
                f"**+{int(set_details['total'] * 100)}%**\n"
                + (
                    ", ".join(active_sets)
                    if active_sets
                    else "нет активных сетов"
                )
            ),
            inline=True,
        )

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
        if rows and not visible_rows:
            embed.description = (
                "По выбранному фильтру ничего нет. "
                f"Фильтр: **{runtime.storage_filters[filter_mode]}**."
            )
        embed.set_footer(
            text=(
                f"Фильтр: {runtime.storage_filters[filter_mode]} · "
                f"Показано {len(visible_rows)}/{len(rows)}"
            )
        )
        return await runtime.fix_emojis(embed)

    async def build_generator_details_embed(interaction, page: int = 0):
        user_id = interaction.user.id
        compact = await runtime.is_accessibility_mode(user_id)

        async with runtime.db.execute(
            """
            SELECT inv.slot, inv.item_id, inv.stars, i.name, i.emoji,
                   i.income_per_hour, i.income_gems_per_hour,
                   i.price, i.rarity
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND inv.location = 'profile'
            ORDER BY inv.slot ASC
            """,
            (user_id,),
        ) as c:
            rows = await c.fetchall()

        embed = runtime.embed(
            title=f"{runtime.emoji('_inventory')} Детали генераторов",
            color=0x3498db,
        )

        if not rows:
            embed.description = (
                "У тебя нет генераторов на энергостанции."
            )
            return embed, 1

        bonus = await runtime.get_status_bonus(user_id)
        clan = await runtime.get_clan(user_id)
        clan_bonus = (clan[4] or 0.0) if clan else 0.0
        pet_coins = await runtime.get_pet_bonus(
            user_id, "income_coins"
        )
        pet_gems = await runtime.get_pet_bonus(
            user_id, "income_gems"
        )
        title_coins = await runtime.get_title_bonus(
            user_id, "income_coins"
        )
        title_gems = await runtime.get_title_bonus(
            user_id, "income_gems"
        )
        combat_pet = await runtime.get_pet_bonus(
            user_id, "combat_power"
        )
        combat_title = await runtime.get_title_bonus(
            user_id, "combat_power"
        )
        combat_mult = 1 + combat_pet + combat_title
        prestige_bonus = await runtime.get_prestige_bonus(user_id)
        collection_bonus = await runtime.get_collection_bonus(user_id)
        set_details = await runtime.get_set_details(user_id)
        set_bonus = set_details["total"]

        mult_coins = (1 + bonus) * (1 + clan_bonus) * (
            1
            + pet_coins
            + title_coins
            + prestige_bonus
            + collection_bonus
            + set_bonus
        )
        mult_gems = (1 + bonus) * (1 + clan_bonus) * (
            1
            + pet_gems
            + title_gems
            + prestige_bonus
            + collection_bonus
            + set_bonus
        )

        details = []
        total_coins = 0.0
        total_gems = 0.0
        total_power = 0
        for (
            slot,
            item_id,
            stars,
            name,
            default_emoji,
            inc_coins,
            inc_gems,
            price,
            rarity,
        ) in rows:
            star_mult = 1 + runtime.star_bonus.get(stars, 0)
            eff_coins = inc_coins * star_mult * 3600 * mult_coins
            eff_gems = inc_gems * star_mult * 3600 * mult_gems
            gen_power = int(
                (price or 0) * (1 + stars * 0.5) * combat_mult
            )
            total_coins += eff_coins
            total_gems += eff_gems
            total_power += gen_power
            set_name = runtime.set_definitions.get(
                runtime.item_set.get(item_id), {}
            ).get("name", "—")
            details.append(
                (
                    slot,
                    name,
                    default_emoji,
                    stars,
                    rarity,
                    eff_coins,
                    eff_gems,
                    set_name,
                    gen_power,
                )
            )

        page_size = runtime.page_size
        total_pages = max(
            1, (len(details) + page_size - 1) // page_size
        )
        page = max(0, min(page, total_pages - 1))
        chunk = details[
            page * page_size:page * page_size + page_size
        ]

        embed.description = (
            f"Страница {page + 1}/{total_pages}. "
            "Доход с учётом звёзд и всех бонусов "
            "(статус, клан, питомец, титул, престиж, коллекция, сеты)."
            + (
                ""
                if compact
                else f"\n-# {runtime.income_hint}"
            )
        )

        for (
            slot,
            name,
            default_emoji,
            stars,
            rarity,
            eff_coins,
            eff_gems,
            set_name,
            gen_power,
        ) in chunk:
            star_str = f"{stars}★" if stars > 0 else "—"
            inc_str = f"🪙 {eff_coins:.2f}/час"
            if eff_gems > 0:
                inc_str += f" | 💎 {eff_gems:.4f}/час"
            embed.add_field(
                name=(
                    f"Слот {slot}: {default_emoji} {name} "
                    f"({star_str})"
                )[:256],
                value=(
                    f"{runtime.rarity_names.get(rarity, rarity)}\n"
                    f"{inc_str}\n"
                    f"⚔️ Мощь: **{gen_power}**\n"
                    f"Сет: {set_name}"
                ),
                inline=False,
            )

        set_lines = []
        for set_id, set_def in runtime.set_definitions.items():
            count = set_details["set_counts"].get(set_id, 0)
            if count <= 0:
                continue
            _, bonus_value = set_details["set_tiers"].get(
                set_id, (0, 0.0)
            )
            set_lines.append(
                f"{set_def['emoji']} {set_def['name']}: "
                f"{count}/{len(set_def['items'])} "
                f"(+{int(bonus_value * 100)}%)"
            )
        if set_lines:
            embed.add_field(
                name="Синергия сетов",
                value=(
                    "Сеты: +{s}%\nСоседство: {p} пар → +{a}%\n"
                    "Этажи: {r} → +{f}%\n**Итого: +{t}%**"
                ).format(
                    s=int(set_details["set_bonus"] * 100),
                    p=set_details["adjacency_pairs"],
                    a=int(set_details["adjacency_bonus"] * 100),
                    r=set_details["full_rows"],
                    f=int(set_details["floor_bonus"] * 100),
                    t=int(set_details["total"] * 100),
                ),
                inline=False,
            )
            embed.add_field(
                name="Наборы",
                value="\n".join(set_lines),
                inline=False,
            )

        embed.add_field(
            name="💰 Итого по энергостанции",
            value=(
                f"🪙 {total_coins:.2f}/час | "
                f"💎 {total_gems:.4f}/час\n"
                f"⚔️ Мощь: **{total_power}**"
            ),
            inline=False,
        )
        embed.set_footer(
            text=(
                f"Генераторов: {len(details)} | "
                "Доход на слот — в каждой строке"
            )
        )
        return await runtime.fix_emojis(embed), total_pages

    return (
        build_stats_embed,
        build_user_profile_embed,
        build_public_profile_embed,
        build_profile_embed,
        build_generator_details_embed,
    )
