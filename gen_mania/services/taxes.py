"""Tax rate service.

Rates depend on guild settings and Discord membership. The service gets
both through runtime callbacks so tests can replace ``bot.guilds`` and
``get_settings`` on the imported bot module without losing behavior.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable

import aiosqlite
import discord


class TaxRuntime:
    """Адаптер между bot.py и налоговым сервисом."""

    def __init__(self):
        self._bot_getter: Callable[[], Any] = lambda: None
        self._settings_getter: Callable[[], Callable] = lambda: None
        self._tax_cache_getter: Callable[[], dict] = lambda: {}
        self.cache_ttl = 600.0
        self.default_tax_rate = 0.02
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        bot_getter: Callable[[], Any],
        settings_getter: Callable[[], Callable],
        tax_cache_getter: Callable[[], dict],
        cache_ttl: float,
        default_tax_rate: float,
        logger: logging.Logger,
    ) -> None:
        self._bot_getter = bot_getter
        self._settings_getter = settings_getter
        self._tax_cache_getter = tax_cache_getter
        self.cache_ttl = cache_ttl
        self.default_tax_rate = default_tax_rate
        self.logger = logger

    @property
    def bot(self):
        return self._bot_getter()

    @property
    def tax_cache(self) -> dict:
        return self._tax_cache_getter()

    async def get_settings(self, guild_id: int) -> dict:
        getter = self._settings_getter()
        return await getter(guild_id)


def make_tax_layer(runtime: TaxRuntime):
    """Возвращает пару ``get_tax_rate_for_user`` / ``get_tax_rate_map``."""

    async def get_tax_rate_for_user(user_id: int) -> float:
        """Ставка налога: максимум по общим гильдиям, иначе дефолт.

        Профиль игрока глобальный, поэтому нельзя брать настройку одной
        случайной гильдии: иначе можно укрыться в гильдии с нулевым налогом.
        """
        now_ts = datetime.datetime.now().timestamp()
        cached = runtime.tax_cache.get(user_id)
        if cached and (now_ts - cached[0]) < runtime.cache_ttl:
            return cached[1]

        rates = []
        for guild in getattr(runtime.bot, "guilds", []) or []:
            try:
                member = guild.get_member(user_id)
                if member is None:
                    try:
                        member = await guild.fetch_member(user_id)
                    except (
                        discord.NotFound,
                        discord.Forbidden,
                        discord.HTTPException,
                        AttributeError,
                        TypeError,
                    ):
                        member = None
                if member is None:
                    continue
            except Exception:
                continue
            settings = await runtime.get_settings(guild.id)
            rate = settings.get("tax_rate", runtime.default_tax_rate)
            if rate is not None:
                rates.append(float(rate))
        if not rates:
            rate = runtime.default_tax_rate
        else:
            rate = max(0.0, min(1.0, max(rates)))
        runtime.tax_cache[user_id] = (now_ts, rate)
        return rate

    async def get_tax_rate_map() -> dict[int, float]:
        """Ставки налогов по всем участникам гильдий за один проход.

        tax_collector не должен делать отдельный обход гильдий на каждого
        игрока: один проход по guild.members строит максимум по гильдиям.
        """
        rates: dict[int, float] = {}
        for guild in getattr(runtime.bot, "guilds", []) or []:
            try:
                settings = await runtime.get_settings(guild.id)
                rate = float(
                    settings.get("tax_rate", runtime.default_tax_rate) or 0.0
                )
                rate = max(0.0, min(1.0, rate))
                for member in getattr(guild, "members", ()) or ():
                    uid = getattr(member, "id", None)
                    if uid is None:
                        continue
                    current = rates.get(uid)
                    if current is None or rate > current:
                        rates[uid] = rate
            except (
                aiosqlite.Error,
                AttributeError,
                TypeError,
                ValueError,
                IndexError,
            ) as exc:
                runtime.logger.debug(
                    "TAX_MAP: пропуск гильдии %s: %s",
                    getattr(guild, "id", None),
                    exc,
                )
                continue
        return rates

    return get_tax_rate_for_user, get_tax_rate_map
