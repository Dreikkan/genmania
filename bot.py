# ============================================================
#  🏰 Gen Mania — Discord Bot (полный финальный файл)
#  Python 3.10+ | discord.py 2.x | aiosqlite
# ============================================================

import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import datetime
import random
import json
import os

# ============================================================
#  📦 КОНСТАНТЫ
# ============================================================

DEFAULT_BOT_NAME = "Gen Mania"
DEFAULT_CURRENCY_COINS = "монеты"
DEFAULT_CURRENCY_GEMS = "гемы"
DEFAULT_PREFIX = "/"
DEFAULT_GEM_CAP = 6
DEFAULT_START_COINS = 10
DEFAULT_PASSIVE_LIMIT = 100000

RARITY_COLORS = {
    "common":    0x808080,
    "uncommon":  0x2ecc71,
    "rare":      0x3498db,
    "epic":      0x9b59b6,
    "legendary": 0xf1c40f,
    "mythic":    0xe74c3c,
}

RARITY_NAMES = {
    "common":    "Обычный",
    "uncommon":  "Необычный",
    "rare":      "Редкий",
    "epic":      "Эпический",
    "legendary": "Легендарный",
    "mythic":    "Мифический",
}

CRAFT_CHAIN = {
    "basic_gen": "wood_gen",
    "wood_gen":  "stone_gen",
    "stone_gen": "iron_gen",
    "iron_gen":  "gold_gen",
    "gold_gen":  "gem_gen",
}

CRAFT_COST = 5

CRAFT_SETTINGS = {
    "basic_gen": {"chance": 1.00, "gems": 0},
    "wood_gen":  {"chance": 0.90, "gems": 0},
    "stone_gen": {"chance": 0.75, "gems": 5},
    "iron_gen":  {"chance": 0.60, "gems": 15},
    "gold_gen":  {"chance": 0.45, "gems": 40},
}

CATALYST_PRICE = 10
CATALYST_BONUS = 0.15
SELL_RATE = 0.15
START_GRID = 36
PAGE_SIZE = 5

QUEST_POOL = {
    "craft_3":        ("Сделай 3 синтеза", 3, 5),
    "craft_5":        ("Сделай 5 синтезов", 5, 10),
    "success_2":      ("Успешно синтезируй 2 раза", 2, 8),
    "buy_3":          ("Купи 3 предмета в магазине", 3, 5),
    "move_2":         ("Перемести 2 предмета между замком и хранилищем", 2, 5),
    "collect_income": ("Собери пассивный доход 1 раз", 1, 3),
    "use_catalyst":   ("Используй 1 катализатор", 1, 10),
}

TOGGLEABLE_COMMANDS = {
    "shop":         "Магазин",
    "upgrades":     "Магазин улучшений",
    "achievements": "Достижения",
    "quests":       "Задания",
    "storage":      "Хранилище",
    "stats":        "Статистика",
}

# Ключи кастомных эмодзи для Embed'ов (кнопки не меняются)
EMOJI_KEYS = {
    "_coin":         ("Монета", "🪙"),
    "_gem":          ("Гем", "💎"),
    "_castle":       ("Замок", "🏰"),
    "_storage":      ("Хранилище", "🎒"),
    "_shop":         ("Магазин", "🛒"),
    "_upgrades":     ("Улучшения", "💎"),
    "_achievements": ("Достижения", "🏆"),
    "_quests":       ("Задания", "📅"),
    "_stats":        ("Статистика", "📊"),
}


# ============================================================
#  🤖 БОТ
# ============================================================

intents = discord.Intents.default()
intents.message_content = True


class CastleBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.db = None

    async def setup_hook(self):
        self.db = await aiosqlite.connect("castle.db")
        await self.init_db()
        await self.tree.sync()

    async def init_db(self):
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                coins INTEGER DEFAULT 10,
                gems INTEGER DEFAULT 0,
                last_collected TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                user_id INTEGER,
                slot INTEGER,
                item_id TEXT,
                location TEXT DEFAULT 'profile',
                PRIMARY KEY (user_id, location, slot)
            )
        """)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                name TEXT,
                price INTEGER,
                income_per_hour INTEGER DEFAULT 0,
                emoji TEXT DEFAULT '📦',
                rarity TEXT DEFAULT 'common',
                buyable INTEGER DEFAULT 1,
                income_gems_per_hour REAL DEFAULT 0
            )
        """)

        for column, definition in [
            ("catalysts", "INTEGER DEFAULT 0"),
            ("last_gem_collected", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("daily_quest_date", "TEXT DEFAULT NULL"),
            ("daily_quest_progress", "TEXT DEFAULT '{}'"),
            ("daily_quest_claimed", "TEXT DEFAULT '[]'"),
            ("total_crafts", "INTEGER DEFAULT 0"),
            ("total_successes", "INTEGER DEFAULT 0"),
            ("grid_size", "INTEGER DEFAULT 36"),
            ("income_bonus", "REAL DEFAULT 0.0"),
        ]:
            try:
                await self.db.execute(f"ALTER TABLE players ADD COLUMN {column} {definition}")
            except Exception:
                pass

        for column, definition in [
            ("emoji", "TEXT DEFAULT '📦'"),
            ("rarity", "TEXT DEFAULT 'common'"),
            ("buyable", "INTEGER DEFAULT 1"),
            ("income_gems_per_hour", "REAL DEFAULT 0"),
        ]:
            try:
                await self.db.execute(f"ALTER TABLE items ADD COLUMN {column} {definition}")
            except Exception:
                pass

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS craft_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_id TEXT,
                success INTEGER,
                gems_spent INTEGER,
                catalyst_used INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                reward_gems INTEGER,
                emoji TEXT DEFAULT '🏆'
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                user_id INTEGER,
                achievement_id TEXT,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, achievement_id)
            )
        """)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                bot_name TEXT DEFAULT 'Gen Mania',
                custom_emojis TEXT DEFAULT '{}',
                currency_coins TEXT DEFAULT 'монеты',
                currency_gems TEXT DEFAULT 'гемы',
                prefix TEXT DEFAULT '/',
                gem_cap INTEGER DEFAULT 6,
                start_coins INTEGER DEFAULT 10,
                passive_limit INTEGER DEFAULT 100000,
                disabled_commands TEXT DEFAULT '[]',
                status_roles TEXT DEFAULT '{}',
                admin_role_id INTEGER DEFAULT NULL
            )
        """)

        for column, definition in [
            ("currency_coins", "TEXT DEFAULT 'монеты'"),
            ("currency_gems", "TEXT DEFAULT 'гемы'"),
            ("prefix", "TEXT DEFAULT '/'"),
            ("gem_cap", "INTEGER DEFAULT 6"),
            ("start_coins", "INTEGER DEFAULT 10"),
            ("passive_limit", "INTEGER DEFAULT 100000"),
            ("disabled_commands", "TEXT DEFAULT '[]'"),
            ("status_roles", "TEXT DEFAULT '{}'"),
            ("admin_role_id", "INTEGER DEFAULT NULL"),
        ]:
            try:
                await self.db.execute(f"ALTER TABLE guild_settings ADD COLUMN {column} {definition}")
            except Exception:
                pass

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS gem_shop (
                id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                price_gems INTEGER,
                emoji TEXT DEFAULT '💎',
                category TEXT DEFAULT 'upgrade',
                max_level INTEGER DEFAULT 1
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS player_upgrades (
                user_id INTEGER,
                upgrade_id TEXT,
                level INTEGER DEFAULT 1,
                purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, upgrade_id)
            )
        """)

        items_data = [
            ("basic_gen", "Базовый генератор",    10, 3 / 3600,          "⚙️", "common",    1, 0),
            ("wood_gen",  "Деревянный генератор",  50, 8 / 3600,          "🪵", "uncommon",  1, 0),
            ("stone_gen", "Каменный генератор",   200, 20 / 3600,         "🪨", "rare",      1, 0),
            ("iron_gen",  "Железный генератор",   800, 50 / 3600,         "⛓️", "epic",      1, 0),
            ("gold_gen",  "Золотой генератор",   3000, 120 / 3600,        "🪙", "legendary", 1, 0),
            ("gem_gen",   "Гемовый генератор",  12000, 0,                 "💎", "mythic",    0, 0.0625 / 3600),
        ]
        for item in items_data:
            await self.db.execute(
                "INSERT OR IGNORE INTO items "
                "(id, name, price, income_per_hour, emoji, rarity, buyable, income_gems_per_hour) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                item
            )

        achievements_data = [
            ("first_craft",   "Первый синтез",   "Сделай свой первый синтез",           5,  "⚗️"),
            ("craft_10",      "Алхимик",         "Сделай 10 синтезов",                  15, "🧪"),
            ("craft_50",      "Мастер-алхимик",  "Сделай 50 синтезов",                  50, "🔮"),
            ("success_10",    "Удачливый",       "Успешно синтезируй 10 раз",           20, "🍀"),
            ("success_50",    "Любимец фортуны", "Успешно синтезируй 50 раз",           75, "🎰"),
            ("fail_5",        "Не везёт",        "Провали 5 синтезов",                  10, "💥"),
            ("first_gem_gen", "Гемовый магнат",  "Получи свой первый гемовый генератор",30, "💎"),
            ("rich_1000",     "Богач",           "Накопи 1000 монет",                   10, "🪙"),
            ("rich_10000",    "Миллионер",       "Накопи 10000 монет",                  50, "💰"),
            ("catalyst_10",   "Химик",           "Используй 10 катализаторов",          25, "🧫"),
        ]
        for a in achievements_data:
            await self.db.execute(
                "INSERT OR IGNORE INTO achievements VALUES (?, ?, ?, ?, ?)", a
            )

        gem_items = [
            ("grid_7x7",   "Сетка 7x7",   "Увеличивает замок до 49 слотов",   50,  "📐", "upgrade", 1),
            ("grid_8x8",   "Сетка 8x8",   "Увеличивает замок до 64 слотов",  150,  "📐", "upgrade", 1),
            ("grid_9x9",   "Сетка 9x9",   "Увеличивает замок до 81 слота",   400,  "📐", "upgrade", 1),
            ("grid_10x10", "Сетка 10x10", "Увеличивает замок до 100 слотов",1000,  "📐", "upgrade", 1),
            ("vip",        "VIP-статус",  "+15% к доходу навсегда",             100,  "⭐", "status", 1),
            ("platinum",   "Платинум",    "+25% к доходу навсегда",             300,  "💠", "status", 1),
            ("gold",       "Голд",        "+35% к доходу навсегда",             700,  "🥇", "status", 1),
            ("diamond",    "Даймонд",     "+45% к доходу навсегда",            1500,  "💎", "status", 1),
        ]
        for g in gem_items:
            await self.db.execute(
                "INSERT OR IGNORE INTO gem_shop VALUES (?, ?, ?, ?, ?, ?, ?)", g
            )

        await self.db.commit()


bot = CastleBot()


# ============================================================
#  🧰 НАСТРОЙКИ СЕРВЕРА
# ============================================================

async def get_settings(guild_id: int) -> dict:
    defaults = {
        "bot_name": DEFAULT_BOT_NAME,
        "custom_emojis": {},
        "currency_coins": DEFAULT_CURRENCY_COINS,
        "currency_gems": DEFAULT_CURRENCY_GEMS,
        "prefix": DEFAULT_PREFIX,
        "gem_cap": DEFAULT_GEM_CAP,
        "start_coins": DEFAULT_START_COINS,
        "passive_limit": DEFAULT_PASSIVE_LIMIT,
        "disabled_commands": [],
        "status_roles": {},
        "admin_role_id": None,
    }
    if not guild_id:
        return defaults

    await bot.db.execute(
        "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,)
    )
    async with bot.db.execute("""
        SELECT bot_name, custom_emojis, currency_coins, currency_gems, prefix,
               gem_cap, start_coins, passive_limit, disabled_commands, status_roles, admin_role_id
        FROM guild_settings WHERE guild_id = ?
    """, (guild_id,)) as c:
        row = await c.fetchone()

    if not row:
        return defaults

    return {
        "bot_name": row[0] or DEFAULT_BOT_NAME,
        "custom_emojis": json.loads(row[1] or "{}"),
        "currency_coins": row[2] or DEFAULT_CURRENCY_COINS,
        "currency_gems": row[3] or DEFAULT_CURRENCY_GEMS,
        "prefix": row[4] or DEFAULT_PREFIX,
        "gem_cap": row[5] or DEFAULT_GEM_CAP,
        "start_coins": row[6] or DEFAULT_START_COINS,
        "passive_limit": row[7] or DEFAULT_PASSIVE_LIMIT,
        "disabled_commands": json.loads(row[8] or "[]"),
        "status_roles": json.loads(row[9] or "{}"),
        "admin_role_id": row[10],
    }


async def save_setting(guild_id: int, key: str, value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    await bot.db.execute(
        f"UPDATE guild_settings SET {key} = ? WHERE guild_id = ?", (value, guild_id)
    )
    await bot.db.commit()


async def get_emoji(guild_id: int, key: str, default: str) -> str:
    settings = await get_settings(guild_id)
    return settings["custom_emojis"].get(key, default)


async def is_command_disabled(guild_id: int, command_key: str) -> bool:
    settings = await get_settings(guild_id)
    return command_key in settings["disabled_commands"]


# ============================================================
#  🧰 ОБЩИЕ ХЕЛПЕРЫ
# ============================================================

def today_str():
    return datetime.date.today().isoformat()


async def get_player_stats(user_id: int, guild_id: int = None):
    async with bot.db.execute(
        "SELECT grid_size, income_bonus, gems, coins FROM players WHERE user_id = ?",
        (user_id,)
    ) as c:
        row = await c.fetchone()

    if not row:
        start = DEFAULT_START_COINS
        if guild_id:
            settings = await get_settings(guild_id)
            start = settings["start_coins"]
        await bot.db.execute(
            "INSERT OR IGNORE INTO players (user_id, coins) VALUES (?, ?)",
            (user_id, start)
        )
        await bot.db.commit()
        return START_GRID, 0.0, 0, start

    return row[0] or START_GRID, row[1] or 0.0, row[2] or 0, row[3] or 0


async def get_grid_size(user_id: int) -> int:
    size, _, _, _ = await get_player_stats(user_id)
    return size


async def get_per_second_income(user_id: int) -> tuple[float, float]:
    grid_size, bonus, gems, coins = await get_player_stats(user_id)
    async with bot.db.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN inv.location = 'profile' THEN i.income_per_hour ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN inv.location = 'profile' THEN i.income_gems_per_hour ELSE 0 END), 0)
        FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ?
    """, (user_id,)) as c:
        per_sec_coins_raw, per_sec_gems_raw = await c.fetchone()
    multiplier = 1 + bonus
    return per_sec_coins_raw * multiplier, per_sec_gems_raw * multiplier


async def calculate_passive_income(user_id: int, guild_id: int = None):
    async with bot.db.execute(
        "SELECT last_collected, last_gem_collected, income_bonus FROM players WHERE user_id = ?",
        (user_id,)
    ) as c:
        row = await c.fetchone()
    if not row:
        return 0, 0
    last_coins_str, last_gems_str, bonus = row
    multiplier = 1 + (bonus or 0)

    settings = await get_settings(guild_id) if guild_id else {"gem_cap": DEFAULT_GEM_CAP, "passive_limit": DEFAULT_PASSIVE_LIMIT}
    gem_cap = settings["gem_cap"]
    passive_limit = settings["passive_limit"]

    now = datetime.datetime.now()

    async with bot.db.execute("""
        SELECT SUM(i.income_per_hour) FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'profile'
    """, (user_id,)) as c:
        per_sec_coins = (await c.fetchone())[0] or 0

    coins = 0
    if per_sec_coins > 0:
        last = datetime.datetime.fromisoformat(last_coins_str)
        seconds = (now - last).total_seconds()
        coins = min(int(seconds * per_sec_coins * multiplier), passive_limit)

    async with bot.db.execute("""
        SELECT SUM(i.income_gems_per_hour) FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND i.income_gems_per_hour > 0 AND inv.location = 'profile'
    """, (user_id,)) as c:
        per_sec_gems = (await c.fetchone())[0] or 0

    gems = 0
    if per_sec_gems > 0:
        last = datetime.datetime.fromisoformat(last_gems_str)
        seconds = (now - last).total_seconds()
        raw = seconds * per_sec_gems * multiplier
        gems = min(int(raw), gem_cap)

    return coins, gems


async def collect_income(user_id: int, guild_id: int = None):
    coins_earned, gems_earned = await calculate_passive_income(user_id, guild_id)
    if coins_earned <= 0 and gems_earned <= 0:
        return 0, 0

    now_iso = datetime.datetime.now().isoformat()
    if coins_earned > 0:
        await bot.db.execute(
            "UPDATE players SET coins = coins + ?, last_collected = ? WHERE user_id = ?",
            (coins_earned, now_iso, user_id)
        )
    if gems_earned > 0:
        await bot.db.execute(
            "UPDATE players SET gems = gems + ?, last_gem_collected = ? WHERE user_id = ?",
            (gems_earned, now_iso, user_id)
        )
    await bot.db.commit()
    await update_quest_progress(user_id, "collect_income")
    return coins_earned, gems_earned


# ============================================================
#  🏆 ДОСТИЖЕНИЯ
# ============================================================

async def check_achievements(user_id: int):
    async with bot.db.execute("""
        SELECT total_crafts, total_successes, gems, coins, catalysts,
               (SELECT COUNT(*) FROM inventory inv
                JOIN items i ON inv.item_id = i.id
                WHERE inv.user_id = ? AND i.income_gems_per_hour > 0)
        FROM players WHERE user_id = ?
    """, (user_id, user_id)) as c:
        row = await c.fetchone()
    if not row:
        return []

    total_crafts, total_successes, gems, coins, catalysts, gem_gens = row

    async with bot.db.execute(
        "SELECT achievement_id FROM player_achievements WHERE user_id = ?", (user_id,)
    ) as c:
        unlocked = {r[0] for r in await c.fetchall()}

    async with bot.db.execute(
        "SELECT COALESCE(SUM(catalyst_used), 0) FROM craft_log WHERE user_id = ?",
        (user_id,)
    ) as c:
        catalysts_used_total = (await c.fetchone())[0] or 0

    conditions = {
        "first_craft":   total_crafts >= 1,
        "craft_10":      total_crafts >= 10,
        "craft_50":      total_crafts >= 50,
        "success_10":    total_successes >= 10,
        "success_50":    total_successes >= 50,
        "fail_5":        (total_crafts - total_successes) >= 5,
        "first_gem_gen": gem_gens >= 1,
        "rich_1000":     coins >= 1000,
        "rich_10000":    coins >= 10000,
        "catalyst_10":   catalysts_used_total >= 10,
    }

    newly_unlocked = []
    for ach_id, ok in conditions.items():
        if ok and ach_id not in unlocked:
            async with bot.db.execute(
                "SELECT reward_gems, name, emoji FROM achievements WHERE id = ?", (ach_id,)
            ) as c:
                reward_gems, name, emoji = await c.fetchone()

            await bot.db.execute(
                "INSERT INTO player_achievements (user_id, achievement_id) VALUES (?, ?)",
                (user_id, ach_id)
            )
            await bot.db.execute(
                "UPDATE players SET gems = gems + ? WHERE user_id = ?",
                (reward_gems, user_id)
            )
            newly_unlocked.append((emoji, name, reward_gems))

    if newly_unlocked:
        await bot.db.commit()
    return newly_unlocked


# ============================================================
#  📅 ЕЖЕДНЕВНЫЕ ЗАДАНИЯ
# ============================================================

async def get_or_create_daily_quests(user_id: int):
    today = today_str()

    async with bot.db.execute(
        "SELECT daily_quest_date, daily_quest_progress, daily_quest_claimed "
        "FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    if not row:
        return [], {}, []

    date, progress_json, claimed_json = row

    if date != today:
        chosen = random.sample(list(QUEST_POOL.keys()), 3)
        progress = {q: 0 for q in chosen}
        claimed = []

        await bot.db.execute(
            "UPDATE players SET daily_quest_date = ?, daily_quest_progress = ?, "
            "daily_quest_claimed = ? WHERE user_id = ?",
            (today, json.dumps(progress), json.dumps(claimed), user_id)
        )
        await bot.db.commit()
        return chosen, progress, claimed

    progress = json.loads(progress_json or "{}")
    claimed = json.loads(claimed_json or "[]")
    return list(progress.keys()), progress, claimed


async def update_quest_progress(user_id: int, quest_id: str, amount: int = 1):
    quests, progress, claimed = await get_or_create_daily_quests(user_id)
    if quest_id not in progress:
        return
    if quest_id in claimed:
        return

    progress[quest_id] = min(progress[quest_id] + amount, QUEST_POOL[quest_id][1])
    await bot.db.execute(
        "UPDATE players SET daily_quest_progress = ? WHERE user_id = ?",
        (json.dumps(progress), user_id)
    )
    await bot.db.commit()


# ============================================================
#  🖼️ EMBED'Ы
# ============================================================

async def build_main_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)
    await collect_income(user_id, guild_id)

    grid_size, bonus, gems, coins = await get_player_stats(user_id, guild_id)
    per_sec_coins, per_sec_gems = await get_per_second_income(user_id)

    coin = await get_emoji(guild_id, "_coin", "🪙")
    gem = await get_emoji(guild_id, "_gem", "💎")
    castle = await get_emoji(guild_id, "_castle", "🏰")

    parts = []
    if per_sec_coins > 0:
        parts.append(f"{coin} {per_sec_coins:.4f}/сек")
    if per_sec_gems > 0:
        parts.append(f"{gem} {per_sec_gems:.5f}/сек")
    income_str = " | ".join(parts) if parts else "нет генераторов"

    embed = discord.Embed(
        title=f"{castle} {settings['bot_name']} — Замок {interaction.user.name}",
        description="Выбери раздел кнопками ниже.",
        color=0x00ff00
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.add_field(
        name=f"Кошелёк ({settings['currency_coins']}/{settings['currency_gems']})",
        value=f"{coin} {coins} | {gem} {gems}",
        inline=False
    )
    embed.add_field(name="Доход", value=income_str, inline=False)
    embed.add_field(name="Бонус", value=f"+{int(bonus * 100)}%", inline=True)
    embed.add_field(name="Сетка", value=f"{grid_size} слотов", inline=True)
    return embed


async def build_profile_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)

    grid_size, bonus, gems, coins = await get_player_stats(user_id, guild_id)

    async with bot.db.execute("""
        SELECT inv.slot, i.id, i.emoji FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'profile'
    """, (user_id,)) as c:
        rows = await c.fetchall()

    custom = settings["custom_emojis"]
    items = {slot: custom.get(item_id, default) for slot, item_id, default in rows}

    coin = await get_emoji(guild_id, "_coin", "🪙")
    gem = await get_emoji(guild_id, "_gem", "💎")
    castle = await get_emoji(guild_id, "_castle", "🏰")

    per_sec_coins, per_sec_gems = await get_per_second_income(user_id)
    parts = []
    if per_sec_coins > 0:
        parts.append(f"{coin} {per_sec_coins:.4f}/сек")
    if per_sec_gems > 0:
        parts.append(f"{gem} {per_sec_gems:.5f}/сек")
    income_str = " | ".join(parts) if parts else "нет генераторов"

    width = int(grid_size ** 0.5)
    embed = discord.Embed(title=f"{castle} Замок {interaction.user.name}", color=0x00ff00)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.add_field(name="Кошелёк", value=f"{coin} {coins} | {gem} {gems}", inline=False)
    embed.add_field(name="Доход", value=income_str, inline=False)
    embed.add_field(name="Бонус", value=f"+{int(bonus * 100)}%", inline=True)
    embed.add_field(name="Сетка", value=f"{width}x{width}", inline=True)

    grid_str = ""
    for slot in range(grid_size):
        grid_str += f"{items.get(slot, '⬛')} "
        if (slot + 1) % width == 0:
            grid_str += "\n"
    embed.add_field(name="Замок", value=f"```\n{grid_str}\n```", inline=False)
    return embed


async def build_storage_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)
    grid_size = await get_grid_size(user_id)

    async with bot.db.execute("""
        SELECT inv.slot, i.id, i.emoji FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'storage'
    """, (user_id,)) as c:
        rows = await c.fetchall()

    custom = settings["custom_emojis"]
    items = {slot: custom.get(item_id, default) for slot, item_id, default in rows}

    storage_emoji = await get_emoji(guild_id, "_storage", "🎒")
    width = int(grid_size ** 0.5)
    embed = discord.Embed(title=f"{storage_emoji} Хранилище {interaction.user.name}", color=0x808080)
    grid_str = ""
    for slot in range(grid_size):
        grid_str += f"{items.get(slot, '⬛')} "
        if (slot + 1) % width == 0:
            grid_str += "\n"
    embed.add_field(name="Предметы (эффекты отключены)", value=f"```\n{grid_str}\n```", inline=False)
    return embed


async def build_shop_page(interaction: discord.Interaction, page: int) -> tuple[discord.Embed, int]:
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)
    custom = settings["custom_emojis"]
    coin = await get_emoji(guild_id, "_coin", "🪙")
    gem = await get_emoji(guild_id, "_gem", "💎")
    shop_emoji = await get_emoji(guild_id, "_shop", "🛒")

    async with bot.db.execute(
        "SELECT id, name, price, income_per_hour, emoji, rarity, income_gems_per_hour "
        "FROM items WHERE buyable = 1"
    ) as c:
        rows = await c.fetchall()

    total = len(rows)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page * PAGE_SIZE: page * PAGE_SIZE + PAGE_SIZE]

    embed = discord.Embed(
        title=f"{shop_emoji} Магазин",
        description=f"Страница {page + 1}/{total_pages}",
        color=0xf1c40f
    )
    for item_id, name, price, income_coins, default_emoji, rarity, income_gems in chunk:
        emoji = custom.get(item_id, default_emoji)
        inc = []
        if income_coins > 0:
            inc.append(f"{coin} {income_coins:.4f}/сек")
        if income_gems > 0:
            inc.append(f"{gem} {income_gems:.5f}/сек")
        inc_str = " ".join(inc) if inc else "без дохода"
        embed.add_field(
            name=f"{emoji} {name} (`{item_id}`)",
            value=f"Цена: {coin} {price} | {inc_str} | {RARITY_NAMES.get(rarity, rarity)}",
            inline=False
        )
    return embed, total_pages


async def build_achievements_page(interaction: discord.Interaction, page: int) -> tuple[discord.Embed, int]:
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    ach_emoji = await get_emoji(guild_id, "_achievements", "🏆")
    gem = await get_emoji(guild_id, "_gem", "💎")

    async with bot.db.execute(
        "SELECT id, name, description, reward_gems, emoji FROM achievements ORDER BY reward_gems ASC"
    ) as c:
        all_ach = await c.fetchall()

    async with bot.db.execute(
        "SELECT achievement_id FROM player_achievements WHERE user_id = ?", (user_id,)
    ) as c:
        unlocked = {r[0] for r in await c.fetchall()}

    total = len(all_ach)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = all_ach[page * PAGE_SIZE: page * PAGE_SIZE + PAGE_SIZE]

    embed = discord.Embed(
        title=f"{ach_emoji} Достижения — {interaction.user.name}",
        description=f"Страница {page + 1}/{total_pages} | Открыто: {len(unlocked)}/{total}",
        color=0xf1c40f
    )
    for ach_id, name, desc, reward, emoji in chunk:
        status = "✅ Открыто" if ach_id in unlocked else "🔒 Закрыто"
        embed.add_field(
            name=f"{emoji} {name}",
            value=f"{desc}\nНаграда: {gem} {reward} — {status}",
            inline=False
        )
    return embed, total_pages


async def build_upgrades_page(interaction: discord.Interaction, page: int) -> tuple[discord.Embed, int]:
    guild_id = interaction.guild_id
    gem = await get_emoji(guild_id, "_gem", "💎")
    up_emoji = await get_emoji(guild_id, "_upgrades", "💎")

    async with bot.db.execute(
        "SELECT id, name, description, price_gems, emoji FROM gem_shop ORDER BY category, price_gems"
    ) as c:
        rows = await c.fetchall()

    async with bot.db.execute(
        "SELECT upgrade_id FROM player_upgrades WHERE user_id = ?", (interaction.user.id,)
    ) as c:
        owned = {r[0] for r in await c.fetchall()}

    total = len(rows)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page * PAGE_SIZE: page * PAGE_SIZE + PAGE_SIZE]

    embed = discord.Embed(
        title=f"{up_emoji} Магазин улучшений",
        description=f"Страница {page + 1}/{total_pages}",
        color=0x9b59b6
    )
    for gid, name, desc, price, emoji in chunk:
        status = "✅ Куплено" if gid in owned else "🔒 Не куплено"
        embed.add_field(
            name=f"{emoji} {name} (`{gid}`)",
            value=f"{desc}\nЦена: {gem} {price}\n{status}",
            inline=False
        )
    return embed, total_pages


async def build_quests_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    quest_emoji = await get_emoji(guild_id, "_quests", "📅")
    gem = await get_emoji(guild_id, "_gem", "💎")

    quests, progress, claimed = await get_or_create_daily_quests(user_id)

    embed = discord.Embed(title=f"{quest_emoji} Ежедневные задания", color=0x3498db)
    for qid in quests:
        desc, target, reward = QUEST_POOL[qid]
        done = progress[qid] >= target
        status = "✅ Получено" if qid in claimed else ("🎁 Готово" if done else "⏳ В процессе")
        embed.add_field(
            name=desc,
            value=f"Прогресс: {progress[qid]}/{target}\nНаграда: {gem} {reward}\n{status}",
            inline=False
        )
    return embed


async def build_stats_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    stats_emoji = await get_emoji(guild_id, "_stats", "📊")
    gem = await get_emoji(guild_id, "_gem", "💎")

    async with bot.db.execute("""
        SELECT COUNT(*), SUM(success), SUM(gems_spent), SUM(catalyst_used)
        FROM craft_log WHERE user_id = ?
    """, (user_id,)) as c:
        total, successes, gems_spent, catalysts_used = await c.fetchone()

    if not total:
        return discord.Embed(
            title=f"{stats_emoji} Статистика синтеза",
            description="У тебя пока нет ни одного синтеза.",
            color=0x9b59b6
        )

    successes = successes or 0
    failures = total - successes
    gems_spent = gems_spent or 0
    catalysts_used = catalysts_used or 0
    winrate = (successes / total) * 100

    embed = discord.Embed(title=f"{stats_emoji} Статистика — {interaction.user.name}", color=0x9b59b6)
    embed.add_field(name="Попыток", value=str(total), inline=True)
    embed.add_field(name="✅ Успехов", value=str(successes), inline=True)
    embed.add_field(name="💥 Провалов", value=str(failures), inline=True)
    embed.add_field(name="Винрейт", value=f"{winrate:.1f}%", inline=True)
    embed.add_field(name=f"{gem} Потрачено", value=str(gems_spent), inline=True)
    embed.add_field(name="🧪 Катализаторов", value=str(catalysts_used), inline=True)
    return embed


# ============================================================
#  🎛️ ПОЛЬЗОВАТЕЛЬСКИЕ VIEW'Ы
# ============================================================

class BaseView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 600):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Это меню открыто не тобой.", ephemeral=True
            )
            return False
        return True

    async def back_to_main(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = await build_main_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=MainMenuView(self.author_id))


class MainMenuView(BaseView):
    @discord.ui.button(label="Замок", emoji="🏰", style=discord.ButtonStyle.primary, row=0)
    async def tab_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))

    @discord.ui.button(label="Хранилище", emoji="🎒", style=discord.ButtonStyle.secondary, row=0)
    async def tab_storage(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await is_command_disabled(interaction.guild_id, "storage"):
            await interaction.response.send_message("❌ Хранилище отключено на этом сервере.", ephemeral=True)
            return
        await interaction.response.defer()
        embed = await build_storage_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=StorageView(self.author_id))

    @discord.ui.button(label="Магазин", emoji="🛒", style=discord.ButtonStyle.secondary, row=0)
    async def tab_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await is_command_disabled(interaction.guild_id, "shop"):
            await interaction.response.send_message("❌ Магазин отключён на этом сервере.", ephemeral=True)
            return
        await interaction.response.defer()
        embed, _ = await build_shop_page(interaction, 0)
        await interaction.edit_original_response(embed=embed, view=ShopView(self.author_id, 0))

    @discord.ui.button(label="Улучшения", emoji="💎", style=discord.ButtonStyle.secondary, row=0)
    async def tab_upgrades(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await is_command_disabled(interaction.guild_id, "upgrades"):
            await interaction.response.send_message("❌ Магазин улучшений отключён.", ephemeral=True)
            return
        await interaction.response.defer()
        embed, _ = await build_upgrades_page(interaction, 0)
        await interaction.edit_original_response(embed=embed, view=UpgradesView(self.author_id, 0))

    @discord.ui.button(label="Достижения", emoji="🏆", style=discord.ButtonStyle.secondary, row=1)
    async def tab_achievements(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await is_command_disabled(interaction.guild_id, "achievements"):
            await interaction.response.send_message("❌ Достижения отключены.", ephemeral=True)
            return
        await interaction.response.defer()
        embed, _ = await build_achievements_page(interaction, 0)
        await interaction.edit_original_response(embed=embed, view=AchievementsView(self.author_id, 0))

    @discord.ui.button(label="Задания", emoji="📅", style=discord.ButtonStyle.secondary, row=1)
    async def tab_quests(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await is_command_disabled(interaction.guild_id, "quests"):
            await interaction.response.send_message("❌ Задания отключены.", ephemeral=True)
            return
        await interaction.response.defer()
        embed = await build_quests_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=QuestsView(self.author_id))

    @discord.ui.button(label="Статистика", emoji="📊", style=discord.ButtonStyle.secondary, row=1)
    async def tab_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await is_command_disabled(interaction.guild_id, "stats"):
            await interaction.response.send_message("❌ Статистика отключена.", ephemeral=True)
            return
        await interaction.response.defer()
        embed = await build_stats_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=StatsView(self.author_id))


class BackOnlyView(BaseView):
    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_main(interaction)


class ProfileView(BackOnlyView):
    @discord.ui.button(label="Переместить", emoji="🔀", style=discord.ButtonStyle.primary, row=1)
    async def move_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(
            title="🔀 Перемещение из Замка",
            description="Выбери предмет, который хочешь убрать в хранилище.",
            color=0x3498db
        )
        await interaction.edit_original_response(embed=embed, view=MoveView(self.author_id, "profile"))

    @discord.ui.button(label="Синтез", emoji="⚗️", style=discord.ButtonStyle.success, row=1)
    async def craft_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(
            title="⚗️ Синтез",
            description="Выбери предмет для синтеза из списка.",
            color=0x3498db
        )
        await interaction.edit_original_response(embed=embed, view=CraftSelectView(self.author_id))

    @discord.ui.button(label="Катализатор", emoji="🧪", style=discord.ButtonStyle.secondary, row=1)
    async def catalyst_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(
            title="🧪 Катализатор",
            description=(
                f"Цена: 💎 {CATALYST_PRICE} за штуку.\n"
                f"Эффект: +{int(CATALYST_BONUS * 100)}% к шансу следующего синтеза.\n\n"
                f"Выбери количество:"
            ),
            color=0x3498db
        )
        await interaction.edit_original_response(embed=embed, view=CatalystSelectView(self.author_id))


class StorageView(BackOnlyView):
    @discord.ui.button(label="Переместить", emoji="🔀", style=discord.ButtonStyle.primary, row=1)
    async def move_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(
            title="🔀 Перемещение из Хранилища",
            description="Выбери предмет, который хочешь вернуть в Замок.",
            color=0x3498db
        )
        await interaction.edit_original_response(embed=embed, view=MoveView(self.author_id, "storage"))


class QuestsView(BackOnlyView):
    @discord.ui.button(label="Забрать награду", emoji="🎁", style=discord.ButtonStyle.success, row=1)
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(
            title="🎁 Забрать награду",
            description="Выбери задание из списка.",
            color=0x3498db
        )
        await interaction.edit_original_response(embed=embed, view=ClaimQuestSelectView(self.author_id))


class StatsView(BackOnlyView):
    pass


# ---------- ПЕРЕМЕЩЕНИЕ ----------

class MoveView(discord.ui.View):
    def __init__(self, author_id: int, source_location: str):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.source_location = source_location
        self.selected_slot = None
        self.item_id = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="Выбери предмет", row=0, options=[discord.SelectOption(label="Загрузка...", value="none")])
    async def item_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values[0] == "none":
            await interaction.response.defer()
            await self.load_items(interaction)
            return
        slot_str, item_id = select.values[0].split(":", 1)
        self.selected_slot = int(slot_str)
        self.item_id = item_id
        await interaction.response.defer()
        await self.show_confirm(interaction)

    async def load_items(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        settings = await get_settings(guild_id)
        custom = settings["custom_emojis"]

        async with bot.db.execute("""
            SELECT inv.slot, inv.item_id, i.name, i.emoji
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND inv.location = ?
            ORDER BY inv.slot ASC
        """, (user_id, self.source_location)) as c:
            rows = await c.fetchall()

        if not rows:
            await interaction.followup.send("❌ В этой локации нет предметов.", ephemeral=True)
            return

        options = []
        for slot, item_id, name, default_emoji in rows[:25]:
            emoji = custom.get(item_id, default_emoji)
            options.append(discord.SelectOption(
                label=f"Слот {slot}: {name}",
                value=f"{slot}:{item_id}",
                emoji=emoji
            ))
        self.item_select.options = options
        await interaction.edit_original_response(view=self)

    async def show_confirm(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        settings = await get_settings(guild_id)
        custom = settings["custom_emojis"]
        async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (self.item_id,)) as c:
            row = await c.fetchone()
        name, default_emoji = row if row else ("предмет", "📦")
        emoji = custom.get(self.item_id, default_emoji)
        target = "storage" if self.source_location == "profile" else "profile"
        target_name = "Хранилище" if target == "storage" else "Замок"

        embed = discord.Embed(
            title="🔀 Перемещение",
            description=f"Переместить {emoji} **{name}** (слот {self.selected_slot}) в **{target_name}**?",
            color=0x3498db
        )
        await interaction.edit_original_response(
            embed=embed,
            view=MoveConfirmView(self.author_id, self.source_location, self.item_id, self.selected_slot)
        )


class MoveConfirmView(discord.ui.View):
    def __init__(self, author_id: int, source: str, item_id: str, slot: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.source = source
        self.item_id = item_id
        self.slot = slot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Переместить", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        user_id = interaction.user.id
        target = "storage" if self.source == "profile" else "profile"

        async with bot.db.execute(
            "SELECT 1 FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
            (user_id, self.source, self.slot)
        ) as c:
            if not await c.fetchone():
                await self.fail(interaction, "Предмета больше нет в этом слоте.")
                return

        async with bot.db.execute(
            "SELECT 1 FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
            (user_id, target, self.slot)
        ) as c:
            if await c.fetchone():
                await self.fail(interaction, f"В целевой локации слот {self.slot} уже занят.")
                return

        await bot.db.execute(
            "DELETE FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
            (user_id, self.source, self.slot)
        )
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location) VALUES (?, ?, ?, ?)",
            (user_id, self.slot, self.item_id, target)
        )
        await bot.db.commit()

        await update_quest_progress(user_id, "move_2")

        if self.source == "profile":
            embed = await build_profile_embed(interaction)
            view = ProfileView(self.author_id)
        else:
            embed = await build_storage_embed(interaction)
            view = StorageView(self.author_id)
        await interaction.edit_original_response(embed=embed, view=view)

    @discord.ui.button(label="Отмена", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.source == "profile":
            embed = await build_profile_embed(interaction)
            view = ProfileView(self.author_id)
        else:
            embed = await build_storage_embed(interaction)
            view = StorageView(self.author_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def fail(self, interaction: discord.Interaction, msg: str):
        embed = discord.Embed(title="❌ Ошибка", description=msg, color=0xe74c3c)
        if self.source == "profile":
            view = ProfileView(self.author_id)
        else:
            view = StorageView(self.author_id)
        await interaction.edit_original_response(embed=embed, view=view)


# ---------- СИНТЕЗ ----------

class CraftSelectView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="Выбери предмет для синтеза", row=0, options=[discord.SelectOption(label="Загрузка...", value="none")])
    async def item_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values[0] == "none":
            await interaction.response.defer()
            await self.load_items(interaction)
            return
        item_id = select.values[0]
        await interaction.response.defer()
        await self.show_confirm(interaction, item_id)

    async def load_items(self, interaction: discord.Interaction):
        options = []
        for item_id, next_id in CRAFT_CHAIN.items():
            async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (item_id,)) as c:
                src = await c.fetchone()
            async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (next_id,)) as c:
                dst = await c.fetchone()
            if not src or not dst:
                continue
            async with bot.db.execute(
                "SELECT COUNT(*) FROM inventory WHERE user_id = ? AND item_id = ?",
                (interaction.user.id, item_id)
            ) as c:
                count = (await c.fetchone())[0]
            options.append(discord.SelectOption(
                label=f"{src[0]} ({count}/5) → {dst[0]}",
                value=item_id,
                emoji=src[1]
            ))
        self.item_select.options = options or [discord.SelectOption(label="Нет доступных", value="none")]
        await interaction.edit_original_response(view=self)

    async def show_confirm(self, interaction: discord.Interaction, item_id: str):
        settings = CRAFT_SETTINGS.get(item_id, {"chance": 1.0, "gems": 0})
        async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (item_id,)) as c:
            src = await c.fetchone()
        async with bot.db.execute("SELECT catalysts FROM players WHERE user_id = ?", (interaction.user.id,)) as c:
            cats = (await c.fetchone())[0]

        embed = discord.Embed(
            title="⚗️ Синтез",
            description=(
                f"Предмет: {src[1]} **{src[0]}**\n"
                f"Шанс успеха: {int(settings['chance'] * 100)}%\n"
                f"Стоимость: 💎 {settings['gems']}\n\n"
                f"Использовать катализатор (+{int(CATALYST_BONUS * 100)}%)?\n"
                f"У тебя катализаторов: **{cats}**"
            ),
            color=0x3498db
        )
        await interaction.edit_original_response(
            embed=embed,
            view=CraftConfirmView(self.author_id, item_id)
        )


class CraftConfirmView(discord.ui.View):
    def __init__(self, author_id: int, item_id: str):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.item_id = item_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Без катализатора", emoji="⚗️", style=discord.ButtonStyle.primary)
    async def no_catalyst(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.do_craft(interaction, False)

    @discord.ui.button(label="С катализатором", emoji="🧪", style=discord.ButtonStyle.success)
    async def with_catalyst(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.do_craft(interaction, True)

    @discord.ui.button(label="Отмена", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))

    async def do_craft(self, interaction: discord.Interaction, use_cat: bool):
        user_id = interaction.user.id
        item_id = self.item_id
        next_id = CRAFT_CHAIN[item_id]
        settings = CRAFT_SETTINGS.get(item_id, {"chance": 1.0, "gems": 0})
        base_chance, gem_cost = settings["chance"], settings["gems"]

        async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (item_id,)) as c:
            src = await c.fetchone()
        async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (next_id,)) as c:
            dst = await c.fetchone()
        src_name, src_emoji = src
        dst_name, dst_emoji = dst

        async with bot.db.execute(
            "SELECT location, slot FROM inventory WHERE user_id = ? AND item_id = ?", (user_id, item_id)
        ) as c:
            owned = await c.fetchall()
        if len(owned) < CRAFT_COST:
            await self.fail(interaction, f"❌ Нужно {CRAFT_COST} × {src_name}.")
            return

        async with bot.db.execute("SELECT gems, catalysts FROM players WHERE user_id = ?", (user_id,)) as c:
            gems, cats = await c.fetchone()
        if gems < gem_cost:
            await self.fail(interaction, f"❌ Нужно 💎 {gem_cost}.")
            return
        if use_cat and cats < 1:
            await self.fail(interaction, "❌ Нет катализаторов.")
            return

        grid_size = await get_grid_size(user_id)
        async with bot.db.execute(
            "SELECT slot FROM inventory WHERE user_id = ? AND location = 'profile'", (user_id,)
        ) as c:
            used = {r[0] for r in await c.fetchall()}
        free = [s for s in range(grid_size) if s not in used]
        if not free:
            await self.fail(interaction, "❌ В замке нет места.")
            return

        if gem_cost > 0:
            await bot.db.execute("UPDATE players SET gems = gems - ? WHERE user_id = ?", (gem_cost, user_id))
        catalyst_used = 0
        if use_cat:
            await bot.db.execute("UPDATE players SET catalysts = catalysts - 1 WHERE user_id = ?", (user_id,))
            catalyst_used = 1

        for location, slot in owned[:CRAFT_COST]:
            await bot.db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
                (user_id, location, slot)
            )

        final_chance = min(1.0, base_chance + (CATALYST_BONUS if use_cat else 0))
        success = random.random() < final_chance

        await bot.db.execute(
            "INSERT INTO craft_log (user_id, item_id, success, gems_spent, catalyst_used) VALUES (?, ?, ?, ?, ?)",
            (user_id, item_id, int(success), gem_cost, catalyst_used)
        )

        if success:
            await bot.db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) VALUES (?, ?, ?, 'profile')",
                (user_id, free[0], next_id)
            )

        await bot.db.execute(
            "UPDATE players SET total_crafts = total_crafts + 1, total_successes = total_successes + ? "
            "WHERE user_id = ?", (int(success), user_id)
        )
        await bot.db.commit()

        await update_quest_progress(user_id, "craft_3")
        await update_quest_progress(user_id, "craft_5")
        if success:
            await update_quest_progress(user_id, "success_2")
        if use_cat:
            await update_quest_progress(user_id, "use_catalyst")

        unlocked = await check_achievements(user_id)

        chance_str = f"🎲 {int(final_chance * 100)}%"
        if use_cat:
            chance_str += f" (база {int(base_chance * 100)}% + 🧪)"
        gem_str = f" | 💎 {gem_cost}" if gem_cost else ""
        if success:
            msg = f"⚗️ Успех! {CRAFT_COST}×{src_emoji} {src_name} → 1×{dst_emoji} {dst_name}\n{chance_str}{gem_str}"
        else:
            msg = f"💥 Провал! {CRAFT_COST}×{src_emoji} {src_name} сгорели.\n{chance_str}{gem_str}"
        if unlocked:
            msg += "\n🏆 " + ", ".join(f"{e} {n}" for e, n, _ in unlocked)

        embed = discord.Embed(title="⚗️ Результат синтеза", description=msg, color=0x9b59b6)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))

    async def fail(self, interaction: discord.Interaction, msg: str):
        embed = discord.Embed(title="❌ Ошибка", description=msg, color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))


# ---------- КАТАЛИЗАТОР ----------

class CatalystSelectView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        placeholder="Сколько катализаторов купить?",
        options=[
            discord.SelectOption(label=f"{q} шт — 💎 {CATALYST_PRICE * q}", value=str(q))
            for q in (1, 2, 5, 10, 25)
        ],
        row=0
    )
    async def quantity_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        qty = int(select.values[0])
        user_id = interaction.user.id
        total = CATALYST_PRICE * qty

        async with bot.db.execute("SELECT gems, catalysts FROM players WHERE user_id = ?", (user_id,)) as c:
            gems, owned = await c.fetchone()
        if gems < total:
            embed = discord.Embed(
                title="❌ Не хватает гемов",
                description=f"Нужно 💎 {total}, у тебя {gems}.",
                color=0xe74c3c
            )
            await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))
            return

        await bot.db.execute(
            "UPDATE players SET gems = gems - ?, catalysts = catalysts + ? WHERE user_id = ?",
            (total, qty, user_id)
        )
        await bot.db.commit()

        embed = discord.Embed(
            title="🧪 Катализатор куплен",
            description=(
                f"Куплено **{qty}** катализатор(ов) за 💎 {total}.\n"
                f"Эффект: +{int(CATALYST_BONUS * 100)}% к шансу следующего синтеза.\n"
                f"Всего катализаторов: **{owned + qty}**."
            ),
            color=0x2ecc71
        )
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))

    @discord.ui.button(label="Отмена", emoji="❌", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))


# ---------- ЗАБРАТЬ НАГРАДУ ----------

class ClaimQuestSelectView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="Выбери задание", row=0, options=[discord.SelectOption(label="Загрузка...", value="none")])
    async def quest_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values[0] == "none":
            await interaction.response.defer()
            await self.load_quests(interaction)
            return
        await interaction.response.defer()
        await self.claim(interaction, select.values[0])

    async def load_quests(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        quests, progress, claimed = await get_or_create_daily_quests(user_id)
        options = []
        for qid in quests:
            if qid in claimed:
                continue
            desc, target, reward = QUEST_POOL[qid]
            done = progress[qid] >= target
            label = f"{desc} — {progress[qid]}/{target}" + (" 🎁" if done else "")
            options.append(discord.SelectOption(
                label=label[:100],
                value=qid,
                emoji="🎁" if done else "⏳"
            ))
        self.quest_select.options = options or [discord.SelectOption(label="Нет доступных заданий", value="none")]
        await interaction.edit_original_response(view=self)

    async def claim(self, interaction: discord.Interaction, qid: str):
        user_id = interaction.user.id
        quests, progress, claimed = await get_or_create_daily_quests(user_id)
        if qid not in quests:
            await self.fail(interaction, "❌ Нет такого задания.")
            return
        if qid in claimed:
            await self.fail(interaction, "❌ Уже получено.")
            return
        desc, target, reward = QUEST_POOL[qid]
        if progress[qid] < target:
            await self.fail(interaction, f"❌ Не выполнено: {progress[qid]}/{target}.")
            return

        claimed.append(qid)
        await bot.db.execute(
            "UPDATE players SET daily_quest_claimed = ?, gems = gems + ? WHERE user_id = ?",
            (json.dumps(claimed), reward, user_id)
        )
        await bot.db.commit()

        embed = discord.Embed(
            title="🎁 Награда получена",
            description=f"💎 **{reward}** гемов за «{desc}»!",
            color=0x2ecc71
        )
        await interaction.edit_original_response(embed=embed, view=QuestsView(self.author_id))

    async def fail(self, interaction: discord.Interaction, msg: str):
        embed = discord.Embed(title="❌ Ошибка", description=msg, color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=QuestsView(self.author_id))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_quests_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=QuestsView(self.author_id))


# ---------- МАГАЗИН ----------

class ShopView(BaseView):
    def __init__(self, author_id: int, page: int):
        super().__init__(author_id)
        self.page = page

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_main(interaction)

    @discord.ui.button(label="Купить", emoji="🛍️", style=discord.ButtonStyle.success, row=0)
    async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🛒 Выбери предмет", description="Выбери предмет из списка ниже.", color=0xf1c40f)
        await interaction.edit_original_response(embed=embed, view=ShopBuySelectView(self.author_id))

    @discord.ui.button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page = max(0, self.page - 1)
        embed, _ = await build_shop_page(interaction, self.page)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, total = await build_shop_page(interaction, self.page + 1)
        self.page = min(total - 1, self.page + 1)
        await interaction.edit_original_response(embed=embed, view=self)


class ShopBuySelectView(BaseView):
    @discord.ui.select(placeholder="Выбери предмет...", row=0, options=[discord.SelectOption(label="Загрузка...", value="none")])
    async def item_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values[0] == "none":
            await interaction.response.defer()
            await self.load_options(interaction)
            return
        item_id = select.values[0]
        await interaction.response.defer()
        async with bot.db.execute("SELECT name, price, emoji FROM items WHERE id = ?", (item_id,)) as c:
            item = await c.fetchone()
        embed = discord.Embed(
            title="🛒 Покупка",
            description=f"{item[2]} **{item[0]}** — 🪙 {item[1]} за штуку.\nВыбери количество:",
            color=0xf1c40f
        )
        await interaction.edit_original_response(
            embed=embed,
            view=BuyItemQuantityView(self.author_id, item_id)
        )

    async def load_options(self, interaction: discord.Interaction):
        async with bot.db.execute("SELECT id, name, price, emoji FROM items WHERE buyable = 1") as c:
            rows = await c.fetchall()
        self.item_select.options = [
            discord.SelectOption(label=f"{name} — 🪙 {price}", value=item_id, emoji=emoji)
            for item_id, name, price, emoji in rows
        ]
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, _ = await build_shop_page(interaction, 0)
        await interaction.edit_original_response(embed=embed, view=ShopView(self.author_id, 0))


class BuyItemQuantityView(discord.ui.View):
    def __init__(self, author_id: int, item_id: str):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.item_id = item_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        placeholder="Сколько купить?",
        options=[discord.SelectOption(label=f"{q} шт", value=str(q)) for q in (1, 5, 10, 25, 50)],
        row=0
    )
    async def quantity_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer()
        qty = int(select.values[0])
        user_id = interaction.user.id

        async with bot.db.execute("SELECT price, name, buyable FROM items WHERE id = ?", (self.item_id,)) as c:
            item = await c.fetchone()
        if not item:
            await self.fail(interaction, "❌ Предмет не найден.")
            return
        price, name, buyable = item
        if not buyable:
            await self.fail(interaction, f"❌ **{name}** нельзя купить.")
            return

        total_cost = price * qty
        async with bot.db.execute("SELECT coins FROM players WHERE user_id = ?", (user_id,)) as c:
            balance = (await c.fetchone())[0]
        if balance < total_cost:
            await self.fail(interaction, f"❌ Нужно {total_cost} монет, у тебя {balance}.")
            return

        grid_size = await get_grid_size(user_id)
        async with bot.db.execute(
            "SELECT slot FROM inventory WHERE user_id = ? AND location = 'profile'", (user_id,)
        ) as c:
            used = {r[0] for r in await c.fetchall()}
        free = [s for s in range(grid_size) if s not in used]
        if len(free) < qty:
            await self.fail(interaction, f"❌ В замке только {len(free)} слотов.")
            return

        await bot.db.execute("UPDATE players SET coins = coins - ? WHERE user_id = ?", (total_cost, user_id))
        for i in range(qty):
            await bot.db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) VALUES (?, ?, ?, 'profile')",
                (user_id, free[i], self.item_id)
            )
        await bot.db.commit()

        await update_quest_progress(user_id, "buy_3", qty)
        unlocked = await check_achievements(user_id)

        msg = f"✅ Куплено **{name}** x{qty} за {total_cost} монет."
        if unlocked:
            msg += "\n🏆 " + ", ".join(f"{e} {n}" for e, n, _ in unlocked)
        embed = discord.Embed(title="🛒 Покупка", description=msg, color=0x2ecc71)
        await interaction.edit_original_response(embed=embed, view=ShopView(self.author_id, 0))

    async def fail(self, interaction: discord.Interaction, msg: str):
        embed = discord.Embed(title="❌ Ошибка", description=msg, color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=ShopView(self.author_id, 0))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, _ = await build_shop_page(interaction, 0)
        await interaction.edit_original_response(embed=embed, view=ShopView(self.author_id, 0))


# ---------- УЛУЧШЕНИЯ ----------

class UpgradesView(BaseView):
    def __init__(self, author_id: int, page: int):
        super().__init__(author_id)
        self.page = page

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_main(interaction)

    @discord.ui.button(label="Купить", emoji="💳", style=discord.ButtonStyle.success, row=0)
    async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="💎 Выбери улучшение", description="Выбери улучшение из списка ниже.", color=0x9b59b6)
        await interaction.edit_original_response(embed=embed, view=UpgradesBuySelectView(self.author_id))

    @discord.ui.button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page = max(0, self.page - 1)
        embed, _ = await build_upgrades_page(interaction, self.page)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, total = await build_upgrades_page(interaction, self.page + 1)
        self.page = min(total - 1, self.page + 1)
        await interaction.edit_original_response(embed=embed, view=self)


class UpgradesBuySelectView(BaseView):
    @discord.ui.select(placeholder="Выбери улучшение...", row=0, options=[discord.SelectOption(label="Загрузка...", value="none")])
    async def upgrade_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values[0] == "none":
            await interaction.response.defer()
            await self.load_options(interaction)
            return
        await interaction.response.defer()
        await self.process_buy(interaction, select.values[0])

    async def load_options(self, interaction: discord.Interaction):
        async with bot.db.execute("SELECT id, name, price_gems, emoji FROM gem_shop ORDER BY category, price_gems") as c:
            rows = await c.fetchall()
        async with bot.db.execute(
            "SELECT upgrade_id FROM player_upgrades WHERE user_id = ?", (interaction.user.id,)
        ) as c:
            owned = {r[0] for r in await c.fetchall()}
        self.upgrade_select.options = [
            discord.SelectOption(
                label=f"{name} — 💎 {price}" + (" ✅" if gid in owned else ""),
                value=gid,
                emoji=emoji
            )
            for gid, name, price, emoji in rows
        ]
        await interaction.edit_original_response(view=self)

    async def process_buy(self, interaction: discord.Interaction, upgrade_id: str):
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        async with bot.db.execute(
            "SELECT name, price_gems, emoji, category FROM gem_shop WHERE id = ?", (upgrade_id,)
        ) as c:
            item = await c.fetchone()
        if not item:
            await interaction.followup.send("❌ Улучшение не найдено.", ephemeral=True)
            return

        name, price, emoji, category = item

        async with bot.db.execute(
            "SELECT 1 FROM player_upgrades WHERE user_id = ? AND upgrade_id = ?", (user_id, upgrade_id)
        ) as c:
            if await c.fetchone():
                await interaction.followup.send(f"❌ **{name}** уже куплено.", ephemeral=True)
                return

        async with bot.db.execute("SELECT gems FROM players WHERE user_id = ?", (user_id,)) as c:
            gems = (await c.fetchone())[0]
        if gems < price:
            await interaction.followup.send(f"❌ Нужно 💎 {price}.", ephemeral=True)
            return

        await bot.db.execute("UPDATE players SET gems = gems - ? WHERE user_id = ?", (price, user_id))
        await bot.db.execute(
            "INSERT INTO player_upgrades (user_id, upgrade_id) VALUES (?, ?)", (user_id, upgrade_id)
        )

        if upgrade_id.startswith("grid_"):
            size = int(upgrade_id.split("_")[1].split("x")[0])
            await bot.db.execute(
                "UPDATE players SET grid_size = ? WHERE user_id = ?", (size * size, user_id)
            )
        elif category == "status":
            bonuses = {"vip": 0.15, "platinum": 0.25, "gold": 0.35, "diamond": 0.45}
            async with bot.db.execute(
                "SELECT upgrade_id FROM player_upgrades WHERE user_id = ? AND upgrade_id IN "
                "('vip','platinum','gold','diamond')", (user_id,)
            ) as c:
                statuses = [r[0] for r in await c.fetchall()]
            max_bonus = max(bonuses[s] for s in statuses) if statuses else 0.0
            await bot.db.execute(
                "UPDATE players SET income_bonus = ? WHERE user_id = ?", (max_bonus, user_id)
            )

            if guild_id:
                settings = await get_settings(guild_id)
                role_id = settings["status_roles"].get(upgrade_id)
                if role_id:
                    guild = interaction.guild
                    member = guild.get_member(user_id) if guild else None
                    role = guild.get_role(role_id) if guild else None
                    if member and role:
                        try:
                            await member.add_roles(role, reason=f"Покупка статуса {name}")
                        except discord.HTTPException:
                            pass

        await bot.db.commit()
        await interaction.followup.send(f"✅ Куплено **{emoji} {name}** за 💎 {price}!", ephemeral=True)


class AchievementsView(BaseView):
    def __init__(self, author_id: int, page: int):
        super().__init__(author_id)
        self.page = page

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_main(interaction)

    @discord.ui.button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page = max(0, self.page - 1)
        embed, _ = await build_achievements_page(interaction, self.page)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, total = await build_achievements_page(interaction, self.page + 1)
        self.page = min(total - 1, self.page + 1)
        await interaction.edit_original_response(embed=embed, view=self)


# ============================================================
#  🛡️ АДМИН-ПАНЕЛЬ
# ============================================================

class AdminPanelView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 600):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Эта панель открыта не тобой.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Начислить", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def grant(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="➕ Начислить валюту", description="Выбери валюту, затем нажми «Ввести ID».", color=0x2ecc71)
        await interaction.edit_original_response(embed=embed, view=AdminGrantView(self.author_id))

    @discord.ui.button(label="Забрать", emoji="➖", style=discord.ButtonStyle.danger, row=0)
    async def take(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="➖ Забрать валюту", description="Выбери валюту, затем нажми «Ввести ID».", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=AdminTakeView(self.author_id))

    @discord.ui.button(label="Профиль", emoji="👤", style=discord.ButtonStyle.primary, row=0)
    async def profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminProfileModal(self.author_id))

    @discord.ui.button(label="Изменить", emoji="✏️", style=discord.ButtonStyle.secondary, row=1)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminEditModal(self.author_id))

    @discord.ui.button(label="Сбросить", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminResetModal(self.author_id))

    @discord.ui.button(label="Выдать предмет", emoji="🎁", style=discord.ButtonStyle.success, row=1)
    async def give_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminGiveItemModal(self.author_id))

    @discord.ui.button(label="Добавить генератор", emoji="⚙️", style=discord.ButtonStyle.secondary, row=2)
    async def add_gen(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddGeneratorModal(self.author_id))

    @discord.ui.button(label="Настройки", emoji="🔧", style=discord.ButtonStyle.secondary, row=2)
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🔧 Настройки сервера", description="Выбери категорию.", color=0x808080)
        await interaction.edit_original_response(embed=embed, view=SettingsView(self.author_id))


class AdminGrantView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.currency = "coins"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="Выбери валюту", options=[
        discord.SelectOption(label="Монеты", value="coins", emoji="🪙"),
        discord.SelectOption(label="Гемы", value="gems", emoji="💎"),
    ], row=0)
    async def currency_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.currency = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Ввести ID", emoji="📝", style=discord.ButtonStyle.primary, row=1)
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminGrantValuesModal(self.author_id, self.currency))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🛡️ Панель администратора", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=AdminPanelView(self.author_id))


class AdminGrantValuesModal(discord.ui.Modal, title="Начислить"):
    user_id = discord.ui.TextInput(label="ID пользователя", placeholder="123456789", required=True)
    amount = discord.ui.TextInput(label="Количество", default="100", required=True)

    def __init__(self, author_id: int, currency: str):
        super().__init__()
        self.author_id = author_id
        self.currency = currency

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            uid = int(self.user_id.value)
            amount = int(self.amount.value)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ ID и количество должны быть числами > 0.", ephemeral=True)
            return

        async with bot.db.execute("SELECT 1 FROM players WHERE user_id = ?", (uid,)) as c:
            if not await c.fetchone():
                await bot.db.execute(
                    "INSERT OR IGNORE INTO players (user_id, coins) VALUES (?, ?)",
                    (uid, DEFAULT_START_COINS)
                )

        await bot.db.execute(
            f"UPDATE players SET {self.currency} = {self.currency} + ? WHERE user_id = ?",
            (amount, uid)
        )
        await bot.db.commit()
        unit = "🪙" if self.currency == "coins" else "💎"
        await interaction.followup.send(f"✅ Начислено {amount} {unit} пользователю <@{uid}>.", ephemeral=True)


class AdminTakeView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.currency = "coins"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="Выбери валюту", options=[
        discord.SelectOption(label="Монеты", value="coins", emoji="🪙"),
        discord.SelectOption(label="Гемы", value="gems", emoji="💎"),
    ], row=0)
    async def currency_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.currency = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Ввести ID", emoji="📝", style=discord.ButtonStyle.primary, row=1)
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminTakeValuesModal(self.author_id, self.currency))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🛡️ Панель администратора", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=AdminPanelView(self.author_id))


class AdminTakeValuesModal(discord.ui.Modal, title="Забрать"):
    user_id = discord.ui.TextInput(label="ID пользователя", placeholder="123456789", required=True)
    amount = discord.ui.TextInput(label="Количество", default="100", required=True)

    def __init__(self, author_id: int, currency: str):
        super().__init__()
        self.author_id = author_id
        self.currency = currency

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            uid = int(self.user_id.value)
            amount = int(self.amount.value)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ ID и количество должны быть числами > 0.", ephemeral=True)
            return

        async with bot.db.execute(
            f"SELECT {self.currency} FROM players WHERE user_id = ?", (uid,)
        ) as c:
            row = await c.fetchone()
        if not row:
            await interaction.followup.send("❌ Игрок не найден.", ephemeral=True)
            return
        if row[0] < amount:
            await interaction.followup.send(f"❌ У игрока только {row[0]}.", ephemeral=True)
            return

        await bot.db.execute(
            f"UPDATE players SET {self.currency} = {self.currency} - ? WHERE user_id = ?",
            (amount, uid)
        )
        await bot.db.commit()
        unit = "🪙" if self.currency == "coins" else "💎"
        await interaction.followup.send(f"✅ Забрано {amount} {unit} у <@{uid}>.", ephemeral=True)


# ---------- АДМИН-МОДАЛКИ ----------

class AdminProfileModal(discord.ui.Modal, title="Профиль игрока"):
    user_id = discord.ui.TextInput(label="ID пользователя", placeholder="123456789", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            uid = int(self.user_id.value)
        except ValueError:
            await interaction.followup.send("❌ ID должен быть числом.", ephemeral=True)
            return

        async with bot.db.execute("SELECT 1 FROM players WHERE user_id = ?", (uid,)) as c:
            if not await c.fetchone():
                await interaction.followup.send("❌ Игрок не найден.", ephemeral=True)
                return

        async with bot.db.execute("""
            SELECT coins, gems, catalysts, grid_size, income_bonus,
                   total_crafts, total_successes, last_collected, last_gem_collected
            FROM players WHERE user_id = ?
        """, (uid,)) as c:
            row = await c.fetchone()
        (coins, gems, catalysts, grid_size, bonus,
         total_crafts, total_successes, last_coins, last_gems) = row

        async with bot.db.execute("""
            SELECT inv.location, inv.slot, i.name, i.emoji
            FROM inventory inv JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? ORDER BY inv.location, inv.slot
        """, (uid,)) as c:
            inv_rows = await c.fetchall()

        profile_items = [f"`{s}` {e} {n}" for loc, s, n, e in inv_rows if loc == "profile"]
        storage_items = [f"`{s}` {e} {n}" for loc, s, n, e in inv_rows if loc == "storage"]

        async with bot.db.execute(
            "SELECT COUNT(*) FROM player_achievements WHERE user_id = ?", (uid,)
        ) as c:
            ach_count = (await c.fetchone())[0]

        async with bot.db.execute(
            "SELECT upgrade_id FROM player_upgrades WHERE user_id = ?", (uid,)
        ) as c:
            upgrades = [r[0] for r in await c.fetchall()]

        embed = discord.Embed(title=f"🛡️ Профиль <@{uid}>", color=0xe74c3c)
        embed.add_field(name="ID", value=f"`{uid}`", inline=False)
        embed.add_field(name="Кошелёк", value=f"🪙 {coins} | 💎 {gems}", inline=True)
        embed.add_field(name="Катализаторы", value=f"🧪 {catalysts}", inline=True)
        embed.add_field(name="Сетка", value=f"{grid_size}", inline=True)
        embed.add_field(name="Бонус", value=f"+{int(bonus * 100)}%", inline=True)
        embed.add_field(name="Синтезы", value=f"{total_crafts} (успешно: {total_successes})", inline=True)
        embed.add_field(name="Достижения", value=f"{ach_count}", inline=True)
        embed.add_field(name="Апгрейды", value=", ".join(upgrades) if upgrades else "нет", inline=False)
        embed.add_field(name="Последний сбор монет", value=last_coins or "—", inline=True)
        embed.add_field(name="Последний сбор гемов", value=last_gems or "—", inline=True)
        embed.add_field(
            name=f"Замок ({len(profile_items)})",
            value="\n".join(profile_items) if profile_items else "пусто",
            inline=False
        )
        embed.add_field(
            name=f"Хранилище ({len(storage_items)})",
            value="\n".join(storage_items) if storage_items else "пусто",
            inline=False
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


class AdminEditModal(discord.ui.Modal, title="Изменить поле профиля"):
    user_id = discord.ui.TextInput(label="ID пользователя", placeholder="123456789", required=True)
    field = discord.ui.TextInput(label="Поле", placeholder="coins / gems / grid_size / income_bonus", required=True)
    value = discord.ui.TextInput(label="Новое значение", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            uid = int(self.user_id.value)
        except ValueError:
            await interaction.followup.send("❌ ID должен быть числом.", ephemeral=True)
            return

        field = self.field.value.strip()
        if field not in ("coins", "gems", "catalysts", "grid_size", "income_bonus"):
            await interaction.followup.send("❌ Неверное поле.", ephemeral=True)
            return

        try:
            if field == "income_bonus":
                parsed = float(self.value.value)
                if parsed < 0 or parsed > 1:
                    raise ValueError
            else:
                parsed = int(self.value.value)
                if parsed < 0:
                    raise ValueError
        except ValueError:
            await interaction.followup.send("❌ Неверное значение.", ephemeral=True)
            return

        await bot.db.execute(f"UPDATE players SET {field} = ? WHERE user_id = ?", (parsed, uid))
        await bot.db.commit()
        await interaction.followup.send(f"✅ `{field}` = **{parsed}** для <@{uid}>.", ephemeral=True)


class AdminResetModal(discord.ui.Modal, title="Сбросить прогресс"):
    user_id = discord.ui.TextInput(label="ID пользователя", placeholder="123456789", required=True)
    confirm = discord.ui.TextInput(label="Введите ДА для подтверждения", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.confirm.value.strip().upper() != "ДА":
            await interaction.followup.send("❌ Отменено.", ephemeral=True)
            return
        try:
            uid = int(self.user_id.value)
        except ValueError:
            await interaction.followup.send("❌ ID должен быть числом.", ephemeral=True)
            return

        await bot.db.execute("""
            UPDATE players SET
                coins = ?, gems = 0, catalysts = 0,
                grid_size = 36, income_bonus = 0.0,
                total_crafts = 0, total_successes = 0,
                last_collected = CURRENT_TIMESTAMP,
                last_gem_collected = CURRENT_TIMESTAMP,
                daily_quest_date = NULL,
                daily_quest_progress = '{}',
                daily_quest_claimed = '[]'
            WHERE user_id = ?
        """, (DEFAULT_START_COINS, uid))
        await bot.db.execute("DELETE FROM inventory WHERE user_id = ?", (uid,))
        await bot.db.execute("DELETE FROM player_achievements WHERE user_id = ?", (uid,))
        await bot.db.execute("DELETE FROM player_upgrades WHERE user_id = ?", (uid,))
        await bot.db.execute("DELETE FROM craft_log WHERE user_id = ?", (uid,))
        await bot.db.commit()
        await interaction.followup.send(f"🗑️ Прогресс <@{uid}> сброшен.", ephemeral=True)


class AdminGiveItemModal(discord.ui.Modal, title="Выдать предмет"):
    user_id = discord.ui.TextInput(label="ID пользователя", placeholder="123456789", required=True)
    item_id = discord.ui.TextInput(label="ID предмета", placeholder="gold_gen", required=True)
    quantity = discord.ui.TextInput(label="Количество", default="1", required=True)
    location = discord.ui.TextInput(label="Куда (profile/storage)", default="profile", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            uid = int(self.user_id.value)
            qty = int(self.quantity.value)
            if qty < 1:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ ID и количество должны быть числами > 0.", ephemeral=True)
            return

        loc = self.location.value.strip()
        if loc not in ("profile", "storage"):
            await interaction.followup.send("❌ Куда: `profile` или `storage`.", ephemeral=True)
            return

        item_id = self.item_id.value.strip()
        async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (item_id,)) as c:
            item = await c.fetchone()
        if not item:
            await interaction.followup.send("❌ Предмет не найден.", ephemeral=True)
            return

        name, emoji = item
        grid_size = await get_grid_size(uid)
        async with bot.db.execute(
            "SELECT slot FROM inventory WHERE user_id = ? AND location = ?", (uid, loc)
        ) as c:
            used = {r[0] for r in await c.fetchall()}
        free = [s for s in range(grid_size) if s not in used]
        if len(free) < qty:
            await interaction.followup.send(f"❌ Только {len(free)} слотов.", ephemeral=True)
            return

        for i in range(qty):
            await bot.db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) VALUES (?, ?, ?, ?)",
                (uid, free[i], item_id, loc)
            )
        await bot.db.commit()
        await interaction.followup.send(
            f"✅ Выдано {qty}×{emoji} {name} пользователю <@{uid}>.", ephemeral=True
        )


class AddGeneratorModal(discord.ui.Modal, title="Добавить генератор"):
    id = discord.ui.TextInput(label="ID (латиницей)", placeholder="my_gen", required=True)
    name = discord.ui.TextInput(label="Название", placeholder="Мой генератор", required=True)
    price = discord.ui.TextInput(label="Цена", default="100", required=True)
    income_coins = discord.ui.TextInput(label="Доход монет/сек", default="0.001", required=True)
    income_gems = discord.ui.TextInput(label="Доход гемов/сек", default="0", required=True)
    emoji = discord.ui.TextInput(label="Эмодзи", default="⚙️", required=True)
    rarity = discord.ui.TextInput(label="Редкость", default="common", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item_id = self.id.value.strip()
        if not item_id.isalnum() or item_id != item_id.lower():
            await interaction.followup.send("❌ ID должен быть латиницей в нижнем регистре.", ephemeral=True)
            return
        async with bot.db.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)) as c:
            if await c.fetchone():
                await interaction.followup.send(f"❌ Предмет с ID `{item_id}` уже существует.", ephemeral=True)
                return

        rarity = self.rarity.value.strip().lower()
        if rarity not in RARITY_COLORS:
            await interaction.followup.send(f"❌ Редкость: {', '.join(RARITY_COLORS.keys())}.", ephemeral=True)
            return

        try:
            price = int(self.price.value)
            inc_c = float(self.income_coins.value)
            inc_g = float(self.income_gems.value)
        except ValueError:
            await interaction.followup.send("❌ Цена и доходы должны быть числами.", ephemeral=True)
            return

        await bot.db.execute(
            "INSERT INTO items (id, name, price, income_per_hour, emoji, rarity, buyable, income_gems_per_hour) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (item_id, self.name.value.strip(), price, inc_c, self.emoji.value.strip(), rarity, inc_g)
        )
        await bot.db.commit()
        await interaction.followup.send(
            f"✅ Генератор **{self.emoji.value} {self.name.value}** (`{item_id}`) добавлен.", ephemeral=True
        )


# ============================================================
#  ⚙️ НАСТРОЙКИ (многошаговые View)
# ============================================================

class SettingsView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Общие", emoji="🌐", style=discord.ButtonStyle.primary, row=0)
    async def general(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SettingsGeneralModal(self.author_id))

    @discord.ui.button(label="Экономика", emoji="💰", style=discord.ButtonStyle.success, row=0)
    async def economy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="💰 Экономика", description="Цены, доход, стартовые монеты, потолок гемов, лимит дохода.", color=0x2ecc71)
        await interaction.edit_original_response(embed=embed, view=SettingsEconomyView(self.author_id))

    @discord.ui.button(label="Валюты", emoji="🪙", style=discord.ButtonStyle.secondary, row=1)
    async def currencies(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SettingsCurrencyModal(self.author_id))

    @discord.ui.button(label="Команды", emoji="🚫", style=discord.ButtonStyle.secondary, row=1)
    async def commands(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🚫 Отключение команд", description="Выбери команды, которые нужно отключить.", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=SettingsCommandsView(self.author_id))

    @discord.ui.button(label="Роли за статус", emoji="🎭", style=discord.ButtonStyle.secondary, row=2)
    async def status_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SettingsStatusRoleModal(self.author_id))

    @discord.ui.button(label="Достижения", emoji="🏆", style=discord.ButtonStyle.secondary, row=2)
    async def achievements(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🏆 Управление достижениями", color=0xf1c40f)
        await interaction.edit_original_response(embed=embed, view=SettingsAchievementsView(self.author_id))

    @discord.ui.button(label="Роль админа", emoji="👑", style=discord.ButtonStyle.danger, row=3)
    async def admin_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SettingsAdminRoleModal(self.author_id))

    @discord.ui.button(label="Эмодзи", emoji="🎨", style=discord.ButtonStyle.secondary, row=3)
    async def emojis(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(
            title="🎨 Кастомные эмодзи",
            description="Выбери, что изменить (для генераторов — через «Общие»).",
            color=0x9b59b6
        )
        await interaction.edit_original_response(embed=embed, view=SettingsEmojisView(self.author_id))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=4)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🛡️ Панель администратора", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=AdminPanelView(self.author_id))


class SettingsGeneralModal(discord.ui.Modal, title="Общие настройки"):
    bot_name = discord.ui.TextInput(label="Название бота", default=DEFAULT_BOT_NAME, required=False)
    item_id = discord.ui.TextInput(label="ID предмета для эмодзи", required=False)
    emoji = discord.ui.TextInput(label="Новый эмодзи", required=False)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        settings = await get_settings(guild_id)
        changes = []

        if self.bot_name.value:
            await save_setting(guild_id, "bot_name", self.bot_name.value.strip())
            changes.append(f"📛 Название: **{self.bot_name.value}**")

        if self.item_id.value and self.emoji.value:
            item_id = self.item_id.value.strip()
            async with bot.db.execute("SELECT name FROM items WHERE id = ?", (item_id,)) as c:
                item = await c.fetchone()
            if not item:
                await interaction.followup.send(f"❌ Предмет `{item_id}` не найден.", ephemeral=True)
                return
            custom = settings["custom_emojis"]
            custom[item_id] = self.emoji.value.strip()
            await save_setting(guild_id, "custom_emojis", custom)
            changes.append(f"🎨 {item[0]}: {self.emoji.value}")

        if changes:
            await interaction.followup.send("✅ Обновлено:\n" + "\n".join(changes), ephemeral=True)
        else:
            await interaction.followup.send("ℹ️ Ничего не изменено.", ephemeral=True)


class SettingsEconomyView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Цена предмета", emoji="🏷️", style=discord.ButtonStyle.primary, row=0)
    async def price(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditItemPriceModal(self.author_id))

    @discord.ui.button(label="Доход предмета", emoji="📈", style=discord.ButtonStyle.primary, row=0)
    async def income(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditItemIncomeModal(self.author_id))

    @discord.ui.button(label="Стартовые монеты", emoji="🪙", style=discord.ButtonStyle.success, row=1)
    async def start_coins(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditStartCoinsModal(self.author_id))

    @discord.ui.button(label="Потолок гемов", emoji="💎", style=discord.ButtonStyle.success, row=1)
    async def gem_cap(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditGemCapModal(self.author_id))

    @discord.ui.button(label="Лимит дохода", emoji="⏳", style=discord.ButtonStyle.secondary, row=2)
    async def passive_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditPassiveLimitModal(self.author_id))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=2)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🔧 Настройки сервера", color=0x808080)
        await interaction.edit_original_response(embed=embed, view=SettingsView(self.author_id))


class EditItemPriceModal(discord.ui.Modal, title="Изменить цену предмета"):
    item_id = discord.ui.TextInput(label="ID предмета", placeholder="basic_gen", required=True)
    price = discord.ui.TextInput(label="Новая цена", placeholder="100", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item_id = self.item_id.value.strip()
        try:
            price = int(self.price.value)
            if price < 0:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ Цена должна быть числом >= 0.", ephemeral=True)
            return
        async with bot.db.execute("SELECT name FROM items WHERE id = ?", (item_id,)) as c:
            item = await c.fetchone()
        if not item:
            await interaction.followup.send(f"❌ Предмет `{item_id}` не найден.", ephemeral=True)
            return
        await bot.db.execute("UPDATE items SET price = ? WHERE id = ?", (price, item_id))
        await bot.db.commit()
        await interaction.followup.send(f"✅ Цена **{item[0]}** = 🪙 {price}.", ephemeral=True)


class EditItemIncomeModal(discord.ui.Modal, title="Изменить доход предмета"):
    item_id = discord.ui.TextInput(label="ID предмета", placeholder="basic_gen", required=True)
    income_coins = discord.ui.TextInput(label="Доход монет/сек", placeholder="0.000833", required=False)
    income_gems = discord.ui.TextInput(label="Доход гемов/сек", placeholder="0", required=False)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item_id = self.item_id.value.strip()
        async with bot.db.execute("SELECT name FROM items WHERE id = ?", (item_id,)) as c:
            item = await c.fetchone()
        if not item:
            await interaction.followup.send(f"❌ Предмет `{item_id}` не найден.", ephemeral=True)
            return
        updates = []
        if self.income_coins.value:
            try:
                inc = float(self.income_coins.value)
                if inc < 0:
                    raise ValueError
                await bot.db.execute("UPDATE items SET income_per_hour = ? WHERE id = ?", (inc, item_id))
                updates.append(f"🪙 {inc}/сек")
            except ValueError:
                await interaction.followup.send("❌ Неверный доход монет.", ephemeral=True)
                return
        if self.income_gems.value:
            try:
                inc = float(self.income_gems.value)
                if inc < 0:
                    raise ValueError
                await bot.db.execute("UPDATE items SET income_gems_per_hour = ? WHERE id = ?", (inc, item_id))
                updates.append(f"💎 {inc}/сек")
            except ValueError:
                await interaction.followup.send("❌ Неверный доход гемов.", ephemeral=True)
                return
        await bot.db.commit()
        await interaction.followup.send(
            f"✅ Доход **{item[0]}** обновлён: {', '.join(updates) if updates else 'без изменений'}.",
            ephemeral=True
        )


class EditStartCoinsModal(discord.ui.Modal, title="Стартовые монеты"):
    value = discord.ui.TextInput(label="Сколько монет выдавать новым игрокам", default="10", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            val = int(self.value.value)
            if val < 0:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ Значение должно быть >= 0.", ephemeral=True)
            return
        await save_setting(interaction.guild_id, "start_coins", val)
        await interaction.followup.send(f"✅ Стартовые монеты: **{val}**.", ephemeral=True)


class EditGemCapModal(discord.ui.Modal, title="Потолок гемов"):
    value = discord.ui.TextInput(label="Максимум гемов за один заход", default="6", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            val = int(self.value.value)
            if val < 0:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ Значение должно быть >= 0.", ephemeral=True)
            return
        await save_setting(interaction.guild_id, "gem_cap", val)
        await interaction.followup.send(f"✅ Потолок гемов: **{val}**.", ephemeral=True)


class EditPassiveLimitModal(discord.ui.Modal, title="Лимит пассивного дохода"):
    value = discord.ui.TextInput(label="Максимум накопления за один заход", default="100000", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            val = int(self.value.value)
            if val < 0:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ Значение должно быть >= 0.", ephemeral=True)
            return
        await save_setting(interaction.guild_id, "passive_limit", val)
        await interaction.followup.send(f"✅ Лимит дохода: **{val}**.", ephemeral=True)


class SettingsCurrencyModal(discord.ui.Modal, title="Названия валют"):
    coins = discord.ui.TextInput(label="Название монет", default=DEFAULT_CURRENCY_COINS, required=True)
    gems = discord.ui.TextInput(label="Название гемов", default=DEFAULT_CURRENCY_GEMS, required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        await save_setting(guild_id, "currency_coins", self.coins.value.strip())
        await save_setting(guild_id, "currency_gems", self.gems.value.strip())
        await interaction.followup.send(
            f"✅ Валюты: **{self.coins.value}** / **{self.gems.value}**.", ephemeral=True
        )


class SettingsCommandsView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        placeholder="Выбери команды для отключения",
        min_values=0,
        max_values=len(TOGGLEABLE_COMMANDS),
        options=[discord.SelectOption(label=name, value=key) for key, name in TOGGLEABLE_COMMANDS.items()],
        row=0
    )
    async def toggle(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        await save_setting(guild_id, "disabled_commands", list(select.values))
        disabled_names = [TOGGLEABLE_COMMANDS[c] for c in select.values]
        await interaction.followup.send(
            f"✅ Отключено: {', '.join(disabled_names) if disabled_names else 'ничего'}.", ephemeral=True
        )

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🔧 Настройки сервера", color=0x808080)
        await interaction.edit_original_response(embed=embed, view=SettingsView(self.author_id))


class SettingsStatusRoleModal(discord.ui.Modal, title="Роль за статус"):
    status = discord.ui.TextInput(label="Статус (vip/platinum/gold/diamond)", placeholder="vip", required=True)
    role_id = discord.ui.TextInput(label="ID роли", placeholder="123456789012345678", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        status = self.status.value.strip().lower()
        if status not in ("vip", "platinum", "gold", "diamond"):
            await interaction.followup.send("❌ Статус: vip/platinum/gold/diamond.", ephemeral=True)
            return
        try:
            role_id = int(self.role_id.value)
        except ValueError:
            await interaction.followup.send("❌ ID роли должен быть числом.", ephemeral=True)
            return
        guild_id = interaction.guild_id
        settings = await get_settings(guild_id)
        roles = settings["status_roles"]
        roles[status] = role_id
        await save_setting(guild_id, "status_roles", roles)
        await interaction.followup.send(
            f"✅ Роль <@&{role_id}> будет выдаваться за статус **{status}**.", ephemeral=True
        )


class SettingsAchievementsView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Изменить награду", emoji="✏️", style=discord.ButtonStyle.primary, row=0)
    async def edit_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditAchievementRewardModal(self.author_id))

    @discord.ui.button(label="Удалить", emoji="🗑️", style=discord.ButtonStyle.danger, row=0)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DeleteAchievementModal(self.author_id))

    @discord.ui.button(label="Добавить", emoji="➕", style=discord.ButtonStyle.success, row=1)
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddAchievementModal(self.author_id))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🔧 Настройки сервера", color=0x808080)
        await interaction.edit_original_response(embed=embed, view=SettingsView(self.author_id))


class EditAchievementRewardModal(discord.ui.Modal, title="Изменить награду достижения"):
    ach_id = discord.ui.TextInput(label="ID достижения", placeholder="first_craft", required=True)
    reward = discord.ui.TextInput(label="Новая награда (гемы)", placeholder="10", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ach_id = self.ach_id.value.strip()
        try:
            reward = int(self.reward.value)
            if reward < 0:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ Награда должна быть >= 0.", ephemeral=True)
            return
        async with bot.db.execute("SELECT name FROM achievements WHERE id = ?", (ach_id,)) as c:
            item = await c.fetchone()
        if not item:
            await interaction.followup.send("❌ Достижение не найдено.", ephemeral=True)
            return
        await bot.db.execute("UPDATE achievements SET reward_gems = ? WHERE id = ?", (reward, ach_id))
        await bot.db.commit()
        await interaction.followup.send(f"✅ Награда «{item[0]}» = 💎 {reward}.", ephemeral=True)


class DeleteAchievementModal(discord.ui.Modal, title="Удалить достижение"):
    ach_id = discord.ui.TextInput(label="ID достижения", placeholder="first_craft", required=True)
    confirm = discord.ui.TextInput(label="Введите ДА", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.confirm.value.strip().upper() != "ДА":
            await interaction.followup.send("❌ Отменено.", ephemeral=True)
            return
        ach_id = self.ach_id.value.strip()
        async with bot.db.execute("SELECT name FROM achievements WHERE id = ?", (ach_id,)) as c:
            item = await c.fetchone()
        if not item:
            await interaction.followup.send("❌ Достижение не найдено.", ephemeral=True)
            return
        await bot.db.execute("DELETE FROM achievements WHERE id = ?", (ach_id,))
        await bot.db.execute("DELETE FROM player_achievements WHERE achievement_id = ?", (ach_id,))
        await bot.db.commit()
        await interaction.followup.send(f"🗑️ Достижение «{item[0]}» удалено.", ephemeral=True)


class AddAchievementModal(discord.ui.Modal, title="Добавить достижение"):
    ach_id = discord.ui.TextInput(label="ID (латиницей)", placeholder="my_ach", required=True)
    name = discord.ui.TextInput(label="Название", placeholder="Моё достижение", required=True)
    desc = discord.ui.TextInput(label="Описание", placeholder="Сделай что-то", required=True)
    reward = discord.ui.TextInput(label="Награда (гемы)", default="10", required=True)
    emoji = discord.ui.TextInput(label="Эмодзи", default="🏆", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ach_id = self.ach_id.value.strip()
        if not ach_id.replace("_", "").isalnum() or ach_id != ach_id.lower():
            await interaction.followup.send("❌ ID: латиница в нижнем регистре и `_`.", ephemeral=True)
            return
        async with bot.db.execute("SELECT 1 FROM achievements WHERE id = ?", (ach_id,)) as c:
            if await c.fetchone():
                await interaction.followup.send("❌ Достижение с таким ID уже существует.", ephemeral=True)
                return
        try:
            reward = int(self.reward.value)
        except ValueError:
            await interaction.followup.send("❌ Награда должна быть числом.", ephemeral=True)
            return
        await bot.db.execute(
            "INSERT INTO achievements (id, name, description, reward_gems, emoji) VALUES (?, ?, ?, ?, ?)",
            (ach_id, self.name.value.strip(), self.desc.value.strip(), reward, self.emoji.value.strip())
        )
        await bot.db.commit()
        await interaction.followup.send(f"✅ Достижение «{self.name.value}» добавлено.", ephemeral=True)


class SettingsAdminRoleModal(discord.ui.Modal, title="Роль администратора"):
    role_id = discord.ui.TextInput(
        label="ID роли (0 — сбросить)",
        placeholder="123456789012345678",
        required=True
    )

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        try:
            role_id = int(self.role_id.value)
            if role_id < 0:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ ID роли должен быть числом >= 0.", ephemeral=True)
            return

        if role_id == 0:
            await save_setting(guild_id, "admin_role_id", None)
            await interaction.followup.send("✅ Роль админа сброшена.", ephemeral=True)
            return

        guild = interaction.guild
        role = guild.get_role(role_id) if guild else None
        if not role:
            await interaction.followup.send(f"❌ Роль с ID `{role_id}` не найдена.", ephemeral=True)
            return

        await save_setting(guild_id, "admin_role_id", role_id)
        await interaction.followup.send(
            f"✅ Роль <@&{role_id}> теперь имеет доступ к `/админ_панель`.\n"
            f"Внимание: владелец сервера и Discord-админы сохраняют доступ.",
            ephemeral=True
        )


class SettingsEmojisView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        placeholder="Что изменить?",
        options=[
            discord.SelectOption(label=name, value=key, emoji=default)
            for key, (name, default) in EMOJI_KEYS.items()
        ],
        row=0
    )
    async def emoji_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        key = select.values[0]
        await interaction.response.send_modal(EditEmojiModal(self.author_id, key))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🔧 Настройки сервера", color=0x808080)
        await interaction.edit_original_response(embed=embed, view=SettingsView(self.author_id))


class EditEmojiModal(discord.ui.Modal, title="Изменить эмодзи"):
    emoji = discord.ui.TextInput(label="Новый эмодзи", placeholder="🏰", required=True)

    def __init__(self, author_id: int, key: str):
        super().__init__()
        self.author_id = author_id
        self.key = key
        name, _ = EMOJI_KEYS.get(key, (key, ""))
        self.title = f"Изменить эмодзи — {name}"

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        settings = await get_settings(guild_id)
        custom = settings["custom_emojis"]
        custom[self.key] = self.emoji.value.strip()
        await save_setting(guild_id, "custom_emojis", custom)
        name, _ = EMOJI_KEYS.get(self.key, (self.key, ""))
        await interaction.followup.send(
            f"✅ {name}: {self.emoji.value}", ephemeral=True
        )


# ============================================================
#  🚪 КОМАНДЫ
# ============================================================

@bot.tree.command(name="меню", description="Открыть главное меню замка")
async def main_menu(interaction: discord.Interaction):
    embed = await build_main_embed(interaction)
    view = MainMenuView(interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="админ_панель", description="Панель администратора")
async def admin_panel(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)
    admin_role_id = settings["admin_role_id"]

    is_owner = interaction.guild and interaction.guild.owner_id == interaction.user.id
    is_discord_admin = interaction.user.guild_permissions.administrator
    is_admin_role = False
    if admin_role_id and interaction.guild:
        member = interaction.guild.get_member(interaction.user.id)
        if member:
            is_admin_role = any(r.id == admin_role_id for r in member.roles)

    if not (is_owner or is_discord_admin or is_admin_role):
        return await interaction.response.send_message(
            "❌ У тебя нет доступа к админ-панели.\n"
            "Попроси администратора выдать роль или настроить её в `/админ_панель` → Настройки → Роль админа.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="🛡️ Панель администратора",
        description="Выбери действие кнопками ниже.",
        color=0xe74c3c
    )
    view = AdminPanelView(interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ============================================================
#  🚀 ЗАПУСК
# ============================================================

if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN", "ТВОЙ_ТОКЕН")
    bot.run(token)
