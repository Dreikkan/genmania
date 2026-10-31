# ============================================================
#  🏰 Gen Mania — Discord Bot (финальная версия)
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
import re
import sqlite3
from pathlib import Path
import asyncio

# ============================================================
#  📦 КОНСТАНТЫ
# ============================================================

DEFAULT_BOT_NAME = "Gen Mania"
DEFAULT_CURRENCY_COINS = "монеты"
DEFAULT_CURRENCY_GEMS = "гемы"
DEFAULT_GEM_CAP = 6
DEFAULT_START_COINS = 3
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
    "basic_gen":      "copper_gen",
    "copper_gen":     "bronze_gen",
    "bronze_gen":     "iron_gen",
    "iron_gen":       "steel_gen",
    "steel_gen":      "silver_gen",
    "silver_gen":     "gold_gen",
    "gold_gen":       "platinum_gen",
    "platinum_gen":   "emerald_gen",
    "emerald_gen":    "ruby_gen",
    "ruby_gen":       "sapphire_gen",
    "sapphire_gen":   "diamond_gen",
    "diamond_gen":    "crystal_gen",
    "crystal_gen":    "mithril_gen",
    "mithril_gen":    "adamantite_gen",
    "adamantite_gen": "obsidian_gen",
    "obsidian_gen":   "dragon_gen",
    "dragon_gen":     "sky_gen",
    "sky_gen":        "star_gen",
    "star_gen":       "cosmic_gen",
    "cosmic_gen":     "galaxy_gen",
    "galaxy_gen":     "nebula_gen",
    "nebula_gen":     "quantum_gen",
    "quantum_gen":    "plasma_gen",
    "plasma_gen":     "dark_gen",
    "dark_gen":       "light_gen",
    "light_gen":      "time_gen",
    "time_gen":       "space_gen",
}

CRAFT_COST = 5

CRAFT_SETTINGS = {
    "basic_gen":      {"chance": 1.00, "gems": 0},
    "copper_gen":     {"chance": 1.00, "gems": 0},
    "bronze_gen":     {"chance": 0.95, "gems": 0},
    "iron_gen":       {"chance": 0.90, "gems": 0},
    "steel_gen":      {"chance": 0.85, "gems": 2},
    "silver_gen":     {"chance": 0.80, "gems": 3},
    "gold_gen":       {"chance": 0.75, "gems": 5},
    "platinum_gen":   {"chance": 0.70, "gems": 8},
    "emerald_gen":    {"chance": 0.65, "gems": 12},
    "ruby_gen":       {"chance": 0.60, "gems": 18},
    "sapphire_gen":   {"chance": 0.55, "gems": 25},
    "diamond_gen":    {"chance": 0.50, "gems": 35},
    "crystal_gen":    {"chance": 0.45, "gems": 50},
    "mithril_gen":    {"chance": 0.40, "gems": 70},
    "adamantite_gen": {"chance": 0.35, "gems": 100},
    "obsidian_gen":   {"chance": 0.30, "gems": 150},
    "dragon_gen":     {"chance": 0.28, "gems": 200},
    "sky_gen":        {"chance": 0.26, "gems": 250},
    "star_gen":       {"chance": 0.24, "gems": 300},
    "cosmic_gen":     {"chance": 0.22, "gems": 350},
    "galaxy_gen":     {"chance": 0.20, "gems": 400},
    "nebula_gen":     {"chance": 0.18, "gems": 450},
    "quantum_gen":    {"chance": 0.16, "gems": 500},
    "plasma_gen":     {"chance": 0.14, "gems": 600},
    "dark_gen":       {"chance": 0.12, "gems": 700},
    "light_gen":      {"chance": 0.10, "gems": 800},
    "time_gen":       {"chance": 0.08, "gems": 1000},
}

STAR_UPGRADE = {
    1: {"copies": 2, "chance": 1.00, "gems": 0},
    2: {"copies": 3, "chance": 0.90, "gems": 0},
    3: {"copies": 4, "chance": 0.75, "gems": 5},
    4: {"copies": 5, "chance": 0.60, "gems": 15},
    5: {"copies": 6, "chance": 0.45, "gems": 40},
}

STAR_BONUS = {
    0: 0.00,
    1: 1.10,
    2: 2.30,
    3: 3.60,
    4: 5.00,
    5: 6.50,
}

CATALYST_PRICE = 10
CATALYST_BONUS = 0.15
SELL_RATE = 0.35
START_GRID = 9
STORAGE_SIZE = 36
PAGE_SIZE = 10
SHOP_SELECT_PAGE_SIZE = 10
SLOT_WIDTH = 8

COINS_PER_GEM = 12
GEMS_PER_COIN_RATE = 9
GEM_EXCHANGE_MIN = 1
COIN_EXCHANGE_MIN = 12

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

CUSTOM_EMOJI_RE = re.compile(r"^<a?:[a-zA-Z0-9_]+:(\d+)>$")

# Сюжетные квесты: id -> (название, описание, цель, тип действия, награда гемами)
STORY_QUESTS = {
    "q_first_gen": ("Первые шаги", "Купи первый генератор", 1, "buy", 10),
    "q_synth_1": ("Алхимик", "Сделай первый синтез", 1, "synthesize", 15),
    "q_stars_1": ("Звездочёт", "Улучши любой генератор до 1★", 1, "stars", 20),
    "q_gold": ("Золотая лихорадка", "Накопи 1000 монет", 1000, "coins", 25),
    "q_raid_1": ("Завоеватель", "Соверши успешный рейд", 1, "raid_win", 30),
}

# Титулы: id -> (название, требование для открытия)
TITLES = {
    "novice": ("Новичок", "Доступен всем"),
    "builder": ("Строитель", "Купи 10 генераторов"),
    "alchemist": ("Алхимик", "Сделай 10 синтезов"),
    "star_lord": ("Звёздный лорд", "Получи 5★ генератор"),
    "rich": ("Богач", "Накопи 10,000 монет"),
    "raider": ("Рейдер", "Выиграй 5 рейдов"),
    "duelist": ("Дуэлянт", "Выиграй 10 дуэлей"),
    "collector": ("Коллекционер", "Собери 20 разных генераторов"),
}

TITLES_PER_PAGE = 25

DAILY_REWARDS = {
    1:  (10,   1,  None),
    2:  (20,   1,  None),
    3:  (30,   2,  None),
    4:  (50,   2,  None),
    5:  (80,   3,  "daily_common"),
    6:  (120,  3,  None),
    7:  (200,  5,  "daily_uncommon"),
    8:  (250,  4,  None),
    9:  (300,  5,  None),
    10: (400,  6,  "daily_rare"),
    11: (450,  6,  None),
    12: (500,  7,  None),
    13: (600,  7,  None),
    14: (700,  8,  "daily_epic"),
    15: (800,  8,  None),
    16: (900,  9,  None),
    17: (1000, 9,  None),
    18: (1100, 10, None),
    19: (1200, 10, None),
    20: (1500, 12, "daily_legendary"),
    21: (1600, 12, None),
    22: (1800, 13, None),
    23: (2000, 14, None),
    24: (2200, 15, None),
    25: (2500, 16, "daily_mythic"),
    26: (2700, 17, None),
    27: (3000, 18, None),
    28: (3300, 19, None),
    29: (3700, 20, None),
    30: (5000, 30, "daily_mythic"),
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
        # 1. Создаём папку data (если её нет)
        DATA_DIR = Path("/app/data")
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # 2. Путь к базе в персистентной папке
        DB_PATH = DATA_DIR / "castle.db"

        # 3. Подключаемся к базе в /app/data
        self.db = await aiosqlite.connect(str(DB_PATH))
        await self.db.execute("PRAGMA busy_timeout = 10000")
        await self.db.execute("PRAGMA journal_mode = WAL")

        # 4. Инициализируем таблицы
        await self.init_db()
        await self.tree.sync()

        # 5. Запускаем фоновые задачи (asyncio, а не self.loop)
        asyncio.create_task(self.auction_closer())
        asyncio.create_task(self.market_updater())
        asyncio.create_task(self.tax_collector())

    async def init_db(self):
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                coins INTEGER DEFAULT 3,
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
                stars INTEGER DEFAULT 0,
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
        try:
            await self.db.execute("ALTER TABLE items ADD COLUMN emoji_by_star TEXT DEFAULT '{}'")
        except Exception:
            pass

        for column, definition in [
            ("catalysts", "INTEGER DEFAULT 0"),
            ("last_gem_collected", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("daily_quest_date", "TEXT DEFAULT NULL"),
            ("daily_quest_progress", "TEXT DEFAULT '{}'"),
            ("daily_quest_claimed", "TEXT DEFAULT '[]'"),
            ("total_crafts", "INTEGER DEFAULT 0"),
            ("total_successes", "INTEGER DEFAULT 0"),
            ("grid_size", "INTEGER DEFAULT 9"),
            ("storage_size", "INTEGER DEFAULT 36"),
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

        try:
            await self.db.execute("ALTER TABLE inventory ADD COLUMN stars INTEGER DEFAULT 0")
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
                start_coins INTEGER DEFAULT 3,
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
            ("start_coins", "INTEGER DEFAULT 3"),
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
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS grid_shop (
                id TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                price_coins INTEGER,
                size INTEGER,
                emoji TEXT DEFAULT '📐'
            )
        """)

        grid_items = [
            ("grid_4x4", "Сетка 4×4", "Увеличивает замок до 16 слотов", 500,   16, "📐"),
            ("grid_5x5", "Сетка 5×5", "Увеличивает замок до 25 слотов", 1250,  25, "📐"),
            ("grid_6x6", "Сетка 6×6", "Увеличивает замок до 36 слотов", 1750,  36, "📐"),
        ]
        for g in grid_items:
            await self.db.execute("INSERT OR IGNORE INTO grid_shop VALUES (?, ?, ?, ?, ?, ?)", g)

        gen_names = [
            ("basic_gen",     "Базовый генератор",        "<:basic_gen:1565443870773215404>", "common",    False),
            ("copper_gen",    "Медный генератор",         "<:copper_gen:1566139443939647620>", "common",    False),
            ("bronze_gen",    "Бронзовый генератор",      "<:bronze_gen:1566139498520121474>", "common",    False),
            ("iron_gen",      "Железный генератор",       "<:iron_gen:1566139543026008237>", "uncommon",  False),
            ("steel_gen",     "Стальной генератор",       "<:steel_gen:1566139809842466987>", "uncommon",  False),
            ("silver_gen",    "Серебряный генератор",     "<:silver_gen:1566139847138214021>", "uncommon",  False),
            ("gold_gen",      "Золотой генератор",        "<:gold_gen:1566139891526406335>", "rare",      False),
            ("platinum_gen",  "Платиновый генератор",     "<:platinum_gen:1566139968206667847>", "rare",      False),
            ("emerald_gen",   "Изумрудный генератор",     "<:emerald_gen:1566140011861115110>", "rare",      False),
            ("ruby_gen",      "Рубиновый генератор",      "<:ruby_gen:1566140046841614478>", "epic",      False),
            ("sapphire_gen",  "Сапфировый генератор",     "<:sapphire_gen:1566140090718101625>", "epic",      False),
            ("diamond_gen",   "Алмазный генератор",       "<:diamond_gen:1566140148830175333>", "epic",      False),
            ("crystal_gen",   "Кристальный генератор",    "<:crystal_gen:1566140180887511181>", "legendary", False),
            ("mithril_gen",   "Мифриловый генератор",     "<:mithril_gen:1566140288580190328>", "legendary", False),
            ("adamantite_gen","Адамантитовый генератор",  "<:adamantite_gen:1566140334248038530>", "legendary", False),
            ("obsidian_gen",  "Обсидиановый генератор",   "<:obsidian_gen:1566140377021284444>", "legendary", False),
            ("dragon_gen",    "Дракониевый генератор",    "<:dragon_gen:1566140417165234387>", "mythic",    False),
            ("sky_gen",       "Небесный генератор",       "<:sky_gen:1566140479471362078>", "mythic",    False),
            ("star_gen",      "Звёздный генератор",       "<:star_gen:1566140565576351997>", "mythic",    False),
            ("cosmic_gen",    "Космический генератор",    "<:cosmic_gen:1566140610350416045>", "mythic",    False),
            ("galaxy_gen",    "Галактический генератор",  "<:galaxy_gen:1566140678885351616>", "mythic",    False),
            ("nebula_gen",    "Туманный генератор",       "<:nebula_gen:1566140723269607665>", "mythic",    False),
            ("quantum_gen",   "Квантовый генератор",      "<:quantum_gen:1566140903234478331>", "mythic",    False),
            ("plasma_gen",    "Плазменный генератор",     "<:plasma_gen:1566140951217307772>", "mythic",    False),
            ("dark_gen",      "Тёмный генератор",         "<:dark_gen:1566140996964581506>", "mythic",    False),
            ("light_gen",     "Световой генератор",       "<:light_gen:1566141131530440834>", "mythic",    False),
            ("time_gen",      "Временной генератор",      "<:time_gen:1566143974899716138>", "mythic",    False),
            ("space_gen",     "Пространственный генератор","<:space_gen:1566145585298538526>", "mythic",   True),
            ("divine_gen",    "Божественный генератор",   "<:divine_gen:1566147767296987146>", "mythic",    True),
            ("legendary_gen", "Легендарный генератор",    "<:legendary_gen:1566149699679813713>", "mythic",    True),
        ]

        star_emojis = {
            "basic_gen": {
                "0": "<:basic_gen:1565443870773215404>",
                "1": "<:basic_gen1:1566161008270114816>",
                "2": "<:basic_gen2:1566161041824555129>",
                "3": "<:basic_gen3:1566161043191758878>",
                "4": "<:basic_gen4:1566161044546650183>",
                "5": "<:basic_gen5:1566161045842821221>",
            },
            "copper_gen": {
                "0": "<:copper_gen:1566139443939647620>",
                "1": "<:copper_gen1:1566161721855447221>",
                "2": "<:copper_gen2:1566161723340357803>",
                "3": "<:copper_gen3:1566161724942581770>",
                "4": "<:copper_gen4:1566161726448205855>",
                "5": "<:copper_gen5:1566161728025141430>",
            },
            # ... для остальных 29 генераторов ...
        }

        GEM_INCOME = {
            "space_gen":     0.02,
            "divine_gen":    0.05,
            "legendary_gen": 0.10,
        }
        
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS admin_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                target_id INTEGER,
                action TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        base_price = 10
        base_income_hour = 1.5
        price = base_price
        income_hour = base_income_hour
        items_data = []
        for item_id, name, emoji, rarity, is_gem in gen_names:
            if is_gem:
                gem_income = GEM_INCOME.get(item_id, 0.02)
                items_data.append((item_id, name, int(price * 10), 0, emoji, rarity, 1, gem_income / 3600))
            else:
                items_data.append((item_id, name, int(price), income_hour / 3600, emoji, rarity, 1, 0))
            price *= 2.2
            income_hour *= 1.5

        for item in items_data:
            await self.db.execute(
                "INSERT OR IGNORE INTO items "
                "(id, name, price, income_per_hour, emoji, rarity, buyable, income_gems_per_hour) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                item
            )

        for item_id, emoji_map in star_emojis.items():
            await self.db.execute(
                "UPDATE items SET emoji_by_star = ? WHERE id = ?",
                (json.dumps(emoji_map, ensure_ascii=False), item_id)
            )
        await self.db.commit()

        achievements_data = [
            ("first_craft",   "Первый синтез",   "Сделай свой первый синтез",           5,  "⚗️"),
            ("star_1", "Первая звезда", "Улучши любой генератор до 1★", 10, "⭐"),
            ("craft_10",      "Алхимик",         "Сделай 10 синтезов",                  15, "🧪"),
            ("star_3", "Звёздный магнат", "Имей генератор с 3★", 25, "🌟"),
            ("craft_50",      "Мастер-алхимик",  "Сделай 50 синтезов",                  50, "🔮"),
            ("star_3x3", "Звёздный коллекционер", "Имей 3 генератора с 3★", 50, "💫"),
            ("success_10",    "Удачливый",       "Успешно синтезируй 10 раз",           20, "🍀"),
            ("success_50",    "Любимец фортуны", "Успешно синтезируй 50 раз",           75, "🎰"),
            ("star_5", "Легенда", "Имей генератор с 5★", 100, "🌠"),
            ("fail_5",        "Не везёт",        "Провали 5 синтезов",                  10, "💥"),
            ("first_gem_gen", "Гемовый магнат",  "Получи свой первый гемовый генератор",30, "💎"),
            ("rich_1000",     "Богач",           "Накопи 1000 монет",                   10, "🪙"),
            ("rich_10000",    "Миллионер",       "Накопи 10000 монет",                  50, "💰"),
            ("catalyst_10",   "Химик",           "Используй 10 катализаторов",          25, "🧫"),
            
        ]
        for a in achievements_data:
            await self.db.execute("INSERT OR IGNORE INTO achievements VALUES (?, ?, ?, ?, ?)", a)

        gem_items = [
            ("grid_7x7",   "Сетка 7×7",   "Увеличивает замок до 49 слотов",  100,  "📐", "upgrade", 1),
            ("grid_8x8",   "Сетка 8×8",   "Увеличивает замок до 64 слотов",  250,  "📐", "upgrade", 1),
            ("grid_9x9",   "Сетка 9×9",   "Увеличивает замок до 81 слота",   400,  "📐", "upgrade", 1),
            ("grid_10x10", "Сетка 10×10", "Увеличивает замок до 100 слотов",1000,  "📐", "upgrade", 1),
            ("vip",        "VIP",         "+15% к доходу навсегда",             100,  "⭐", "status", 1),
            ("gold",       "Gold",        "+25% к доходу навсегда",             300,  "🥇", "status", 1),
            ("platinum",   "Platinum",    "+35% к доходу навсегда",             700,  "💠", "status", 1),
            ("diamond",    "Diamond",     "+45% к доходу навсегда",            1500,  "💎", "status", 1),
        ]
        for g in gem_items:
            await self.db.execute("INSERT OR IGNORE INTO gem_shop VALUES (?, ?, ?, ?, ?, ?, ?)", g)

        await self.db.commit()

        # --- PVP И РЕЙДЫ ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS raid_parties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                leader_id INTEGER,
                member2_id INTEGER DEFAULT NULL,
                member3_id INTEGER DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS raid_cooldowns (
                user_id INTEGER PRIMARY KEY,
                last_raid_time TIMESTAMP,
                last_attacked_time TIMESTAMP
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS duel_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                winner_id INTEGER, loser_id INTEGER, bet INTEGER, type TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- КЛАНЫ ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS clans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE, leader_id INTEGER, treasury INTEGER DEFAULT 0, bonus REAL DEFAULT 0.0
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS clan_members (
                user_id INTEGER PRIMARY KEY,
                clan_id INTEGER,
                role TEXT DEFAULT 'member',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            await self.db.execute("ALTER TABLE clan_members ADD COLUMN role TEXT DEFAULT 'member'")
        except Exception:
            pass
        try:
            await self.db.execute("ALTER TABLE clan_members ADD COLUMN joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            pass

        # --- ЭКОНОМИКА ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS bank_deposits (
                user_id INTEGER PRIMARY KEY,
                amount INTEGER,
                interest_rate REAL DEFAULT 0.05,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Миграция для bank_deposits (если таблица уже была создана без start_time)
        for column, definition in [
            ("start_time", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("end_time", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("interest_rate", "REAL DEFAULT 0.05"),
        ]:
            try:
                await self.db.execute(f"ALTER TABLE bank_deposits ADD COLUMN {column} {definition}")
            except Exception:
                pass
                
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS market_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER, item_id TEXT, stars INTEGER, price INTEGER, expires_at TIMESTAMP
            )
        """)

        # --- ПРОГРЕССИЯ И КОСМЕТИКА ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS user_pets (
                user_id INTEGER PRIMARY KEY, pet_id TEXT, level INTEGER DEFAULT 1, last_fed TIMESTAMP
            )
        """)
        
        # Ежедневный вход
        try: await self.db.execute("ALTER TABLE players ADD COLUMN streak_days INTEGER DEFAULT 0")
        except Exception: pass
        try: await self.db.execute("ALTER TABLE players ADD COLUMN last_daily TIMESTAMP DEFAULT NULL")
        except Exception: pass
        try: await self.db.execute("ALTER TABLE players ADD COLUMN title TEXT DEFAULT 'Новичок'")
        except Exception: pass

        # Косметика
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS user_cosmetics (
                user_id INTEGER PRIMARY KEY,
                embed_color INTEGER DEFAULT 65280, -- 0x00ff00 (зелёный)
                bg_url TEXT DEFAULT NULL,
                castle_icon TEXT DEFAULT NULL
            )
        """)

        # Прогресс сюжетных квестов
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS player_quests (
                user_id INTEGER,
                quest_id TEXT,
                progress INTEGER DEFAULT 0,
                completed INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, quest_id)
            )
        """)

        # Добавляем эксклюзивные генераторы для 30-го дня (если их нет)
        
        daily_gens = [
            ("daily_common",    "Ежедневный лист",   "🍃", "common",    0),
            ("daily_uncommon",  "Ежедневный камень", "🪨", "uncommon",  0),
            ("daily_rare",      "Ежедневный кристалл","💠", "rare",      0),
            ("daily_epic",      "Ежедневная сфера",  "🔮", "epic",      0),
            ("daily_legendary", "Ежедневная корона", "👑", "legendary", 0),
            ("daily_mythic",    "Ежедневный феникс", "🔥", "mythic",    0),
        ]
        for item_id, name, emoji, rarity, price in daily_gens:
            await self.db.execute(
                "INSERT OR IGNORE INTO items "
                "(id, name, emoji, rarity, price, buyable, income_per_hour) "
                "VALUES (?, ?, ?, ?, ?, 0, 1.5)",
                (item_id, name, emoji, rarity, price)
            )

        # --- КЛАНЫ ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS clans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                leader_id INTEGER,
                treasury INTEGER DEFAULT 0,
                bonus REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS clan_members (
                user_id INTEGER PRIMARY KEY,
                clan_id INTEGER,
                role TEXT DEFAULT 'member',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS clan_inventory (
                clan_id INTEGER,
                slot INTEGER,
                item_id TEXT,
                stars INTEGER DEFAULT 0,
                PRIMARY KEY (clan_id, slot)
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS clan_wars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clan1_id INTEGER,
                clan2_id INTEGER,
                winner_id INTEGER,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS clan_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clan_id INTEGER,
                inviter_id INTEGER,
                target_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
                # Приглашения
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS clan_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clan_id INTEGER,
                inviter_id INTEGER,
                target_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Клановые квесты (прогресс)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS clan_quests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clan_id INTEGER,
                quest_type TEXT,
                progress INTEGER DEFAULT 0,
                target INTEGER,
                reward INTEGER,
                completed INTEGER DEFAULT 0,
                week_start TIMESTAMP
            )
        """)
        # Клановый лог (для истории)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS clan_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clan_id INTEGER,
                action TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- АУКЦИОН ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS auctions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER,
                item_id TEXT,
                stars INTEGER DEFAULT 0,
                start_price INTEGER,
                current_bid INTEGER DEFAULT 0,
                current_bidder INTEGER DEFAULT NULL,
                end_time TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS auction_bids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auction_id INTEGER,
                bidder_id INTEGER,
                amount INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- БИРЖА (рыночные цены) ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS market_prices (
                item_id TEXT PRIMARY KEY,
                base_price INTEGER,
                current_price INTEGER,
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                demand INTEGER DEFAULT 0,
                supply INTEGER DEFAULT 0
            )
        """)

        # --- БАНК ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS bank_deposits (
                user_id INTEGER PRIMARY KEY,
                amount INTEGER,
                interest_rate REAL DEFAULT 0.05,
                start_time TIMESTAMP,
                end_time TIMESTAMP
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS bank_loans (
                user_id INTEGER PRIMARY KEY,
                amount INTEGER,
                interest_rate REAL DEFAULT 0.10,
                due_time TIMESTAMP,
                collateral_item TEXT DEFAULT NULL
            )
        """)

        # --- НАЛОГИ ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS tax_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                tax_type TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Миграции в players и guild_settings
        try:
            await self.db.execute("ALTER TABLE players ADD COLUMN last_tax_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            pass
        try:
            await self.db.execute("ALTER TABLE guild_settings ADD COLUMN tax_rate REAL DEFAULT 0.02")  # 2% в сутки
        except Exception:
            pass
        try:
            await self.db.execute("ALTER TABLE guild_settings ADD COLUMN inflation_rate REAL DEFAULT 0.0")  # 0% по умолчанию
        except Exception:
            pass
        try:
            await self.db.execute("ALTER TABLE guild_settings ADD COLUMN auction_fee REAL DEFAULT 0.05")  # 5% комиссия аукциона
        except Exception:
            pass

        async with self.db.execute("SELECT id, price FROM items WHERE buyable = 1") as c:
            items = await c.fetchall()
        for item_id, base_price in items:
            await self.db.execute(
                "INSERT OR IGNORE INTO market_prices (item_id, base_price, current_price) VALUES (?, ?, ?)",
                (item_id, base_price, base_price)
            )
        await self.db.commit()

# ---------- ФОНОВЫЕ ЗАДАЧИ ----------

    async def auction_closer(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await asyncio.sleep(300)  # 5 минут
                now = datetime.datetime.now().isoformat()
                async with self.db.execute(
                    "SELECT id, seller_id, item_id, stars, current_bid, current_bidder "
                    "FROM auctions WHERE status = 'active' AND end_time < ?",
                    (now,)
                ) as c:
                    lots = await c.fetchall()

                for lot in lots:
                    aid, seller_id, item_id, stars, current_bid, bidder = lot
                    if bidder:
                        # Передаём предмет победителю
                        async with self.db.execute(
                            "SELECT slot FROM inventory WHERE user_id = ? AND location = 'profile'",
                            (bidder,)
                        ) as c:
                            used = {r[0] for r in await c.fetchall()}
                        free = [s for s in range(36) if s not in used]
                        if free:
                            await self.db.execute(
                                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                                "VALUES (?, ?, ?, 'profile', ?)",
                                (bidder, free[0], item_id, stars)
                            )
                        # Продавцу — деньги с комиссией 5%
                        fee = int(current_bid * 0.05)
                        await self.db.execute(
                            "UPDATE players SET coins = coins + ? WHERE user_id = ?",
                            (current_bid - fee, seller_id)
                        )
                    else:
                        # Никто не купил — возвращаем предмет
                        async with self.db.execute(
                            "SELECT slot FROM inventory WHERE user_id = ? AND location = 'profile'",
                            (seller_id,)
                        ) as c:
                            used = {r[0] for r in await c.fetchall()}
                        free = [s for s in range(36) if s not in used]
                        if free:
                            await self.db.execute(
                                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                                "VALUES (?, ?, ?, 'profile', ?)",
                                (seller_id, free[0], item_id, stars)
                            )
                    await self.db.execute(
                        "UPDATE auctions SET status = 'finished' WHERE id = ?", (aid,)
                    )
                await self.db.commit()
            except Exception as e:
                print(f"[AUCTION_CLOSER] Ошибка: {e}")
                await asyncio.sleep(60)


    async def market_updater(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await asyncio.sleep(21600)  # 6 часов
                async with self.db.execute(
                    "SELECT item_id, base_price, demand, supply FROM market_prices"
                ) as c:
                    rows = await c.fetchall()

                for item_id, base, demand, supply in rows:
                    ratio = 1.0 + (demand - supply) / max(1, demand + supply) * 0.5
                    new_price = int(base * ratio)
                    new_price = max(int(base * 0.5), min(int(base * 2.0), new_price))
                    await self.db.execute(
                        "UPDATE market_prices SET current_price = ?, demand = 0, supply = 0, "
                        "last_update = ? WHERE item_id = ?",
                        (new_price, datetime.datetime.now().isoformat(), item_id)
                    )
                await self.db.commit()
            except Exception as e:
                print(f"[MARKET_UPDATER] Ошибка: {e}")
                await asyncio.sleep(300)


    async def tax_collector(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await asyncio.sleep(86400)  # 24 часа
                async with self.db.execute(
                    "SELECT user_id, coins, last_tax_time FROM players"
                ) as c:
                    players = await c.fetchall()

                now = datetime.datetime.now()
                for uid, coins, last_tax in players:
                    last = datetime.datetime.fromisoformat(last_tax) if last_tax else now
                    if (now - last).total_seconds() >= 86400:
                        tax = int(coins * 0.02)
                        if tax > 0:
                            await self.db.execute(
                                "UPDATE players SET coins = coins - ?, last_tax_time = ? WHERE user_id = ?",
                                (tax, now.isoformat(), uid)
                            )
                            await self.db.execute(
                                "INSERT INTO tax_log (user_id, amount, tax_type) VALUES (?, ?, 'daily')",
                                (uid, tax)
                            )
                await self.db.commit()
            except Exception as e:
                print(f"[TAX_COLLECTOR] Ошибка: {e}")
                await asyncio.sleep(600)



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
        "prefix": "/",
        "gem_cap": DEFAULT_GEM_CAP,
        "start_coins": DEFAULT_START_COINS,
        "passive_limit": DEFAULT_PASSIVE_LIMIT,
        "disabled_commands": [],
        "status_roles": {},
        "admin_role_id": None,
    }
    if not guild_id:
        return defaults

    await bot.db.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,))
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
        "prefix": row[4] or "/",
        "gem_cap": row[5] or DEFAULT_GEM_CAP,
        "start_coins": row[6] or DEFAULT_START_COINS,
        "passive_limit": row[7] or DEFAULT_PASSIVE_LIMIT,
        "disabled_commands": json.loads(row[8] or "[]"),
        "status_roles": json.loads(row[9] or "{}"),
        "admin_role_id": row[10],
    }

async def get_star_emoji(item_id: str, stars: int, default_emoji: str) -> str:
    """Возвращает эмодзи для генератора с учётом звёздности.
    Если в БД настроен emoji_by_star, берём оттуда. Иначе — default + звёзды."""
    async with bot.db.execute("SELECT emoji_by_star FROM items WHERE id = ?", (item_id,)) as c:
        row = await c.fetchone()
    if row and row[0]:
        try:
            emoji_map = json.loads(row[0])
            if str(stars) in emoji_map and emoji_map[str(stars)]:
                return emoji_map[str(stars)]
        except Exception:
            pass
    # Fallback: базовый эмодзи + звёзды
    if stars > 0:
        return f"{default_emoji}({stars}⭐)"
    return default_emoji

async def save_setting(guild_id: int, key: str, value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    await bot.db.execute(f"UPDATE guild_settings SET {key} = ? WHERE guild_id = ?", (value, guild_id))
    await bot.db.commit()


async def is_command_disabled(guild_id: int, command_key: str) -> bool:
    settings = await get_settings(guild_id)
    return command_key in settings["disabled_commands"]


# ============================================================
#  🧰 ОБЩИЕ ХЕЛПЕРЫ
# ============================================================

def today_str():
    return datetime.date.today().isoformat()

def is_valid_emoji(s: str) -> bool:
    s = s.strip()
    if not s: return False
    if CUSTOM_EMOJI_RE.match(s): return True
    if len(s) <= 8 and not s.isascii(): return True
    return False

def parse_emoji(emoji_str: str):
    """Возвращает discord.PartialEmoji для кастомных, или строку для юникодных."""
    m = CUSTOM_EMOJI_RE.match(emoji_str)
    if m:
        try:
            return discord.PartialEmoji(name="custom", id=int(m.group(1)))
        except:
            return None
    return emoji_str

def format_slot(emoji: str, stars: int) -> str:
    """Добавляет пробелы, не ломая кастомные эмодзи."""
    if stars > 0:
        text = f"{emoji}({stars}⭐)"
    else:
        text = emoji
    return text + "  "  # Просто 2 пробела, Discord сам выровняет картинку

def make_select(placeholder: str, options: list[discord.SelectOption], callback, row: int = 0) -> discord.ui.Select:
    select = discord.ui.Select(placeholder=placeholder, options=options, row=row)
    select.callback = callback
    return select

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
            "INSERT OR IGNORE INTO players (user_id, coins, grid_size, storage_size) VALUES (?, ?, ?, ?)",
            (user_id, start, START_GRID, STORAGE_SIZE)
        )
        await bot.db.commit()
        return START_GRID, 0.0, 0, start

    return row[0] or START_GRID, row[1] or 0.0, row[2] or 0, row[3] or 0

async def get_combat_power(user_id: int) -> int:
    """Считает боевую мощь на основе цены и звезд генераторов в замке."""
    async with bot.db.execute("""
        SELECT SUM(i.price * (1 + inv.stars * 0.5)) 
        FROM inventory inv 
        JOIN items i ON inv.item_id = i.id 
        WHERE inv.user_id = ? AND inv.location = 'profile'
    """, (user_id,)) as c:
        power = (await c.fetchone())[0] or 0
    return int(power)

async def get_clan(user_id: int):
    async with bot.db.execute(
        "SELECT c.* FROM clans c JOIN clan_members cm ON c.id = cm.clan_id WHERE cm.user_id = ?",
        (user_id,)
    ) as c:
        return await c.fetchone()

async def get_clan_members(clan_id: int):
    async with bot.db.execute(
        "SELECT user_id, role FROM clan_members WHERE clan_id = ?", (clan_id,)
    ) as c:
        return await c.fetchall()

async def get_clan_power(clan_id: int):
    async with bot.db.execute("""
        SELECT SUM(power) FROM (
            SELECT SUM(i.price * (1 + inv.stars * 0.5)) as power 
            FROM inventory inv 
            JOIN items i ON inv.item_id = i.id 
            JOIN clan_members cm ON cm.user_id = inv.user_id 
            WHERE cm.clan_id = ? AND inv.location = 'profile' 
            GROUP BY inv.user_id
        )
    """, (clan_id,)) as c:
        members_power = (await c.fetchone())[0] or 0
    async with bot.db.execute("""
        SELECT SUM(i.price * (1 + ci.stars * 0.5)) 
        FROM clan_inventory ci 
        JOIN items i ON ci.item_id = i.id 
        WHERE ci.clan_id = ?
    """, (clan_id,)) as c:
        clan_power = (await c.fetchone())[0] or 0
    return int(members_power + clan_power)

async def get_clan_role(user_id: int, clan_id: int) -> str:
    async with bot.db.execute(
        "SELECT role FROM clan_members WHERE user_id = ? AND clan_id = ?", (user_id, clan_id)
    ) as c:
        row = await c.fetchone()
    return row[0] if row else "none"

async def log_clan(clan_id: int, action: str, details: str = ""):
    await bot.db.execute(
        "INSERT INTO clan_log (clan_id, action, details) VALUES (?, ?, ?)",
        (clan_id, action, details)
    )
    await bot.db.commit()

def has_clan_permission(role: str, action: str) -> bool:
    perms = {
        "leader": ["invite", "kick", "promote", "buy", "war", "treasury", "disband"],
        "deputy": ["invite", "kick", "promote", "buy", "war", "treasury", "disband"],
        "officer": ["invite", "buy", "treasury"],
        "veteran": ["buy"],
        "member": [],
    }
    return action in perms.get(role, [])


async def get_grid_size(user_id: int) -> int:
    size, _, _, _ = await get_player_stats(user_id)
    return size


async def get_storage_size(user_id: int) -> int:
    async with bot.db.execute(
        "SELECT storage_size FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    if not row:
        return STORAGE_SIZE
    return row[0] or STORAGE_SIZE


async def get_per_second_income(user_id: int) -> tuple[float, float]:
    async with bot.db.execute(
        "SELECT income_bonus FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    bonus = (row[0] if row else 0.0) or 0.0
    multiplier = 1 + bonus
        # Клановый бонус
    clan = await get_clan(user_id)
    if clan:
        clan_bonus = clan[4] or 0.0
        multiplier *= (1 + clan_bonus)

    async with bot.db.execute("""
        SELECT inv.stars, i.income_per_hour, i.income_gems_per_hour
        FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'profile'
    """, (user_id,)) as c:
        rows = await c.fetchall()

    per_sec_coins_raw = 0.0
    per_sec_gems_raw = 0.0
    for stars, inc_coins, inc_gems in rows:
        star_mult = 1 + STAR_BONUS.get(stars, 0)
        per_sec_coins_raw += inc_coins * star_mult
        per_sec_gems_raw += inc_gems * star_mult

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

    async with bot.db.execute("""
        SELECT inv.stars, i.income_per_hour, i.income_gems_per_hour
        FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'profile'
    """, (user_id,)) as c:
        rows = await c.fetchall()

    per_sec_coins = 0.0
    per_sec_gems = 0.0
    for stars, inc_coins, inc_gems in rows:
        star_mult = 1 + STAR_BONUS.get(stars, 0)
        per_sec_coins += inc_coins * star_mult
        per_sec_gems += inc_gems * star_mult

    now = datetime.datetime.now()

    # --- ШТРАФ ЗА ОФЛАЙН ---
    # Если игрок не заходил больше 2 часов, доход за время сверх 2 часов
    # умножается на 0.7 (режется на 30%)
    def apply_offline_penalty(seconds: float) -> float:
        if seconds <= 7200:  # 2 часа
            return 1.0  # без штрафа
        offline_seconds = seconds - 7200
        # Штраф применяется только к офлайн-части
        effective_seconds = 7200 + offline_seconds * 0.7
        return effective_seconds / seconds

    # --- МОНЕТЫ ---
    coins = 0
    if per_sec_coins > 0:
        last = datetime.datetime.fromisoformat(last_coins_str)
        seconds = (now - last).total_seconds()
        penalty = apply_offline_penalty(seconds)
        coins = min(int(seconds * per_sec_coins * multiplier * penalty), passive_limit)

    # --- ГЕМЫ ---
    gems = 0
    if per_sec_gems > 0:
        last = datetime.datetime.fromisoformat(last_gems_str)
        seconds = (now - last).total_seconds()
        penalty = apply_offline_penalty(seconds)
        raw = seconds * per_sec_gems * multiplier * penalty
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
    await update_story_quests(user_id, "coins", coins_earned)
    await update_story_quests(user_id, "collect_income", 1)


async def place_items(user_id: int, item_id: str, quantity: int) -> tuple[int, int]:
    grid_size = await get_grid_size(user_id)
    storage_size = await get_storage_size(user_id)

    async with bot.db.execute(
        "SELECT slot FROM inventory WHERE user_id = ? AND location = 'profile'", (user_id,)
    ) as c:
        used_profile = {r[0] for r in await c.fetchall()}
    free_profile = [s for s in range(grid_size) if s not in used_profile]

    async with bot.db.execute(
        "SELECT slot FROM inventory WHERE user_id = ? AND location = 'storage'", (user_id,)
    ) as c:
        used_storage = {r[0] for r in await c.fetchall()}
    free_storage = [s for s in range(storage_size) if s not in used_storage]

    total_free = len(free_profile) + len(free_storage)
    if total_free < quantity:
        raise ValueError(f"Не хватает места: свободно {total_free}, нужно {quantity}.")

    to_profile = min(quantity, len(free_profile))
    to_storage = quantity - to_profile

    for i in range(to_profile):
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) VALUES (?, ?, ?, 'profile', 0)",
            (user_id, free_profile[i], item_id)
        )
    for i in range(to_storage):
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) VALUES (?, ?, ?, 'storage', 0)",
            (user_id, free_storage[i], item_id)
        )
    await bot.db.commit()
    return to_profile, to_storage


async def sort_inventory(user_id: int, location: str):
    async with bot.db.execute("""
        SELECT inv.slot, inv.item_id, inv.stars, i.price
        FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = ?
        ORDER BY i.price DESC, inv.stars DESC
    """, (user_id, location)) as c:
        rows = await c.fetchall()

    if not rows:
        return

    await bot.db.execute(
        "DELETE FROM inventory WHERE user_id = ? AND location = ?",
        (user_id, location)
    )

    for new_slot, (_, item_id, stars, _) in enumerate(rows):
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) VALUES (?, ?, ?, ?, ?)",
            (user_id, new_slot, item_id, location, stars)
        )
    await bot.db.commit()

async def sort_inventory_by(user_id: int, location: str, sort_type: str):
    """Сортирует инвентарь по выбранному критерию."""
    # Получаем все предметы
    async with bot.db.execute("""
        SELECT inv.slot, inv.item_id, inv.stars, i.price, i.income_per_hour, i.rarity
        FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = ?
    """, (user_id, location)) as c:
        rows = await c.fetchall()

    if not rows:
        return

    rarity_order = {"common": 1, "uncommon": 2, "rare": 3, "epic": 4, "legendary": 5, "mythic": 6}

    if sort_type == "price_desc":
        rows.sort(key=lambda r: r[3], reverse=True)
    elif sort_type == "price_asc":
        rows.sort(key=lambda r: r[3])
    elif sort_type == "stars_desc":
        rows.sort(key=lambda r: (r[2], r[3]), reverse=True)
    elif sort_type == "stars_asc":
        rows.sort(key=lambda r: (r[2], r[3]))
    elif sort_type == "income_desc":
        rows.sort(key=lambda r: r[4], reverse=True)
    elif sort_type == "rarity_desc":
        rows.sort(key=lambda r: (rarity_order.get(r[5], 0), r[3]), reverse=True)
    else:
        # По умолчанию: цена (убывание), затем звёзды
        rows.sort(key=lambda r: (r[3], r[2]), reverse=True)

    # Удаляем и вставляем заново
    await bot.db.execute(
        "DELETE FROM inventory WHERE user_id = ? AND location = ?",
        (user_id, location)
    )
    for new_slot, (_, item_id, stars, _, _, _) in enumerate(rows):
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) VALUES (?, ?, ?, ?, ?)",
            (user_id, new_slot, item_id, location, stars)
        )
    await bot.db.commit()

async def log_admin_action(admin_id: int, target_id: int, action: str, details: str = ""):
    await bot.db.execute(
        "INSERT INTO admin_log (admin_id, target_id, action, details) VALUES (?, ?, ?, ?)",
        (admin_id, target_id, action, details)
    )
    await bot.db.commit()

async def invite_to_clan(inviter_id: int, target_id: int) -> str:
    inviter_clan = await get_clan(inviter_id)
    if not inviter_clan:
        return "❌ Ты не в клане."
    if inviter_clan[2] != inviter_id:
        return "❌ Только лидер клана может приглашать."

    target_clan = await get_clan(target_id)
    if target_clan:
        return "❌ Этот игрок уже в клане."

    # Проверка, что приглашение не дублируется
    async with bot.db.execute(
        "SELECT 1 FROM clan_invites WHERE clan_id = ? AND target_id = ?",
        (inviter_clan[0], target_id)
    ) as c:
        if await c.fetchone():
            return "❌ Приглашение уже отправлено."

    await bot.db.execute(
        "INSERT INTO clan_invites (clan_id, inviter_id, target_id) VALUES (?, ?, ?)",
        (inviter_clan[0], inviter_id, target_id)
    )
    await bot.db.commit()
    return f"✅ Приглашение отправлено <@{target_id}>."

async def update_story_quests(user_id: int, action_type: str, amount: int = 1):
    """Обновляет прогресс сюжетных квестов при действиях."""
    async with bot.db.execute("SELECT quest_id, progress FROM player_quests WHERE user_id = ?", (user_id,)) as c:
        rows = await c.fetchall()
    progress_map = {r[0]: r[1] for r in rows}

    for qid, (name, desc, target, q_type, reward) in STORY_QUESTS.items():
        if q_type != action_type:
            continue
        current = progress_map.get(qid, 0)
        if current >= target:
            continue

        new_val = min(current + amount, target)
        await bot.db.execute(
            "INSERT INTO player_quests (user_id, quest_id, progress, completed) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, quest_id) DO UPDATE SET progress = ?, completed = ?",
            (user_id, qid, new_val, int(new_val >= target), new_val, int(new_val >= target))
        )
        # Если квест только что выполнен — даём награду
        if new_val >= target and current < target:
            await bot.db.execute("UPDATE players SET gems = gems + ? WHERE user_id = ?", (reward, user_id))
    await bot.db.commit()

async def claim_daily(user_id: int) -> dict:
    async with bot.db.execute(
        "SELECT last_daily, streak_days FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    if not row:
        return {"ok": False, "reason": "Профиль не найден."}

    last_daily, streak = row
    now = datetime.datetime.now()
    today = now.date()

    if last_daily:
        last_date = datetime.datetime.fromisoformat(last_daily).date()
        delta = (today - last_date).days
        if delta == 0:
            return {"ok": False, "reason": "Ты уже забирал награду сегодня. Возвращайся завтра!"}
        new_streak = min(streak + 1, 30) if delta == 1 else 1
    else:
        new_streak = 1

    coins, gems, item_id = DAILY_REWARDS[new_streak]

    await bot.db.execute(
        "UPDATE players SET coins = coins + ?, gems = gems + ?, "
        "last_daily = ?, streak_days = ? WHERE user_id = ?",
        (coins, gems, now.isoformat(), new_streak, user_id)
    )
    await bot.db.commit()

    item_name = None
    if item_id:
        try:
            await place_items(user_id, item_id, 1)
            async with bot.db.execute("SELECT name FROM items WHERE id = ?", (item_id,)) as c:
                r = await c.fetchone()
                item_name = r[0] if r else item_id
        except ValueError:
            item_name = f"{item_id} (нет места — предмет потерян)"

    return {"ok": True, "day": new_streak, "coins": coins, "gems": gems,
            "item": item_name, "streak": new_streak}


async def get_unlocked_titles(user_id: int) -> set:
    async with bot.db.execute("""
        SELECT 
            (SELECT COUNT(*) FROM inventory WHERE user_id = ? AND location = 'profile') AS gens,
            (SELECT COUNT(*) FROM inventory WHERE user_id = ? AND location = 'profile' AND stars >= 5) AS five_star,
            (SELECT COUNT(DISTINCT item_id) FROM inventory WHERE user_id = ? AND location = 'profile') AS distinct_gens,
            (SELECT total_crafts FROM players WHERE user_id = ?) AS crafts,
            (SELECT coins FROM players WHERE user_id = ?) AS coins
    """, (user_id, user_id, user_id, user_id, user_id)) as c:
        row = await c.fetchone()
    gens, five_star, distinct_gens, crafts, coins = row or (0,)*5

    async with bot.db.execute(
        "SELECT progress FROM player_quests WHERE user_id = ? AND quest_id = 'q_raid_1'", (user_id,)
    ) as c:
        r = await c.fetchone()
        raid_wins = r[0] if r else 0

    async with bot.db.execute(
        "SELECT COUNT(*) FROM duel_history WHERE winner_id = ?", (user_id,)
    ) as c:
        duel_wins = (await c.fetchone())[0] or 0

    unlocked = {"novice"}
    if gens >= 10: unlocked.add("builder")
    if crafts >= 10: unlocked.add("alchemist")
    if five_star >= 1: unlocked.add("star_lord")
    if coins >= 10000: unlocked.add("rich")
    if raid_wins >= 5: unlocked.add("raider")
    if duel_wins >= 10: unlocked.add("duelist")
    if distinct_gens >= 20: unlocked.add("collector")
    return unlocked
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

    # Считаем звёздные достижения
    async with bot.db.execute("""
        SELECT 
            MAX(stars) AS max_stars,
            SUM(CASE WHEN stars >= 3 THEN 1 ELSE 0 END) AS stars_3_count,
            SUM(CASE WHEN stars >= 1 THEN 1 ELSE 0 END) AS stars_1_count
        FROM inventory
        WHERE user_id = ? AND location = 'profile'
    """, (user_id,)) as c:
        star_row = await c.fetchone()

    max_stars = star_row[0] or 0
    stars_3_count = star_row[1] or 0
    stars_1_count = star_row[2] or 0

    async with bot.db.execute(
        "SELECT achievement_id FROM player_achievements WHERE user_id = ?", (user_id,)
    ) as c:
        unlocked = {r[0] for r in await c.fetchall()}

    async with bot.db.execute(
        "SELECT COALESCE(SUM(catalyst_used), 0) FROM craft_log WHERE user_id = ?", (user_id,)
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
        "star_1":    stars_1_count >= 1,
        "star_3":    max_stars >= 3,
        "star_3x3":  stars_3_count >= 3,
        "star_5":    max_stars >= 5,
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
    if quest_id not in progress or quest_id in claimed:
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

    custom = settings["custom_emojis"]
    coin = custom.get("_coin", "🪙")
    gem = custom.get("_gem", "💎")
    castle = custom.get("_castle", "🏰")

    parts = []
    if per_sec_coins > 0:
        parts.append(f"{coin} {per_sec_coins * 3600:.2f}/час ({per_sec_coins:.4f}/сек)")
    if per_sec_gems > 0:
        parts.append(f"{gem} {per_sec_gems * 3600:.4f}/час ({per_sec_gems:.5f}/сек)")
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
        SELECT inv.slot, i.id, i.emoji, inv.stars FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'profile'
    """, (user_id,)) as c:
        rows = await c.fetchall()

    custom = settings["custom_emojis"]
    items = {}
    for slot, item_id, default_emoji, stars in rows:
        emoji = custom.get(item_id, default_emoji)
        emoji = await get_star_emoji(item_id, stars, emoji)
        items[slot] = emoji

    coin = custom.get("_coin", "🪙")
    gem = custom.get("_gem", "💎")
    castle = custom.get("_castle", "🏰")

    per_sec_coins, per_sec_gems = await get_per_second_income(user_id)
    parts = []
    if per_sec_coins > 0:
        parts.append(f"{coin} {per_sec_coins * 3600:.2f}/час ({per_sec_coins:.4f}/сек)")
    if per_sec_gems > 0:
        parts.append(f"{gem} {per_sec_gems * 3600:.4f}/час ({per_sec_gems:.5f}/сек)")
    income_str = " | ".join(parts) if parts else "нет генераторов"

    width = int(grid_size ** 0.5)
    embed = discord.Embed(title=f"{castle} Замок {interaction.user.name}", color=0x00ff00)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.add_field(name="Кошелёк", value=f"{coin} {coins} | {gem} {gems}", inline=False)
    embed.add_field(name="Доход", value=income_str, inline=False)
    embed.add_field(name="Бонус", value=f"+{int(bonus * 100)}%", inline=True)
    embed.add_field(name="Сетка", value=f"{width}x{width}", inline=True)

    # Выводим сетку по рядам (каждый ряд — отдельное Inline-поле)
    for row_idx in range(width):
        row_items = []
        for col_idx in range(width):
            slot = row_idx * width + col_idx
            row_items.append(items.get(slot, "⬛"))
        
        # Соединяем ячейки пробелами
        row_str = "  ".join(row_items)
        embed.add_field(name="\u200b", value=row_str, inline=False)

    return embed


async def build_storage_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)
    grid_size = await get_storage_size(user_id)

    async with bot.db.execute("""
        SELECT inv.slot, i.id, i.emoji, inv.stars FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'storage'
    """, (user_id,)) as c:
        rows = await c.fetchall()

    custom = settings["custom_emojis"]
    items = {}
    for slot, item_id, default_emoji, stars in rows:
        emoji = custom.get(item_id, default_emoji)
        emoji = await get_star_emoji(item_id, stars, emoji)
        items[slot] = emoji

    storage_emoji = custom.get("_storage", "🎒")
    width = int(grid_size ** 0.5)
    embed = discord.Embed(title=f"{storage_emoji} Хранилище {interaction.user.name}", color=0x808080)

    # Выводим сетку по рядам
    for row_idx in range(width):
        row_items = []
        for col_idx in range(width):
            slot = row_idx * width + col_idx
            row_items.append(items.get(slot, "⬛"))
        
        row_str = "  ".join(row_items)
        embed.add_field(name="\u200b", value=row_str, inline=False)

    return embed


async def build_shop_page(interaction: discord.Interaction, page: int) -> tuple[discord.Embed, int]:
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)
    custom = settings["custom_emojis"]
    coin = custom.get("_coin", "🪙")
    gem = custom.get("_gem", "💎")
    shop_emoji = custom.get("_shop", "🛒")

    async with bot.db.execute(
        "SELECT id, name, price, income_per_hour, emoji, rarity, income_gems_per_hour "
        "FROM items WHERE buyable = 1 ORDER BY price ASC"
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
            inc.append(f"{coin} {income_coins * 3600:.2f}/час")
        if income_gems > 0:
            inc.append(f"{gem} {income_gems * 3600:.4f}/час")
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
    custom = (await get_settings(guild_id))["custom_emojis"]
    ach_emoji = custom.get("_achievements", "🏆")
    gem = custom.get("_gem", "💎")

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
    custom = (await get_settings(guild_id))["custom_emojis"]
    gem = custom.get("_gem", "💎")
    coin = custom.get("_coin", "🪙")
    up_emoji = custom.get("_upgrades", "💎")

    async with bot.db.execute("""
        SELECT id, name, description, price_coins as price, emoji, 'coins' as currency FROM grid_shop
        UNION ALL
        SELECT id, name, description, price_gems as price, emoji, 'gems' as currency FROM gem_shop
    """) as c:
        rows = await c.fetchall()

    order = {
        "grid_4x4": 1, "grid_5x5": 2, "grid_6x6": 3,
        "grid_7x7": 4, "grid_8x8": 5, "grid_9x9": 6, "grid_10x10": 7,
        "vip": 10, "gold": 11, "platinum": 12, "diamond": 13,
    }
    rows = sorted(rows, key=lambda r: order.get(r[0], 99))

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
    for gid, name, desc, price, emoji, currency in chunk:
        status = "✅ Куплено" if gid in owned else "🔒 Не куплено"
        price_str = f"{coin} {price}" if currency == "coins" else f"{gem} {price}"
        embed.add_field(
            name=f"{emoji} {name} (`{gid}`)",
            value=f"{desc}\nЦена: {price_str}\n{status}",
            inline=False
        )
    return embed, total_pages


async def build_quests_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    custom = (await get_settings(guild_id))["custom_emojis"]
    quest_emoji = custom.get("_quests", "📅")
    gem = custom.get("_gem", "💎")

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
    custom = (await get_settings(guild_id))["custom_emojis"]
    stats_emoji = custom.get("_stats", "📊")
    gem = custom.get("_gem", "💎")

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

async def build_user_profile_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)
    custom = settings["custom_emojis"]
    
    # Получаем данные из БД
    async with bot.db.execute("""
        SELECT coins, gems, catalysts, total_crafts, total_successes, grid_size, income_bonus
        FROM players WHERE user_id = ?
    """, (user_id,)) as c:
        row = await c.fetchone()
        
    if not row:
        return discord.Embed(title="❌ Профиль не найден", color=0xe74c3c)
        
    coins, gems, catalysts, crafts, successes, grid, bonus = row
    
    # Считаем достижения
    async with bot.db.execute("SELECT COUNT(*) FROM player_achievements WHERE user_id = ?", (user_id,)) as c:
        ach_count = (await c.fetchone())[0]
        
    # Считаем рейды/уровни и прочее (если пока нет — ставим 0)
    winrate = (successes / crafts * 100) if crafts > 0 else 0.0
    
    embed = discord.Embed(
        title=f"👤 Профиль — {interaction.user.name}",
        description="Подробная информация о твоих успехах.",
        color=0x3498db
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    async with bot.db.execute("SELECT title FROM players WHERE user_id = ?", (user_id,)) as c:
        title_row = await c.fetchone()
    title = (title_row[0] if title_row else None) or "Новичок"

    embed.add_field(name="🏅 Титул", value=title, inline=True)
    embed.add_field(name="🪙 Кошелёк", value=f"Монеты: **{coins}**\nГемы: **{gems}**\nКатализаторы: **{catalysts}**", inline=True)
    embed.add_field(name="📈 Статистика", value=f"Синтезов: **{crafts}**\nУспешных: **{successes}**\nВинрейт: **{winrate:.1f}%**", inline=True)
    
    embed.add_field(name="🏰 Замок", value=f"Сетка: **{grid}** слотов\nБонус дохода: **+{int(bonus * 100)}%**", inline=True)
    embed.add_field(name="🏆 Достижения", value=f"Открыто: **{ach_count}**", inline=True)
    embed.add_field(name="🆔 ID", value=f"`{user_id}`", inline=True)
    
    return embed

async def build_daily_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    async with bot.db.execute(
        "SELECT last_daily, streak_days FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    last_daily, streak = row if row else (None, 0)

    today = datetime.date.today()
    can_claim = True
    if last_daily:
        last_date = datetime.datetime.fromisoformat(last_daily).date()
        can_claim = (today - last_date).days >= 1
        delta = (today - last_date).days
        if delta == 0:
            next_day = streak
        elif delta == 1:
            next_day = min(streak + 1, 30)
        else:
            next_day = 1
    else:
        next_day = 1

    coins, gems, item_id = DAILY_REWARDS[next_day]
    embed = discord.Embed(
        title="📅 Ежедневный вход",
        description=(
            f"🔥 Стрик: **{streak}** / 30 дней\n"
            f"Награда за день **{next_day}**:\n"
            f"🪙 {coins} | 💎 {gems}" + (f" | 🎁 {item_id}" if item_id else "")
        ),
        color=0x3498db
    )
    days_str = ""
    for d in range(next_day, min(next_day + 7, 31)):
        c_, g_, it = DAILY_REWARDS[d]
        mark = "🎁" if it else "·"
        days_str += f"**{d}.** 🪙{c_} 💎{g_} {mark}\n"
    embed.add_field(name="Ближайшие дни", value=days_str, inline=False)
    embed.set_footer(text="Нажми «Забрать», чтобы получить награду!" if can_claim
                     else "Возвращайся завтра за следующей наградой.")
    return embed


async def build_story_quests_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    async with bot.db.execute(
        "SELECT quest_id, progress, completed FROM player_quests WHERE user_id = ?", (user_id,)
    ) as c:
        rows = await c.fetchall()
    progress_map = {r[0]: (r[1], r[2]) for r in rows}

    embed = discord.Embed(title="📜 Сюжетные квесты", color=0x9b59b6)
    for qid, (name, desc, target, q_type, reward) in STORY_QUESTS.items():
        prog, done = progress_map.get(qid, (0, 0))
        status = "✅ Выполнено" if done else f"⏳ {prog}/{target}"
        embed.add_field(
            name=name,
            value=f"{desc}\n{status} | Награда: 💎 {reward}",
            inline=False
        )
    return embed


async def build_cosmetics_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    async with bot.db.execute(
        "SELECT embed_color, bg_url, castle_icon FROM user_cosmetics WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    if not row:
        await bot.db.execute("INSERT OR IGNORE INTO user_cosmetics (user_id) VALUES (?)", (user_id,))
        await bot.db.commit()
        row = (65280, None, None)
    color, bg, icon = row
    embed = discord.Embed(
        title="🎨 Косметика",
        description="Настрой внешний вид своего профиля.",
        color=color or 0x00ff00
    )
    embed.add_field(name="Цвет эмбеда", value=f"`#{color:06X}`" if color else "по умолчанию", inline=True)
    embed.add_field(name="Фон (URL)", value=bg or "не задан", inline=True)
    embed.add_field(name="Иконка замка", value=icon or "не задана", inline=True)
    return embed


# ============================================================
#  🎛️ БАЗОВЫЙ VIEW
# ============================================================

class BaseView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 600):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Это меню открыто не тобой.", ephemeral=True)
            return False
        return True

    async def back_to_main(self, interaction: discord.Interaction):
        embed = await build_main_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=MainMenuView(self.author_id))


# ============================================================
#  🏠 ГЛАВНОЕ МЕНЮ
# ============================================================

class MainMenuView(BaseView):
    @discord.ui.button(label="Замок", emoji="🏰", style=discord.ButtonStyle.primary, row=0)
    async def tab_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))

    @discord.ui.button(label="Хранилище", emoji="🎒", style=discord.ButtonStyle.secondary, row=0)
    async def tab_storage(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await is_command_disabled(interaction.guild_id, "storage"):
            await interaction.response.send_message("❌ Хранилище отключено.", ephemeral=True)
            return
        await interaction.response.defer()
        embed = await build_storage_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=StorageView(self.author_id))

    @discord.ui.button(label="Магазин", emoji="🛒", style=discord.ButtonStyle.secondary, row=0)
    async def tab_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await is_command_disabled(interaction.guild_id, "shop"):
            await interaction.response.send_message("❌ Магазин отключён.", ephemeral=True)
            return
        await interaction.response.defer()
        embed, _ = await build_shop_page(interaction, 0)
        await interaction.edit_original_response(embed=embed, view=ShopView(self.author_id, 0))

    @discord.ui.button(label="Улучшения", emoji="💎", style=discord.ButtonStyle.secondary, row=0)
    async def tab_upgrades(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await is_command_disabled(interaction.guild_id, "upgrades"):
            await interaction.response.send_message("❌ Улучшения отключены.", ephemeral=True)
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

    @discord.ui.button(label="Квесты", emoji="📋", style=discord.ButtonStyle.primary, row=4)
    async def tab_quests_hub(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(
            title="📋 Квесты",
            description="Выбери раздел: сюжетные квесты или ежедневные задания.",
            color=0x3498db
        )
        await interaction.edit_original_response(embed=embed, view=QuestsHubView(self.author_id))

    @discord.ui.button(label="Ежедневная награда", emoji="📅", style=discord.ButtonStyle.success, row=4)
    async def tab_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_daily_embed(interaction)
        await interaction.edit_original_response(
            embed=embed, view=DailyView(self.author_id, return_to="main")
        )

    @discord.ui.button(label="Статистика", emoji="📊", style=discord.ButtonStyle.secondary, row=1)
    async def tab_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await is_command_disabled(interaction.guild_id, "stats"):
            await interaction.response.send_message("❌ Статистика отключена.", ephemeral=True)
            return
        await interaction.response.defer()
        embed = await build_stats_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=StatsView(self.author_id))

    @discord.ui.button(label="Обмен", emoji="💱", style=discord.ButtonStyle.success, row=2)
    async def tab_exchange(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(
            title="💱 Обмен валют",
            description=(
                f"Курсы (с комиссией):\n"
                f"🪙 {COINS_PER_GEM} монет → 💎 1 гем\n"
                f"💎 1 гем → 🪙 {GEMS_PER_COIN_RATE} монет\n\n"
                f"Выбери направление:"
            ),
            color=0x2ecc71
        )
        await interaction.edit_original_response(embed=embed, view=ExchangeView(self.author_id))

    @discord.ui.button(label="Экономика", emoji="📈", style=discord.ButtonStyle.success, row=3)
    async def tab_economy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="📈 Экономика", description="Выбери раздел:", color=0x3498db)
        view = EconomyView(self.author_id)
        await interaction.edit_original_response(embed=embed, view=view)

    @discord.ui.button(label="Мой профиль", emoji="👤", style=discord.ButtonStyle.primary, row=2)
    async def tab_my_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_user_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=UserProfileView(self.author_id))

    @discord.ui.button(label="Социум", emoji="⚔️", style=discord.ButtonStyle.danger, row=2)
    async def tab_social(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="⚔️ Социум", description="Выбери действие:", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=SocialView(self.author_id))

class QuestsHubView(BaseView):
    @discord.ui.button(label="Сюжетные", emoji="📜", style=discord.ButtonStyle.primary, row=0)
    async def btn_story(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_story_quests_embed(interaction)
        await interaction.edit_original_response(
            embed=embed, view=StoryQuestsView(self.author_id, return_to="quests")
        )

    @discord.ui.button(label="Ежедневные задания", emoji="📅", style=discord.ButtonStyle.success, row=0)
    async def btn_daily_tasks(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_quests_embed(interaction)
        await interaction.edit_original_response(
            embed=embed, view=QuestsView(self.author_id, return_to="quests")
        )

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_main_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=MainMenuView(self.author_id))

class SocialView(BaseView):
    @discord.ui.button(label="Рейд", emoji="🏰", style=discord.ButtonStyle.primary)
    async def btn_raid(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="⚔️ Подготовка к рейду", description="Выбери режим:", color=0xe74c3c)
        view = discord.ui.View()

        solo = discord.ui.Button(label="В одиночку", emoji="1️⃣", style=discord.ButtonStyle.secondary)
        solo.callback = lambda i: open_raid_targets(i, self.author_id, 1)
        view.add_item(solo)

        duo = discord.ui.Button(label="Группа (2 чел)", emoji="2️⃣", style=discord.ButtonStyle.secondary)
        duo.callback = lambda i: open_raid_targets(i, self.author_id, 2)
        view.add_item(duo)

        trio = discord.ui.Button(label="Группа (3 чел)", emoji="3️⃣", style=discord.ButtonStyle.secondary)
        trio.callback = lambda i: open_raid_targets(i, self.author_id, 3)
        view.add_item(trio)

        await interaction.edit_original_response(embed=embed, view=view)

    @discord.ui.button(label="Дуэль", emoji="🤺", style=discord.ButtonStyle.success)
    async def btn_duel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DuelModal(self.author_id))

    @discord.ui.button(label="Клан", emoji="🏰", style=discord.ButtonStyle.success)
    async def btn_clan(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        clan = await get_clan(self.author_id)
        if clan:
            embed = await build_clan_embed(interaction, clan)
            view = ClanMenuView(self.author_id, clan[0])
        else:
            embed = discord.Embed(
                title="🏰 Кланы",
                description="Ты не состоишь в клане.\nСоздай свой за **500 монет** или вступи в существующий.",
                color=0x3498db
            )
            view = NoClanView(self.author_id)
        await interaction.edit_original_response(embed=embed, view=view)

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_main_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=MainMenuView(self.author_id))

async def build_clan_embed(interaction, clan):
    # clan = (id, name, leader_id, treasury, bonus)  — 5 колонок
    c_id = clan[0]
    name = clan[1]
    leader_id = clan[2]
    treasury = clan[3]
    bonus = clan[4]

    members = await get_clan_members(c_id)
    power = await get_clan_power(c_id)

    embed = discord.Embed(title=f"🏰 Клан «{name}»", color=0x9b59b6)
    embed.add_field(name="Лидер", value=f"<@{leader_id}>", inline=True)
    embed.add_field(name="Участников", value=str(len(members)), inline=True)
    embed.add_field(name="Мощь клана", value=str(power), inline=True)
    embed.add_field(name="Сундук", value=f"🪙 {treasury}", inline=True)
    embed.add_field(name="Бонус к доходу", value=f"+{int(bonus*100)}%", inline=True)
    return embed

async def build_clan_inventory_embed(interaction: discord.Interaction, clan_id: int) -> discord.Embed:
    async with bot.db.execute("""
        SELECT ci.slot, i.id, i.emoji, ci.stars FROM clan_inventory ci
        JOIN items i ON ci.item_id = i.id
        WHERE ci.clan_id = ?
    """, (clan_id,)) as c:
        rows = await c.fetchall()

    items = {}
    for slot, item_id, default_emoji, stars in rows:
        emoji = await get_star_emoji(item_id, stars, default_emoji)
        items[slot] = emoji

    width = 6  # Сетка клана — 6x6
    embed = discord.Embed(title=f"🏗️ Клановая сетка", color=0x9b59b6)

    for row_idx in range(width):
        row_items = [items.get(row_idx * width + col_idx, "⬛") for col_idx in range(width)]
        embed.add_field(name="\u200b", value="  ".join(row_items), inline=False)

    return embed

class NoClanView(BaseView):
    @discord.ui.button(label="Создать клан", emoji="➕", style=discord.ButtonStyle.success)
    async def btn_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CreateClanModal(self.author_id))

    @discord.ui.button(label="Вступить", emoji="🚪", style=discord.ButtonStyle.primary)
    async def btn_join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Чтобы вступить, попроси лидера клана пригласить тебя. (Команда `/клан_пригласить`)",
            ephemeral=True
        )

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="⚔️ Социум", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=SocialView(self.author_id))

class ClanMenuView(BaseView):
    def __init__(self, author_id: int, clan_id: int):
        super().__init__(author_id)
        self.clan_id = clan_id

    async def _check(self, interaction: discord.Interaction, action: str):
        role = await get_clan_role(self.author_id, self.clan_id)
        if not has_clan_permission(role, action):
            await interaction.response.send_message("❌ Недостаточно прав.", ephemeral=True)
            return None
        return role

    @discord.ui.button(label="Пригласить", emoji="📩", style=discord.ButtonStyle.success, row=0)
    async def btn_invite(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction, "invite"):
            return
        await interaction.response.send_modal(ClanInviteModal(self.author_id, self.clan_id))

    @discord.ui.button(label="Купить для клана", emoji="🛒", style=discord.ButtonStyle.primary, row=0)
    async def btn_buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction, "buy"):
            return
        await interaction.response.defer()
        await open_clan_buy_select(interaction, self.author_id, self.clan_id, 0)

    @discord.ui.button(label="Сундук", emoji="💰", style=discord.ButtonStyle.secondary, row=0)
    async def btn_treasury(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DepositClanModal(self.author_id))

    @discord.ui.button(label="Война", emoji="🔥", style=discord.ButtonStyle.danger, row=1)
    async def btn_war(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction, "war"):
            return
        await interaction.response.defer()
        clan = await get_clan(self.author_id)
        async with bot.db.execute("SELECT id, name FROM clans WHERE id != ? ORDER BY RANDOM() LIMIT 1", (self.clan_id,)) as c:
            enemy = await c.fetchone()
        if not enemy:
            return await interaction.followup.send("❌ Нет других кланов.", ephemeral=True)
        await bot.db.execute(
            "INSERT INTO clan_wars (clan1_id, clan2_id, start_time, status) VALUES (?, ?, ?, 'active')",
            (self.clan_id, enemy[0], datetime.datetime.now().isoformat())
        )
        await bot.db.commit()
        await log_clan(self.clan_id, "war", f"Против {enemy[1]}")
        embed = discord.Embed(title="🔥 Война объявлена!", description=f"Клан против **{enemy[1]}**.", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Квесты", emoji="📜", style=discord.ButtonStyle.secondary, row=1)
    async def btn_quests(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_clan_quests_embed(self.clan_id)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Участники", emoji="👥", style=discord.ButtonStyle.secondary, row=2)
    async def btn_members(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        members = await get_clan_members(self.clan_id)
        embed = discord.Embed(title="👥 Участники клана", color=0x9b59b6)
        role_names = {
            "leader": "👑 Лидер",
            "deputy": "🥈 Заместитель",
            "officer": "🥉 Офицер",
            "veteran": "🎖️ Ветеран",
            "member": "👤 Участник",
        }
        for uid, role in members:
            # Пытаемся получить имя пользователя
            user = bot.get_user(uid)
            if user is None:
                try:
                    user = await bot.fetch_user(uid)
                except discord.NotFound:
                    user = None
                except discord.HTTPException:
                    user = None

            if user:
                display = f"**{user.name}**"
            else:
                display = f"`{uid}`"

            embed.add_field(
                name=display,
                value=role_names.get(role, role),
                inline=True
            )
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Управление", emoji="⚙️", style=discord.ButtonStyle.danger, row=2)
    async def btn_manage(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = await self._check(interaction, "kick")
        if not role:
            return
        await interaction.response.defer()
        embed = discord.Embed(title="⚙️ Управление кланом", description="Выбери действие:", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=ClanManageView(self.author_id, self.clan_id))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=3)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="⚔️ Социум", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=SocialView(self.author_id))

class ClanManageView(BaseView):
    def __init__(self, author_id: int, clan_id: int):
        super().__init__(author_id)
        self.clan_id = clan_id

    async def _check(self, interaction: discord.Interaction, action: str):
        role = await get_clan_role(self.author_id, self.clan_id)
        if not has_clan_permission(role, action):
            await interaction.response.send_message("❌ Недостаточно прав.", ephemeral=True)
            return None
        return role

    @discord.ui.button(label="Повысить", emoji="⬆️", style=discord.ButtonStyle.primary, row=0)
    async def btn_promote(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction, "promote"):
            return
        await interaction.response.send_modal(ClanRoleModal(self.author_id, self.clan_id, "promote"))

    @discord.ui.button(label="Понизить", emoji="⬇️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_demote(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction, "promote"):
            return
        await interaction.response.send_modal(ClanRoleModal(self.author_id, self.clan_id, "demote"))

    @discord.ui.button(label="Исключить", emoji="🚫", style=discord.ButtonStyle.danger, row=0)
    async def btn_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction, "kick"):
            return
        await interaction.response.send_modal(ClanKickModal(self.author_id, self.clan_id))

    @discord.ui.button(label="Передать лидерство", emoji="👑", style=discord.ButtonStyle.danger, row=1)
    async def btn_transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction, "disband"):
            return
        await interaction.response.send_modal(ClanTransferModal(self.author_id, self.clan_id))

    @discord.ui.button(label="Распустить клан", emoji="💀", style=discord.ButtonStyle.danger, row=1)
    async def btn_disband(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction, "disband"):
            return
        await interaction.response.send_modal(ClanDisbandModal(self.author_id, self.clan_id))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=2)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        clan = await get_clan(self.author_id)
        embed = await build_clan_embed(interaction, clan)
        await interaction.edit_original_response(embed=embed, view=ClanMenuView(self.author_id, self.clan_id))

class ClanInviteModal(discord.ui.Modal, title="Пригласить в клан"):
    user_id = discord.ui.TextInput(label="ID игрока", required=True)
    def __init__(self, author_id: int, clan_id: int):
        super().__init__()
        self.author_id, self.clan_id = author_id, clan_id
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target = int(self.user_id.value)
        except ValueError:
            return await interaction.followup.send("❌ Неверный ID.", ephemeral=True)
        if await get_clan(target):
            return await interaction.followup.send("❌ Игрок уже в клане.", ephemeral=True)
        async with bot.db.execute("SELECT 1 FROM clan_invites WHERE clan_id = ? AND target_id = ?", (self.clan_id, target)) as c:
            if await c.fetchone():
                return await interaction.followup.send("❌ Приглашение уже отправлено.", ephemeral=True)
        await bot.db.execute("INSERT INTO clan_invites (clan_id, inviter_id, target_id) VALUES (?, ?, ?)", (self.clan_id, self.author_id, target))
        await bot.db.commit()
        await log_clan(self.clan_id, "invite", f"<@{target}>")
        await interaction.followup.send(f"✅ Приглашение отправлено <@{target}>.", ephemeral=True)

class ClanRoleModal(discord.ui.Modal, title="Изменить роль"):
    user_id = discord.ui.TextInput(label="ID игрока", required=True)
    def __init__(self, author_id: int, clan_id: int, action: str):
        super().__init__()
        self.author_id, self.clan_id, self.action = author_id, clan_id, action
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target = int(self.user_id.value)
        except ValueError:
            return await interaction.followup.send("❌ Неверный ID.", ephemeral=True)
        async with bot.db.execute("SELECT role FROM clan_members WHERE user_id = ? AND clan_id = ?", (target, self.clan_id)) as c:
            row = await c.fetchone()
        if not row:
            return await interaction.followup.send("❌ Игрок не в клане.", ephemeral=True)
        old = row[0]
        if old == "leader":
            return await interaction.followup.send("❌ Нельзя менять роль лидера.", ephemeral=True)
        order = ["member", "veteran", "officer", "deputy"]
        if self.action == "promote":
            if old not in order or old == "deputy":
                return await interaction.followup.send("❌ Нельзя повысить.", ephemeral=True)
            new = order[order.index(old) + 1]
        else:
            if old not in order or old == "member":
                return await interaction.followup.send("❌ Нельзя понизить.", ephemeral=True)
            new = order[order.index(old) - 1]
        await bot.db.execute("UPDATE clan_members SET role = ? WHERE user_id = ? AND clan_id = ?", (new, target, self.clan_id))
        await bot.db.commit()
        await log_clan(self.clan_id, self.action, f"<@{target}>: {old} → {new}")
        await interaction.followup.send(f"✅ Роль <@{target}> изменена: {old} → {new}.", ephemeral=True)

class ClanKickModal(discord.ui.Modal, title="Исключить из клана"):
    user_id = discord.ui.TextInput(label="ID игрока", required=True)
    def __init__(self, author_id: int, clan_id: int):
        super().__init__()
        self.author_id, self.clan_id = author_id, clan_id
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target = int(self.user_id.value)
        except ValueError:
            return await interaction.followup.send("❌ Неверный ID.", ephemeral=True)
        role = await get_clan_role(target, self.clan_id)
        if role == "leader":
            return await interaction.followup.send("❌ Нельзя исключить лидера.", ephemeral=True)
        await bot.db.execute("DELETE FROM clan_members WHERE user_id = ? AND clan_id = ?", (target, self.clan_id))
        await bot.db.commit()
        await log_clan(self.clan_id, "kick", f"<@{target}>")
        await interaction.followup.send(f"✅ <@{target}> исключён из клана.", ephemeral=True)

class ClanTransferModal(discord.ui.Modal, title="Передать лидерство"):
    user_id = discord.ui.TextInput(label="ID нового лидера", required=True)
    confirm = discord.ui.TextInput(label="Введите ДА", required=True)
    def __init__(self, author_id: int, clan_id: int):
        super().__init__()
        self.author_id, self.clan_id = author_id, clan_id
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.confirm.value.strip().upper() != "ДА":
            return await interaction.followup.send("❌ Отменено.", ephemeral=True)
        try:
            target = int(self.user_id.value)
        except ValueError:
            return await interaction.followup.send("❌ Неверный ID.", ephemeral=True)
        if await get_clan_role(target, self.clan_id) == "none":
            return await interaction.followup.send("❌ Игрок не в клане.", ephemeral=True)
        await bot.db.execute("UPDATE clan_members SET role = 'member' WHERE user_id = ? AND clan_id = ?", (self.author_id, self.clan_id))
        await bot.db.execute("UPDATE clan_members SET role = 'leader' WHERE user_id = ? AND clan_id = ?", (target, self.clan_id))
        await bot.db.execute("UPDATE clans SET leader_id = ? WHERE id = ?", (target, self.clan_id))
        await bot.db.commit()
        await log_clan(self.clan_id, "transfer", f"Лидерство → <@{target}>")
        await interaction.followup.send(f"👑 Лидерство передано <@{target}>.", ephemeral=True)

class ClanDisbandModal(discord.ui.Modal, title="Распустить клан"):
    confirm = discord.ui.TextInput(label="Введите УДАЛИТЬ", required=True)
    def __init__(self, author_id: int, clan_id: int):
        super().__init__()
        self.author_id, self.clan_id = author_id, clan_id
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.confirm.value.strip() != "УДАЛИТЬ":
            return await interaction.followup.send("❌ Отменено.", ephemeral=True)
        async with bot.db.execute("SELECT treasury FROM clans WHERE id = ?", (self.clan_id,)) as c:
            treasury = (await c.fetchone())[0]
        await bot.db.execute("UPDATE players SET coins = coins + ? WHERE user_id IN (SELECT user_id FROM clan_members WHERE clan_id = ?)", (treasury // max(1, len(await get_clan_members(self.clan_id))), self.clan_id))
        await bot.db.execute("DELETE FROM clan_inventory WHERE clan_id = ?", (self.clan_id,))
        await bot.db.execute("DELETE FROM clan_members WHERE clan_id = ?", (self.clan_id,))
        await bot.db.execute("DELETE FROM clan_invites WHERE clan_id = ?", (self.clan_id,))
        await bot.db.execute("DELETE FROM clan_quests WHERE clan_id = ?", (self.clan_id,))
        await bot.db.execute("DELETE FROM clan_wars WHERE clan1_id = ? OR clan2_id = ?", (self.clan_id, self.clan_id))
        await bot.db.execute("DELETE FROM clans WHERE id = ?", (self.clan_id,))
        await bot.db.commit()
        await interaction.followup.send("💀 Клан распущен.", ephemeral=True)

async def open_clan_buy_select(interaction: discord.Interaction, author_id: int, clan_id: int, page: int = 0):
    async with bot.db.execute("SELECT id, name, price, emoji FROM items WHERE buyable = 1 ORDER BY price ASC") as c:
        rows = await c.fetchall()
    total_pages = max(1, (len(rows) + 9) // 10)
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page*10:page*10+10]
    options = [discord.SelectOption(label=f"{name} — 🪙 {price}", value=item_id, emoji=parse_emoji(emoji)) for item_id, name, price, emoji in chunk]
    embed = discord.Embed(title="🛒 Купить для клана", description=f"Страница {page+1}/{total_pages}", color=0xf1c40f)
    await interaction.edit_original_response(embed=embed, view=ClanBuySelectView(author_id, clan_id, options, page, total_pages))

class ClanBuySelectView(discord.ui.View):
    def __init__(self, author_id: int, clan_id: int, options, page: int, total_pages: int):
        super().__init__(timeout=120)
        self.author_id, self.clan_id, self.page, self.total_pages = author_id, clan_id, page, total_pages
        self.add_item(make_select("Выбери предмет", options, self.item_select, row=0))
        if total_pages > 1:
            p = discord.ui.Button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1); p.callback = self.prev; self.add_item(p)
            n = discord.ui.Button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1); n.callback = self.next; self.add_item(n)
        b = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=2); b.callback = self.back; self.add_item(b)
    async def interaction_check(self, i): return i.user.id == self.author_id
    async def item_select(self, interaction):
        item_id = interaction.data["values"][0]
        await interaction.response.defer()
        async with bot.db.execute("SELECT name, price FROM items WHERE id = ?", (item_id,)) as c:
            name, price = await c.fetchone()
        async with bot.db.execute("SELECT coins FROM players WHERE user_id = ?", (self.author_id,)) as c:
            coins = (await c.fetchone())[0]
        if coins < price:
            return await interaction.followup.send("❌ Недостаточно монет.", ephemeral=True)
        async with bot.db.execute("SELECT slot FROM clan_inventory WHERE clan_id = ?", (self.clan_id,)) as c:
            used = {r[0] for r in await c.fetchall()}
        free = [s for s in range(36) if s not in used]
        if not free:
            return await interaction.followup.send("❌ В клановой сетке нет места.", ephemeral=True)
        await bot.db.execute("INSERT INTO clan_inventory (clan_id, slot, item_id) VALUES (?, ?, ?)", (self.clan_id, free[0], item_id))
        await bot.db.execute("UPDATE players SET coins = coins - ? WHERE user_id = ?", (price, self.author_id))
        await bot.db.commit()
        await log_clan(self.clan_id, "buy", f"{name} за {price}")
        await interaction.followup.send(f"✅ Куплено **{name}** для клана за 🪙 {price}.", ephemeral=True)
    async def prev(self, i): await i.response.defer(); await open_clan_buy_select(i, self.author_id, self.clan_id, self.page-1)
    async def next(self, i): await i.response.defer(); await open_clan_buy_select(i, self.author_id, self.clan_id, self.page+1)
    async def back(self, i):
        await i.response.defer()
        clan = await get_clan(self.author_id)
        embed = await build_clan_embed(i, clan)
        await i.edit_original_response(embed=embed, view=ClanMenuView(self.author_id, self.clan_id))

CLAN_QUESTS = [
    ("synthesize", "Сделать 20 синтезов", 20, 500),
    ("buy", "Купить 10 генераторов", 10, 300),
    ("raid", "Совершить 5 рейдов", 5, 400),
    ("war", "Выиграть войну", 1, 1000),
]

async def get_or_create_clan_quests(clan_id: int):
    week_start = datetime.date.today().isocalendar()[:2]
    async with bot.db.execute("SELECT id, quest_type, progress, target, reward, completed FROM clan_quests WHERE clan_id = ?", (clan_id,)) as c:
        rows = await c.fetchall()
    if not rows:
        for qt, desc, target, reward in CLAN_QUESTS:
            await bot.db.execute("INSERT INTO clan_quests (clan_id, quest_type, target, reward, week_start) VALUES (?, ?, ?, ?, ?)", (clan_id, qt, target, reward, str(week_start)))
        await bot.db.commit()
        async with bot.db.execute("SELECT id, quest_type, progress, target, reward, completed FROM clan_quests WHERE clan_id = ?", (clan_id,)) as c:
            rows = await c.fetchall()
    return rows

async def build_clan_quests_embed(clan_id: int):
    rows = await get_or_create_clan_quests(clan_id)
    embed = discord.Embed(title="📜 Клановые квесты", description="Недельные задания для всего клана", color=0x3498db)
    for qid, qt, prog, target, reward, completed in rows:
        desc = next(d for t, d, _, _ in CLAN_QUESTS if t == qt)
        status = "✅ Выполнено" if completed else "⏳ В процессе"
        embed.add_field(name=desc, value=f"Прогресс: {prog}/{target}\nНаграда: 🪙 {reward}\n{status}", inline=False)
    return embed

async def update_clan_quest(clan_id: int, quest_type: str, amount: int = 1):
    async with bot.db.execute("SELECT id, progress, target, reward, completed FROM clan_quests WHERE clan_id = ? AND quest_type = ?", (clan_id, quest_type)) as c:
        row = await c.fetchone()
    if not row or row[4]: return
    qid, prog, target, reward, _ = row
    prog = min(prog + amount, target)
    completed = prog >= target
    await bot.db.execute("UPDATE clan_quests SET progress = ?, completed = ? WHERE id = ?", (prog, int(completed), qid))
    if completed:
        await bot.db.execute("UPDATE clans SET treasury = treasury + ? WHERE id = ?", (reward, clan_id))
        await log_clan(clan_id, "quest_complete", f"Тип: {quest_type}, +{reward} в сундук")
    await bot.db.commit()

class CreateClanModal(discord.ui.Modal, title="Создание клана"):
    name = discord.ui.TextInput(label="Название клана", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cost = 500

        # Проверка баланса
        async with bot.db.execute("SELECT coins FROM players WHERE user_id = ?", (self.author_id,)) as c:
            row = await c.fetchone()
        coins = row[0] if row else 0
        if coins < cost:
            return await interaction.followup.send(f"❌ Нужно {cost} монет для создания клана.", ephemeral=True)

        # Проверка, что не в клане
        existing = await get_clan(self.author_id)
        if existing:
            return await interaction.followup.send("❌ Ты уже в клане.", ephemeral=True)

        # Проверка названия
        clan_name = self.name.value.strip()
        if len(clan_name) < 3 or len(clan_name) > 32:
            return await interaction.followup.send("❌ Название должно быть от 3 до 32 символов.", ephemeral=True)

        # Создание клана
        try:
            cursor = await bot.db.execute(
                "INSERT INTO clans (name, leader_id, treasury) VALUES (?, ?, 0)",
                (clan_name, self.author_id)
            )
            clan_id = cursor.lastrowid
            await bot.db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) VALUES (?, ?, 'leader')",
                (self.author_id, clan_id)
            )
            await bot.db.execute(
                "UPDATE players SET coins = coins - ? WHERE user_id = ?",
                (cost, self.author_id)
            )
            await bot.db.commit()
            await interaction.followup.send(
                f"✅ Клан **{clan_name}** создан за {cost} монет!", ephemeral=True
            )
        except Exception as e:
            await bot.db.rollback()
            await interaction.followup.send(f"❌ Ошибка: `{e}`", ephemeral=True)


class DepositClanModal(discord.ui.Modal, title="Пополнить сундук клана"):
    amount = discord.ui.TextInput(label="Сумма (монеты)", default="100", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            amt = int(self.amount.value)
            if amt <= 0: raise ValueError
        except ValueError:
            return await interaction.followup.send("❌ Неверная сумма.", ephemeral=True)

        clan = await get_clan(self.author_id)
        if not clan:
            return await interaction.followup.send("❌ Ты не в клане.", ephemeral=True)

        async with bot.db.execute("SELECT coins FROM players WHERE user_id = ?", (self.author_id,)) as c:
            coins = (await c.fetchone())[0]
        if coins < amt:
            return await interaction.followup.send("❌ Недостаточно монет.", ephemeral=True)

        await bot.db.execute("UPDATE players SET coins = coins - ? WHERE user_id = ?", (amt, self.author_id))
        await bot.db.execute("UPDATE clans SET treasury = treasury + ? WHERE id = ?", (amt, clan[0]))
        await bot.db.commit()
        await interaction.followup.send(f"✅ В сундук клана внесено 🪙 {amt}.", ephemeral=True)

async def open_raid_targets(interaction: discord.Interaction, author_id: int, group_size: int):
    await interaction.response.send_modal(RaidTargetModal(author_id, group_size))

class RaidTargetModal(discord.ui.Modal, title="Атака замка"):
    target_id = discord.ui.TextInput(label="ID игрока для атаки", required=True)

    def __init__(self, author_id: int, group_size: int):
        super().__init__()
        self.author_id = author_id
        self.group_size = group_size

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            target = int(self.target_id.value)
        except ValueError:
            return await interaction.followup.send("❌ Неверный ID.", ephemeral=True)
        
        if target == self.author_id:
            return await interaction.followup.send("❌ Нельзя атаковать себя.", ephemeral=True)

        # 1. Кулдауны
        async with bot.db.execute("SELECT last_raid_time, last_attacked_time FROM raid_cooldowns WHERE user_id = ?", (self.author_id,)) as c:
            row = await c.fetchone()
        
        now = datetime.datetime.now()
        if row:
            if row[0]:
                last_raid = datetime.datetime.fromisoformat(row[0])
                if (now - last_raid).total_seconds() < 3600: # 1 час
                    return await interaction.followup.send("❌ Кулдаун на рейд: 1 час.", ephemeral=True)
            if row[1]:
                last_attacked = datetime.datetime.fromisoformat(row[1])
                if (now - last_attacked).total_seconds() < 21600: # 6 часов
                    return await interaction.followup.send("❌ Этого игрока уже атаковали недавно (кулдаун 6 ч).", ephemeral=True)

                # 2. Мощь атакующих
        power_atk = await get_combat_power(self.author_id)
        if power_atk <= 0:
            return await interaction.followup.send(
                "❌ У тебя нет генераторов в замке. Мощь = 0. Купи генераторы в магазине.",
                ephemeral=True
            )
        # Групповой бонус: +50% за каждого дополнительного члена группы
        if self.group_size > 1:
            power_atk = int(power_atk * (1 + 0.5 * (self.group_size - 1)))

        # 3. Мощь защиты
        power_def = await get_combat_power(target)
        if power_def <= 0:
            return await interaction.followup.send(
                "❌ У цели нет генераторов. Атаковать нечего.",
                ephemeral=True
            )
            
        # 4. Расчёт (рандом с учётом мощи)
        import random
        roll_atk = random.randint(1, power_atk)
        roll_def = random.randint(1, power_def)
        
        success = roll_atk > roll_def

        # Запись кулдаунов
        await bot.db.execute("""
            INSERT INTO raid_cooldowns (user_id, last_raid_time, last_attacked_time) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_raid_time = ?, last_attacked_time = ?
        """, (self.author_id, now.isoformat(), now.isoformat(), now.isoformat(), now.isoformat()))
        
        # Ставим кулдаун на жертву
        await bot.db.execute("""
            INSERT INTO raid_cooldowns (user_id, last_attacked_time) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_attacked_time = ?
        """, (target, now.isoformat(), now.isoformat()))
        await bot.db.commit()

        if success:
            # Забираем 15% баланса
            async with bot.db.execute("SELECT coins FROM players WHERE user_id = ?", (target,)) as c:
                victim_coins = (await c.fetchone())[0]
            
            loot = int(victim_coins * 0.15)
            if loot > 0:
                await bot.db.execute("UPDATE players SET coins = coins - ? WHERE user_id = ?", (loot, target))
                await bot.db.execute("UPDATE players SET coins = coins + ? WHERE user_id = ?", (loot, self.author_id))
                await bot.db.commit()
                msg = f"🏆 **Успешный рейд!**\nТвоя мощь: {power_atk} (бросок {roll_atk})\nЗащита врага: {power_def} (бросок {roll_def})\nВы украли 🪙 **{loot}** монет!"
            else:
                msg = "🏆 Победа, но у врага пустой кошелёк."
        else:
            msg = f"💥 **Провал!**\nТвоя мощь: {power_atk} (бросок {roll_atk})\nЗащита врага: {power_def} (бросок {roll_def})\nТы ничего не украл."

        embed = discord.Embed(title="Результат рейда", description=msg, color=0x2ecc71 if success else 0xe74c3c)
        await interaction.followup.send(embed=embed)
        await update_story_quests(self.author_id, "raid_win", 1)

class DuelModal(discord.ui.Modal, title="Вызов на дуэль"):
    opponent_id = discord.ui.TextInput(label="ID противника", required=True)
    bet = discord.ui.TextInput(label="Ставка (монеты)", default="100", required=True)
    mode = discord.ui.TextInput(label="Режим (dice/power)", default="dice", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target = int(self.opponent_id.value)
            bet = int(self.bet.value)
            if bet <= 0 or target == self.author_id: raise ValueError
        except ValueError:
            return await interaction.followup.send("❌ Неверные данные.", ephemeral=True)

        mode = self.mode.value.strip().lower()
        if mode not in ("dice", "power"):
            return await interaction.followup.send("❌ Режим: dice или power.", ephemeral=True)

        async with bot.db.execute("SELECT coins FROM players WHERE user_id = ?", (self.author_id,)) as c:
            c1 = (await c.fetchone())[0]
        async with bot.db.execute("SELECT coins FROM players WHERE user_id = ?", (target,)) as c:
            row = await c.fetchone()
            c2 = row[0] if row else 0
        
        if c1 < bet or c2 < bet:
            return await interaction.followup.send("❌ У кого-то не хватает монет на ставку.", ephemeral=True)

        if mode == "dice":
            import random
            r1, r2 = random.randint(1, 100), random.randint(1, 100)
            winner = self.author_id if r1 > r2 else target
            text = f"🎲 Выпало: {r1} против {r2}"
        else:
            p1 = await get_combat_power(self.author_id)
            p2 = await get_combat_power(target)
            if p1 <= 0 or p2 <= 0:
                return await interaction.followup.send(
                    "❌ У одного из игроков нет генераторов для дуэли.",
                    ephemeral=True
                )
            winner = self.author_id if p1 > p2 else target
            text = f"⚔️ Мощь: {p1} против {p2}"

        # Перевод монет
        await bot.db.execute("UPDATE players SET coins = coins - ? WHERE user_id = ?", (bet, self.author_id))
        await bot.db.execute("UPDATE players SET coins = coins - ? WHERE user_id = ?", (bet, target))
        await bot.db.execute("UPDATE players SET coins = coins + ? WHERE user_id = ?", (bet * 2, winner))
        
        # История
        loser = target if winner == self.author_id else self.author_id
        await bot.db.execute("INSERT INTO duel_history (winner_id, loser_id, bet, type) VALUES (?, ?, ?, ?)", (winner, loser, bet, mode))
        await bot.db.commit()

        if winner == self.author_id:
            msg = f"🏆 Ты победил в дуэли!\n{text}\nЗабрал банк: 🪙 {bet * 2}."
        else:
            msg = f"💥 Ты проиграл.\n{text}\nПотерял: 🪙 {bet}."

        embed = discord.Embed(title="Результат дуэли", description=msg, color=0x2ecc71 if winner == self.author_id else 0xe74c3c)
        await interaction.followup.send(embed=embed, ephemeral=True)


class BackOnlyView(BaseView):
    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_main(interaction)

class EconomyView(BaseView):
    @discord.ui.button(label="Банк", emoji="🏦", style=discord.ButtonStyle.primary, row=0)
    async def btn_bank(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        deposit = await get_deposit(self.author_id)
        embed = discord.Embed(title="🏦 Банк", color=0x2ecc71)
        if deposit:
            amount, rate, start, end = deposit
            embed.description = (
                f"Вклад: 🪙 {amount}\n"
                f"Процент: {int(rate * 100)}%\n"
                f"Срок: до {datetime.datetime.fromisoformat(end).strftime('%d.%m %H:%M')}"
            )
            view = discord.ui.View()
            w = discord.ui.Button(label="Забрать вклад", emoji="💰", style=discord.ButtonStyle.success)
            w.callback = lambda i: i.response.send_modal(BankWithdrawModal(self.author_id))
            view.add_item(w)
        else:
            embed.description = "У тебя нет вклада. Открой его, чтобы получать проценты."
            view = discord.ui.View()
            d = discord.ui.Button(label="Открыть вклад", emoji="📥", style=discord.ButtonStyle.success)
            d.callback = lambda i: i.response.send_modal(BankDepositModal(self.author_id))
            view.add_item(d)
        b = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary)
        b.callback = lambda i: self._back(i)
        view.add_item(b)
        await interaction.edit_original_response(embed=embed, view=view)

    @discord.ui.button(label="Аукцион", emoji="🏛️", style=discord.ButtonStyle.primary, row=0)
    async def btn_auction(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        async with bot.db.execute(
            "SELECT id, item_id, stars, current_bid, end_time FROM auctions WHERE status = 'active' ORDER BY end_time ASC LIMIT 10"
        ) as c:
            lots = await c.fetchall()
        embed = discord.Embed(title="🏛️ Аукцион", color=0xf1c40f)
        if lots:
            for aid, item_id, stars, bid, end in lots:
                embed.add_field(
                    name=f"Лот #{aid}: {item_id} ({stars}★)",
                    value=f"Текущая ставка: 🪙 {bid}\nДо: {datetime.datetime.fromisoformat(end).strftime('%d.%m %H:%M')}",
                    inline=False
                )
        else:
            embed.description = "Активных лотов нет."
        view = discord.ui.View()
        s = discord.ui.Button(label="Выставить лот", emoji="📤", style=discord.ButtonStyle.success)
        s.callback = lambda i: i.response.send_modal(AuctionSellModal(self.author_id))
        view.add_item(s)
        b = discord.ui.Button(label="Ставка", emoji="💸", style=discord.ButtonStyle.primary)
        b.callback = lambda i: i.response.send_modal(AuctionBidModal(self.author_id))
        view.add_item(b)
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary)
        back.callback = lambda i: self._back(i)
        view.add_item(back)
        await interaction.edit_original_response(embed=embed, view=view)

    @discord.ui.button(label="Биржа", emoji="📈", style=discord.ButtonStyle.primary, row=1)
    async def btn_market(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        async with bot.db.execute(
            "SELECT item_id, base_price, current_price, demand, supply FROM market_prices ORDER BY ABS(current_price - base_price) DESC LIMIT 10"
        ) as c:
            rows = await c.fetchall()
        embed = discord.Embed(title="📈 Биржа (самые волатильные)", color=0x9b59b6)
        for item_id, base, current, demand, supply in rows:
            trend = "🟢" if current > base else ("🔴" if current < base else "⚪")
            embed.add_field(
                name=f"{trend} {item_id}",
                value=f"Текущая: 🪙 {current} (база {base})\nСпрос: {demand} | Предл.: {supply}",
                inline=False
            )
        b = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary)
        b.callback = lambda i: self._back(i)
        view = discord.ui.View()
        view.add_item(b)
        await interaction.edit_original_response(embed=embed, view=view)

    @discord.ui.button(label="Налоги", emoji="🏦", style=discord.ButtonStyle.danger, row=1)
    async def btn_taxes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        async with bot.db.execute(
            "SELECT amount, tax_type, timestamp FROM tax_log WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (self.author_id,)
        ) as c:
            rows = await c.fetchall()
        embed = discord.Embed(title="🏦 Налоги", description="Твои последние списания:", color=0xe74c3c)
        if rows:
            for amt, ttype, ts in rows:
                embed.add_field(name=f"`{ttype}`", value=f"🪙 {amt} | {ts}", inline=False)
        else:
            embed.description = "Налогов пока не было."
        b = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary)
        b.callback = lambda i: self._back(i)
        view = discord.ui.View()
        view.add_item(b)
        await interaction.edit_original_response(embed=embed, view=view)

    async def _back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = await build_main_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=MainMenuView(self.author_id))

async def open_titles_view(interaction: discord.Interaction, author_id: int, page: int = 0, return_to: str = "main"):
    user_id = interaction.user.id
    unlocked = await get_unlocked_titles(user_id)
    async with bot.db.execute("SELECT title FROM players WHERE user_id = ?", (user_id,)) as c:
        current = (await c.fetchone())[0] or "Новичок"

    all_titles = list(TITLES.items())
    total_pages = max(1, (len(all_titles) + TITLES_PER_PAGE - 1) // TITLES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    chunk = all_titles[page*TITLES_PER_PAGE:(page+1)*TITLES_PER_PAGE]

    options = []
    for tid, (name, req) in chunk:
        if tid not in unlocked:
            options.append(discord.SelectOption(label=f"🔒 {name}"[:100], value=tid, description=req[:100]))
        else:
            mark = "✅" if name == current else "•"
            options.append(discord.SelectOption(label=f"{mark} {name}"[:100], value=tid, description=req[:100]))

    embed = discord.Embed(
        title="🏅 Титулы",
        description=f"Текущий: **{current}**\nСтраница {page+1}/{total_pages}",
        color=0xf1c40f
    )
    await interaction.edit_original_response(
        embed=embed,
        view=TitlesView(author_id, options, page, total_pages, return_to)
    )


class TitlesView(discord.ui.View):
    def __init__(self, author_id: int, options, page: int, total_pages: int, return_to: str = "main"):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.page = page
        self.total_pages = total_pages
        self.return_to = return_to
        self.add_item(make_select("Выбери титул", options, self.select, row=0))
        if total_pages > 1:
            p = discord.ui.Button(label="◀️", style=discord.ButtonStyle.secondary, row=1)
            p.callback = self.prev; self.add_item(p)
            n = discord.ui.Button(label="▶️", style=discord.ButtonStyle.secondary, row=1)
            n.callback = self.next; self.add_item(n)
        b = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=2)
        b.callback = self.back; self.add_item(b)

    async def interaction_check(self, interaction):
        return interaction.user.id == self.author_id

    async def select(self, interaction: discord.Interaction):
        tid = interaction.data["values"][0]
        await interaction.response.defer()
        unlocked = await get_unlocked_titles(self.author_id)
        if tid not in unlocked:
            await interaction.followup.send("❌ Титул ещё не открыт.", ephemeral=True)
            return
        name = TITLES[tid][0]
        await bot.db.execute("UPDATE players SET title = ? WHERE user_id = ?", (name, self.author_id))
        await bot.db.commit()
        await interaction.followup.send(f"✅ Титул изменён на **{name}**.", ephemeral=True)

    async def prev(self, i):
        await i.response.defer()
        await open_titles_view(i, self.author_id, self.page-1, self.return_to)

    async def next(self, i):
        await i.response.defer()
        await open_titles_view(i, self.author_id, self.page+1, self.return_to)

    async def back(self, i):
        await i.response.defer()
        if self.return_to == "hub":
            embed = discord.Embed(
                title="🎨 Кастомизация",
                description="Выбери раздел: титулы, дейли, косметика, сюжетные квесты.",
                color=0x9b59b6
            )
            await i.edit_original_response(embed=embed, view=CustomizationHubView(self.author_id))
        else:
            embed = await build_main_embed(i)
            await i.edit_original_response(embed=embed, view=MainMenuView(self.author_id))

class DailyView(BaseView):
    def __init__(self, author_id: int, return_to: str = "main", timeout: int = 600):
        super().__init__(author_id, timeout)
        self.return_to = return_to

    @discord.ui.button(label="Забрать", emoji="🎁", style=discord.ButtonStyle.success, row=0)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        res = await claim_daily(interaction.user.id)
        if not res["ok"]:
            await interaction.followup.send(f"❌ {res['reason']}", ephemeral=True)
            return
        msg = f"🎉 День **{res['day']}**! Получено 🪙 {res['coins']} и 💎 {res['gems']}."
        if res["item"]:
            msg += f"\n🎁 Предмет: **{res['item']}**"
        embed = discord.Embed(title="📅 Награда получена", description=msg, color=0x2ecc71)
        await interaction.edit_original_response(embed=embed, view=DailyView(self.author_id, self.return_to))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.return_to == "hub":
            embed = discord.Embed(
                title="🎨 Кастомизация",
                description="Выбери раздел: титулы, дейли, косметика, сюжетные квесты.",
                color=0x9b59b6
            )
            await interaction.edit_original_response(embed=embed, view=CustomizationHubView(self.author_id))
        else:
            await self.back_to_main(interaction)


class StoryQuestsView(BaseView):
    def __init__(self, author_id: int, return_to: str = "main", timeout: int = 600):
        super().__init__(author_id, timeout)
        self.return_to = return_to

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.return_to == "hub":
            embed = discord.Embed(
                title="🎨 Кастомизация",
                description="Выбери раздел: титулы, дейли, косметика, сюжетные квесты.",
                color=0x9b59b6
            )
            await interaction.edit_original_response(embed=embed, view=CustomizationHubView(self.author_id))
        else:
            await self.back_to_main(interaction)


class CosmeticsView(BaseView):
    def __init__(self, author_id: int, return_to: str = "main", timeout: int = 600):
        super().__init__(author_id, timeout)
        self.return_to = return_to

    @discord.ui.button(label="Цвет", emoji="🎨", style=discord.ButtonStyle.primary, row=0)
    async def set_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CosmeticColorModal(self.author_id))

    @discord.ui.button(label="Фон", emoji="🖼️", style=discord.ButtonStyle.primary, row=0)
    async def set_bg(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CosmeticBgModal(self.author_id))

    @discord.ui.button(label="Иконка", emoji="🏰", style=discord.ButtonStyle.primary, row=0)
    async def set_icon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CosmeticIconModal(self.author_id))

    @discord.ui.button(label="Сбросить всё", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await bot.db.execute(
            "UPDATE user_cosmetics SET embed_color = 65280, bg_url = NULL, castle_icon = NULL WHERE user_id = ?",
            (self.author_id,)
        )
        await bot.db.commit()
        embed = await build_cosmetics_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=CosmeticsView(self.author_id, self.return_to))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.return_to == "hub":
            embed = discord.Embed(
                title="🎨 Кастомизация",
                description="Выбери раздел: титулы, дейли, косметика, сюжетные квесты.",
                color=0x9b59b6
            )
            await interaction.edit_original_response(embed=embed, view=CustomizationHubView(self.author_id))
        else:
            await self.back_to_main(interaction)


class CosmeticColorModal(discord.ui.Modal, title="Цвет эмбеда"):
    hex_code = discord.ui.TextInput(label="HEX (например, FF0000)", required=True, max_length=7)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        val = self.hex_code.value.strip().lstrip("#")
        try:
            color = int(val, 16)
            if not (0 <= color <= 0xFFFFFF):
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ Неверный HEX.", ephemeral=True)
            return
        await bot.db.execute(
            "UPDATE user_cosmetics SET embed_color = ? WHERE user_id = ?", (color, self.author_id)
        )
        await bot.db.commit()
        await interaction.followup.send(f"✅ Цвет `#{color:06X}` сохранён.", ephemeral=True)


class CosmeticBgModal(discord.ui.Modal, title="Фон профиля"):
    url = discord.ui.TextInput(label="URL картинки", required=True, max_length=300)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        url = self.url.value.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            await interaction.followup.send("❌ Нужен http(s)-URL.", ephemeral=True)
            return
        await bot.db.execute(
            "UPDATE user_cosmetics SET bg_url = ? WHERE user_id = ?", (url, self.author_id)
        )
        await bot.db.commit()
        await interaction.followup.send("✅ Фон сохранён.", ephemeral=True)


class CosmeticIconModal(discord.ui.Modal, title="Иконка замка"):
    emoji = discord.ui.TextInput(label="Эмодзи или <:name:id>", required=True, max_length=100)
    note = discord.ui.TextInput(label="Комментарий (необязательно)", required=False, max_length=100)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        val = self.emoji.value.strip()
        if not is_valid_emoji(val):
            await interaction.followup.send("❌ Неверный эмодзи.", ephemeral=True)
            return
        await bot.db.execute(
            "UPDATE user_cosmetics SET castle_icon = ? WHERE user_id = ?", (val, self.author_id)
        )
        await bot.db.commit()
        await interaction.followup.send("✅ Иконка сохранена.", ephemeral=True)


# ============================================================
#  💱 ОБМЕН ВАЛЮТ
# ============================================================

class ExchangeView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Монеты → Гемы", emoji="🪙", style=discord.ButtonStyle.primary, row=0)
    async def coins_to_gems(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CoinsToGemsModal(self.author_id))

    @discord.ui.button(label="Гемы → Монеты", emoji="💎", style=discord.ButtonStyle.success, row=0)
    async def gems_to_coins(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GemsToCoinsModal(self.author_id))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_main_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=MainMenuView(self.author_id))


class CoinsToGemsModal(discord.ui.Modal, title="Обмен монет на гемы"):
    amount = discord.ui.TextInput(
        label=f"Сколько монет обменять (мин. {COIN_EXCHANGE_MIN})",
        placeholder=f"Например, {COINS_PER_GEM}",
        required=True
    )

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        try:
            coins = int(self.amount.value)
            if coins < COIN_EXCHANGE_MIN:
                raise ValueError
        except ValueError:
            await interaction.followup.send(f"❌ Минимум {COIN_EXCHANGE_MIN} монет.", ephemeral=True)
            return

        gems = coins // COINS_PER_GEM
        if gems < 1:
            await interaction.followup.send(f"❌ Нужно минимум {COINS_PER_GEM} монет для 1 гема.", ephemeral=True)
            return
        spent_coins = gems * COINS_PER_GEM
        remainder = coins - spent_coins

        async with bot.db.execute("SELECT coins FROM players WHERE user_id = ?", (user_id,)) as c:
            balance = (await c.fetchone())[0]
        if balance < spent_coins:
            await interaction.followup.send(f"❌ Нужно 🪙 {spent_coins}, у тебя {balance}.", ephemeral=True)
            return

        await bot.db.execute(
            "UPDATE players SET coins = coins - ?, gems = gems + ? WHERE user_id = ?",
            (spent_coins, gems, user_id)
        )
        await bot.db.commit()

        msg = f"✅ Обменяно 🪙 {spent_coins} → 💎 {gems}."
        if remainder > 0:
            msg += f"\nОстаток {remainder} монет не обменян (нужно кратно {COINS_PER_GEM})."
        await interaction.followup.send(msg, ephemeral=True)


class GemsToCoinsModal(discord.ui.Modal, title="Обмен гемов на монеты"):
    amount = discord.ui.TextInput(
        label=f"Сколько гемов обменять (мин. {GEM_EXCHANGE_MIN})",
        placeholder="Например, 1",
        required=True
    )

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        try:
            gems = int(self.amount.value)
            if gems < GEM_EXCHANGE_MIN:
                raise ValueError
        except ValueError:
            await interaction.followup.send(f"❌ Минимум {GEM_EXCHANGE_MIN} гем.", ephemeral=True)
            return

        coins = gems * GEMS_PER_COIN_RATE

        async with bot.db.execute("SELECT gems FROM players WHERE user_id = ?", (user_id,)) as c:
            balance = (await c.fetchone())[0]
        if balance < gems:
            await interaction.followup.send(f"❌ Нужно 💎 {gems}, у тебя {balance}.", ephemeral=True)
            return

        await bot.db.execute(
            "UPDATE players SET gems = gems - ?, coins = coins + ? WHERE user_id = ?",
            (gems, coins, user_id)
        )
        await bot.db.commit()

        await interaction.followup.send(f"✅ Обменяно 💎 {gems} → 🪙 {coins}.", ephemeral=True)


# ============================================================
#  🏰 ЗАМОК
# ============================================================

class ProfileView(BackOnlyView):
    @discord.ui.button(label="Переместить", emoji="🔀", style=discord.ButtonStyle.primary, row=1)
    async def move_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await open_move_view(interaction, "profile", self.author_id)

    @discord.ui.button(label="Синтез", emoji="⚗️", style=discord.ButtonStyle.success, row=1)
    async def craft_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await open_craft_view(interaction, self.author_id)

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

    @discord.ui.button(label="Звёзды", emoji="⭐", style=discord.ButtonStyle.success, row=2)
    async def stars_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await open_star_view(interaction, self.author_id)

    @discord.ui.button(label="Поменять", emoji="↔️", style=discord.ButtonStyle.secondary, row=2)
    async def swap_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await open_swap_view(interaction, "profile", self.author_id)

    @discord.ui.button(label="Сортировка", emoji="🔄", style=discord.ButtonStyle.secondary, row=2)
    async def sort_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(
            title="🔄 Сортировка генераторов",
            description="Выбери, как упорядочить генераторы в замке:",
            color=0x3498db
        )
        await interaction.edit_original_response(embed=embed, view=SortMenuView(self.author_id))

class SortMenuView(BaseView):
    def __init__(self, author_id: int):
        super().__init__(author_id)

    async def _do_sort(self, interaction: discord.Interaction, sort_type: str):
        await interaction.response.defer()
        await sort_inventory_by(self.author_id, "profile", sort_type)
        embed = await build_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))

    @discord.ui.button(label="По цене (убыв.)", emoji="💰", style=discord.ButtonStyle.primary, row=0)
    async def sort_price_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do_sort(interaction, "price_desc")

    @discord.ui.button(label="По цене (возр.)", emoji="💸", style=discord.ButtonStyle.secondary, row=0)
    async def sort_price_asc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do_sort(interaction, "price_asc")

    @discord.ui.button(label="По звёздам (убыв.)", emoji="⭐", style=discord.ButtonStyle.success, row=1)
    async def sort_stars_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do_sort(interaction, "stars_desc")

    @discord.ui.button(label="По звёздам (возр.)", emoji="✨", style=discord.ButtonStyle.secondary, row=1)
    async def sort_stars_asc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do_sort(interaction, "stars_asc")

    @discord.ui.button(label="По доходу", emoji="📈", style=discord.ButtonStyle.success, row=2)
    async def sort_income_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do_sort(interaction, "income_desc")

    @discord.ui.button(label="По редкости", emoji="🏆", style=discord.ButtonStyle.secondary, row=2)
    async def sort_rarity_desc(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._do_sort(interaction, "rarity_desc")

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=3)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))


class StorageView(BackOnlyView):
    @discord.ui.button(label="Переместить", emoji="🔀", style=discord.ButtonStyle.primary, row=1)
    async def move_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await open_move_view(interaction, "storage", self.author_id)

    @discord.ui.button(label="Поменять", emoji="↔️", style=discord.ButtonStyle.secondary, row=1)
    async def swap_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await open_swap_view(interaction, "storage", self.author_id)

    @discord.ui.button(label="Продать", emoji="💰", style=discord.ButtonStyle.success, row=2)
    async def sell_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await open_sell_view(interaction, self.author_id)

async def open_sell_view(interaction: discord.Interaction, author_id: int, page: int = 0):
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)
    custom = settings["custom_emojis"]

    async with bot.db.execute("""
        SELECT inv.slot, inv.item_id, i.name, i.emoji, i.price, inv.stars
        FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'storage'
        ORDER BY inv.slot ASC
    """, (user_id,)) as c:
        rows = await c.fetchall()

    if not rows:
        await interaction.followup.send("❌ В хранилище нет предметов для продажи.", ephemeral=True)
        return

    total_pages = max(1, (len(rows) + SHOP_SELECT_PAGE_SIZE - 1) // SHOP_SELECT_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page * SHOP_SELECT_PAGE_SIZE: page * SHOP_SELECT_PAGE_SIZE + SHOP_SELECT_PAGE_SIZE]

    options = []
    for slot, item_id, name, default_emoji, price, stars in chunk:
        emoji_obj = parse_emoji(custom.get(item_id, default_emoji))
        sell_price = int(price * SELL_RATE)
        stars_str = f"({stars}⭐)" if stars > 0 else ""
        options.append(discord.SelectOption(
            label=f"Слот {slot}: {name} {stars_str} → 🪙 {sell_price}".strip(),
            value=f"{slot}:{item_id}",
            emoji=emoji_obj
        ))

    embed = discord.Embed(
        title="💰 Продажа предметов",
        description=f"Страница {page + 1}/{total_pages}\nЦена продажи — {int(SELL_RATE * 100)}% от магазинной.",
        color=0x2ecc71
    )
    await interaction.edit_original_response(
        embed=embed,
        view=SellSelectView(author_id, options, page, total_pages)
    )


class SellSelectView(discord.ui.View):
    def __init__(self, author_id: int, options: list[discord.SelectOption], page: int, total_pages: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.page = page
        self.total_pages = total_pages
        self.add_item(make_select("Выбери предмет", options, self.item_select, row=0))

        if total_pages > 1:
            prev = discord.ui.Button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self.prev_page
            self.add_item(prev)
            nxt = discord.ui.Button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1)
            nxt.callback = self.next_page
            self.add_item(nxt)

        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=2)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    async def item_select(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        slot_str, item_id = value.split(":", 1)
        slot = int(slot_str)
        await interaction.response.defer()

        async with bot.db.execute(
            "SELECT i.name, i.price, inv.stars FROM inventory inv "
            "JOIN items i ON inv.item_id = i.id "
            "WHERE inv.user_id = ? AND inv.location = 'storage' AND inv.slot = ?",
            (interaction.user.id, slot)
        ) as c:
            row = await c.fetchone()
        if not row:
            await interaction.followup.send("❌ Предмет не найден.", ephemeral=True)
            return

        name, price, stars = row
        sell_price = int(price * SELL_RATE)

        embed = discord.Embed(
            title="💰 Подтверждение продажи",
            description=(
                f"**{name}** {'⭐' * stars if stars > 0 else ''}\n"
                f"Цена продажи: 🪙 {sell_price}\n\n"
                f"Продать этот предмет?"
            ),
            color=0x2ecc71
        )
        await interaction.edit_original_response(
            embed=embed,
            view=SellConfirmView(self.author_id, slot, item_id, sell_price, self.page)
        )

    async def prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await open_sell_view(interaction, self.author_id, self.page - 1)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await open_sell_view(interaction, self.author_id, self.page + 1)

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = await build_storage_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=StorageView(self.author_id))


class SellConfirmView(discord.ui.View):
    def __init__(self, author_id: int, slot: int, item_id: str, price: int, page: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.slot = slot
        self.item_id = item_id
        self.price = price
        self.page = page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="Продать", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        user_id = interaction.user.id

        async with bot.db.execute(
            "SELECT 1 FROM inventory WHERE user_id = ? AND location = 'storage' AND slot = ?",
            (user_id, self.slot)
        ) as c:
            if not await c.fetchone():
                await interaction.edit_original_response(
                    embed=discord.Embed(title="❌ Ошибка", description="Предмета уже нет.", color=0xe74c3c),
                    view=StorageView(self.author_id)
                )
                return

        await bot.db.execute(
            "DELETE FROM inventory WHERE user_id = ? AND location = 'storage' AND slot = ?",
            (user_id, self.slot)
        )
        await bot.db.execute(
            "UPDATE players SET coins = coins + ? WHERE user_id = ?",
            (self.price, user_id)
        )
        await bot.db.commit()

        embed = discord.Embed(
            title="✅ Продано",
            description=f"Ты получил 🪙 **{self.price}** за предмет.",
            color=0x2ecc71
        )
        await interaction.edit_original_response(embed=embed, view=StorageView(self.author_id))

    @discord.ui.button(label="Отмена", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_storage_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=StorageView(self.author_id))


# ============================================================
#  ↔️ ОБМЕН СЛОТОВ
# ============================================================

async def open_swap_view(interaction: discord.Interaction, location: str, author_id: int):
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)
    custom = settings["custom_emojis"]

    async with bot.db.execute("""
        SELECT inv.slot, inv.item_id, i.name, i.emoji, inv.stars
        FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = ?
        ORDER BY inv.slot ASC
    """, (user_id, location)) as c:
        rows = await c.fetchall()

    if len(rows) < 2:
        await interaction.followup.send("❌ Нужно минимум 2 предмета для обмена.", ephemeral=True)
        return

    options = []
    for slot, item_id, name, default_emoji, stars in rows[:25]:
        emoji_str = custom.get(item_id, default_emoji)
        emoji_obj = parse_emoji(emoji_str)
        stars_str = f"({stars}⭐)" if stars > 0 else ""
        options.append(discord.SelectOption(
            label=f"Слот {slot}: {name} {stars_str}".strip(),
            value=str(slot),
            emoji=emoji_obj
        ))

    embed = discord.Embed(
        title="↔️ Обмен слотами",
        description="Выбери **первый** предмет для обмена:",
        color=0x3498db
    )
    await interaction.edit_original_response(
        embed=embed,
        view=SwapFirstView(author_id, location, options)
    )


class SwapFirstView(discord.ui.View):
    def __init__(self, author_id: int, location: str, options: list[discord.SelectOption]):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.location = location
        self.add_item(make_select("Выбери первый слот", options, self.first_select, row=0))
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def first_select(self, interaction: discord.Interaction):
        first_slot = int(interaction.data["values"][0])
        await interaction.response.defer()
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        custom = (await get_settings(guild_id))["custom_emojis"]

        async with bot.db.execute("""
            SELECT inv.slot, inv.item_id, i.name, i.emoji, inv.stars
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND inv.location = ? AND inv.slot != ?
            ORDER BY inv.slot ASC
        """, (user_id, self.location, first_slot)) as c:
            rows = await c.fetchall()

        options = []
        for slot, item_id, name, default_emoji, stars in rows[:25]:
            emoji_str = custom.get(item_id, default_emoji)
            emoji_obj = parse_emoji(emoji_str)
            stars_str = f"({stars}⭐)" if stars > 0 else ""
            options.append(discord.SelectOption(
                label=f"Слот {slot}: {name} {stars_str}".strip(),
                value=str(slot),
                emoji=emoji_obj
            ))

        embed = discord.Embed(
            title="↔️ Обмен слотами",
            description=f"Первый слот: **{first_slot}**.\nВыбери **второй** слот:",
            color=0x3498db
        )
        await interaction.edit_original_response(
            embed=embed,
            view=SwapSecondView(self.author_id, self.location, first_slot, options)
        )

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.location == "profile":
            embed = await build_profile_embed(interaction)
            view = ProfileView(self.author_id)
        else:
            embed = await build_storage_embed(interaction)
            view = StorageView(self.author_id)
        await interaction.edit_original_response(embed=embed, view=view)


class SwapSecondView(discord.ui.View):
    def __init__(self, author_id: int, location: str, first_slot: int, options: list[discord.SelectOption]):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.location = location
        self.first_slot = first_slot
        self.add_item(make_select("Выбери второй слот", options, self.second_select, row=0))
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def second_select(self, interaction: discord.Interaction):
        second_slot = int(interaction.data["values"][0])
        await interaction.response.defer()
        user_id = interaction.user.id
        first_slot = self.first_slot

        async with bot.db.execute(
            "SELECT item_id, stars FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
            (user_id, self.location, first_slot)
        ) as c:
            first = await c.fetchone()
        async with bot.db.execute(
            "SELECT item_id, stars FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
            (user_id, self.location, second_slot)
        ) as c:
            second = await c.fetchone()

        if not first or not second:
            await self.fail(interaction, "❌ Один из слотов пуст.")
            return

        await bot.db.execute(
            "DELETE FROM inventory WHERE user_id = ? AND location = ? AND slot IN (?, ?)",
            (user_id, self.location, first_slot, second_slot)
        )
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) VALUES (?, ?, ?, ?, ?)",
            (user_id, first_slot, second[0], self.location, second[1])
        )
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) VALUES (?, ?, ?, ?, ?)",
            (user_id, second_slot, first[0], self.location, first[1])
        )
        await bot.db.commit()

        embed = discord.Embed(
            title="✅ Слоты поменяны",
            description=f"Предметы в слотах **{first_slot}** и **{second_slot}** поменялись местами.",
            color=0x2ecc71
        )
        if self.location == "profile":
            view = ProfileView(self.author_id)
        else:
            view = StorageView(self.author_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def fail(self, interaction: discord.Interaction, msg: str):
        embed = discord.Embed(title="❌ Ошибка", description=msg, color=0xe74c3c)
        if self.location == "profile":
            view = ProfileView(self.author_id)
        else:
            view = StorageView(self.author_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.location == "profile":
            embed = await build_profile_embed(interaction)
            view = ProfileView(self.author_id)
        else:
            embed = await build_storage_embed(interaction)
            view = StorageView(self.author_id)
        await interaction.edit_original_response(embed=embed, view=view)


# ============================================================
#  ⭐ УЛУЧШЕНИЕ ЗВЁЗД
# ============================================================

async def open_star_view(interaction: discord.Interaction, author_id: int):
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)
    custom = settings["custom_emojis"]

    async with bot.db.execute("""
        SELECT inv.slot, inv.item_id, i.name, i.emoji, inv.stars
        FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'profile' AND inv.stars < 5
        ORDER BY inv.slot ASC
    """, (user_id,)) as c:
        rows = await c.fetchall()

    if not rows:
        await interaction.followup.send("❌ Нет генераторов для улучшения (все 5★ или пусто).", ephemeral=True)
        return

    options = []
    for slot, item_id, name, default_emoji, stars in rows[:25]:
        emoji_str = custom.get(item_id, default_emoji)
        emoji_obj = parse_emoji(emoji_str)
        next_star = stars + 1
        need = STAR_UPGRADE[next_star]["copies"]
        async with bot.db.execute(
            "SELECT COUNT(*) FROM inventory WHERE user_id = ? AND location = 'profile' AND item_id = ? AND stars = ?",
            (user_id, item_id, stars)
        ) as c:
            have = (await c.fetchone())[0]
        options.append(discord.SelectOption(
            label=f"Слот {slot}: {name} {stars}★ → {next_star}★ ({have}/{need})",
            value=f"{slot}:{item_id}:{stars}",
            emoji=emoji_obj
        ))

    embed = discord.Embed(
        title="⭐ Улучшение звёзд",
        description=(
            f"Бонус к доходу за звёзды (суммарный):\n"
            f"1★ +{int(STAR_BONUS[1] * 100)}%, 2★ +{int(STAR_BONUS[2] * 100)}%, "
            f"3★ +{int(STAR_BONUS[3] * 100)}%, 4★ +{int(STAR_BONUS[4] * 100)}%, "
            f"5★ +{int(STAR_BONUS[5] * 100)}%.\n\n"
            f"Чтобы поднять звезду, нужно **несколько копий** того же генератора с такой же звёздностью.\n"
            f"При провале копии сгорают, но звезда **не понижается**.\n\n"
            f"Выбери генератор:"
        ),
        color=0xf1c40f
    )
    await interaction.edit_original_response(embed=embed, view=StarSelectView(author_id, options))


class StarSelectView(discord.ui.View):
    def __init__(self, author_id: int, options: list[discord.SelectOption]):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.add_item(make_select("Выбери генератор", options, self.item_select, row=0))
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def item_select(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        slot_str, item_id, stars_str = value.split(":", 2)
        slot = int(slot_str)
        stars = int(stars_str)
        next_star = stars + 1
        if next_star > 5:
            await interaction.response.defer()
            await interaction.followup.send("❌ Уже 5★.", ephemeral=True)
            return
        await interaction.response.defer()
        await show_star_confirm(interaction, slot, item_id, stars, next_star, self.author_id)

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = await build_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))


async def show_star_confirm(interaction: discord.Interaction, slot: int, item_id: str, current_stars: int, next_star: int, author_id: int):
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)
    custom = settings["custom_emojis"]
    async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (item_id,)) as c:
        row = await c.fetchone()
    name, default_emoji = row if row else ("генератор", "⚙️")
    emoji = custom.get(item_id, default_emoji)

    settings_star = STAR_UPGRADE[next_star]
    async with bot.db.execute(
        "SELECT COUNT(*) FROM inventory WHERE user_id = ? AND location = 'profile' AND item_id = ? AND stars = ?",
        (interaction.user.id, item_id, current_stars)
    ) as c:
        have = (await c.fetchone())[0]

    need = settings_star["copies"]
    enough = have >= need

    embed = discord.Embed(
        title=f"⭐ Улучшение до {next_star}★",
        description=(
            f"Генератор: {emoji} **{name}** (слот {slot}, {current_stars}★)\n\n"
            f"Нужно копий: **{have}/{need}**\n"
            f"Шанс успеха: **{int(settings_star['chance'] * 100)}%**\n"
            f"Стоимость: **💎 {settings_star['gems']}**\n"
            f"Новый суммарный бонус: **+{int(STAR_BONUS[next_star] * 100)}%** к доходу.\n\n"
            f"При провале копии сгорают, но звезда **не понижается**."
        ),
        color=0xf1c40f if enough else 0xe74c3c
    )
    await interaction.edit_original_response(
        embed=embed,
        view=StarConfirmView(author_id, slot, item_id, current_stars, next_star)
    )


class StarConfirmView(discord.ui.View):
    def __init__(self, author_id: int, slot: int, item_id: str, current_stars: int, next_star: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.slot = slot
        self.item_id = item_id
        self.current_stars = current_stars
        self.next_star = next_star

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Улучшить", emoji="⭐", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        user_id = interaction.user.id
        settings_star = STAR_UPGRADE[self.next_star]
        cost = settings_star["gems"]
        need = settings_star["copies"]

        async with bot.db.execute("SELECT gems FROM players WHERE user_id = ?", (user_id,)) as c:
            gems = (await c.fetchone())[0]
        if gems < cost:
            await self.fail(interaction, f"❌ Нужно 💎 {cost}, у тебя {gems}.")
            return

        async with bot.db.execute(
            "SELECT item_id, stars FROM inventory WHERE user_id = ? AND location = 'profile' AND slot = ?",
            (user_id, self.slot)
        ) as c:
            row = await c.fetchone()
        if not row:
            await self.fail(interaction, "❌ Генератор не найден.")
            return
        real_item_id, real_stars = row
        if real_item_id != self.item_id or real_stars != self.current_stars:
            await self.fail(interaction, "❌ Данные изменились, попробуй снова.")
            return

        async with bot.db.execute(
            "SELECT slot FROM inventory WHERE user_id = ? AND location = 'profile' AND item_id = ? AND stars = ? ORDER BY slot ASC",
            (user_id, self.item_id, self.current_stars)
        ) as c:
            copies = [r[0] for r in await c.fetchall()]

        if len(copies) < need:
            await self.fail(interaction, f"❌ Нужно {need} копий, у тебя {len(copies)}.")
            return

        if cost > 0:
            await bot.db.execute(
                "UPDATE players SET gems = gems - ? WHERE user_id = ?", (cost, user_id)
            )

        if self.slot in copies:
            keep_slot = self.slot
            to_delete = [s for s in copies if s != self.slot][:need - 1]
        else:
            to_delete = copies[:need]
            keep_slot = to_delete[0] if to_delete else self.slot

        for s in to_delete:
            await bot.db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND location = 'profile' AND slot = ?",
                (user_id, s)
            )

        success = random.random() < settings_star["chance"]

        if success:
            await bot.db.execute(
                "UPDATE inventory SET stars = ? WHERE user_id = ? AND location = 'profile' AND slot = ?",
                (self.next_star, user_id, keep_slot)
            )
            await update_story_quests(self.author_id, "stars", 1)

        await bot.db.commit()

        if success:
            await check_achievements(user_id)

        if success:
            unlocked = await check_achievements(user_id)
            desc = (
                f"Генератор в слоте {keep_slot} улучшен до **{self.next_star}★**.\n"
                f"Суммарный бонус к доходу: **+{int(STAR_BONUS[self.next_star] * 100)}%**.\n"
                f"Сгорело копий: **{len(to_delete)}**."
            )
            if unlocked:
                desc += "\n\n🏆 " + ", ".join(f"{e} {n}" for e, n, _ in unlocked)
            embed = discord.Embed(title="⭐ Успех!", description=desc, color=0x2ecc71)
        else:
            embed = discord.Embed(
                title="💥 Провал",
                description=(
                    f"Улучшение до **{self.next_star}★** не удалось.\n"
                    f"Копии сгорели, звезда не понизилась."
                ),
                color=0xe74c3c
            )

        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))

    @discord.ui.button(label="Отмена", emoji="❌", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))

    async def fail(self, interaction: discord.Interaction, msg: str):
        embed = discord.Embed(title="❌ Ошибка", description=msg, color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))


# ============================================================
#  🔀 ПЕРЕМЕЩЕНИЕ
# ============================================================

async def open_move_view(interaction: discord.Interaction, source: str, author_id: int, page: int = 0):
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    settings = await get_settings(guild_id)
    custom = settings["custom_emojis"]

    async with bot.db.execute("""
        SELECT inv.slot, inv.item_id, i.name, i.emoji, inv.stars
        FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = ?
        ORDER BY inv.slot ASC
    """, (user_id, source)) as c:
        rows = await c.fetchall()

    if not rows:
        await interaction.followup.send("❌ В этой локации нет предметов.", ephemeral=True)
        return

    total_pages = max(1, (len(rows) + SHOP_SELECT_PAGE_SIZE - 1) // SHOP_SELECT_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page * SHOP_SELECT_PAGE_SIZE: page * SHOP_SELECT_PAGE_SIZE + SHOP_SELECT_PAGE_SIZE]

    options = []
    for slot, item_id, name, default_emoji, stars in chunk:
        emoji_str = custom.get(item_id, default_emoji)
        emoji_obj = parse_emoji(emoji_str)
        stars_str = f"({stars}⭐)" if stars > 0 else ""
        options.append(discord.SelectOption(
            label=f"Слот {slot}: {name} {stars_str}".strip(),
            value=f"{slot}:{item_id}:{stars}",
            emoji=emoji_obj
        ))

    location_name = "Замка" if source == "profile" else "Хранилища"
    embed = discord.Embed(
        title=f"🔀 Перемещение из {location_name}",
        description=f"Страница {page + 1}/{total_pages}\nВыбери предмет:",
        color=0x3498db
    )
    await interaction.edit_original_response(
        embed=embed,
        view=MoveView(author_id, source, options, page, total_pages)
    )


class MoveView(discord.ui.View):
    def __init__(self, author_id: int, source: str, options: list[discord.SelectOption], page: int, total_pages: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.source = source
        self.page = page
        self.total_pages = total_pages

        self.add_item(make_select("Выбери предмет", options, self.item_select, row=0))

        if total_pages > 1:
            prev = discord.ui.Button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self.prev_page
            self.add_item(prev)
            nxt = discord.ui.Button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1)
            nxt.callback = self.next_page
            self.add_item(nxt)

        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=2)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def item_select(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        slot_str, item_id, stars_str = value.split(":", 2)
        await interaction.response.defer()
        await show_move_confirm(interaction, self.source, item_id, int(slot_str), int(stars_str), self.author_id)

    async def prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await open_move_view(interaction, self.source, self.author_id, self.page - 1)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await open_move_view(interaction, self.source, self.author_id, self.page + 1)

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.source == "profile":
            embed = await build_profile_embed(interaction)
            view = ProfileView(self.author_id)
        else:
            embed = await build_storage_embed(interaction)
            view = StorageView(self.author_id)
        await interaction.edit_original_response(embed=embed, view=view)


async def show_move_confirm(interaction: discord.Interaction, source: str, item_id: str, slot: int, stars: int, author_id: int):
    guild_id = interaction.guild_id
    custom = (await get_settings(guild_id))["custom_emojis"]
    async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (item_id,)) as c:
        row = await c.fetchone()
    name, default_emoji = row if row else ("предмет", "📦")
    emoji = custom.get(item_id, default_emoji)
    stars_str = f"({stars}⭐)" if stars > 0 else ""
    target = "storage" if source == "profile" else "profile"
    target_name = "Хранилище" if target == "storage" else "Замок"
    embed = discord.Embed(
        title="🔀 Перемещение",
        description=f"Переместить {emoji} **{name}** {stars_str} (слот {slot}) в **{target_name}**?",
        color=0x3498db
    )
    await interaction.edit_original_response(
        embed=embed,
        view=MoveConfirmView(author_id, source, item_id, slot, stars)
    )


class MoveConfirmView(discord.ui.View):
    def __init__(self, author_id: int, source: str, item_id: str, slot: int, stars: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.source = source
        self.item_id = item_id
        self.slot = slot
        self.stars = stars

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

        # Проверяем, что предмет ещё в исходной локации
        async with bot.db.execute(
            "SELECT item_id, stars FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
            (user_id, self.source, self.slot)
        ) as c:
            row = await c.fetchone()

        if not row:
            await self.fail(interaction, "❌ Предмета нет в этом слоте.")
            return

        item_id, stars = row

        # Ищем свободный слот в целевой локации
        if target == "storage":
            target_size = await get_storage_size(user_id)
        else:
            target_size = await get_grid_size(user_id)

        async with bot.db.execute(
            "SELECT slot FROM inventory WHERE user_id = ? AND location = ?",
            (user_id, target)
        ) as c:
            used = {r[0] for r in await c.fetchall()}

        free = [s for s in range(target_size) if s not in used]

        if not free:
            await self.fail(interaction, f"❌ В целевой локации нет свободных слотов (макс. {target_size}).")
            return

        new_slot = free[0]

        # Удаляем из исходной локации
        await bot.db.execute(
            "DELETE FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
            (user_id, self.source, self.slot)
        )

        # Вставляем в свободный слот
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location, stars) VALUES (?, ?, ?, ?, ?)",
            (user_id, new_slot, item_id, target, stars)
        )
        await bot.db.commit()

        await update_quest_progress(user_id, "move_2")
        await sort_inventory(user_id, "profile")
        await sort_inventory(user_id, "storage")

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


# ============================================================
#  ⚗️ СИНТЕЗ (с пагинацией)
# ============================================================

async def open_craft_view(interaction: discord.Interaction, author_id: int, page: int = 0):
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    custom = (await get_settings(guild_id))["custom_emojis"]
    chain_items = list(CRAFT_CHAIN.items())

    options_all = []
    for item_id, next_id in chain_items:
        async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (item_id,)) as c:
            src = await c.fetchone()
        async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (next_id,)) as c:
            dst = await c.fetchone()
        if not src or not dst:
            continue
        async with bot.db.execute(
            "SELECT COUNT(*) FROM inventory WHERE user_id = ? AND item_id = ?",
            (user_id, item_id)
        ) as c:
            count = (await c.fetchone())[0]
        
        emoji_str = custom.get(item_id, src[1])
        emoji_obj = parse_emoji(emoji_str)
        
        options_all.append(discord.SelectOption(
            label=f"{src[0]} ({count}/5) → {dst[0]}",
            value=item_id,
            emoji=emoji_obj
        ))

    if not options_all:
        await interaction.followup.send("❌ Нет предметов для синтеза.", ephemeral=True)
        return

    total_pages = max(1, (len(options_all) + SHOP_SELECT_PAGE_SIZE - 1) // SHOP_SELECT_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = options_all[page * SHOP_SELECT_PAGE_SIZE: page * SHOP_SELECT_PAGE_SIZE + SHOP_SELECT_PAGE_SIZE]

    embed = discord.Embed(
        title="⚗️ Синтез",
        description=f"Страница {page + 1}/{total_pages}\nВыбери предмет для синтеза:",
        color=0x3498db
    )
    await interaction.edit_original_response(
        embed=embed,
        view=CraftSelectView(author_id, chunk, page, total_pages)
    )


class CraftSelectView(discord.ui.View):
    def __init__(self, author_id: int, options: list[discord.SelectOption], page: int = 0, total_pages: int = 1):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.page = page
        self.total_pages = total_pages
        self.add_item(make_select("Выбери предмет для синтеза", options, self.item_select, row=0))

        if total_pages > 1:
            prev = discord.ui.Button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self.prev_page
            self.add_item(prev)
            nxt = discord.ui.Button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1)
            nxt.callback = self.next_page
            self.add_item(nxt)

        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=2)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def item_select(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        await interaction.response.defer()
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
        await interaction.edit_original_response(embed=embed, view=CraftConfirmView(self.author_id, item_id))

    async def prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await open_craft_view(interaction, self.author_id, self.page - 1)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await open_craft_view(interaction, self.author_id, self.page + 1)

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = await build_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))


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
            "SELECT location, slot FROM inventory WHERE user_id = ? AND item_id = ?",
            (user_id, item_id)
        ) as c:
            owned = await c.fetchall()

        if len(owned) < CRAFT_COST:
            await self.fail(interaction, f"❌ Нужно {CRAFT_COST} × {src_name}, у тебя {len(owned)}.")
            return

        async with bot.db.execute("SELECT gems, catalysts FROM players WHERE user_id = ?", (user_id,)) as c:
            gems, cats = await c.fetchone()
        if gems < gem_cost:
            await self.fail(interaction, f"❌ Нужно 💎 {gem_cost}, у тебя {gems}.")
            return
        if use_cat and cats < 1:
            await self.fail(interaction, "❌ Нет катализаторов.")
            return

        to_remove = owned[:CRAFT_COST]
        for location, slot in to_remove:
            await bot.db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
                (user_id, location, slot)
            )

        if gem_cost > 0:
            await bot.db.execute("UPDATE players SET gems = gems - ? WHERE user_id = ?", (gem_cost, user_id))
        catalyst_used = 0
        if use_cat:
            await bot.db.execute("UPDATE players SET catalysts = catalysts - 1 WHERE user_id = ?", (user_id,))
            catalyst_used = 1

        final_chance = min(1.0, base_chance + (CATALYST_BONUS if use_cat else 0))
        success = random.random() < final_chance

        await bot.db.execute(
            "INSERT INTO craft_log (user_id, item_id, success, gems_spent, catalyst_used) VALUES (?, ?, ?, ?, ?)",
            (user_id, item_id, int(success), gem_cost, catalyst_used)
        )

        if success:
            try:
                await place_items(user_id, next_id, 1)
            except ValueError:
                pass

        await bot.db.execute(
            "UPDATE players SET total_crafts = total_crafts + 1, total_successes = total_successes + ? "
            "WHERE user_id = ?", (int(success), user_id)
        )
        await bot.db.commit()
        await update_story_quests(user_id, "synthesize", 1)

        await sort_inventory(user_id, "profile")
        await sort_inventory(user_id, "storage")

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


# ============================================================
#  🧪 КАТАЛИЗАТОР
# ============================================================

class CatalystSelectView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        options = [discord.SelectOption(label=f"{q} шт — 💎 {CATALYST_PRICE * q}", value=str(q)) for q in (1, 2, 5, 10, 25)]
        self.add_item(make_select("Сколько катализаторов купить?", options, self.quantity_select, row=0))
        back = discord.ui.Button(label="Отмена", emoji="❌", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self.cancel
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def quantity_select(self, interaction: discord.Interaction):
        await interaction.response.defer()
        qty = int(interaction.data["values"][0])
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

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = await build_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))


# ============================================================
#  📅 Банк
# ============================================================

async def get_deposit(user_id: int):
    async with bot.db.execute(
        "SELECT amount, interest_rate, start_time, end_time FROM bank_deposits WHERE user_id = ?",
        (user_id,)
    ) as c:
        return await c.fetchone()

async def calculate_deposit_interest(user_id: int) -> int:
    deposit = await get_deposit(user_id)
    if not deposit:
        return 0
    amount, rate, start, end = deposit
    start_dt = datetime.datetime.fromisoformat(start)
    end_dt = datetime.datetime.fromisoformat(end)
    now = datetime.datetime.now()
    if now >= end_dt:
        return int(amount * (1 + rate))
    days_passed = (now - start_dt).total_seconds() / 86400
    total_days = (end_dt - start_dt).total_seconds() / 86400
    if total_days <= 0:
        return amount
    return int(amount + amount * rate * (days_passed / total_days))

class BankDepositModal(discord.ui.Modal, title="Открыть вклад"):
    amount = discord.ui.TextInput(label="Сумма (монеты)", required=True)
    days = discord.ui.TextInput(label="Срок (дней, 1–30)", default="7", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            amt = int(self.amount.value)
            days = int(self.days.value)
            if amt <= 0 or days < 1 or days > 30:
                raise ValueError
        except ValueError:
            return await interaction.followup.send("❌ Сумма > 0, срок 1–30 дней.", ephemeral=True)

        # Проверка, что нет активного вклада
        if await get_deposit(self.author_id):
            return await interaction.followup.send("❌ У тебя уже есть вклад. Сначала забери его.", ephemeral=True)

        async with bot.db.execute("SELECT coins FROM players WHERE user_id = ?", (self.author_id,)) as c:
            coins = (await c.fetchone())[0]
        if coins < amt:
            return await interaction.followup.send("❌ Недостаточно монет.", ephemeral=True)

        now = datetime.datetime.now()
        end = now + datetime.timedelta(days=days)
        rate = 0.05 * days  # 5% за каждый день (максимум 150% за 30 дней — это много, но капнем)

        await bot.db.execute("UPDATE players SET coins = coins - ? WHERE user_id = ?", (amt, self.author_id))
        await bot.db.execute("""
            INSERT INTO bank_deposits (user_id, amount, interest_rate, start_time, end_time)
            VALUES (?, ?, ?, ?, ?)
        """, (self.author_id, amt, rate, now.isoformat(), end.isoformat()))
        await bot.db.commit()

        await interaction.followup.send(
            f"✅ Вклад открыт: 🪙 {amt} на {days} дней.\n"
            f"Процент: {int(rate * 100)}% (вернёшь ~{int(amt * (1 + rate))} монет).",
            ephemeral=True
        )

class BankWithdrawModal(discord.ui.Modal, title="Забрать вклад"):
    confirm = discord.ui.TextInput(label="Введите ДА", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.confirm.value.strip().upper() != "ДА":
            return await interaction.followup.send("❌ Отменено.", ephemeral=True)

        deposit = await get_deposit(self.author_id)
        if not deposit:
            return await interaction.followup.send("❌ У тебя нет вклада.", ephemeral=True)

        amount, rate, start, end = deposit
        start_dt = datetime.datetime.fromisoformat(start)
        end_dt = datetime.datetime.fromisoformat(end)
        now = datetime.datetime.now()
        days_passed = (now - start_dt).total_seconds() / 86400
        total_days = (end_dt - start_dt).total_seconds() / 86400

        if now >= end_dt:
            payout = int(amount * (1 + rate))
        else:
            # Досрочное закрытие: возврат без процентов (или с минимальным)
            payout = amount

        await bot.db.execute("UPDATE players SET coins = coins + ? WHERE user_id = ?", (payout, self.author_id))
        await bot.db.execute("DELETE FROM bank_deposits WHERE user_id = ?", (self.author_id,))
        await bot.db.commit()

        await interaction.followup.send(
            f"✅ Вклад закрыт. Получено 🪙 {payout} (из {amount} вложенных).",
            ephemeral=True
        )

# ============================================================
#  Аукцион
# ============================================================

class AuctionSellModal(discord.ui.Modal, title="Выставить на аукцион"):
    item_id = discord.ui.TextInput(label="ID предмета", required=True)
    stars = discord.ui.TextInput(label="Звёзды (0–5)", default="0", required=True)
    start_price = discord.ui.TextInput(label="Стартовая цена", required=True)
    hours = discord.ui.TextInput(label="Длительность (часов)", default="24", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            item_id = self.item_id.value.strip()
            stars = int(self.stars.value)
            start = int(self.start_price.value)
            hours = int(self.hours.value)
            if start <= 0 or hours < 1 or hours > 72 or stars < 0 or stars > 5:
                raise ValueError
        except ValueError:
            return await interaction.followup.send("❌ Неверные данные.", ephemeral=True)

        # Проверка, что предмет есть
        async with bot.db.execute(
            "SELECT slot FROM inventory WHERE user_id = ? AND item_id = ? AND stars = ? AND location = 'profile'",
            (self.author_id, item_id, stars)
        ) as c:
            row = await c.fetchone()
        if not row:
            return await interaction.followup.send("❌ У тебя нет такого предмета.", ephemeral=True)

        # Удаляем из инвентаря
        await bot.db.execute(
            "DELETE FROM inventory WHERE user_id = ? AND slot = ? AND location = 'profile'",
            (self.author_id, row[0])
        )

        end = datetime.datetime.now() + datetime.timedelta(hours=hours)
        await bot.db.execute("""
            INSERT INTO auctions (seller_id, item_id, stars, start_price, current_bid, end_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (self.author_id, item_id, stars, start, start, end.isoformat()))
        await bot.db.commit()

        await interaction.followup.send(
            f"✅ Лот выставлен: **{item_id}** ({stars}★), стартовая цена 🪙 {start}, "
            f"до {end.strftime('%H:%M %d.%m')}.",
            ephemeral=True
        )

class AuctionBidModal(discord.ui.Modal, title="Сделать ставку"):
    auction_id = discord.ui.TextInput(label="ID лота", required=True)
    amount = discord.ui.TextInput(label="Ставка (монеты)", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            aid = int(self.auction_id.value)
            amt = int(self.amount.value)
            if amt <= 0:
                raise ValueError
        except ValueError:
            return await interaction.followup.send("❌ Неверные данные.", ephemeral=True)

        async with bot.db.execute(
            "SELECT seller_id, current_bid, current_bidder, end_time, status FROM auctions WHERE id = ?",
            (aid,)
        ) as c:
            lot = await c.fetchone()
        if not lot:
            return await interaction.followup.send("❌ Лот не найден.", ephemeral=True)

        seller_id, current_bid, current_bidder, end_time, status = lot
        if status != "active":
            return await interaction.followup.send("❌ Лот уже закрыт.", ephemeral=True)

        if datetime.datetime.fromisoformat(end_time) < datetime.datetime.now():
            return await interaction.followup.send("❌ Время лота истекло.", ephemeral=True)

        if amt <= current_bid:
            return await interaction.followup.send(f"❌ Ставка должна быть > {current_bid}.", ephemeral=True)

        if self.author_id == seller_id:
            return await interaction.followup.send("❌ Нельзя ставить на свой лот.", ephemeral=True)

        async with bot.db.execute("SELECT coins FROM players WHERE user_id = ?", (self.author_id,)) as c:
            coins = (await c.fetchone())[0]
        if coins < amt:
            return await interaction.followup.send("❌ Недостаточно монет.", ephemeral=True)

        # Возврат предыдущему лидеру (если был)
        if current_bidder:
            await bot.db.execute("UPDATE players SET coins = coins + ? WHERE user_id = ?", (current_bid, current_bidder))

        # Списываем у нового
        await bot.db.execute("UPDATE players SET coins = coins - ? WHERE user_id = ?", (amt, self.author_id))
        await bot.db.execute(
            "UPDATE auctions SET current_bid = ?, current_bidder = ? WHERE id = ?",
            (amt, self.author_id, aid)
        )
        await bot.db.execute(
            "INSERT INTO auction_bids (auction_id, bidder_id, amount) VALUES (?, ?, ?)",
            (aid, self.author_id, amt)
        )
        await bot.db.commit()

        await interaction.followup.send(f"✅ Ставка 🪙 {amt} принята. Ты лидер лота!", ephemeral=True)
        
# ============================================================
#  📅 ЗАДАНИЯ
# ============================================================

class QuestsView(BaseView):
    def __init__(self, author_id: int, return_to: str = "main", timeout: int = 600):
        super().__init__(author_id, timeout)
        self.return_to = return_to

    @discord.ui.button(label="Забрать награду", emoji="🎁", style=discord.ButtonStyle.success, row=1)
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        user_id = interaction.user.id
        quests, progress, claimed = await get_or_create_daily_quests(user_id)
        options = []
        for qid in quests:
            if qid in claimed:
                continue
            desc, target, reward = QUEST_POOL[qid]
            done = progress[qid] >= target
            label = f"{desc} — {progress[qid]}/{target}" + (" 🎁" if done else "")
            options.append(discord.SelectOption(label=label[:100], value=qid, emoji="🎁" if done else "⏳"))
        if not options:
            await interaction.followup.send("❌ Нет доступных заданий.", ephemeral=True)
            return
        embed = discord.Embed(title="🎁 Забрать награду", description="Выбери задание:", color=0x3498db)
        await interaction.edit_original_response(
            embed=embed, view=ClaimQuestSelectView(self.author_id, options)
        )

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.return_to == "quests":
            embed = discord.Embed(
                title="📋 Квесты",
                description="Выбери раздел: сюжетные квесты или ежедневные задания.",
                color=0x3498db
            )
            await interaction.edit_original_response(embed=embed, view=QuestsHubView(self.author_id))
        else:
            await self.back_to_main(interaction)


class ClaimQuestSelectView(discord.ui.View):
    def __init__(self, author_id: int, options: list[discord.SelectOption]):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.add_item(make_select("Выбери задание", options, self.quest_select, row=0))
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def quest_select(self, interaction: discord.Interaction):
        qid = interaction.data["values"][0]
        await interaction.response.defer()
        user_id = interaction.user.id
        quests, progress, claimed = await get_or_create_daily_quests(user_id)
        if qid not in quests or qid in claimed:
            await self.fail(interaction, "❌ Недоступно.")
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
        embed = discord.Embed(title="🎁 Награда получена", description=f"💎 **{reward}** гемов за «{desc}»!", color=0x2ecc71)
        await interaction.edit_original_response(embed=embed, view=QuestsView(self.author_id))

    async def fail(self, interaction: discord.Interaction, msg: str):
        embed = discord.Embed(title="❌ Ошибка", description=msg, color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=QuestsView(self.author_id))

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = await build_quests_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=QuestsView(self.author_id))


# ============================================================
#  🛒 МАГАЗИН
# ============================================================

class ShopView(BaseView):
    def __init__(self, author_id: int, page: int):
        super().__init__(author_id)
        self.page = page
        self.add_buttons()

    def add_buttons(self):
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
        back.callback = self.back
        self.add_item(back)
        buy = discord.ui.Button(label="Купить", emoji="🛍️", style=discord.ButtonStyle.success, row=0)
        buy.callback = self.buy
        self.add_item(buy)
        prev = discord.ui.Button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1)
        prev.callback = self.prev_page
        self.add_item(prev)
        nxt = discord.ui.Button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1)
        nxt.callback = self.next_page
        self.add_item(nxt)

    async def back(self, interaction: discord.Interaction):
        await self.back_to_main(interaction)

    async def buy(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with bot.db.execute(
            "SELECT id, name, price, emoji FROM items WHERE buyable = 1 ORDER BY price ASC"
        ) as c:
            rows = await c.fetchall()
        if not rows:
            await interaction.followup.send("❌ Магазин пуст.", ephemeral=True)
            return
        await open_shop_buy_select(interaction, self.author_id, rows, 0)

    async def prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page = max(0, self.page - 1)
        embed, _ = await build_shop_page(interaction, self.page)
        await interaction.edit_original_response(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed, total = await build_shop_page(interaction, self.page + 1)
        self.page = min(total - 1, self.page + 1)
        await interaction.edit_original_response(embed=embed, view=self)


async def open_shop_buy_select(interaction: discord.Interaction, author_id: int, rows: list, page: int):
    guild_id = interaction.guild_id
    custom = (await get_settings(guild_id))["custom_emojis"]
    total = len(rows)
    total_pages = max(1, (total + SHOP_SELECT_PAGE_SIZE - 1) // SHOP_SELECT_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page * SHOP_SELECT_PAGE_SIZE: page * SHOP_SELECT_PAGE_SIZE + SHOP_SELECT_PAGE_SIZE]

    options = []
    for item_id, name, price, default_emoji in chunk:
        emoji_str = custom.get(item_id, default_emoji)
        emoji_obj = parse_emoji(emoji_str)
        options.append(discord.SelectOption(label=f"{name} — 🪙 {price}", value=item_id, emoji=emoji_obj))
        
    embed = discord.Embed(
        title="🛒 Выбери предмет",
        description=f"Страница {page + 1}/{total_pages}\nВыбери предмет из списка:",
        color=0xf1c40f
    )
    await interaction.edit_original_response(
        embed=embed,
        view=ShopBuySelectView(author_id, options, page, total_pages)
    )


class ShopBuySelectView(discord.ui.View):
    def __init__(self, author_id: int, options: list[discord.SelectOption], page: int = 0, total_pages: int = 1):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.page = page
        self.total_pages = total_pages
        self.add_item(make_select("Выбери предмет...", options, self.item_select, row=0))

        if total_pages > 1:
            prev = discord.ui.Button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self.prev_page
            self.add_item(prev)
            nxt = discord.ui.Button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1)
            nxt.callback = self.next_page
            self.add_item(nxt)

        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=2)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def item_select(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        await interaction.response.defer()
        async with bot.db.execute("SELECT name, price, emoji FROM items WHERE id = ?", (item_id,)) as c:
            item = await c.fetchone()
        embed = discord.Embed(
            title="🛒 Покупка",
            description=f"{item[2]} **{item[0]}** — 🪙 {item[1]} за штуку.\nВыбери количество:",
            color=0xf1c40f
        )
        await interaction.edit_original_response(embed=embed, view=BuyItemQuantityView(self.author_id, item_id))

    async def prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with bot.db.execute(
            "SELECT id, name, price, emoji FROM items WHERE buyable = 1 ORDER BY price ASC"
        ) as c:
            rows = await c.fetchall()
        await open_shop_buy_select(interaction, self.author_id, rows, self.page - 1)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with bot.db.execute(
            "SELECT id, name, price, emoji FROM items WHERE buyable = 1 ORDER BY price ASC"
        ) as c:
            rows = await c.fetchall()
        await open_shop_buy_select(interaction, self.author_id, rows, self.page + 1)

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed, _ = await build_shop_page(interaction, 0)
        await interaction.edit_original_response(embed=embed, view=ShopView(self.author_id, 0))


class BuyItemQuantityView(discord.ui.View):
    def __init__(self, author_id: int, item_id: str):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.item_id = item_id
        options = [discord.SelectOption(label=f"{q} шт", value=str(q)) for q in (1, 5, 10, 25, 50)]
        self.add_item(make_select("Сколько купить?", options, self.quantity_select, row=0))
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def quantity_select(self, interaction: discord.Interaction):
        await interaction.response.defer()
        qty = int(interaction.data["values"][0])
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

        try:
            to_profile, to_storage = await place_items(user_id, self.item_id, qty)
        except ValueError as e:
            await self.fail(interaction, f"❌ {e}")
            return

        await bot.db.execute("UPDATE players SET coins = coins - ? WHERE user_id = ?", (total_cost, user_id))
        await bot.db.commit()

        await sort_inventory(user_id, "profile")
        await sort_inventory(user_id, "storage")

        await update_quest_progress(user_id, "buy_3", qty)
        unlocked = await check_achievements(user_id)

        msg = f"✅ Куплено **{name}** x{qty} за {total_cost} монет."
        if to_storage > 0:
            msg += f"\n📦 {to_profile} в замок, {to_storage} в хранилище (в замке не хватило места)."
        if unlocked:
            msg += "\n🏆 " + ", ".join(f"{e} {n}" for e, n, _ in unlocked)
        embed = discord.Embed(title="🛒 Покупка", description=msg, color=0x2ecc71)
        await interaction.edit_original_response(embed=embed, view=ShopView(self.author_id, 0))

        await update_story_quests(user_id, "buy", qty)

    async def fail(self, interaction: discord.Interaction, msg: str):
        embed = discord.Embed(title="❌ Ошибка", description=msg, color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=ShopView(self.author_id, 0))

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed, _ = await build_shop_page(interaction, 0)
        await interaction.edit_original_response(embed=embed, view=ShopView(self.author_id, 0))


# ============================================================
#  💎 УЛУЧШЕНИЯ
# ============================================================

class UpgradesView(BaseView):
    def __init__(self, author_id: int, page: int):
        super().__init__(author_id)
        self.page = page
        self.add_buttons()

    def add_buttons(self):
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
        back.callback = self.back
        self.add_item(back)
        buy = discord.ui.Button(label="Купить", emoji="💳", style=discord.ButtonStyle.success, row=0)
        buy.callback = self.buy
        self.add_item(buy)
        prev = discord.ui.Button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1)
        prev.callback = self.prev_page
        self.add_item(prev)
        nxt = discord.ui.Button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1)
        nxt.callback = self.next_page
        self.add_item(nxt)

    async def back(self, interaction: discord.Interaction):
        await self.back_to_main(interaction)

    async def buy(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with bot.db.execute("""
            SELECT id, name, price_coins as price, emoji, 'coins' as currency FROM grid_shop
            UNION ALL
            SELECT id, name, price_gems as price, emoji, 'gems' as currency FROM gem_shop
        """) as c:
            rows = await c.fetchall()

        order = {
            "grid_4x4": 1, "grid_5x5": 2, "grid_6x6": 3,
            "grid_7x7": 4, "grid_8x8": 5, "grid_9x9": 6, "grid_10x10": 7,
            "vip": 10, "gold": 11, "platinum": 12, "diamond": 13,
        }
        rows = sorted(rows, key=lambda r: order.get(r[0], 99))

        async with bot.db.execute(
            "SELECT upgrade_id FROM player_upgrades WHERE user_id = ?", (interaction.user.id,)
        ) as c:
            owned = {r[0] for r in await c.fetchall()}
        if not rows:
            await interaction.followup.send("❌ Улучшений нет.", ephemeral=True)
            return
        await open_upgrades_buy_select(interaction, self.author_id, rows, owned, 0)

    async def prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page = max(0, self.page - 1)
        embed, _ = await build_upgrades_page(interaction, self.page)
        await interaction.edit_original_response(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed, total = await build_upgrades_page(interaction, self.page + 1)
        self.page = min(total - 1, self.page + 1)
        await interaction.edit_original_response(embed=embed, view=self)


async def open_upgrades_buy_select(interaction: discord.Interaction, author_id: int, rows: list, owned: set, page: int):
    total = len(rows)
    total_pages = max(1, (total + SHOP_SELECT_PAGE_SIZE - 1) // SHOP_SELECT_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page * SHOP_SELECT_PAGE_SIZE: page * SHOP_SELECT_PAGE_SIZE + SHOP_SELECT_PAGE_SIZE]

    options = []
    for gid, name, price, emoji, currency in chunk:
        cur = "🪙" if currency == "coins" else "💎"
        options.append(discord.SelectOption(
            label=f"{name} — {cur} {price}" + (" ✅" if gid in owned else ""),
            value=gid, emoji=emoji
        ))
    embed = discord.Embed(
        title="💎 Выбери улучшение",
        description=f"Страница {page + 1}/{total_pages}\nВыбери улучшение:",
        color=0x9b59b6
    )
    await interaction.edit_original_response(
        embed=embed,
        view=UpgradesBuySelectView(author_id, options, page, total_pages)
    )


class UpgradesBuySelectView(discord.ui.View):
    def __init__(self, author_id: int, options: list[discord.SelectOption], page: int = 0, total_pages: int = 1):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.page = page
        self.total_pages = total_pages
        self.add_item(make_select("Выбери улучшение...", options, self.upgrade_select, row=0))

        if total_pages > 1:
            prev = discord.ui.Button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self.prev_page
            self.add_item(prev)
            nxt = discord.ui.Button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1)
            nxt.callback = self.next_page
            self.add_item(nxt)

        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=2)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def upgrade_select(self, interaction: discord.Interaction):
        upgrade_id = interaction.data["values"][0]
        await interaction.response.defer()
        user_id = interaction.user.id
        guild_id = interaction.guild_id

        async with bot.db.execute(
            "SELECT name, price_coins, emoji, size FROM grid_shop WHERE id = ?", (upgrade_id,)
        ) as c:
            grid_item = await c.fetchone()

        if grid_item:
            name, price, emoji, size = grid_item
            currency = "coins"
            category = "grid"
        else:
            async with bot.db.execute(
                "SELECT name, price_gems, emoji, category FROM gem_shop WHERE id = ?", (upgrade_id,)
            ) as c:
                gem_item = await c.fetchone()
            if not gem_item:
                await interaction.followup.send("❌ Не найдено.", ephemeral=True)
                return
            name, price, emoji, category = gem_item
            currency = "gems"

        async with bot.db.execute(
            "SELECT 1 FROM player_upgrades WHERE user_id = ? AND upgrade_id = ?", (user_id, upgrade_id)
        ) as c:
            if await c.fetchone():
                await interaction.followup.send(f"❌ **{name}** уже куплено.", ephemeral=True)
                return

        async with bot.db.execute(
            f"SELECT {currency} FROM players WHERE user_id = ?", (user_id,)
        ) as c:
            balance = (await c.fetchone())[0]

        if balance < price:
            unit = "🪙" if currency == "coins" else "💎"
            await interaction.followup.send(f"❌ Нужно {unit} {price}, у тебя {balance}.", ephemeral=True)
            return

        await bot.db.execute(
            f"UPDATE players SET {currency} = {currency} - ? WHERE user_id = ?", (price, user_id)
        )
        await bot.db.execute(
            "INSERT INTO player_upgrades (user_id, upgrade_id) VALUES (?, ?)", (user_id, upgrade_id)
        )

        if category == "grid":
            await bot.db.execute(
                "UPDATE players SET grid_size = ? WHERE user_id = ?", (size, user_id)
            )
        elif upgrade_id.startswith("grid_"):
            size = int(upgrade_id.split("_")[1].split("x")[0])
            await bot.db.execute(
                "UPDATE players SET grid_size = ? WHERE user_id = ?", (size * size, user_id)
            )
        elif category == "status":
            bonuses = {"vip": 0.15, "gold": 0.35, "platinum": 0.25, "diamond": 0.45}
            async with bot.db.execute(
                "SELECT upgrade_id FROM player_upgrades WHERE user_id = ? AND upgrade_id IN "
                "('vip','gold','platinum','diamond')", (user_id,)
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
                            await member.add_roles(role, reason=f"Покупка {name}")
                        except discord.HTTPException:
                            pass

        await bot.db.commit()
        unit = "🪙" if currency == "coins" else "💎"
        await interaction.followup.send(f"✅ Куплено **{emoji} {name}** за {unit} {price}!", ephemeral=True)

    async def prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with bot.db.execute("""
            SELECT id, name, price_coins as price, emoji, 'coins' as currency FROM grid_shop
            UNION ALL
            SELECT id, name, price_gems as price, emoji, 'gems' as currency FROM gem_shop
        """) as c:
            rows = await c.fetchall()
        order = {
            "grid_4x4": 1, "grid_5x5": 2, "grid_6x6": 3,
            "grid_7x7": 4, "grid_8x8": 5, "grid_9x9": 6, "grid_10x10": 7,
            "vip": 10, "gold": 11, "platinum": 12, "diamond": 13,
        }
        rows = sorted(rows, key=lambda r: order.get(r[0], 99))
        async with bot.db.execute(
            "SELECT upgrade_id FROM player_upgrades WHERE user_id = ?", (interaction.user.id,)
        ) as c:
            owned = {r[0] for r in await c.fetchall()}
        await open_upgrades_buy_select(interaction, self.author_id, rows, owned, self.page - 1)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        async with bot.db.execute("""
            SELECT id, name, price_coins as price, emoji, 'coins' as currency FROM grid_shop
            UNION ALL
            SELECT id, name, price_gems as price, emoji, 'gems' as currency FROM gem_shop
        """) as c:
            rows = await c.fetchall()
        order = {
            "grid_4x4": 1, "grid_5x5": 2, "grid_6x6": 3,
            "grid_7x7": 4, "grid_8x8": 5, "grid_9x9": 6, "grid_10x10": 7,
            "vip": 10, "gold": 11, "platinum": 12, "diamond": 13,
        }
        rows = sorted(rows, key=lambda r: order.get(r[0], 99))
        async with bot.db.execute(
            "SELECT upgrade_id FROM player_upgrades WHERE user_id = ?", (interaction.user.id,)
        ) as c:
            owned = {r[0] for r in await c.fetchall()}
        await open_upgrades_buy_select(interaction, self.author_id, rows, owned, self.page + 1)

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed, _ = await build_upgrades_page(interaction, 0)
        await interaction.edit_original_response(embed=embed, view=UpgradesView(self.author_id, 0))

# ============================================================
#  Личные настройки
# ============================================================

class UserProfileView(BaseView):
    @discord.ui.button(label="Настройки", emoji="⚙️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(
            title="⚙️ Личные настройки",
            description="Здесь ты можешь управлять своим профилем.",
            color=0x808080
        )
        await interaction.edit_original_response(embed=embed, view=UserSettingsView(self.author_id))

    @discord.ui.button(label="Кастомизация", emoji="🎨", style=discord.ButtonStyle.success, row=0)
    async def btn_custom(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(
            title="🎨 Кастомизация",
            description="Выбери раздел: титулы, дейли, косметика, сюжетные квесты.",
            color=0x9b59b6
        )
        await interaction.edit_original_response(embed=embed, view=CustomizationHubView(self.author_id))

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_main_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=MainMenuView(self.author_id))


class CustomizationHubView(BaseView):
    @discord.ui.button(label="Титулы", emoji="🏅", style=discord.ButtonStyle.primary, row=0)
    async def btn_titles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await open_titles_view(interaction, self.author_id, 0, return_to="hub")

    @discord.ui.button(label="Косметика", emoji="🎨", style=discord.ButtonStyle.primary, row=0)
    async def btn_cosmetics(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_cosmetics_embed(interaction)
        await interaction.edit_original_response(
            embed=embed, view=CosmeticsView(self.author_id, return_to="hub")
        )

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_user_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=UserProfileView(self.author_id))

class UserSettingsView(BaseView):
    @discord.ui.button(label="Сбросить прогресс", emoji="🗑️", style=discord.ButtonStyle.danger, row=0)
    async def btn_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(UserResetModal(self.author_id))

    @discord.ui.button(label="Сменить цвет", emoji="🎨", style=discord.ButtonStyle.primary, row=0)
    async def btn_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Просто отправляем модалку с вводом HEX-кода
        await interaction.response.send_modal(UserColorModal(self.author_id))

    @discord.ui.button(label="Экспорт данных", emoji="📤", style=discord.ButtonStyle.success, row=1)
    async def btn_export(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        async with bot.db.execute("""
            SELECT inv.slot, i.name, inv.stars, inv.location 
            FROM inventory inv JOIN items i ON inv.item_id = i.id 
            WHERE inv.user_id = ?
        """, (interaction.user.id,)) as c:
            inv_rows = await c.fetchall()
            
        data = {
            "user_id": interaction.user.id,
            "inventory": [{"slot": r[0], "name": r[1], "stars": r[2], "loc": r[3]} for r in inv_rows]
        }
        
        import io
        file = discord.File(io.BytesIO(json.dumps(data, ensure_ascii=False, indent=4).encode()), filename="my_profile.json")
        await interaction.followup.send("Вот твои данные:", file=file, ephemeral=True)

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_user_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=UserProfileView(self.author_id))

class UserResetModal(discord.ui.Modal, title="Сброс прогресса"):
    confirm = discord.ui.TextInput(label="Введите 'УДАЛИТЬ' для сброса", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.confirm.value.strip() != "УДАЛИТЬ":
            await interaction.followup.send("❌ Сброс отменён.", ephemeral=True)
            return
        
        # Сбрасываем только СВОЙ прогресс
        uid = interaction.user.id
        await bot.db.execute("""
            UPDATE players SET
                coins = 3, gems = 0, catalysts = 0,
                grid_size = 9, storage_size = 36, income_bonus = 0.0,
                total_crafts = 0, total_successes = 0,
                last_collected = CURRENT_TIMESTAMP,
                last_gem_collected = CURRENT_TIMESTAMP,
                daily_quest_date = NULL,
                daily_quest_progress = '{}',
                daily_quest_claimed = '[]'
            WHERE user_id = ?
        """, (uid,))
        await bot.db.execute("DELETE FROM inventory WHERE user_id = ?", (uid,))
        await bot.db.execute("DELETE FROM player_achievements WHERE user_id = ?", (uid,))
        await bot.db.execute("DELETE FROM player_upgrades WHERE user_id = ?", (uid,))
        await bot.db.execute("DELETE FROM craft_log WHERE user_id = ?", (uid,))
        await bot.db.commit()
        
        await interaction.followup.send("🗑️ Твой прогресс полностью сброшен. Начни заново!", ephemeral=True)

class UserColorModal(discord.ui.Modal, title="Смена цвета профиля"):
    color = discord.ui.TextInput(label="HEX-код цвета (например, #FF0000)", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        color_str = self.color.value.strip()
        
        # Проверка формата
        try:
            if not color_str.startswith("#"): color_str = "#" + color_str
            color_int = int(color_str.replace("#", ""), 16)
            # В базе пока нет поля для цвета, сохраним в guild_settings (или добавим колонку в players).
            # Для простоты просто отправим уведомление, что функция в разработке (чтобы не ломать БД).
            await interaction.followup.send(f"🎨 Цвет **{color_str}** сохранён! (Функция отображения будет добавлена позже).", ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Неверный формат HEX-кода.", ephemeral=True)
# ============================================================
#  🏆 ДОСТИЖЕНИЯ
# ============================================================

class AchievementsView(BaseView):
    def __init__(self, author_id: int, page: int):
        super().__init__(author_id)
        self.page = page
        self.add_buttons()

    def add_buttons(self):
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
        back.callback = self.back
        self.add_item(back)
        prev = discord.ui.Button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1)
        prev.callback = self.prev_page
        self.add_item(prev)
        nxt = discord.ui.Button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1)
        nxt.callback = self.next_page
        self.add_item(nxt)

    async def back(self, interaction: discord.Interaction):
        await self.back_to_main(interaction)

    async def prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page = max(0, self.page - 1)
        embed, _ = await build_achievements_page(interaction, self.page)
        await interaction.edit_original_response(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed, total = await build_achievements_page(interaction, self.page + 1)
        self.page = min(total - 1, self.page + 1)
        await interaction.edit_original_response(embed=embed, view=self)


class StatsView(BackOnlyView):
    pass


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
        
    @discord.ui.button(label="Логи", emoji="📜", style=discord.ButtonStyle.secondary, row=3)
    async def logs(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await open_admin_logs(interaction, self.author_id, page=0)

@bot.tree.command(name="debug_emoji", description="Проверить эмодзи по звёздам")
async def debug_emoji(interaction: discord.Interaction, item_id: str):
    await interaction.response.defer(ephemeral=True)
    async with bot.db.execute("SELECT emoji_by_star FROM items WHERE id = ?", (item_id,)) as c:
        row = await c.fetchone()
    if not row:
        return await interaction.followup.send("❌ Генератор не найден.", ephemeral=True)
    await interaction.followup.send(f"`{item_id}`: `{row[0]}`", ephemeral=True)


class AdminGrantView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.currency = "coins"
        options = [discord.SelectOption(label="Монеты", value="coins", emoji="🪙"), discord.SelectOption(label="Гемы", value="gems", emoji="💎")]
        self.add_item(make_select("Выбери валюту", options, self.currency_select, row=0))
        enter = discord.ui.Button(label="Ввести ID", emoji="📝", style=discord.ButtonStyle.primary, row=1)
        enter.callback = self.enter
        self.add_item(enter)
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def currency_select(self, interaction: discord.Interaction):
        self.currency = interaction.data["values"][0]
        await interaction.response.defer()

    async def enter(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AdminGrantValuesModal(self.author_id, self.currency))

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = discord.Embed(title="🛡️ Панель администратора", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=AdminPanelView(self.author_id))


class AdminTakeView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.currency = "coins"
        options = [discord.SelectOption(label="Монеты", value="coins", emoji="🪙"), discord.SelectOption(label="Гемы", value="gems", emoji="💎")]
        self.add_item(make_select("Выбери валюту", options, self.currency_select, row=0))
        enter = discord.ui.Button(label="Ввести ID", emoji="📝", style=discord.ButtonStyle.primary, row=1)
        enter.callback = self.enter
        self.add_item(enter)
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def currency_select(self, interaction: discord.Interaction):
        self.currency = interaction.data["values"][0]
        await interaction.response.defer()

    async def enter(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AdminTakeValuesModal(self.author_id, self.currency))

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = discord.Embed(title="🛡️ Панель администратора", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=AdminPanelView(self.author_id))

async def open_admin_logs(interaction: discord.Interaction, author_id: int, page: int = 0):
    async with bot.db.execute("""
        SELECT admin_id, target_id, action, details, timestamp
        FROM admin_log ORDER BY id DESC LIMIT ? OFFSET ?
    """, (PAGE_SIZE, page * PAGE_SIZE)) as c:
        rows = await c.fetchall()

    async with bot.db.execute("SELECT COUNT(*) FROM admin_log") as c:
        total = (await c.fetchone())[0]

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = rows

    embed = discord.Embed(
        title="📜 Логи администрации",
        description=f"Страница {page + 1}/{total_pages} | Всего записей: {total}",
        color=0xe74c3c
    )
    if not chunk:
        embed.add_field(name="Пусто", value="Действий пока не было.")
    for admin_id, target_id, action, details, ts in chunk:
        embed.add_field(
            name=f"`{action}` — <@{admin_id}> → <@{target_id}>",
            value=f"{details}\n{ts}",
            inline=False
        )
    view = AdminLogsView(author_id, page, total_pages)
    await interaction.edit_original_response(embed=embed, view=view)


class AdminLogsView(discord.ui.View):
    def __init__(self, author_id: int, page: int, total_pages: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.page = page
        self.total_pages = total_pages
        if total_pages > 1:
            prev = discord.ui.Button(label="◀️ Стр.", style=discord.ButtonStyle.secondary)
            prev.callback = self.prev_page
            self.add_item(prev)
            nxt = discord.ui.Button(label="Стр. ▶️", style=discord.ButtonStyle.secondary)
            nxt.callback = self.next_page
            self.add_item(nxt)
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    async def prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await open_admin_logs(interaction, self.author_id, self.page - 1)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await open_admin_logs(interaction, self.author_id, self.page + 1)

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = discord.Embed(title="🛡️ Панель администратора", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=AdminPanelView(self.author_id))

# ---------- АДМИН-МОДАЛКИ ----------

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
            await interaction.followup.send("❌ ID и количество — числа > 0.", ephemeral=True)
            return
        async with bot.db.execute("SELECT 1 FROM players WHERE user_id = ?", (uid,)) as c:
            if not await c.fetchone():
                await bot.db.execute("INSERT OR IGNORE INTO players (user_id, coins) VALUES (?, ?)", (uid, DEFAULT_START_COINS))
        await bot.db.execute(
            f"UPDATE players SET {self.currency} = {self.currency} + ? WHERE user_id = ?",
            (amount, uid)
        )
        await bot.db.commit()
        await log_admin_action(
            self.author_id, uid, "grant",
            f"{self.currency} +{amount}"
        )
        unit = "🪙" if self.currency == "coins" else "💎"
        await interaction.followup.send(f"✅ Начислено {amount} {unit} <@{uid}>.", ephemeral=True)


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
            await interaction.followup.send("❌ ID и количество — числа > 0.", ephemeral=True)
            return
        async with bot.db.execute(f"SELECT {self.currency} FROM players WHERE user_id = ?", (uid,)) as c:
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
        await log_admin_action(
            self.author_id, uid, "grant",
            f"{self.currency} +{amount}"
        )
        unit = "🪙" if self.currency == "coins" else "💎"
        await interaction.followup.send(f"✅ Забрано {amount} {unit} у <@{uid}>.", ephemeral=True)


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
        (coins, gems, catalysts, grid_size, bonus, total_crafts, total_successes, last_coins, last_gems) = row

        async with bot.db.execute("""
            SELECT inv.location, inv.slot, i.name, i.emoji, inv.stars
            FROM inventory inv JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? ORDER BY inv.location, inv.slot
        """, (uid,)) as c:
            inv_rows = await c.fetchall()

        profile_items = [f"`{s}` {e} {n} ({st}⭐)" if st > 0 else f"`{s}` {e} {n}" for loc, s, n, e, st in inv_rows if loc == "profile"]
        storage_items = [f"`{s}` {e} {n} ({st}⭐)" if st > 0 else f"`{s}` {e} {n}" for loc, s, n, e, st in inv_rows if loc == "storage"]

        async with bot.db.execute("SELECT COUNT(*) FROM player_achievements WHERE user_id = ?", (uid,)) as c:
            ach_count = (await c.fetchone())[0]

        async with bot.db.execute("SELECT upgrade_id FROM player_upgrades WHERE user_id = ?", (uid,)) as c:
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
        embed.add_field(name=f"Замок ({len(profile_items)})", value="\n".join(profile_items) if profile_items else "пусто", inline=False)
        embed.add_field(name=f"Хранилище ({len(storage_items)})", value="\n".join(storage_items) if storage_items else "пусто", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)


class AdminEditModal(discord.ui.Modal, title="Изменить поле профиля"):
    user_id = discord.ui.TextInput(label="ID пользователя", required=True)
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
        if field not in ("coins", "gems", "catalysts", "grid_size", "storage_size", "income_bonus"):
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
        await log_admin_action(
            self.author_id, uid, "grant",
            f"{self.currency} +{amount}"
        )
        await interaction.followup.send(f"✅ `{field}` = **{parsed}** для <@{uid}>.", ephemeral=True)


class AdminResetModal(discord.ui.Modal, title="Сбросить прогресс"):
    user_id = discord.ui.TextInput(label="ID пользователя", required=True)
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
                grid_size = 9, storage_size = 36, income_bonus = 0.0,
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
        await log_admin_action(
            self.author_id, uid, "grant",
            f"{self.currency} +{amount}"
        )
        await interaction.followup.send(f"🗑️ Прогресс <@{uid}> сброшен.", ephemeral=True)


class AdminGiveItemModal(discord.ui.Modal, title="Выдать предмет"):
    user_id = discord.ui.TextInput(label="ID пользователя", required=True)
    item_id = discord.ui.TextInput(label="ID предмета", placeholder="basic_gen", required=True)
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
            await interaction.followup.send("❌ ID и количество — числа > 0.", ephemeral=True)
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

        if loc == "profile":
            try:
                to_profile, to_storage = await place_items(uid, item_id, qty)
            except ValueError as e:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)
                return
            msg = f"✅ Выдано {qty}×{emoji} {name} <@{uid}>."
            if to_storage > 0:
                msg += f"\n📦 {to_profile} в замок, {to_storage} в хранилище."
        else:
            storage_size = await get_storage_size(uid)
            async with bot.db.execute(
                "SELECT slot FROM inventory WHERE user_id = ? AND location = 'storage'", (uid,)
            ) as c:
                used = {r[0] for r in await c.fetchall()}
            free = [s for s in range(storage_size) if s not in used]
            if len(free) < qty:
                await interaction.followup.send(f"❌ В хранилище только {len(free)} слотов.", ephemeral=True)
                return
            for i in range(qty):
                await bot.db.execute(
                    "INSERT INTO inventory (user_id, slot, item_id, location, stars) VALUES (?, ?, ?, 'storage', 0)",
                    (uid, free[i], item_id)
                )
            await bot.db.commit()
            await log_admin_action(
            self.author_id, uid, "grant",
            f"{self.currency} +{amount}"
        )
            msg = f"✅ Выдано {qty}×{emoji} {name} в хранилище <@{uid}>."

        await sort_inventory(uid, "profile")
        await sort_inventory(uid, "storage")
        await interaction.followup.send(msg, ephemeral=True)


class AddGeneratorModal(discord.ui.Modal, title="Добавить генератор (шаг 1/2)"):
    id = discord.ui.TextInput(label="ID (латиницей)", placeholder="my_gen", required=True)
    name = discord.ui.TextInput(label="Название", placeholder="Мой генератор", required=True)
    price = discord.ui.TextInput(label="Цена", default="100", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item_id = self.id.value.strip()
        if not item_id.isalnum() or item_id != item_id.lower():
            await interaction.followup.send("❌ ID: латиница в нижнем регистре.", ephemeral=True)
            return
        async with bot.db.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)) as c:
            if await c.fetchone():
                await interaction.followup.send(f"❌ ID `{item_id}` уже существует.", ephemeral=True)
                return
        try:
            price = int(self.price.value)
            if price < 0:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ Цена >= 0.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Добавить генератор (шаг 2/2)",
            description=(
                f"ID: `{item_id}`\n"
                f"Название: **{self.name.value.strip()}**\n"
                f"Цена: 🪙 {price}\n\n"
                f"Заполни доходы и внешний вид:"
            ),
            color=0x3498db
        )
        await interaction.edit_original_response(
            embed=embed,
            view=AddGeneratorStep2View(self.author_id, item_id, self.name.value.strip(), price)
        )


class AddGeneratorStep2View(discord.ui.View):
    def __init__(self, author_id: int, item_id: str, name: str, price: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.item_id = item_id
        self.name = name
        self.price = price

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Заполнить", emoji="📝", style=discord.ButtonStyle.primary, row=0)
    async def fill(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            AddGeneratorStep2Modal(self.author_id, self.item_id, self.name, self.price)
        )

    @discord.ui.button(label="Отмена", emoji="❌", style=discord.ButtonStyle.secondary, row=0)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🛡️ Панель администратора", color=0xe74c3c)
        await interaction.edit_original_response(embed=embed, view=AdminPanelView(self.author_id))


class AddGeneratorStep2Modal(discord.ui.Modal, title="Добавить генератор (шаг 2/2)"):
    income_coins = discord.ui.TextInput(label="Доход монет/сек", default="0.001", required=True)
    income_gems = discord.ui.TextInput(label="Доход гемов/сек", default="0", required=True)
    emoji = discord.ui.TextInput(label="Эмодзи", default="⚙️", required=True)
    rarity = discord.ui.TextInput(label="Редкость", default="common", required=True)

    def __init__(self, author_id: int, item_id: str, name: str, price: int):
        super().__init__()
        self.author_id = author_id
        self.item_id = item_id
        self.name = name
        self.price = price

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rarity = self.rarity.value.strip().lower()
        if rarity not in RARITY_COLORS:
            await interaction.followup.send(
                f"❌ Редкость: {', '.join(RARITY_COLORS.keys())}.", ephemeral=True
            )
            return
        try:
            inc_c = float(self.income_coins.value)
            inc_g = float(self.income_gems.value)
            if inc_c < 0 or inc_g < 0:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ Доходы должны быть числами >= 0.", ephemeral=True)
            return

        await bot.db.execute(
            "INSERT INTO items (id, name, price, income_per_hour, emoji, rarity, buyable, income_gems_per_hour) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (self.item_id, self.name, self.price, inc_c, self.emoji.value.strip(), rarity, inc_g)
        )
        await bot.db.commit()
        await log_admin_action(
            self.author_id, uid, "grant",
            f"{self.currency} +{amount}"
        )
        await interaction.followup.send(
            f"✅ Генератор **{self.emoji.value} {self.name}** (`{self.item_id}`) добавлен.",
            ephemeral=True
        )


# ============================================================
#  ⚙️ НАСТРОЙКИ
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
        embed = discord.Embed(title="💰 Экономика", description="Цены, доход, стартовые монеты, потолок, лимит.", color=0x2ecc71)
        await interaction.edit_original_response(embed=embed, view=SettingsEconomyView(self.author_id))

    @discord.ui.button(label="Валюты", emoji="🪙", style=discord.ButtonStyle.secondary, row=1)
    async def currencies(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SettingsCurrencyModal(self.author_id))

    @discord.ui.button(label="Команды", emoji="🚫", style=discord.ButtonStyle.secondary, row=1)
    async def commands(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="🚫 Отключение команд", description="Выбери команды.", color=0xe74c3c)
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
        embed = discord.Embed(title="🎨 Кастомные эмодзи", description="Выбери, что изменить.", color=0x9b59b6)
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
            emoji_val = self.emoji.value.strip()
            if not is_valid_emoji(emoji_val):
                await interaction.followup.send(
                    "❌ Эмодзи должен быть юникод-символом (👑) или кастомным (`<:name:id>`).",
                    ephemeral=True
                )
                return
            async with bot.db.execute("SELECT name FROM items WHERE id = ?", (item_id,)) as c:
                item = await c.fetchone()
            if not item:
                await interaction.followup.send(f"❌ Предмет `{item_id}` не найден.", ephemeral=True)
                return
            custom = settings["custom_emojis"]
            custom[item_id] = emoji_val
            await save_setting(guild_id, "custom_emojis", custom)
            changes.append(f"🎨 {item[0]}: {emoji_val}")
        await interaction.followup.send(
            "✅ Обновлено:\n" + "\n".join(changes) if changes else "ℹ️ Ничего не изменено.", ephemeral=True
        )


class SettingsEconomyView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Цена", emoji="🏷️", style=discord.ButtonStyle.primary, row=0)
    async def price(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditItemPriceModal(self.author_id))

    @discord.ui.button(label="Доход", emoji="📈", style=discord.ButtonStyle.primary, row=0)
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


class EditItemPriceModal(discord.ui.Modal, title="Изменить цену"):
    item_id = discord.ui.TextInput(label="ID предмета", placeholder="basic_gen", required=True)
    price = discord.ui.TextInput(label="Новая цена", required=True)

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
            await interaction.followup.send("❌ Цена >= 0.", ephemeral=True)
            return
        async with bot.db.execute("SELECT name FROM items WHERE id = ?", (item_id,)) as c:
            item = await c.fetchone()
        if not item:
            await interaction.followup.send(f"❌ `{item_id}` не найден.", ephemeral=True)
            return
        await bot.db.execute("UPDATE items SET price = ? WHERE id = ?", (price, item_id))
        await bot.db.commit()
        await interaction.followup.send(f"✅ Цена **{item[0]}** = 🪙 {price}.", ephemeral=True)


class EditItemIncomeModal(discord.ui.Modal, title="Изменить доход"):
    item_id = discord.ui.TextInput(label="ID предмета", placeholder="basic_gen", required=True)
    income_coins = discord.ui.TextInput(label="Доход монет/сек", required=False)
    income_gems = discord.ui.TextInput(label="Доход гемов/сек", required=False)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item_id = self.item_id.value.strip()
        async with bot.db.execute("SELECT name FROM items WHERE id = ?", (item_id,)) as c:
            item = await c.fetchone()
        if not item:
            await interaction.followup.send(f"❌ `{item_id}` не найден.", ephemeral=True)
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
            f"✅ Доход **{item[0]}**: {', '.join(updates) if updates else 'без изменений'}.", ephemeral=True
        )


class EditStartCoinsModal(discord.ui.Modal, title="Стартовые монеты"):
    value = discord.ui.TextInput(label="Монет новым игрокам", default="3", required=True)

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
            await interaction.followup.send("❌ Значение >= 0.", ephemeral=True)
            return
        await save_setting(interaction.guild_id, "start_coins", val)
        await interaction.followup.send(f"✅ Стартовые монеты: **{val}**.", ephemeral=True)


class EditGemCapModal(discord.ui.Modal, title="Потолок гемов"):
    value = discord.ui.TextInput(label="Максимум гемов за заход", default="6", required=True)

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
            await interaction.followup.send("❌ Значение >= 0.", ephemeral=True)
            return
        await save_setting(interaction.guild_id, "gem_cap", val)
        await interaction.followup.send(f"✅ Потолок гемов: **{val}**.", ephemeral=True)


class EditPassiveLimitModal(discord.ui.Modal, title="Лимит пассивного дохода"):
    value = discord.ui.TextInput(label="Максимум накопления", default="100000", required=True)

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
            await interaction.followup.send("❌ Значение >= 0.", ephemeral=True)
            return
        await save_setting(interaction.guild_id, "passive_limit", val)
        await interaction.followup.send(f"✅ Лимит дохода: **{val}**.", ephemeral=True)


class SettingsCurrencyModal(discord.ui.Modal, title="Названия валют"):
    coins = discord.ui.TextInput(label="Монеты", default=DEFAULT_CURRENCY_COINS, required=True)
    gems = discord.ui.TextInput(label="Гемы", default=DEFAULT_CURRENCY_GEMS, required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        await save_setting(guild_id, "currency_coins", self.coins.value.strip())
        await save_setting(guild_id, "currency_gems", self.gems.value.strip())
        await interaction.followup.send(f"✅ Валюты: **{self.coins.value}** / **{self.gems.value}**.", ephemeral=True)


class SettingsCommandsView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        options = [discord.SelectOption(label=name, value=key) for key, name in TOGGLEABLE_COMMANDS.items()]
        self.add_item(make_select("Выбери команды для отключения", options, self.toggle, row=0))
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=1)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def toggle(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        await save_setting(guild_id, "disabled_commands", list(interaction.data["values"]))
        names = [TOGGLEABLE_COMMANDS[c] for c in interaction.data["values"]]
        await interaction.followup.send(f"✅ Отключено: {', '.join(names) if names else 'ничего'}.", ephemeral=True)

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = discord.Embed(title="🔧 Настройки сервера", color=0x808080)
        await interaction.edit_original_response(embed=embed, view=SettingsView(self.author_id))


class SettingsStatusRoleModal(discord.ui.Modal, title="Роль за статус"):
    status = discord.ui.TextInput(label="Статус (vip/platinum/gold/diamond)", required=True)
    role_id = discord.ui.TextInput(label="ID роли", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        status = self.status.value.strip().lower()
        if status not in ("vip", "platinum", "gold", "diamond"):
            await interaction.followup.send("❌ vip/platinum/gold/diamond.", ephemeral=True)
            return
        try:
            role_id = int(self.role_id.value)
        except ValueError:
            await interaction.followup.send("❌ ID роли — число.", ephemeral=True)
            return
        guild_id = interaction.guild_id
        settings = await get_settings(guild_id)
        roles = settings["status_roles"]
        roles[status] = role_id
        await save_setting(guild_id, "status_roles", roles)
        await interaction.followup.send(f"✅ Роль <@&{role_id}> за статус **{status}**.", ephemeral=True)


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


class EditAchievementRewardModal(discord.ui.Modal, title="Изменить награду"):
    ach_id = discord.ui.TextInput(label="ID достижения", required=True)
    reward = discord.ui.TextInput(label="Награда (гемы)", required=True)

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
            await interaction.followup.send("❌ Награда >= 0.", ephemeral=True)
            return
        async with bot.db.execute("SELECT name FROM achievements WHERE id = ?", (ach_id,)) as c:
            item = await c.fetchone()
        if not item:
            await interaction.followup.send("❌ Не найдено.", ephemeral=True)
            return
        await bot.db.execute("UPDATE achievements SET reward_gems = ? WHERE id = ?", (reward, ach_id))
        await bot.db.commit()
        await interaction.followup.send(f"✅ Награда «{item[0]}» = 💎 {reward}.", ephemeral=True)


class DeleteAchievementModal(discord.ui.Modal, title="Удалить достижение"):
    ach_id = discord.ui.TextInput(label="ID достижения", required=True)
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
            await interaction.followup.send("❌ Не найдено.", ephemeral=True)
            return
        await bot.db.execute("DELETE FROM achievements WHERE id = ?", (ach_id,))
        await bot.db.execute("DELETE FROM player_achievements WHERE achievement_id = ?", (ach_id,))
        await bot.db.commit()
        await interaction.followup.send(f"🗑️ «{item[0]}» удалено.", ephemeral=True)


class AddAchievementModal(discord.ui.Modal, title="Добавить достижение"):
    ach_id = discord.ui.TextInput(label="ID (латиницей)", required=True)
    name = discord.ui.TextInput(label="Название", required=True)
    desc = discord.ui.TextInput(label="Описание", required=True)
    reward = discord.ui.TextInput(label="Награда", default="10", required=True)
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
                await interaction.followup.send("❌ Уже существует.", ephemeral=True)
                return
        try:
            reward = int(self.reward.value)
        except ValueError:
            await interaction.followup.send("❌ Награда — число.", ephemeral=True)
            return
        await bot.db.execute(
            "INSERT INTO achievements (id, name, description, reward_gems, emoji) VALUES (?, ?, ?, ?, ?)",
            (ach_id, self.name.value.strip(), self.desc.value.strip(), reward, self.emoji.value.strip())
        )
        await bot.db.commit()
        await interaction.followup.send(f"✅ «{self.name.value}» добавлено.", ephemeral=True)


class SettingsAdminRoleModal(discord.ui.Modal, title="Роль администратора"):
    role_id = discord.ui.TextInput(label="ID роли (0 — сбросить)", required=True)

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
            await interaction.followup.send("❌ ID роли >= 0.", ephemeral=True)
            return
        if role_id == 0:
            await save_setting(guild_id, "admin_role_id", None)
            await interaction.followup.send("✅ Роль админа сброшена.", ephemeral=True)
            return
        guild = interaction.guild
        role = guild.get_role(role_id) if guild else None
        if not role:
            await interaction.followup.send(f"❌ Роль `{role_id}` не найдена.", ephemeral=True)
            return
        await save_setting(guild_id, "admin_role_id", role_id)
        await interaction.followup.send(f"✅ Роль <@&{role_id}> получила доступ.", ephemeral=True)


class SettingsEmojisView(discord.ui.View):
    def __init__(self, author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        options = [discord.SelectOption(label=name, value=key, emoji=default) for key, (name, default) in EMOJI_KEYS.items()]
        self.add_item(make_select("Что изменить?", options, self.emoji_select, row=0))

        # Кнопка "Эмодзи по звёздам"
        stars = discord.ui.Button(label="Эмодзи по звёздам", emoji="⭐", style=discord.ButtonStyle.primary, row=1)
        stars.callback = self.star_emoji_select
        self.add_item(stars)

        # Кнопка "Назад"
        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Не твоё меню.", ephemeral=True)
            return False
        return True

    async def emoji_select(self, interaction: discord.Interaction):
        key = interaction.data["values"][0]
        await interaction.response.send_modal(EditEmojiModal(self.author_id, key))

    async def star_emoji_select(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await open_star_emoji_select(interaction, self.author_id, page=0)

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = discord.Embed(title="🔧 Настройки сервера", color=0x808080)
        await interaction.edit_original_response(embed=embed, view=SettingsView(self.author_id))

async def open_star_emoji_select(interaction: discord.Interaction, author_id: int, page: int = 0):
    async with bot.db.execute("SELECT id, name FROM items WHERE buyable = 1 ORDER BY price ASC") as c:
        items = await c.fetchall()

    total_pages = max(1, (len(items) + 9) // 10)  # по 10 на страницу
    page = max(0, min(page, total_pages - 1))
    chunk = items[page * 10: page * 10 + 10]

    options = [discord.SelectOption(label=name, value=item_id) for item_id, name in chunk]

    embed = discord.Embed(
        title="⭐ Эмодзи по звёздам",
        description=f"Страница {page + 1}/{total_pages}\nВыбери генератор, для которого настроить эмодзи 0★–5★.",
        color=0xf1c40f
    )
    view = StarEmojiPaginatedView(author_id, options, page, total_pages)
    await interaction.edit_original_response(embed=embed, view=view)


class StarEmojiPaginatedView(discord.ui.View):
    def __init__(self, author_id: int, options: list[discord.SelectOption], page: int, total_pages: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.page = page
        self.total_pages = total_pages
        self.add_item(make_select("Выбери генератор", options, self.item_select, row=0))

        if total_pages > 1:
            prev = discord.ui.Button(label="◀️ Стр.", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self.prev_page
            self.add_item(prev)
            nxt = discord.ui.Button(label="Стр. ▶️", style=discord.ButtonStyle.secondary, row=1)
            nxt.callback = self.next_page
            self.add_item(nxt)

        back = discord.ui.Button(label="Назад", emoji="◀️", style=discord.ButtonStyle.danger, row=2)
        back.callback = self.back
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    async def item_select(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        await interaction.response.send_modal(StarEmojiModal1(self.author_id, item_id))

    async def prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await open_star_emoji_select(interaction, self.author_id, self.page - 1)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await open_star_emoji_select(interaction, self.author_id, self.page + 1)

    async def back(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = discord.Embed(title="🎨 Кастомные эмодзи", color=0x9b59b6)
        await interaction.edit_original_response(embed=embed, view=SettingsEmojisView(self.author_id))

class StarEmojiModal1(discord.ui.Modal, title="Эмодзи по звёздам (1/2)"):
    e0 = discord.ui.TextInput(label="0★", required=False, placeholder="<:basic_0:123>")
    e1 = discord.ui.TextInput(label="1★", required=False, placeholder="<:basic_1:123>")
    e2 = discord.ui.TextInput(label="2★", required=False, placeholder="<:basic_2:123>")

    def __init__(self, author_id: int, item_id: str):
        super().__init__()
        self.author_id = author_id
        self.item_id = item_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Сохраняем первую партию
        async with bot.db.execute("SELECT emoji_by_star FROM items WHERE id = ?", (self.item_id,)) as c:
            row = await c.fetchone()
        emojis = json.loads(row[0] or "{}") if row else {}
        
        for star, field in enumerate([self.e0, self.e1, self.e2]):
            val = field.value.strip() if field.value else ""
            if val:
                emojis[str(star)] = val
        
        await bot.db.execute(
            "UPDATE items SET emoji_by_star = ? WHERE id = ?",
            (json.dumps(emojis, ensure_ascii=False), self.item_id)
        )
        await bot.db.commit()

        # Показываем кнопку для второй части
        embed = discord.Embed(
            title="Эмодзи по звёздам (1/2)",
            description="Первая часть (0★–2★) сохранена. Теперь настрой 3★–5★.",
            color=0xf1c40f
        )
        view = discord.ui.View()
        nxt = discord.ui.Button(label="Далее (3★–5★)", emoji="➡️", style=discord.ButtonStyle.primary)
        nxt.callback = lambda i: i.response.send_modal(StarEmojiModal2(self.author_id, self.item_id))
        view.add_item(nxt)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class StarEmojiModal2(discord.ui.Modal, title="Эмодзи по звёздам (2/2)"):
    e3 = discord.ui.TextInput(label="3★", required=False, placeholder="<:basic_3:123>")
    e4 = discord.ui.TextInput(label="4★", required=False, placeholder="<:basic_4:123>")
    e5 = discord.ui.TextInput(label="5★", required=False, placeholder="<:basic_5:123>")

    def __init__(self, author_id: int, item_id: str):
        super().__init__()
        self.author_id = author_id
        self.item_id = item_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        async with bot.db.execute("SELECT name, emoji_by_star FROM items WHERE id = ?", (self.item_id,)) as c:
            row = await c.fetchone()
        if not row:
            return await interaction.followup.send("❌ Генератор не найден.", ephemeral=True)

        name, emoji_json = row
        emojis = json.loads(emoji_json or "{}")

        for star, field in enumerate([self.e3, self.e4, self.e5], start=3):
            val = field.value.strip() if field.value else ""
            if val:
                emojis[str(star)] = val

        await bot.db.execute(
            "UPDATE items SET emoji_by_star = ? WHERE id = ?",
            (json.dumps(emojis, ensure_ascii=False), self.item_id)
        )
        await bot.db.commit()

        count = len(emojis)
        await interaction.followup.send(
            f"✅ Для **{name}** сохранено {count} эмодзи: "
            f"{', '.join(f'{k}★' for k in sorted(emojis.keys(), key=int))}.",
            ephemeral=True
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
            "Попроси администратора выдать роль или настроить её в Настройках.",
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
