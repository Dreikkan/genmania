"""In-game guide sections, text paging and embeds."""
from __future__ import annotations

import logging
from typing import Any, Callable


def _format_percent(value: float) -> str:
    text = f"{value * 100:.1f}"
    return text.rstrip("0").rstrip(".")


def _format_plain(value: float) -> str:
    text = f"{value:.2f}"
    return text.rstrip("0").rstrip(".")


class GuideRuntime:
    """Адаптер между bot.py и сервисом путеводителя."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self._price_formatter: Callable[[int], str] = str
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._season_xp_getter: Callable[[], Callable] = lambda: None
        self.constants: dict = {}
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        embed_factory: Callable[..., Any],
        emoji_fixer: Callable[[Any], Any],
        price_formatter: Callable[[int], str],
        emoji_getter: Callable[[], Callable],
        season_xp_getter: Callable[[], Callable],
        constants: dict,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._embed_factory = embed_factory
        self._emoji_fixer = emoji_fixer
        self._price_formatter = price_formatter
        self._emoji_getter = emoji_getter
        self._season_xp_getter = season_xp_getter
        self.constants = constants
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

    def emoji(self, key: str):
        return self._emoji_getter()(key)

    def season_expected_daily_xp(self):
        return self._season_xp_getter()()


def make_guide_layer(runtime: GuideRuntime):
    """Возвращает функции путеводителя, привязанные к runtime."""

    async def _guide_section_data(key: str) -> tuple[str, str]:
        config = runtime.constants
        AUCTION_ANTI_SNIPE_SECONDS = config["AUCTION_ANTI_SNIPE_SECONDS"]
        ACHIEVEMENT_COUNT = config["ACHIEVEMENT_COUNT"]
        AUTOCOLLECT_LEVELS = config["AUTOCOLLECT_LEVELS"]
        AUTOCOLLECT_PRICE_GEMS = config["AUTOCOLLECT_PRICE_GEMS"]
        BANK_DAILY_RATE = config["BANK_DAILY_RATE"]
        BANK_DEPOSIT_INCOME_HOURS = config["BANK_DEPOSIT_INCOME_HOURS"]
        BANK_LOAN_INCOME_HOURS = config["BANK_LOAN_INCOME_HOURS"]
        BANK_LOAN_INTEREST = config["BANK_LOAN_INTEREST"]
        BANK_LOAN_LTV = config["BANK_LOAN_LTV"]
        BANK_LOAN_MAX = config["BANK_LOAN_MAX"]
        BANK_LOAN_TERM_DAYS = config["BANK_LOAN_TERM_DAYS"]
        BANK_MAX_DEPOSIT = config["BANK_MAX_DEPOSIT"]
        CASTLE = config["CASTLE"]
        CATALYST_BONUS = config["CATALYST_BONUS"]
        COLLECTION_BONUS_PER_ITEM = config["COLLECTION_BONUS_PER_ITEM"]
        CRAFT_COST_EARLY = config["CRAFT_COST_EARLY"]
        CRAFT_COST_LATE = config["CRAFT_COST_LATE"]
        CRAFT_HARD_PITY = config["CRAFT_HARD_PITY"]
        CRAFT_PITY_BONUS = config["CRAFT_PITY_BONUS"]
        CRAFT_PITY_MAX = config["CRAFT_PITY_MAX"]
        CRAFT_SETTINGS = config["CRAFT_SETTINGS"]
        DEFAULT_TAX_RATE = config["DEFAULT_TAX_RATE"]
        DUEL_COOLDOWN_SECONDS = config["DUEL_COOLDOWN_SECONDS"]
        DUEL_MAX_BET_PCT = config["DUEL_MAX_BET_PCT"]
        DUEL_POWER_TOLERANCE = config["DUEL_POWER_TOLERANCE"]
        EXCHANGE_DAILY_GEM_CAP = config["EXCHANGE_DAILY_GEM_CAP"]
        EXCHANGE_FEE_RATE = config["EXCHANGE_FEE_RATE"]
        GEM_INCOME = config["GEM_INCOME"]
        GEMS_PER_COIN_RATE = config["GEMS_PER_COIN_RATE"]
        GENERATOR_EARLY_INCOME_MULT = config[
            "GENERATOR_EARLY_INCOME_MULT"
        ]
        GENERATOR_EARLY_PRICE_MULT = config["GENERATOR_EARLY_PRICE_MULT"]
        GENERATOR_LATE_INCOME_MULT = config[
            "GENERATOR_LATE_INCOME_MULT"
        ]
        GENERATOR_LATE_PRICE_MULT = config["GENERATOR_LATE_PRICE_MULT"]
        GENERATOR_LATE_START_TIER = config["GENERATOR_LATE_START_TIER"]
        GENERATOR_TIER_COUNT = config["GENERATOR_TIER_COUNT"]
        MARKET_MAX_ACTIVE_ORDERS = config["MARKET_MAX_ACTIVE_ORDERS"]
        MARKET_MAX_DAILY_VOLUME = config["MARKET_MAX_DAILY_VOLUME"]
        MARKET_MAX_ORDER_QTY = config["MARKET_MAX_ORDER_QTY"]
        MARKET_MAX_ORDER_VALUE = config["MARKET_MAX_ORDER_VALUE"]
        MARKET_ORDER_DURATION_HOURS = config["MARKET_ORDER_DURATION_HOURS"]
        MARKET_ORDER_FEE_RATE = config["MARKET_ORDER_FEE_RATE"]
        PET_BREAKTHROUGH_EFFECT_BONUS = config[
            "PET_BREAKTHROUGH_EFFECT_BONUS"
        ]
        PET_BREAKTHROUGH_LEVELS = config["PET_BREAKTHROUGH_LEVELS"]
        PET_EFFECT_NAMES = config["PET_EFFECT_NAMES"]
        PET_FEED_COOLDOWN_HOURS = config["PET_FEED_COOLDOWN_HOURS"]
        PET_FEED_COST_COIN_GROWTH = config["PET_FEED_COST_COIN_GROWTH"]
        PET_FEED_COST_COINS = config["PET_FEED_COST_COINS"]
        PET_FEED_COST_GEM_GROWTH = config["PET_FEED_COST_GEM_GROWTH"]
        PET_FEED_COST_GEMS = config["PET_FEED_COST_GEMS"]
        PET_MAX_LEVEL = config["PET_MAX_LEVEL"]
        PET_TYPES = config["PET_TYPES"]
        PET_COUNT = config["PET_COUNT"]
        TITLE_COUNT = config["TITLE_COUNT"]
        TOP_COUNT = config["TOP_COUNT"]
        PRESTIGE_BASE_REQUIREMENT = config["PRESTIGE_BASE_REQUIREMENT"]
        PRESTIGE_BONUS_CAP = config["PRESTIGE_BONUS_CAP"]
        PRESTIGE_BONUS_PER_POINT = config["PRESTIGE_BONUS_PER_POINT"]
        PRESTIGE_STEP_REQUIREMENT = config["PRESTIGE_STEP_REQUIREMENT"]
        RAID_DAILY_LOSS_CAP = config["RAID_DAILY_LOSS_CAP"]
        RAID_LOOT_RATE = config["RAID_LOOT_RATE"]
        RAID_MIN_TARGET_POWER_RATIO = config[
            "RAID_MIN_TARGET_POWER_RATIO"
        ]
        RAID_TARGET_SHIELD_HOURS = config["RAID_TARGET_SHIELD_HOURS"]
        SEASON_PREMIUM_COST_GEMS = config["SEASON_PREMIUM_COST_GEMS"]
        SEASON_TOTAL_XP_TEXT = config["SEASON_TOTAL_XP_TEXT"]
        SEASON_XP_BASE = config["SEASON_XP_BASE"]
        SEASON_XP_STEP = config["SEASON_XP_STEP"]
        SET_ADJACENCY_BONUS = config["SET_ADJACENCY_BONUS"]
        SET_ADJACENCY_MAX = config["SET_ADJACENCY_MAX"]
        SET_DEFINITIONS = config["SET_DEFINITIONS"]
        SET_FLOOR_BONUS = config["SET_FLOOR_BONUS"]
        SET_FLOOR_MAX = config["SET_FLOOR_MAX"]
        SET_TOTAL_MAX = config["SET_TOTAL_MAX"]
        STAR_BONUS = config["STAR_BONUS"]
        STAR_HARD_PITY = config["STAR_HARD_PITY"]
        STAR_PITY_BONUS = config["STAR_PITY_BONUS"]
        STAR_PITY_MAX = config["STAR_PITY_MAX"]
        STAR_UPGRADE = config["STAR_UPGRADE"]

        star_chances = " / ".join(
            f"{star}\u2605 {int(STAR_UPGRADE[star]['chance'] * 100)}%"
            for star in range(1, 6)
        )
        craft_chance_min = min(
            settings["chance"] for settings in CRAFT_SETTINGS.values()
        )
        craft_gem_max = max(
            settings["gems"] for settings in CRAFT_SETTINGS.values()
        )
        max_pet_levels = min(PET_MAX_LEVEL, 10) * (
            1
            + PET_BREAKTHROUGH_EFFECT_BONUS
            * len(PET_BREAKTHROUGH_LEVELS)
        )
        pet_lines = []
        for pet in PET_TYPES.values():
            effects = [(pet["effect"], pet["per_level"])]
            effects.extend(pet.get("extra_effects", {}).items())
            effect_text = ", ".join(
                f"+{_format_percent(per_level)}% "
                f"{PET_EFFECT_NAMES.get(effect, effect)}/ур."
                for effect, per_level in effects
            )
            pet_lines.append(
                f"{pet['emoji']} {pet['name']} ({pet['price_gems']} 💎) "
                f"\u2014 {effect_text}"
            )
        pet_max_lines = []
        for pet in PET_TYPES.values():
            effects = [(pet["effect"], pet["per_level"])]
            effects.extend(pet.get("extra_effects", {}).items())
            effect_text = ", ".join(
                f"+{_format_percent(per_level * max_pet_levels)}% "
                f"{PET_EFFECT_NAMES.get(effect, effect)}"
                for effect, per_level in effects
            )
            pet_max_lines.append(
                f"{pet['emoji']} {pet['name']} \u2014 {effect_text}"
            )

        gem_income_lines = ""
        if key == "generators":
            gem_ids = tuple(GEM_INCOME)
            placeholders = ",".join("?" for _ in gem_ids)
            async with runtime.db.execute(
                f"SELECT id, name, emoji FROM items WHERE id IN ({placeholders})",
                gem_ids,
            ) as c:
                gem_rows = {
                    row[0]: (row[1], row[2]) for row in await c.fetchall()
                }
            order = {item_id: index for index, item_id in enumerate(gem_ids)}
            sorted_ids = sorted(gem_rows, key=lambda item_id: order[item_id])
            gem_income_lines = "\n".join(
                f"\u2022 {gem_rows[item_id][1]} {gem_rows[item_id][0]}: "
                f"**{_format_plain(GEM_INCOME[item_id])} 💎/\u0447**"
                for item_id in sorted_ids
            )

        sections = {
            "economy": (
                "💰 Экономика",
                "**Валюты:**\n"
                "🪙 Монеты — пассивный доход, дейли, квесты, продажа.\n"
                "💎 Гемы — дейли, квесты, достижения, аукцион, премиум-покупки.\n\n"
                f"**Обмен:** прогрессивный курс: чем больше монет меняешь за сутки, "
                f"тем дороже гем ({runtime.format_price(1000)} → "
                f"{runtime.format_price(15000)} монет за гем). "
                f"Комиссия {int(EXCHANGE_FEE_RATE * 100)}%, "
                f"дневной лимит {EXCHANGE_DAILY_GEM_CAP} гемов из монет. "
                f"Обратно: 1 гем → {GEMS_PER_COIN_RATE} монет.\n\n"
                "**Офлайн-доход:** копится до 24 часов; после 2 часов "
                "ручной сбор даёт 70% дохода, автосборщик — 100% в "
                "пределах этого лимита. При установке или снятии "
                "генератора точка накопления сбрасывается.\n\n"
                "**Гемы:** накопление не ограничено потолком.\n\n"
                f"**Банк:** вклад до {runtime.format_price(BANK_MAX_DEPOSIT)} монет "
                f"(или {BANK_DEPOSIT_INCOME_HOURS} ч дохода), "
                f"{int(BANK_DAILY_RATE * 100)}% в день (сложный процент), срок 1–30 дней; "
                "досрочное закрытие — без процентов.\n"
                f"Кредит до {runtime.format_price(BANK_LOAN_MAX)} монет "
                f"(или {BANK_LOAN_INCOME_HOURS} ч дохода) под залог генератора, "
                f"до {int(BANK_LOAN_LTV * 100)}% его стоимости, "
                f"переплата {int(BANK_LOAN_INTEREST * 100)}% за "
                f"{BANK_LOAN_TERM_DAYS} дней. При просрочке залог теряется.\n\n"
                f"**Налоги:** {int(DEFAULT_TAX_RATE * 100)}% в сутки от баланса монет "
                "(значение задаётся в настройках гильдии). Вклады не облагаются.\n\n"
                "**Продажа:** прямая продажа — 10% цены; быстрая продажа 0★ — "
                "безопасно и пачкой; биржа — 70% текущей цены, исполнение по встречным ордерам.\n\n"
                f"**Биржа:** ордера — до {MARKET_MAX_ORDER_QTY} шт., "
                f"{MARKET_MAX_ACTIVE_ORDERS} активных, срок "
                f"{MARKET_ORDER_DURATION_HOURS} ч; цена для магазинных "
                "генераторов — 80–100% магазинной, для epic+ — 50–200%.\n\n"
                "**Где смотреть:** главное меню → «Обмен валют»; «Социум» → «Банк» / «Налоги»."
            ),
            "prestige": (
                "🔁 Перерождение",
                "**Что это:** сброс энергостанции ради постоянного бонуса к доходу.\n\n"
                f"**Очки:** 1-е — {runtime.format_price(PRESTIGE_BASE_REQUIREMENT)}, "
                f"2-е — {runtime.format_price(PRESTIGE_BASE_REQUIREMENT + PRESTIGE_STEP_REQUIREMENT)}, "
                f"3-е — {runtime.format_price(PRESTIGE_BASE_REQUIREMENT + 2 * PRESTIGE_STEP_REQUIREMENT)} "
                f"и т.д. (каждое следующее +{runtime.format_price(PRESTIGE_STEP_REQUIREMENT)}). "
                "Уже полученные очки учитываются.\n\n"
                f"**Бонус:** +{_format_percent(PRESTIGE_BONUS_PER_POINT)}% к доходу "
                f"за каждое очко, максимум +{_format_percent(PRESTIGE_BONUS_CAP)}%. "
                "Очки сохраняются навсегда.\n\n"
                "**Сбрасывается:** монеты, инвентарь, сетка, катализаторы, улучшения, вклад, ежедневные квесты.\n\n"
                "**Остаётся:** гемы, питомцы, титулы, активные временные статусы, достижения, клан, косметика, сюжетные квесты, статистика.\n\n"
                "**Где:** главное меню → «Перерождение»."
            ),
            "collection": (
                "📖 Коллекция",
                "**Что это:** все генераторы, которые ты когда-либо получал.\n\n"
                f"**Бонус:** +{_format_percent(COLLECTION_BONUS_PER_ITEM)}% к доходу "
                f"за каждый открытый генератор; всего {GENERATOR_TIER_COUNT} "
                f"генераторов → максимум +{_format_percent(COLLECTION_BONUS_PER_ITEM * GENERATOR_TIER_COUNT)}%.\n\n"
                "**Как открыть:** купить, получить синтезом, в дейли, адвенте или на аукционе.\n\n"
                "**Где:** «Мой профиль» → «Коллекция»."
            ),
            "generators": (
                "🏗️ Генераторы",
                "**Покупка:** common/uncommon/rare — в «Магазине»; epic–mythic — биржа или аукцион; пространственный/божественный/легендарный — только синтез.\n\n"
                f"**Экономика тиров:** до {GENERATOR_LATE_START_TIER - 1} тира "
                f"цена ×{_format_plain(GENERATOR_EARLY_PRICE_MULT)}, "
                f"доход ×{_format_plain(GENERATOR_EARLY_INCOME_MULT)}; "
                f"с {GENERATOR_LATE_START_TIER} тира — "
                f"×{_format_plain(GENERATOR_LATE_PRICE_MULT)} и "
                f"×{_format_plain(GENERATOR_LATE_INCOME_MULT)}. "
                "Высокие тиры окупаются дольше, зато дают больше дохода на слот.\n\n"
                f"**Синтез:** до {GENERATOR_LATE_START_TIER - 1} тира — "
                f"{CRAFT_COST_EARLY} одинаковых 0★ → 1 выше уровнем; "
                f"с {GENERATOR_LATE_START_TIER} тира — "
                f"{CRAFT_COST_LATE} копии. Шанс падает с тиром "
                f"({_format_percent(1.0)}% → "
                f"{_format_percent(craft_chance_min)}%), стоимость в гемах растёт "
                f"(0 → {runtime.format_price(craft_gem_max)}). "
                f"При провале сгорает {CRAFT_COST_EARLY - 1} копия "
                f"(на раннем участке) или {CRAFT_COST_LATE - 1} "
                f"(на позднем), одна возвращается. "
                f"Катализатор +{int(CATALYST_BONUS * 100)}%, "
                f"за каждый провал шанс растёт на {int(CRAFT_PITY_BONUS * 100)}% "
                f"(до +{int(CRAFT_PITY_MAX * 100)}%), "
                f"на {CRAFT_HARD_PITY}-й попытке — гарантия.\n\n"
                f"**Гем-генераторы:**\n{gem_income_lines}\n\n"
                f"**Звёзды:** 0–5★. Шанс: {star_chances}. "
                f"Каждый провал даёт +{int(STAR_PITY_BONUS * 100)}% к шансу "
                f"(до +{int(STAR_PITY_MAX * 100)}%), на {STAR_HARD_PITY}-й попытке — гарантия. "
                "При провале сгорает 1 копия, звезда не понижается.\n"
                f"Бонус к доходу: 1★ +{int(STAR_BONUS[1] * 100)}%, "
                f"2★ +{int(STAR_BONUS[2] * 100)}%, 3★ +{int(STAR_BONUS[3] * 100)}%, "
                f"4★ +{int(STAR_BONUS[4] * 100)}%, 5★ +{int(STAR_BONUS[5] * 100)}%.\n\n"
                "**Продажа:** прямая — только `common`/`uncommon`/`rare`, 10% от цены. "
                "Быстрая продажа 0★ — обычные/необычные/редкие и дубликаты, "
                "звёздные и `epic`+ защищены. `epic`+ — биржа, аукцион или синтез.\n\n"
                "**Хранилище:** «Энергостанция» → «Хранилище». Генераторы там не дают доход.\n\n"
                "**Временное хранилище:** 100 слотов для предметов, которым не хватило места на энергостанции и хранилище."
            ),
            "sets": (
                "🧩 Сеты",
                "**Что это:** генераторы объединяются в сеты по теме.\n\n"
                "**Бонусы:**\n"
                "• за количество предметов сета — до +6% за сет;\n"
                f"• за соседние пары одного сета — +{_format_percent(SET_ADJACENCY_BONUS)}% "
                f"за пару (до +{_format_percent(SET_ADJACENCY_MAX)}%);\n"
                f"• за заполненные ряды — +{_format_percent(SET_FLOOR_BONUS)}% "
                f"за ряд (до +{_format_percent(SET_FLOOR_MAX)}%).\n\n"
                f"**Потолок синергии:** +{_format_percent(SET_TOTAL_MAX)}% к доходу.\n\n"
                "**Где смотреть:** «Энергостанция» → поле «Сеты»; подробности — в профиле.\n\n"
                "**Совет:** ставь генераторы одного сета рядом, чтобы получать больше."
            ),
            "pets": (
                "🐾 Питомцы",
                f"**{PET_COUNT} видов (эффект за уровень):**\n"
                + "\n".join(pet_lines)
                + "\n\n"
                f"**Soft cap:** после 10 ур. прямой рост останавливается. "
                f"Каждый прорыв даёт +{_format_percent(PET_BREAKTHROUGH_EFFECT_BONUS)}% "
                f"к эффективному уровню; максимум — "
                f"{_format_plain(max_pet_levels)} эффективных уровней.\n\n"
                "**Максимум эффекта на "
                f"{PET_MAX_LEVEL} ур.:**\n"
                + "\n".join(pet_max_lines)
                + "\n\n"
                f"**Кормление:** раз в {PET_FEED_COOLDOWN_HOURS} ч, "
                f"базовая цена {PET_FEED_COST_COINS} 🪙 + "
                f"{PET_FEED_COST_GEMS} 💎, +1 уровень. Максимум "
                f"{PET_MAX_LEVEL} ур. За каждый прорыв цена растёт "
                f"×{PET_FEED_COST_COIN_GROWTH} (монеты) и "
                f"×{PET_FEED_COST_GEM_GROWTH} (гемы).\n\n"
                "**Прорывы:** 10, 25, 50, 75, 100, 125, 150, 175, 200 ур.\n\n"
                "**Активный:** только один, но купить можно всех.\n\n"
                "**Где:** «Магазин» → «Питомцы» или «Мой профиль» → «Питомцы»."
            ),
            "titles": (
                "🏅 Титулы",
                f"**{TITLE_COUNT} титул**, почти каждый даёт **+1–3%** к доходу/синтезу/мощи/рейдам. "
                "Активен только один титул.\n\n"
                "**Примеры:**\n"
                "«Новичок» — всем.\n"
                "«Богач» — 10 000 монет → +2% доход.\n"
                "«Алхимик» — 10 синтезов → +1% шанс синтеза.\n"
                "«Звёздный лорд» — 5★ генератор → +2% мощь.\n"
                "«Герой сюжета» — 5 квестов → +2% шанс синтеза.\n\n"
                "**Где:** «Мой профиль» → «Титулы»."
            ),
            "clans": (
                "🏰 Кланы",
                "**Создание:** 500 🪙.\n\n"
                "**Состав:** базово 10 мест; расширяется за монеты из сундука в «Улучшениях» (до 50).\n\n"
                "**Роли:** лидер, заместитель, офицер, ветеран, участник.\n\n"
                "**Сундук:** общий банк клана.\n\n"
                "**Сетка:** 6×6, отдельная от личной энергостанции. Генераторы в ней дают **мощь клана** для войн и не приносят монеты напрямую. "
                "Личные генераторы на энергостанции на клан не работают.\n\n"
                "**Бонус к доходу:** зависит от уровня клана: +1% за уровень, максимум +20%. "
                "Уровень растёт от клановых квестов, пожертвований, войн и взносов в сундук.\n\n"
                "**Квесты:** недельные (синтезы, покупки, рейды, войны).\n\n"
                "**Войны:** 24 ч, у кланов есть HP. Участники атакуют раз в 1 ч; урон зависит от мощи. "
                "Победитель получает сундук и XP; награда растёт с уровнем клана.\n\n"
                "**Где:** «Социум» → «Клан»."
            ),
            "pvp": (
                "⚔️ PvP",
                "**Рейды:**\n"
                f"• 1–3 чел, кулдаун 1 ч; щит цели "
                f"{RAID_TARGET_SHIELD_HOURS} ч.\n"
                f"• Кража {int(RAID_LOOT_RATE * 100)}% кошелька (+бонус волка).\n"
                f"• Дневной лимит потерь цели: {int(RAID_DAILY_LOSS_CAP * 100)}% баланса.\n"
                f"• Нельзя атаковать цель слабее {int(RAID_MIN_TARGET_POWER_RATIO * 100)}% мощи отряда.\n"
                "• Дневной лимит добычи атакующего: 50% своего баланса (мин. 1000).\n"
                "• Мощь = сумма (цена × (1 + звёзды × 0.5)).\n\n"
                "**Дуэли:**\n"
                f"• Ставка не больше {int(DUEL_MAX_BET_PCT * 100)}% баланса каждого.\n"
                f"• КД после дуэли: {DUEL_COOLDOWN_SECONDS // 60} мин.\n"
                "• Режимы: `dice` (рандом) или `power` (мощь с разбросом).\n"
                f"• В power-дуэли соперник должен быть в диапазоне ±{int(DUEL_POWER_TOLERANCE * 100)}% твоей мощи.\n"
                "• Победитель забирает банк.\n\n"
                "**Где:** «Социум» → «Рейд» / «Дуэль»."
            ),
            "power": (
                f"{runtime.emoji('_raid')} Мощь",
                "**Формула:**\n"
                "Мощь генератора = цена × (1 + 0.5 × звёзды).\n"
                "Мощь игрока = сумма всех генераторов **на энергостанции**, "
                "затем × (1 + бонус питомца + бонус титулов).\n\n"
                "**Пример:** Базовый генератор 15, 3★ → 15 × 2.5 = 37.5 → "
                "**37** (дробная часть отбрасывается).\n\n"
                "**Что не считается:** генераторы в хранилище, временном "
                "хранилище и клановой сетке. Звёзды учитываются только у "
                "генераторов на личной энергостанции.\n\n"
                f"**Бонусы:** Дракончик даёт +4% мощи за уровень "
                f"(с soft cap, максимум +"
                f"{_format_percent(0.04 * max_pet_levels)}%), титулы "
                "«Звёздный лорд», «Дуэлянт», «Клановый воин» и «Охотник за "
                "достижениями» — свои проценты.\n\n"
                "**Где используется:** рейды, дуэли в режиме `power`, "
                "клановые войны и топ по мощи."
            ),
            "auction": (
                "🏛️ Аукцион",
                "**Лоты:** любой генератор, кроме synthesis-only, 1–72 ч.\n\n"
                f"**Ставка:** должна быть выше текущей; ставка в последние "
                f"{AUCTION_ANTI_SNIPE_SECONDS // 60} мин продлевает лот.\n\n"
                "**Buyout:** продавец задаёт цену мгновенного выкупа при "
                "выставлении лота. Buyout должен быть больше стартовой "
                "цены; если он не больше текущей ставки, кнопка выкупа "
                "недоступна. Покупатель сразу получает предмет, продавец — "
                "деньги за вычетом комиссии.\n\n"
                "**Комиссия:** 5% с продавца.\n\n"
                "**Закрытие:** предмет передаётся победителю или возвращается продавцу, если ставок не было.\n\n"
                "**Где:** «Социум» → «Аукцион»."
            ),
            "orders": (
                "📋 Ордера биржи",
                "**Что это:** заявка на покупку или продажу предметов по своей цене.\n\n"
                "**Продажа:** предмет уходит в эскроу, при исполнении продавец получает деньги.\n\n"
                "**Покупка:** монеты резервируются, при исполнении покупатель получает предмет.\n\n"
                "**Отмена:** активный ордер можно отменить; эскроу/резерв возвращается.\n\n"
                f"**Срок:** {MARKET_ORDER_DURATION_HOURS} ч.\n\n"
                f"**Лимиты:** до {MARKET_MAX_ACTIVE_ORDERS} активных ордеров, "
                f"до {MARKET_MAX_ORDER_QTY} предметов в одном ордере, "
                f"стоимость ордера до {runtime.format_price(MARKET_MAX_ORDER_VALUE)}, "
                f"дневной оборот до {runtime.format_price(MARKET_MAX_DAILY_VOLUME)}.\n\n"
                "**Цена:** для магазинных генераторов — 80–100% магазинной, "
                "для epic+ — 50–200% базовой цены.\n\n"
                f"**Комиссия:** {int(MARKET_ORDER_FEE_RATE * 100)}% "
                "с продавца при исполнении.\n\n"
                "**Ограничения:** торгуемые редкости, 0★, кроме synthesis-only; "
                "исполнение частичное, приоритет цены и времени.\n\n"
                "**Где:** «Социум» → «Биржа» → «Мои ордера»."
            ),
            "quests": (
                "📜 Квесты",
                "**Сюжетные (10 глав):**\n"
                "1. Первые шаги — купи генератор (10 💎)\n"
                "2. Алхимик — первый синтез (15 💎)\n"
                "3. Звездочёт — 1★ (20 💎)\n"
                "4. Золотая лихорадка — 1000 монет (25 💎)\n"
                "5. Завоеватель — рейд (30 💎)\n"
                "6. Мастер-алхимик — 10 синтезов (40 💎)\n"
                "7. Дуэлянт — победа в дуэли (50 💎)\n"
                "8. Питомец — купи питомца (60 💎)\n"
                "9. Клановый — вступи в клан (70 💎)\n"
                "10. Коллекционер — 5 достижений (100 💎)\n\n"
                "**Ежедневные:** 3 случайных из пула (синтезы, покупки, перемещения).\n\n"
                "**Масштабирование:** монеты и гемы за дейли и ежедневные квесты растут с престижем (до ×3).\n\n"
                "**Где:** «Квесты» → «Сюжетные» / «Ежедневные»."
            ),
            "season": (
                "🎫 Сезон",
                "**Что это:** месячный battle pass на 30 уровней.\n\n"
                f"**Стоимость уровней:** 1-й — {SEASON_XP_BASE} XP, каждый "
                f"следующий +{SEASON_XP_STEP} XP (100, 200, 300 … 3000).\n"
                f"Всего до 30 уровня — **{SEASON_TOTAL_XP_TEXT} XP**.\n\n"
                "**Сколько XP даёт действие:**\n"
                "• Синтез: +50 за успех, +15 за провал.\n"
                "• Рейд: +150 за победу, +40 за поражение.\n"
                "• Дуэль: +150 за победу, +40 за поражение.\n"
                "• Ежедневная награда: +250.\n"
                "• Ежедневный квест: +120.\n"
                "• Сюжетный квест: +200; достижение: +100.\n"
                "• Перерождение: +500.\n\n"
                "**Дневные лимиты:**\n"
                "• Синтез: 400 успех / 120 провал.\n"
                "• Рейд: 300 победа / 80 поражение.\n"
                "• Дуэль: 450 победа / 120 поражение.\n"
                "• Дейли: 250; квест: 360.\n"
                "• Сюжетные квесты: 400; достижения: 300.\n"
                "• Перерождение: 500.\n\n"
                "**Лимит за одно начисление:** сюжетный квест — не больше 400 XP, "
                "достижение — не больше 300 XP. Остальные действия "
                "начисляются по одному событию.\n\n"
                f"**Достижимость:** активная игра даёт около "
                f"{runtime.season_expected_daily_xp()} XP/день; за 30 дней это "
                f"~{runtime.season_expected_daily_xp() * 30} XP, поэтому 30 уровень "
                "достижим без хардкора.\n\n"
                "**Выходные:** +50% к XP, но дневные лимиты не обходятся.\n\n"
                "**Награды:** бесплатная линейка — монеты, гемы и предметы; "
                "премиум — дополнительные гемы и катализаторы.\n\n"
                f"**Премиум:** {SEASON_PREMIUM_COST_GEMS} 💎; "
                "награды выдаются только один раз.\n\n"
                "**Сброс:** в начале нового месяца прогресс начинается заново.\n\n"
                "**Где:** главное меню → «Сезон» или «Квесты» → «Сезон»."
            ),
            "daily": (
                "📅 Дейли и адвент",
                "**Дейли:**\n"
                "• 30-дневный стрик.\n"
                "• Награды растут плавно: 30 🪙 (день 1) → 1500 🪙 + 8 💎 + предмет (день 30).\n"
                "• Предметы: дни 5, 7, 10, 14, 20, 25, 30.\n"
                "• Монеты и гемы растут с престижем (до ×3).\n"
                "• Сброс при пропуске дня.\n\n"
                "**Праздничный календарь:**\n"
                "• Открывается на праздники: зимние, Хэллоуин, майские, 23 февраля, 8 Марта, "
                "Валентинов день, День святого Патрика, День космонавтики, День России, Октоберфест, День народного единства.\n"
                "• Национальные события: Китай, США, Великобритания, Беларусь, Казахстан.\n"
                "• Количество окошек зависит от события.\n"
                "• Открывается 1 окошко в день, только следующее.\n"
                "• Награды: монеты, гемы, предметы.\n\n"
                "**Где:** «Ежедневная награда» в главном меню, «Мой профиль» → «Праздники»."
            ),
            "achievements": (
                "🏆 Достижения",
                f"**{ACHIEVEMENT_COUNT} штук:** за синтезы, звёзды, гемы, монеты, катализаторы, рейды.\n\n"
                "**Награда:** гемы; растёт с престижем (до ×3).\n\n"
                "**Примеры:**\n"
                "«Первый синтез» — +5 💎.\n"
                "«Богач» — 1000 монет → +10 💎.\n"
                "«Легенда» — 5★ → +80 💎.\n"
                "«Гемовый магнат» — первый гемовый генератор → +20 💎.\n\n"
                "**Где:** «Мой профиль» → «Достижения»."
            ),
            "cosmetics": (
                "🎨 Кастомизация",
                "**Цвет эмбеда:** HEX-код (например, `#FF0000`).\n\n"
                "**Фон:** URL картинки (отображается в профиле и энергостанции).\n\n"
                "**Иконка энергостанции:** эмодзи или кастомный `<:name:id>`.\n\n"
                "**Титулы:** выбор активного (влияет на бонус).\n\n"
                "**Где:** «Мой профиль» → «Косметика» / «Титулы»."
            ),
            "autocollector": (
                "🤖 Автосборщик",
                f"**Покупка:** {AUTOCOLLECT_PRICE_GEMS} 💎.\n\n"
                "**Уровни:**\n"
                f"1 ур. — раз в {AUTOCOLLECT_LEVELS[1][1]} ч (после покупки)\n"
                f"2 ур. — {AUTOCOLLECT_LEVELS[2][0]} 💎, "
                f"раз в {AUTOCOLLECT_LEVELS[2][1]} ч\n"
                f"3 ур. — {AUTOCOLLECT_LEVELS[3][0]} 💎, "
                f"раз в {AUTOCOLLECT_LEVELS[3][1]} ч\n\n"
                "**Эффект:** собирает 100% дохода автоматически, без офлайн-штрафа и без потолка.\n\n"
                "**Где:** «Магазин» → «Автосборщик»."
            ),
            "notifications": (
                "🔔 Уведомления",
                "**5 типов:**\n"
                "🐾 Питомец голоден\n"
                "📅 Дейли доступен\n"
                "🏛️ Аукцион скоро закончится\n"
                "🤖 Автосборщик собрал доход\n"
                "⚔️ Клановая война\n\n"
                "**Кулдаун:** аукцион — 1 ч, автосборщик — 4 ч, питомец — 6 ч, "
                "клан — 12 ч, дейли — 20 ч.\n\n"
                "⚠️ Если ЛС закрыты — бот не сможет писать. Открой: Настройки Discord → Конфиденциальность → «Личные сообщения от участников сервера».\n\n"
                "**Где:** «Мой профиль» → «Настройки» → «Уведомления»."
            ),
            "tops": (
                "📊 Топы",
                f"**{TOP_COUNT} типов:** монеты, гемы, мощь, синтезы, питомцы, кланы, престиж, коллекция, дуэли.\n\n"
                "**Режимы:** глобальный (все серверы) и локальный (только этот сервер).\n\n"
                "**Размер:** 10 / 20 / 30.\n\n"
                "**Кэш:** 5 минут (обновляется по кнопке «Обновить»).\n\n"
                "**Где:** «Социум» → «Топы»."
            ),
            "glossary": (
                "📚 Глоссарий",
                "**Энергостанция** — личная сетка генераторов, приносящая доход.\n\n"
                "**Генератор** — предмет, который даёт монеты или гемы в секунду; "
                "в интерфейсе доход показан за час.\n\n"
                "**Звёзды** — улучшение генератора копиями: 0–5★, каждая звезда "
                "повышает доход и мощь.\n\n"
                "**Синтез** — объединение одинаковых 0★-генераторов в один "
                "генератор следующего тира.\n\n"
                "**Коллекция** — все когда-либо открытые генераторы; даёт "
                "постоянный бонус к доходу.\n\n"
                "**Сет** — набор соседних генераторов, дающий синергию.\n\n"
                "**Мощь** — суммарная сила генераторов на энергостанции; "
                "используется в рейдах, дуэлях и войнах.\n\n"
                "**Престиж** — добровольный сброс станции ради постоянного "
                "бонуса к доходу.\n\n"
                "**Сезон** — месячный battle pass на 30 уровней.\n\n"
                "**Гемы** — премиальная валюта; монеты — основная.\n\n"
                "**Где:** «Путеводитель» → «Глоссарий»."
            ),
            "analytics": (
                "📈 Аналитика",
                "**Что внутри:**\n"
                "💰 Доход (монеты/час, гемы/час, полный бонус)\n"
                f"{CASTLE} Энергостанция (генераторы, средний доход, сетка, мощь)\n"
                "🧩 Коллекция и сеты (бонусы, сезон)\n"
                "⚗️ Синтез (попытки, винрейт, катализаторы)\n"
                "🐾 Питомцы (куплено, лучший ур., активный)\n"
                "🏅 Титулы (активный, открыто)\n"
                "⚔️ PvP (дуэли, рейды)\n"
                "🏦 Экономика (вклад, налоги, аукцион)\n"
                "🏆 Прогресс (достижения, гемы, монеты)\n"
                "📊 Всего заработано\n\n"
                "**Где:** «Мой профиль» → «Аналитика»."
            ),
        }

        if key == "sets":
            set_item_ids = [
                item_id
                for set_def in SET_DEFINITIONS.values()
                for item_id in set_def["items"]
            ]
            placeholders = ",".join("?" for _ in set_item_ids)
            async with runtime.db.execute(
                f"SELECT id, name, emoji FROM items WHERE id IN ({placeholders})",
                set_item_ids,
            ) as c:
                item_rows = {row[0]: (row[1], row[2]) for row in await c.fetchall()}
            set_lines = []
            for set_def in SET_DEFINITIONS.values():
                members = []
                for item_id in set_def["items"]:
                    name, emoji = item_rows.get(item_id, (item_id, "⚙️"))
                    members.append(f"{emoji} {name}")
                set_lines.append(
                    f"**{set_def['emoji']} {set_def['name']}** ({len(set_def['items'])}): "
                    + ", ".join(members)
                )
            title, body = sections["sets"]
            sections["sets"] = (
                title,
                body + "\n\n**Состав сетов:**\n" + "\n".join(set_lines),
            )

        if key == "power":
            async with runtime.db.execute(
                "SELECT name, price FROM items "
                "WHERE id LIKE '%_gen' AND price > 0 ORDER BY price ASC"
            ) as c:
                generator_rows = await c.fetchall()
            pairs = [
                f"{name} — **{runtime.format_price(price)}**"
                for name, price in generator_rows
            ]
            table_lines = []
            for index in range(0, len(pairs), 2):
                left = pairs[index]
                right = pairs[index + 1] if index + 1 < len(pairs) else ""
                table_lines.append(f"{left} | {right}".rstrip(" |"))
            title, body = sections["power"]
            sections["power"] = (
                title,
                body
                + "\n\n**Базовая мощь генераторов (0★ = цена):**\n"
                + "\n".join(table_lines),
            )

        return sections.get(key, ("📖 Путеводитель", "Раздел не найден."))


    def _split_guide_text(body: str, limit: int = 3200) -> list[str]:
        """Делит длинный текст гайда на страницы по абзацам."""
        paragraphs = body.split("\n\n")
        pages: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = (
                f"{current}\n\n{paragraph}".strip()
                if current
                else paragraph
            )
            if len(candidate) <= limit:
                current = candidate
                continue
            if current:
                pages.append(current)
            while len(paragraph) > limit:
                pages.append(paragraph[:limit])
                paragraph = paragraph[limit:]
            current = paragraph
        if current:
            pages.append(current)
        return pages or [body]

    async def build_guide_section_page(key: str, page: int = 0):
        title, body = await _guide_section_data(key)
        pages = _split_guide_text(body)
        total_pages = len(pages)
        page = max(0, min(page, total_pages - 1))
        embed = runtime.embed(
            title=title,
            description=pages[page],
            color=0x3498DB,
        )
        if total_pages > 1:  # pragma: no cover
            embed.set_footer(text=f"Страница {page + 1}/{total_pages}")
        return await runtime.fix_emojis(embed), total_pages

    async def build_guide_section_embed(key: str):
        embed, _ = await build_guide_section_page(key, 0)
        return embed

    return (
        _guide_section_data,
        _split_guide_text,
        build_guide_section_page,
        build_guide_section_embed,
    )
