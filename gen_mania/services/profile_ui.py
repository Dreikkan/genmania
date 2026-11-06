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
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self._price_formatter: Callable[[int], str] = str
        self.titles: dict = {}
        self.title_bonuses: dict = {}
        self.btype_names: dict = {}
        self.button_emojis: dict = {}
        self.pet_types: dict = {}
        self.autocollect_levels: dict = {}
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
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        price_formatter: Callable[[int], str],
        titles: dict,
        title_bonuses: dict,
        btype_names: dict,
        button_emojis: dict,
        pet_types: dict,
        autocollect_levels: dict,
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
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self._price_formatter = price_formatter
        self.titles = titles
        self.title_bonuses = title_bonuses
        self.btype_names = btype_names
        self.button_emojis = button_emojis
        self.pet_types = pet_types
        self.autocollect_levels = autocollect_levels
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
        guild_id = interaction.guild_id
        settings = await runtime.get_settings(guild_id)
        compact = await runtime.is_accessibility_mode(user_id)
        custom = settings["custom_emojis"]

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

    return (
        build_stats_embed,
        build_user_profile_embed,
        build_public_profile_embed,
    )
