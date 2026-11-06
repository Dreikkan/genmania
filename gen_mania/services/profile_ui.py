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
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self.titles: dict = {}
        self.title_bonuses: dict = {}
        self.btype_names: dict = {}
        self.button_emojis: dict = {}
        self.pet_types: dict = {}
        self.autocollect_levels: dict = {}
        self.castle = "⚡"
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
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        titles: dict,
        title_bonuses: dict,
        btype_names: dict,
        button_emojis: dict,
        pet_types: dict,
        autocollect_levels: dict,
        castle: str,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._settings_getter = settings_getter
        self._accessibility_getter = accessibility_getter
        self._status_bonus_getter = status_bonus_getter
        self._titles_getter = titles_getter
        self._pet_getter = pet_getter
        self._autocollector_getter = autocollector_getter
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self.titles = titles
        self.title_bonuses = title_bonuses
        self.btype_names = btype_names
        self.button_emojis = button_emojis
        self.pet_types = pet_types
        self.autocollect_levels = autocollect_levels
        self.castle = castle
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

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

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

    return build_stats_embed, build_user_profile_embed
