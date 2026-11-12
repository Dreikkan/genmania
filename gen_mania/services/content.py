"""Content editor validation and persistence service."""
from __future__ import annotations

import logging
import math
from typing import Any, Callable


SHORT_NUMBER_SUFFIXES = (
    "", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc"
)


class ContentRuntime:
    """Адаптер между bot.py и сервисом контент-редактора."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._valid_emoji_getter: Callable[[], Callable] = lambda: None
        self._audit_getter: Callable[[], Callable] = lambda: None
        self.id_re = None
        self.max_name = 100
        self.max_description = 500
        self.max_price = 10**18
        self.max_income = 10**9
        self.rarity_colors: dict = {}
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        valid_emoji_getter: Callable[[], Callable],
        audit_getter: Callable[[], Callable],
        id_re,
        max_name: int,
        max_description: int,
        max_price: int,
        max_income: int,
        rarity_colors: dict,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._valid_emoji_getter = valid_emoji_getter
        self._audit_getter = audit_getter
        self.id_re = id_re
        self.max_name = max_name
        self.max_description = max_description
        self.max_price = max_price
        self.max_income = max_income
        self.rarity_colors = rarity_colors
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    def valid_emoji(self, value) -> bool:
        return self._valid_emoji_getter()(value)

    async def audit(self, *args, **kwargs) -> None:
        await self._audit_getter()(*args, **kwargs)


def make_content_layer(runtime: ContentRuntime):
    """Возвращает content-editor функции, привязанные к runtime."""

    def normalize_content_id(value) -> str | None:
        value = (str(value) if value is not None else "").strip()
        return value if runtime.id_re.fullmatch(value) else None

    def normalize_content_name(
        value, max_length: int = None
    ) -> str | None:
        max_length = max_length or runtime.max_name
        value = (str(value) if value is not None else "").strip()
        if not value or len(value) > max_length:
            return None
        return value

    def parse_content_int(
        value, maximum: int = None
    ) -> int | None:
        maximum = runtime.max_price if maximum is None else maximum
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        if number < 0 or number > maximum:
            return None
        return number

    def parse_content_float(
        value, maximum: float = None
    ) -> float | None:
        maximum = runtime.max_income if maximum is None else maximum
        try:
            number = float(str(value).strip().replace(",", "."))
        except (TypeError, ValueError):
            return None
        if not (0 <= number <= maximum):
            return None
        return number

    def format_content_number(value) -> str:
        number = value if value is not None else 0
        try:
            numeric = float(number)
        except (TypeError, ValueError):
            return str(number)
        if math.isfinite(numeric) and abs(numeric) >= 1000:
            sign = "-" if numeric < 0 else ""
            scaled_value = abs(numeric)
            tier = min(
                int(math.log10(scaled_value) // 3),
                len(SHORT_NUMBER_SUFFIXES) - 1,
            )
            scaled = scaled_value / (1000 ** tier)
            if scaled >= 999.5 and tier < len(SHORT_NUMBER_SUFFIXES) - 1:
                tier += 1
                scaled = scaled_value / (1000 ** tier)
            text = (
                f"{scaled:.0f}" if scaled >= 100 else f"{scaled:.1f}"
            )
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return f"{sign}{text}{SHORT_NUMBER_SUFFIXES[tier]}"
        if isinstance(value, float):
            text = f"{value:.8f}".rstrip("0").rstrip(".")
            return text or "0"
        return str(value if value is not None else 0)

    def is_non_negative_number(value) -> bool:
        try:
            return float(value) >= 0
        except (TypeError, ValueError):
            return False

    async def get_content_status() -> dict:
        """Возвращает версию контента и последнюю ручную правку."""
        status = {
            "content_version": 0,
            "manual_revision": 0,
            "last_editor_id": None,
            "last_edit_at": None,
        }
        async with runtime.db.execute(
            "SELECT key, value FROM content_meta WHERE key IN "
            "('content_version', 'manual_revision', "
            "'last_content_editor_id', 'last_content_edit_at')"
        ) as c:
            rows = await c.fetchall()
        for key, value in rows:
            if key in ("content_version", "manual_revision"):
                try:
                    status[key] = int(value)
                except (TypeError, ValueError):
                    status[key] = 0
            elif key == "last_content_editor_id":
                try:
                    status["last_editor_id"] = int(value)
                except (TypeError, ValueError):
                    status["last_editor_id"] = None
            else:
                status["last_edit_at"] = value
        return status

    async def record_content_edit(
        editor_id: int,
        entity: str,
        entity_id: str,
        action: str = "edit",
        details: str = "",
    ):
        """Фиксирует ручную правку контента и увеличивает ревизию."""
        await runtime.db.execute(
            "INSERT INTO content_meta (key, value) "
            "VALUES ('manual_revision', '1') "
            "ON CONFLICT(key) DO UPDATE SET "
            "value = CAST(value AS INTEGER) + 1"
        )
        await runtime.db.execute(
            "INSERT INTO content_meta (key, value) "
            "VALUES ('last_content_editor_id', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(editor_id),),
        )
        await runtime.db.execute(
            "INSERT INTO content_meta (key, value) VALUES "
            "('last_content_edit_at', CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value = CURRENT_TIMESTAMP"
        )
        await runtime.audit(
            editor_id,
            0,
            f"content_{entity}_{action}",
            details or str(entity_id),
        )

    async def validate_content_data() -> list[str]:
        """Проверяет предметы и достижения на некорректные значения."""
        issues: list[str] = []
        async with runtime.db.execute(
            "SELECT id, name, price, income_per_hour, "
            "income_gems_per_hour, rarity, buyable, emoji "
            "FROM items ORDER BY id"
        ) as c:
            items = await c.fetchall()
        for (
            item_id,
            name,
            price,
            income,
            gem_income,
            rarity,
            buyable,
            emoji,
        ) in items:
            if not normalize_content_id(item_id):
                issues.append(f"предмет `{item_id}`: неверный ID")
            if not normalize_content_name(name):
                issues.append(
                    f"предмет `{item_id}`: пустое или длинное название"
                )
            if price is None or not is_non_negative_number(price):
                issues.append(f"предмет `{item_id}`: цена < 0")
            if not is_non_negative_number(income):
                issues.append(
                    f"предмет `{item_id}`: доход монет < 0"
                )
            if not is_non_negative_number(gem_income):
                issues.append(
                    f"предмет `{item_id}`: доход гемов < 0"
                )
            if rarity not in runtime.rarity_colors:
                issues.append(
                    f"предмет `{item_id}`: неизвестная редкость "
                    f"`{rarity}`"
                )
            if buyable not in (0, 1, None):
                issues.append(
                    f"предмет `{item_id}`: buyable должен быть 0/1"
                )
            if not emoji or not runtime.valid_emoji(str(emoji)):
                issues.append(
                    f"предмет `{item_id}`: неверный эмодзи"
                )

        async with runtime.db.execute(
            "SELECT id, name, description, reward_gems, emoji "
            "FROM achievements ORDER BY id"
        ) as c:
            achievements = await c.fetchall()
        for ach_id, name, description, reward, emoji in achievements:
            if not normalize_content_id(ach_id):
                issues.append(
                    f"достижение `{ach_id}`: неверный ID"
                )
            if not normalize_content_name(name):
                issues.append(
                    f"достижение `{ach_id}`: пустое или длинное название"
                )
            if not normalize_content_name(
                description, runtime.max_description
            ):
                issues.append(
                    f"достижение `{ach_id}`: пустое или длинное описание"
                )
            if reward is None or not is_non_negative_number(reward):
                issues.append(
                    f"достижение `{ach_id}`: награда < 0"
                )
            if not emoji or not runtime.valid_emoji(str(emoji)):
                issues.append(
                    f"достижение `{ach_id}`: неверный эмодзи"
                )

        return issues[:20]

    async def update_item_content(
        editor_id: int,
        item_id: str,
        name_value,
        price_value,
        income_value,
        gem_income_value,
        rarity_value,
    ) -> tuple[bool, str]:
        item_id = normalize_content_id(item_id)
        if not item_id:
            return (
                False,
                "❌ ID: латиница в нижнем регистре, цифры и `_` "
                "(2–32 символа).",
            )
        name = normalize_content_name(name_value)
        if not name:
            return False, "❌ Название: от 1 до 100 символов."
        price = parse_content_int(price_value)
        if price is None:
            return False, "❌ Цена: целое число от 0."
        income = parse_content_float(income_value)
        if income is None:
            return False, "❌ Доход монет: число от 0."
        gem_income = parse_content_float(gem_income_value)
        if gem_income is None:
            return False, "❌ Доход гемов: число от 0."
        rarity = (
            str(rarity_value) if rarity_value is not None else ""
        ).strip().lower()
        if rarity not in runtime.rarity_colors:
            return (
                False,
                f"❌ Редкость: "
                f"{', '.join(runtime.rarity_colors.keys())}.",
            )

        async with runtime.db.execute(
            "SELECT 1 FROM items WHERE id = ?", (item_id,)
        ) as c:
            if not await c.fetchone():
                return False, f"❌ Предмет `{item_id}` не найден."

        async with runtime.transaction():
            await runtime.db.execute(
                "UPDATE items SET name = ?, price = ?, "
                "income_per_hour = ?, income_gems_per_hour = ?, "
                "rarity = ? WHERE id = ?",
                (name, price, income, gem_income, rarity, item_id),
            )
            await record_content_edit(
                editor_id,
                "item",
                item_id,
                "edit",
                f"name={name}, price={price}, rarity={rarity}",
            )
        return True, f"✅ Предмет `{item_id}` обновлён."

    async def update_item_appearance(
        editor_id: int,
        item_id: str,
        emoji_value,
        buyable_value,
    ) -> tuple[bool, str]:
        item_id = normalize_content_id(item_id)
        if not item_id:
            return False, "❌ Неверный ID предмета."
        emoji = (
            str(emoji_value) if emoji_value is not None else ""
        ).strip()
        if not runtime.valid_emoji(emoji):
            return (
                False,
                "❌ Эмодзи: юникод-символ или `<:name:id>`.",
            )
        buyable = parse_content_int(buyable_value, maximum=1)
        if buyable is None:
            return False, "❌ Покупаемость: 1 или 0."

        async with runtime.db.execute(
            "SELECT 1 FROM items WHERE id = ?", (item_id,)
        ) as c:
            if not await c.fetchone():
                return False, f"❌ Предмет `{item_id}` не найден."

        async with runtime.transaction():
            await runtime.db.execute(
                "UPDATE items SET emoji = ?, buyable = ? WHERE id = ?",
                (emoji, buyable, item_id),
            )
            await record_content_edit(
                editor_id,
                "item",
                item_id,
                "appearance",
                f"emoji={emoji}, buyable={buyable}",
            )
        return True, f"✅ Вид предмета `{item_id}` обновлён."

    async def set_item_price(
        editor_id: int, item_id: str, price_value
    ) -> tuple[bool, str]:
        item_id = normalize_content_id(item_id)
        if not item_id:
            return False, "❌ Неверный ID предмета."
        price = parse_content_int(price_value)
        if price is None:
            return False, "❌ Цена: целое число от 0."
        async with runtime.db.execute(
            "SELECT name FROM items WHERE id = ?", (item_id,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return False, f"❌ `{item_id}` не найден."
        async with runtime.transaction():
            await runtime.db.execute(
                "UPDATE items SET price = ? WHERE id = ?",
                (price, item_id),
            )
            await record_content_edit(
                editor_id,
                "item",
                item_id,
                "price",
                f"price={price}",
            )
        return True, f"✅ Цена **{row[0]}** = 🪙 {price}."

    async def set_item_income(
        editor_id: int,
        item_id: str,
        income_value,
        gem_income_value,
    ) -> tuple[bool, str]:
        item_id = normalize_content_id(item_id)
        if not item_id:
            return False, "❌ Неверный ID предмета."
        async with runtime.db.execute(
            "SELECT name, income_per_hour, income_gems_per_hour "
            "FROM items WHERE id = ?",
            (item_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            return False, f"❌ `{item_id}` не найден."

        income_text = (
            str(income_value) if income_value is not None else ""
        ).strip()
        gem_text = (
            str(gem_income_value)
            if gem_income_value is not None
            else ""
        ).strip()
        income = (
            parse_content_float(income_text)
            if income_text
            else (row[1] or 0)
        )
        gem_income = (
            parse_content_float(gem_text)
            if gem_text
            else (row[2] or 0)
        )
        if income is None:
            return False, "❌ Неверный доход монет."
        if gem_income is None:
            return False, "❌ Неверный доход гемов."

        async with runtime.transaction():
            await runtime.db.execute(
                "UPDATE items SET income_per_hour = ?, "
                "income_gems_per_hour = ? WHERE id = ?",
                (income, gem_income, item_id),
            )
            await record_content_edit(
                editor_id,
                "item",
                item_id,
                "income",
                f"coins={format_content_number(income)}, "
                f"gems={format_content_number(gem_income)}",
            )
        return True, (
            f"✅ Доход **{row[0]}**: "
            f"🪙 {format_content_number(income)}/час, "
            f"💎 {format_content_number(gem_income)}/час."
        )

    async def add_generator_content(
        editor_id: int,
        item_id: str,
        name_value,
        price_value,
        income_value,
        gem_income_value,
        emoji_value,
        rarity_value,
    ) -> tuple[bool, str]:
        item_id = normalize_content_id(item_id)
        if not item_id:
            return (
                False,
                "❌ ID: латиница в нижнем регистре, цифры и `_` "
                "(2–32 символа).",
            )
        name = normalize_content_name(name_value)
        if not name:
            return False, "❌ Название: от 1 до 100 символов."
        price = parse_content_int(price_value)
        if price is None:
            return False, "❌ Цена: целое число от 0."
        income = parse_content_float(income_value)
        if income is None:
            return False, "❌ Доход монет: число от 0."
        gem_income = parse_content_float(gem_income_value)
        if gem_income is None:
            return False, "❌ Доход гемов: число от 0."
        emoji = (
            str(emoji_value) if emoji_value is not None else ""
        ).strip()
        if not runtime.valid_emoji(emoji):
            return (
                False,
                "❌ Эмодзи: юникод-символ или `<:name:id>`.",
            )
        rarity = (
            str(rarity_value) if rarity_value is not None else ""
        ).strip().lower()
        if rarity not in runtime.rarity_colors:
            return (
                False,
                f"❌ Редкость: "
                f"{', '.join(runtime.rarity_colors.keys())}.",
            )

        async with runtime.db.execute(
            "SELECT 1 FROM items WHERE id = ?", (item_id,)
        ) as c:
            if await c.fetchone():
                return False, f"❌ ID `{item_id}` уже существует."

        buyable = 1 if rarity in ("common", "uncommon", "rare") else 0
        async with runtime.transaction():
            await runtime.db.execute(
                "INSERT INTO items (id, name, price, "
                "income_per_hour, emoji, rarity, buyable, "
                "income_gems_per_hour) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item_id,
                    name,
                    price,
                    income,
                    emoji,
                    rarity,
                    buyable,
                    gem_income,
                ),
            )
            await runtime.db.execute(
                "INSERT OR IGNORE INTO market_prices "
                "(item_id, base_price, current_price) "
                "VALUES (?, ?, ?)",
                (item_id, price, price),
            )
            await record_content_edit(
                editor_id,
                "item",
                item_id,
                "create",
                f"{name} ({rarity})",
            )
        return True, (
            f"✅ Генератор **{emoji} {name}** (`{item_id}`) добавлен."
        )

    async def update_achievement_content(
        editor_id: int,
        ach_id: str,
        name_value,
        description_value,
        reward_value,
        emoji_value,
    ) -> tuple[bool, str]:
        ach_id = normalize_content_id(ach_id)
        if not ach_id:
            return (
                False,
                "❌ ID: латиница в нижнем регистре, цифры и `_` "
                "(2–32 символа).",
            )
        name = normalize_content_name(name_value)
        if not name:
            return False, "❌ Название: от 1 до 100 символов."
        description = normalize_content_name(
            description_value, runtime.max_description
        )
        if not description:
            return False, "❌ Описание: от 1 до 500 символов."
        reward = parse_content_int(reward_value, maximum=10**9)
        if reward is None:
            return False, "❌ Награда: целое число от 0."
        emoji = (
            str(emoji_value) if emoji_value is not None else ""
        ).strip()
        if not runtime.valid_emoji(emoji):
            return (
                False,
                "❌ Эмодзи: юникод-символ или `<:name:id>`.",
            )

        async with runtime.db.execute(
            "SELECT 1 FROM achievements WHERE id = ?", (ach_id,)
        ) as c:
            if not await c.fetchone():
                return False, "❌ Достижение не найдено."

        async with runtime.transaction():
            await runtime.db.execute(
                "UPDATE achievements SET name = ?, description = ?, "
                "reward_gems = ?, emoji = ? WHERE id = ?",
                (name, description, reward, emoji, ach_id),
            )
            await record_content_edit(
                editor_id,
                "achievement",
                ach_id,
                "edit",
                f"name={name}, reward={reward}",
            )
        return True, f"✅ Достижение `{ach_id}` обновлено."

    async def add_achievement_content(
        editor_id: int,
        ach_id: str,
        name_value,
        description_value,
        reward_value,
        emoji_value,
    ) -> tuple[bool, str]:
        ach_id = normalize_content_id(ach_id)
        if not ach_id:
            return (
                False,
                "❌ ID: латиница в нижнем регистре, цифры и `_` "
                "(2–32 символа).",
            )
        name = normalize_content_name(name_value)
        if not name:
            return False, "❌ Название: от 1 до 100 символов."
        description = normalize_content_name(
            description_value, runtime.max_description
        )
        if not description:
            return False, "❌ Описание: от 1 до 500 символов."
        reward = parse_content_int(reward_value, maximum=10**9)
        if reward is None:
            return False, "❌ Награда: целое число от 0."
        emoji = (
            str(emoji_value) if emoji_value is not None else ""
        ).strip()
        if not runtime.valid_emoji(emoji):
            return (
                False,
                "❌ Эмодзи: юникод-символ или `<:name:id>`.",
            )

        async with runtime.db.execute(
            "SELECT 1 FROM achievements WHERE id = ?", (ach_id,)
        ) as c:
            if await c.fetchone():
                return False, "❌ Уже существует."

        async with runtime.transaction():
            await runtime.db.execute(
                "INSERT INTO achievements "
                "(id, name, description, reward_gems, emoji) "
                "VALUES (?, ?, ?, ?, ?)",
                (ach_id, name, description, reward, emoji),
            )
            await record_content_edit(
                editor_id,
                "achievement",
                ach_id,
                "create",
                f"{name} (+{reward}💎)",
            )
        return True, f"✅ «{name}» добавлено."

    async def delete_achievement_content(
        editor_id: int, ach_id: str, confirmed: bool
    ) -> tuple[bool, str]:
        if not confirmed:
            return False, "❌ Отменено."
        ach_id = normalize_content_id(ach_id)
        if not ach_id:
            return False, "❌ Неверный ID достижения."
        async with runtime.db.execute(
            "SELECT name FROM achievements WHERE id = ?", (ach_id,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return False, "❌ Не найдено."

        async with runtime.transaction():
            await runtime.db.execute(
                "DELETE FROM achievements WHERE id = ?", (ach_id,)
            )
            await runtime.db.execute(
                "DELETE FROM player_achievements "
                "WHERE achievement_id = ?",
                (ach_id,),
            )
            await record_content_edit(
                editor_id,
                "achievement",
                ach_id,
                "delete",
                f"{row[0]}",
            )
        return True, f"🗑️ «{row[0]}» удалено."

    return (
        normalize_content_id,
        normalize_content_name,
        parse_content_int,
        parse_content_float,
        format_content_number,
        is_non_negative_number,
        get_content_status,
        record_content_edit,
        validate_content_data,
        update_item_content,
        update_item_appearance,
        set_item_price,
        set_item_income,
        add_generator_content,
        update_achievement_content,
        add_achievement_content,
        delete_achievement_content,
    )
