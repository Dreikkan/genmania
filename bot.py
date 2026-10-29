# ============================================================
#  🏰 Castle Mania — Discord Bot (только меню)
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
GEM_GEN_CAP = 3
SELL_RATE = 0.15

START_COINS = 10
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
            ("total_raids_won", "INTEGER DEFAULT 0"),
            ("total_votes", "INTEGER DEFAULT 0"),
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
                bot_name TEXT DEFAULT 'Castle Mania',
                custom_emojis TEXT DEFAULT '{}'
            )
        """)

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
            ("basic_gen", "Базовый генератор",    10, 3,   "⚙️", "common",    1, 0),
            ("wood_gen",  "Деревянный генератор",  50, 8,   "🪵", "uncommon",  1, 0),
            ("stone_gen", "Каменный генератор",   200, 20,  "🪨", "rare",      1, 0),
            ("iron_gen",  "Железный генератор",   800, 50,  "⛓️", "epic",      1, 0),
            ("gold_gen",  "Золотой генератор",   3000, 120, "🪙", "legendary", 1, 0),
            ("gem_gen",   "Гемовый генератор",  12000, 0,   "💎", "mythic",    0, 0.05),
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
#  🧰 ХЕЛПЕРЫ
# ============================================================

def today_str():
    return datetime.date.today().isoformat()


async def get_player_stats(user_id: int):
    async with bot.db.execute(
        "SELECT grid_size, income_bonus, gems, coins FROM players WHERE user_id = ?",
        (user_id,)
    ) as c:
        row = await c.fetchone()

    if not row:
        await bot.db.execute(
            "INSERT OR IGNORE INTO players (user_id, coins) VALUES (?, ?)",
            (user_id, START_COINS)
        )
        await bot.db.commit()
        return START_GRID, 0.0, 0, START_COINS

    return row[0] or START_GRID, row[1] or 0.0, row[2] or 0, row[3] or 0


async def get_grid_size(user_id: int) -> int:
    size, _, _, _ = await get_player_stats(user_id)
    return size


async def get_guild_emojis(guild_id: int) -> dict:
    if not guild_id:
        return {}
    async with bot.db.execute(
        "SELECT custom_emojis FROM guild_settings WHERE guild_id = ?", (guild_id,)
    ) as c:
        row = await c.fetchone()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except Exception:
            return {}
    return {}


async def get_hourly_income(user_id: int) -> tuple[float, float]:
    grid_size, bonus, gems, coins = await get_player_stats(user_id)
    async with bot.db.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN inv.location = 'profile' THEN i.income_per_hour ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN inv.location = 'profile' THEN i.income_gems_per_hour ELSE 0 END), 0)
        FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ?
    """, (user_id,)) as c:
        hourly_coins_raw, hourly_gems_raw = await c.fetchone()
    multiplier = 1 + bonus
    return hourly_coins_raw * multiplier, hourly_gems_raw * multiplier


async def calculate_passive_income(user_id: int):
    async with bot.db.execute(
        "SELECT last_collected, last_gem_collected, income_bonus FROM players WHERE user_id = ?",
        (user_id,)
    ) as c:
        row = await c.fetchone()
    if not row:
        return 0, 0
    last_coins_str, last_gems_str, bonus = row
    multiplier = 1 + (bonus or 0)

    now = datetime.datetime.now()

    async with bot.db.execute("""
        SELECT SUM(i.income_per_hour) FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'profile'
    """, (user_id,)) as c:
        hourly_coins = (await c.fetchone())[0] or 0

    coins = 0
    if hourly_coins > 0:
        last = datetime.datetime.fromisoformat(last_coins_str)
        coins = int(((now - last).total_seconds() / 3600) * hourly_coins * multiplier)

    async with bot.db.execute("""
        SELECT SUM(i.income_gems_per_hour) FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND i.income_gems_per_hour > 0 AND inv.location = 'profile'
    """, (user_id,)) as c:
        hourly_gems = (await c.fetchone())[0] or 0

    gems = 0
    if hourly_gems > 0:
        last = datetime.datetime.fromisoformat(last_gems_str)
        hours = (now - last).total_seconds() / 3600
        raw = hours * hourly_gems * multiplier
        gems = min(int(raw), GEM_GEN_CAP)

    return coins, gems


async def collect_income(user_id: int):
    coins_earned, gems_earned = await calculate_passive_income(user_id)
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

async def check_achievements(user_id: int, extra: dict = None):
    extra = extra or {}

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

async def build_main_embed(interaction: discord.Interaction, notice: str = None) -> discord.Embed:
    user_id = interaction.user.id
    await collect_income(user_id)
    grid_size, bonus, gems, coins = await get_player_stats(user_id)
    hourly_coins, hourly_gems = await get_hourly_income(user_id)

    parts = []
    if hourly_coins > 0:
        parts.append(f"🪙 {hourly_coins:.2f}/час")
    if hourly_gems > 0:
        parts.append(f"💎 {hourly_gems:.3f}/час")
    income_str = " | ".join(parts) if parts else "нет генераторов"

    embed = discord.Embed(
        title=f"🏰 Замок {interaction.user.name}",
        description=notice or "Выбери раздел кнопками ниже.",
        color=0x00ff00
    )
    embed.add_field(name="Кошелёк", value=f"🪙 {coins} | 💎 {gems}", inline=False)
    embed.add_field(name="Доход", value=income_str, inline=False)
    embed.add_field(name="Бонус", value=f"+{int(bonus * 100)}%", inline=True)
    embed.add_field(name="Сетка", value=f"{grid_size} слотов", inline=True)
    return embed


async def build_profile_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    guild_id = interaction.guild_id

    grid_size, bonus, gems, coins = await get_player_stats(user_id)

    async with bot.db.execute("""
        SELECT inv.slot, i.id, i.emoji FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'profile'
    """, (user_id,)) as c:
        rows = await c.fetchall()

    custom_emojis = await get_guild_emojis(guild_id)
    items = {slot: custom_emojis.get(item_id, default) for slot, item_id, default in rows}

    hourly_coins, hourly_gems = await get_hourly_income(user_id)
    parts = []
    if hourly_coins > 0:
        parts.append(f"🪙 {hourly_coins:.2f}/час")
    if hourly_gems > 0:
        parts.append(f"💎 {hourly_gems:.3f}/час")
    income_str = " | ".join(parts) if parts else "нет генераторов"

    width = int(grid_size ** 0.5)
    embed = discord.Embed(title=f"🏰 Замок {interaction.user.name}", color=0x00ff00)
    embed.add_field(name="Кошелёк", value=f"🪙 {coins} | 💎 {gems}", inline=False)
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
    grid_size = await get_grid_size(user_id)

    async with bot.db.execute("""
        SELECT inv.slot, i.id, i.emoji FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'storage'
    """, (user_id,)) as c:
        rows = await c.fetchall()

    custom_emojis = await get_guild_emojis(guild_id)
    items = {slot: custom_emojis.get(item_id, default) for slot, item_id, default in rows}

    width = int(grid_size ** 0.5)
    embed = discord.Embed(title=f"🎒 Хранилище {interaction.user.name}", color=0x808080)
    grid_str = ""
    for slot in range(grid_size):
        grid_str += f"{items.get(slot, '⬛')} "
        if (slot + 1) % width == 0:
            grid_str += "\n"
    embed.add_field(name="Предметы (эффекты отключены)", value=f"```\n{grid_str}\n```", inline=False)
    return embed


async def build_shop_page(interaction: discord.Interaction, page: int) -> tuple[discord.Embed, int]:
    guild_id = interaction.guild_id
    custom_emojis = await get_guild_emojis(guild_id)

    async with bot.db.execute(
        "SELECT id, name, price, income_per_hour, emoji, rarity, income_gems_per_hour "
        "FROM items WHERE buyable = 1"
    ) as c:
        rows = await c.fetchall()

    total = len(rows)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page * PAGE_SIZE: page * PAGE_SIZE + PAGE_SIZE]

    embed = discord.Embed(title="🛒 Магазин", description=f"Страница {page + 1}/{total_pages}", color=0xf1c40f)
    for item_id, name, price, income_coins, default_emoji, rarity, income_gems in chunk:
        emoji = custom_emojis.get(item_id, default_emoji)
        inc = []
        if income_coins > 0:
            inc.append(f"🪙 {income_coins}/час")
        if income_gems > 0:
            inc.append(f"💎 {income_gems}/час")
        inc_str = " ".join(inc) if inc else "без дохода"
        embed.add_field(
            name=f"{emoji} {name} (`{item_id}`)",
            value=f"Цена: 🪙 {price} | {inc_str} | {RARITY_NAMES.get(rarity, rarity)}",
            inline=False
        )
    return embed, total_pages


async def build_achievements_page(interaction: discord.Interaction, page: int) -> tuple[discord.Embed, int]:
    user_id = interaction.user.id

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
        title=f"🏆 Достижения — {interaction.user.name}",
        description=f"Страница {page + 1}/{total_pages} | Открыто: {len(unlocked)}/{total}",
        color=0xf1c40f
    )
    for ach_id, name, desc, reward, emoji in chunk:
        status = "✅ Открыто" if ach_id in unlocked else "🔒 Закрыто"
        embed.add_field(
            name=f"{emoji} {name}",
            value=f"{desc}\nНаграда: 💎 {reward} — {status}",
            inline=False
        )
    return embed, total_pages


async def build_upgrades_page(interaction: discord.Interaction, page: int) -> tuple[discord.Embed, int]:
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
        title="💎 Магазин улучшений",
        description=f"Страница {page + 1}/{total_pages}",
        color=0x9b59b6
    )
    for gid, name, desc, price, emoji in chunk:
        status = "✅ Куплено" if gid in owned else "🔒 Не куплено"
        embed.add_field(
            name=f"{emoji} {name} (`{gid}`)",
            value=f"{desc}\nЦена: 💎 {price}\n{status}",
            inline=False
        )
    return embed, total_pages


async def build_quests_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id
    quests, progress, claimed = await get_or_create_daily_quests(user_id)

    embed = discord.Embed(title="📅 Ежедневные задания", color=0x3498db)
    for qid in quests:
        desc, target, reward = QUEST_POOL[qid]
        done = progress[qid] >= target
        status = "✅ Получено" if qid in claimed else ("🎁 Готово" if done else "⏳ В процессе")
        embed.add_field(
            name=desc,
            value=f"Прогресс: {progress[qid]}/{target}\nНаграда: 💎 {reward}\n{status}",
            inline=False
        )
    return embed


async def build_stats_embed(interaction: discord.Interaction) -> discord.Embed:
    user_id = interaction.user.id

    async with bot.db.execute("""
        SELECT COUNT(*), SUM(success), SUM(gems_spent), SUM(catalyst_used)
        FROM craft_log WHERE user_id = ?
    """, (user_id,)) as c:
        total, successes, gems_spent, catalysts_used = await c.fetchone()

    if not total:
        return discord.Embed(
            title="📊 Статистика синтеза",
            description="У тебя пока нет ни одного синтеза.",
            color=0x9b59b6
        )

    successes = successes or 0
    failures = total - successes
    gems_spent = gems_spent or 0
    catalysts_used = catalysts_used or 0
    winrate = (successes / total) * 100

    embed = discord.Embed(title=f"📊 Статистика — {interaction.user.name}", color=0x9b59b6)
    embed.add_field(name="Попыток", value=str(total), inline=True)
    embed.add_field(name="✅ Успехов", value=str(successes), inline=True)
    embed.add_field(name="💥 Провалов", value=str(failures), inline=True)
    embed.add_field(name="Винрейт", value=f"{winrate:.1f}%", inline=True)
    embed.add_field(name="💎 Потрачено", value=str(gems_spent), inline=True)
    embed.add_field(name="🧪 Катализаторов", value=str(catalysts_used), inline=True)
    return embed


# ============================================================
#  🎛️ VIEW'Ы
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
        await interaction.response.defer()
        embed = await build_storage_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=StorageView(self.author_id))

    @discord.ui.button(label="Магазин", emoji="🛒", style=discord.ButtonStyle.secondary, row=0)
    async def tab_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, _ = await build_shop_page(interaction, 0)
        await interaction.edit_original_response(embed=embed, view=ShopView(self.author_id, 0))

    @discord.ui.button(label="Улучшения", emoji="💎", style=discord.ButtonStyle.secondary, row=0)
    async def tab_upgrades(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, _ = await build_upgrades_page(interaction, 0)
        await interaction.edit_original_response(embed=embed, view=UpgradesView(self.author_id, 0))

    @discord.ui.button(label="Достижения", emoji="🏆", style=discord.ButtonStyle.secondary, row=1)
    async def tab_achievements(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed, _ = await build_achievements_page(interaction, 0)
        await interaction.edit_original_response(embed=embed, view=AchievementsView(self.author_id, 0))

    @discord.ui.button(label="Задания", emoji="📅", style=discord.ButtonStyle.secondary, row=1)
    async def tab_quests(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_quests_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=QuestsView(self.author_id))

    @discord.ui.button(label="Статистика", emoji="📊", style=discord.ButtonStyle.secondary, row=1)
    async def tab_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_stats_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=StatsView(self.author_id))

    @discord.ui.button(label="Убрать", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class BackOnlyView(BaseView):
    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_main(interaction)


class ProfileView(BackOnlyView):
    @discord.ui.button(label="Переместить", emoji="🔀", style=discord.ButtonStyle.primary, row=1)
    async def move_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MoveModal(self.author_id))

    @discord.ui.button(label="Синтез", emoji="⚗️", style=discord.ButtonStyle.success, row=1)
    async def craft_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CraftModal(self.author_id))

    @discord.ui.button(label="Катализатор", emoji="🧪", style=discord.ButtonStyle.secondary, row=1)
    async def catalyst_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CatalystModal(self.author_id))


class StorageView(BackOnlyView):
    @discord.ui.button(label="Переместить", emoji="🔀", style=discord.ButtonStyle.primary, row=1)
    async def move_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MoveModal(self.author_id))


class QuestsView(BackOnlyView):
    @discord.ui.button(label="Забрать награду", emoji="🎁", style=discord.ButtonStyle.success, row=1)
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ClaimQuestModal(self.author_id))


class StatsView(BackOnlyView):
    pass


class ShopView(BaseView):
    def __init__(self, author_id: int, page: int):
        super().__init__(author_id)
        self.page = page

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_main(interaction)

    @discord.ui.button(label="Купить", emoji="🛍️", style=discord.ButtonStyle.success, row=0)
    async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BuyItemModal(self.author_id))

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


class UpgradesView(BaseView):
    def __init__(self, author_id: int, page: int):
        super().__init__(author_id)
        self.page = page

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.back_to_main(interaction)

    @discord.ui.button(label="Купить улучшение", emoji="💳", style=discord.ButtonStyle.success, row=0)
    async def buy_upgrade(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BuyUpgradeModal(self.author_id))

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
#  📝 МОДАЛЬНЫЕ ОКНА
# ============================================================

class BuyItemModal(discord.ui.Modal, title="Купить предмет"):
    item_id = discord.ui.TextInput(label="ID предмета", placeholder="например, basic_gen", required=True)
    quantity = discord.ui.TextInput(label="Количество", default="1", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        try:
            qty = int(self.quantity.value)
            if qty < 1:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ Количество должно быть числом больше 0.", ephemeral=True)
            return

        item_id = self.item_id.value.strip()
        async with bot.db.execute("SELECT price, name, buyable FROM items WHERE id = ?", (item_id,)) as c:
            item = await c.fetchone()
        if not item:
            await interaction.followup.send("❌ Предмет не найден.", ephemeral=True)
            return

        price, name, buyable = item
        if not buyable:
            await interaction.followup.send(f"❌ **{name}** нельзя купить (только синтез).", ephemeral=True)
            return

        total_cost = price * qty
        async with bot.db.execute("SELECT coins FROM players WHERE user_id = ?", (user_id,)) as c:
            balance = (await c.fetchone())[0]
        if balance < total_cost:
            await interaction.followup.send(f"❌ Не хватает монет. Нужно {total_cost}.", ephemeral=True)
            return

        grid_size = await get_grid_size(user_id)
        async with bot.db.execute(
            "SELECT slot FROM inventory WHERE user_id = ? AND location = 'profile'", (user_id,)
        ) as c:
            used = {r[0] for r in await c.fetchall()}
        free = [s for s in range(grid_size) if s not in used]
        if len(free) < qty:
            await interaction.followup.send(f"❌ В замке нет места! (Максимум {grid_size})", ephemeral=True)
            return

        await bot.db.execute("UPDATE players SET coins = coins - ? WHERE user_id = ?", (total_cost, user_id))
        for i in range(qty):
            await bot.db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) VALUES (?, ?, ?, 'profile')",
                (user_id, free[i], item_id)
            )
        await bot.db.commit()

        await update_quest_progress(user_id, "buy_3", qty)
        unlocked = await check_achievements(user_id)

        msg = f"✅ Куплено **{name}** x{qty} за {total_cost} монет."
        if unlocked:
            msg += "\n🏆 " + ", ".join(f"{e} {n}" for e, n, _ in unlocked)
        await interaction.followup.send(msg, ephemeral=True)


class MoveModal(discord.ui.Modal, title="Переместить предмет"):
    slot = discord.ui.TextInput(label="Номер слота", placeholder="0–35", required=True)
    to = discord.ui.TextInput(label="Куда (profile/storage)", default="storage", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        try:
            slot = int(self.slot.value)
        except ValueError:
            await interaction.followup.send("❌ Номер слота должен быть числом.", ephemeral=True)
            return
        to = self.to.value.strip()
        if to not in ("profile", "storage"):
            await interaction.followup.send("❌ Куда: `profile` или `storage`.", ephemeral=True)
            return

        grid_size = await get_grid_size(user_id)
        if slot < 0 or slot >= grid_size:
            await interaction.followup.send(f"❌ Слот от 0 до {grid_size - 1}.", ephemeral=True)
            return

        async with bot.db.execute(
            "SELECT item_id, location FROM inventory WHERE user_id = ? AND slot = ?", (user_id, slot)
        ) as c:
            row = await c.fetchone()
        if not row:
            await interaction.followup.send("❌ В этом слоте нет предмета.", ephemeral=True)
            return

        item_id, current = row
        if current == to:
            await interaction.followup.send("❌ Предмет уже там.", ephemeral=True)
            return

        async with bot.db.execute(
            "SELECT 1 FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
            (user_id, to, slot)
        ) as c:
            if await c.fetchone():
                await interaction.followup.send("❌ Целевой слот занят.", ephemeral=True)
                return

        await bot.db.execute(
            "DELETE FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
            (user_id, current, slot)
        )
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location) VALUES (?, ?, ?, ?)",
            (user_id, slot, item_id, to)
        )
        await bot.db.commit()

        await update_quest_progress(user_id, "move_2")
        await interaction.followup.send("✅ Предмет перемещён.", ephemeral=True)


class CraftModal(discord.ui.Modal, title="Синтез"):
    item_id = discord.ui.TextInput(label="ID предмета", placeholder="basic_gen", required=True)
    use_catalyst = discord.ui.TextInput(label="Катализатор (да/нет)", default="нет", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        item_id = self.item_id.value.strip()
        use_cat = self.use_catalyst.value.strip().lower() in ("да", "yes", "1", "true")

        if item_id not in CRAFT_CHAIN:
            await interaction.followup.send("❌ Этот предмет нельзя синтезировать.", ephemeral=True)
            return

        next_id = CRAFT_CHAIN[item_id]
        settings = CRAFT_SETTINGS.get(item_id, {"chance": 1.0, "gems": 0})
        base_chance, gem_cost = settings["chance"], settings["gems"]

        async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (item_id,)) as c:
            src = await c.fetchone()
        async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (next_id,)) as c:
            dst = await c.fetchone()
        if not src or not dst:
            await interaction.followup.send("❌ Ошибка конфигурации.", ephemeral=True)
            return

        src_name, src_emoji = src
        dst_name, dst_emoji = dst

        async with bot.db.execute(
            "SELECT location, slot FROM inventory WHERE user_id = ? AND item_id = ?", (user_id, item_id)
        ) as c:
            owned = await c.fetchall()
        if len(owned) < CRAFT_COST:
            await interaction.followup.send(f"❌ Нужно {CRAFT_COST} × {src_name}.", ephemeral=True)
            return

        async with bot.db.execute("SELECT gems, catalysts FROM players WHERE user_id = ?", (user_id,)) as c:
            gems, cats = await c.fetchone()
        if gems < gem_cost:
            await interaction.followup.send(f"❌ Нужно 💎 {gem_cost}.", ephemeral=True)
            return
        if use_cat and cats < 1:
            await interaction.followup.send("❌ Нет катализаторов.", ephemeral=True)
            return

        grid_size = await get_grid_size(user_id)
        async with bot.db.execute(
            "SELECT slot FROM inventory WHERE user_id = ? AND location = 'profile'", (user_id,)
        ) as c:
            used = {r[0] for r in await c.fetchall()}
        free = [s for s in range(grid_size) if s not in used]
        if not free:
            await interaction.followup.send("❌ В замке нет места.", ephemeral=True)
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

        await interaction.followup.send(msg, ephemeral=True)


class CatalystModal(discord.ui.Modal, title="Купить катализатор"):
    quantity = discord.ui.TextInput(label="Количество", default="1", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        try:
            qty = int(self.quantity.value)
            if qty < 1:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ Количество > 0.", ephemeral=True)
            return

        total = CATALYST_PRICE * qty
        async with bot.db.execute("SELECT gems, catalysts FROM players WHERE user_id = ?", (user_id,)) as c:
            gems, owned = await c.fetchone()
        if gems < total:
            await interaction.followup.send(f"❌ Нужно 💎 {total}.", ephemeral=True)
            return

        await bot.db.execute(
            "UPDATE players SET gems = gems - ?, catalysts = catalysts + ? WHERE user_id = ?",
            (total, qty, user_id)
        )
        await bot.db.commit()
        await interaction.followup.send(
            f"🧪 Куплено {qty} катализатор(ов) за 💎 {total}. Всего: {owned + qty}.", ephemeral=True
        )


class ClaimQuestModal(discord.ui.Modal, title="Забрать награду"):
    quest_id = discord.ui.TextInput(label="ID задания", placeholder="craft_3", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        qid = self.quest_id.value.strip()

        quests, progress, claimed = await get_or_create_daily_quests(user_id)
        if qid not in quests:
            await interaction.followup.send("❌ Нет такого задания сегодня.", ephemeral=True)
            return
        if qid in claimed:
            await interaction.followup.send("❌ Уже получено.", ephemeral=True)
            return

        desc, target, reward = QUEST_POOL[qid]
        if progress[qid] < target:
            await interaction.followup.send(f"❌ Не выполнено: {progress[qid]}/{target}.", ephemeral=True)
            return

        claimed.append(qid)
        await bot.db.execute(
            "UPDATE players SET daily_quest_claimed = ?, gems = gems + ? WHERE user_id = ?",
            (json.dumps(claimed), reward, user_id)
        )
        await bot.db.commit()
        await interaction.followup.send(f"🎁 Получено 💎 {reward} за «{desc}»!", ephemeral=True)


class BuyUpgradeModal(discord.ui.Modal, title="Купить улучшение"):
    upgrade_id = discord.ui.TextInput(label="ID улучшения", placeholder="vip / grid_7x7", required=True)

    def __init__(self, author_id: int):
        super().__init__()
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        uid = self.upgrade_id.value.strip()

        async with bot.db.execute(
            "SELECT name, price_gems, emoji, category FROM gem_shop WHERE id = ?", (uid,)
        ) as c:
            item = await c.fetchone()
        if not item:
            await interaction.followup.send("❌ Улучшение не найдено.", ephemeral=True)
            return

        name, price, emoji, category = item

        async with bot.db.execute(
            "SELECT 1 FROM player_upgrades WHERE user_id = ? AND upgrade_id = ?", (user_id, uid)
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
            "INSERT INTO player_upgrades (user_id, upgrade_id) VALUES (?, ?)", (user_id, uid)
        )

        if uid.startswith("grid_"):
            size = int(uid.split("_")[1].split("x")[0])
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

        await bot.db.commit()
        await interaction.followup.send(f"✅ Куплено **{emoji} {name}** за 💎 {price}!", ephemeral=True)


# ============================================================
#  🚪 ЕДИНСТВЕННАЯ ПОЛЬЗОВАТЕЛЬСКАЯ КОМАНДА
# ============================================================

@bot.tree.command(name="меню", description="Открыть главное меню замка")
async def main_menu(interaction: discord.Interaction):
    embed = await build_main_embed(interaction)
    view = MainMenuView(interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ============================================================
#  ⚙️ НАСТРОЙКИ (АДМИН)
# ============================================================

@bot.tree.command(name="настройки", description="Настройки бота (только админы)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    название="Новое название бота",
    предмет="ID предмета для смены эмодзи",
    эмодзи="Новый эмодзи"
)
async def settings_cmd(
    interaction: discord.Interaction,
    название: str = None,
    предмет: str = None,
    эмодзи: str = None
):
    guild_id = interaction.guild_id
    await bot.db.execute(
        "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,)
    )

    changes = []
    if название:
        await bot.db.execute(
            "UPDATE guild_settings SET bot_name = ? WHERE guild_id = ?",
            (название, guild_id)
        )
        changes.append(f"📛 Название: **{название}**")

    if предмет and эмодзи:
        async with bot.db.execute("SELECT name FROM items WHERE id = ?", (предмет,)) as c:
            item = await c.fetchone()
        if not item:
            return await interaction.response.send_message(
                f"❌ Предмет `{предмет}` не найден.", ephemeral=True
            )
        async with bot.db.execute(
            "SELECT custom_emojis FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ) as c:
            current = json.loads((await c.fetchone())[0] or "{}")
        current[предмет] = эмодзи
        await bot.db.execute(
            "UPDATE guild_settings SET custom_emojis = ? WHERE guild_id = ?",
            (json.dumps(current), guild_id)
        )
        changes.append(f"🎨 {item[0]}: {эмодзи}")

    await bot.db.commit()

    if not changes:
        async with bot.db.execute(
            "SELECT bot_name, custom_emojis FROM guild_settings WHERE guild_id = ?",
            (guild_id,)
        ) as c:
            name, emojis = await c.fetchone()
        embed = discord.Embed(title="⚙️ Настройки сервера", color=0x808080)
        embed.add_field(name="Название", value=name, inline=False)
        embed.add_field(name="Кастомные эмодзи", value=emojis or "нет", inline=False)
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    await interaction.response.send_message(
        "✅ Настройки обновлены:\n" + "\n".join(changes), ephemeral=True
    )


@bot.tree.command(name="добавить_генератор", description="Добавить генератор (админ)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    id="Уникальный ID (латиницей)",
    название="Название",
    цена="Цена в монетах",
    доход_монет="Доход монет/час",
    доход_гемов="Доход гемов/час",
    эмодзи="Эмодзи",
    редкость="common/uncommon/rare/epic/legendary/mythic"
)
async def add_generator_cmd(
    interaction: discord.Interaction,
    id: str,
    название: str,
    цена: int,
    доход_монет: int = 0,
    доход_гемов: float = 0.0,
    эмодзи: str = "⚙️",
    редкость: str = "common"
):
    if not id.isalnum() or id != id.lower():
        return await interaction.response.send_message(
            "❌ ID должен быть латиницей в нижнем регистре.", ephemeral=True
        )

    async with bot.db.execute("SELECT 1 FROM items WHERE id = ?", (id,)) as c:
        if await c.fetchone():
            return await interaction.response.send_message(
                f"❌ Предмет с ID `{id}` уже существует.", ephemeral=True
            )

    if редкость not in RARITY_COLORS:
        return await interaction.response.send_message(
            f"❌ Неверная редкость. Допустимо: {', '.join(RARITY_COLORS.keys())}.", ephemeral=True
        )

    await bot.db.execute(
        "INSERT INTO items (id, name, price, income_per_hour, emoji, rarity, buyable, income_gems_per_hour) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (id, название, цена, доход_монет, эмодзи, редкость, доход_гемов)
    )
    await bot.db.commit()

    await interaction.response.send_message(
        f"✅ Генератор **{эмодзи} {название}** (`{id}`) добавлен.", ephemeral=True
    )


# ============================================================
#  🛡️ АДМИН-ПАНЕЛЬ
# ============================================================

admin_group = app_commands.Group(
    name="админ",
    description="Меню администрации",
    default_permissions=discord.Permissions(administrator=True)
)


async def _resolve_target(interaction: discord.Interaction, target: discord.User):
    async with bot.db.execute("SELECT 1 FROM players WHERE user_id = ?", (target.id,)) as c:
        exists = await c.fetchone()
    if not exists:
        await bot.db.execute(
            "INSERT OR IGNORE INTO players (user_id, coins) VALUES (?, ?)",
            (target.id, START_COINS)
        )
        await bot.db.commit()
    return True


@admin_group.command(name="начислить", description="Начислить монеты или гемы")
@app_commands.describe(пользователь="Кому", валюта="Что", количество="Сколько")
@app_commands.choices(валюта=[
    app_commands.Choice(name="Монеты", value="coins"),
    app_commands.Choice(name="Гемы", value="gems"),
])
async def admin_grant(interaction, пользователь: discord.User, валюта: str, количество: int):
    if количество <= 0:
        return await interaction.response.send_message("❌ Количество > 0.", ephemeral=True)
    if not await _resolve_target(interaction, пользователь):
        return
    column = "coins" if валюта == "coins" else "gems"
    await bot.db.execute(
        f"UPDATE players SET {column} = {column} + ? WHERE user_id = ?",
        (количество, пользователь.id)
    )
    await bot.db.commit()
    unit = "🪙" if валюта == "coins" else "💎"
    await interaction.response.send_message(
        f"✅ Начислено {количество} {unit} {пользователь.mention}.", ephemeral=True
    )


@admin_group.command(name="забрать", description="Забрать монеты или гемы")
@app_commands.describe(пользователь="У кого", валюта="Что", количество="Сколько")
@app_commands.choices(валюта=[
    app_commands.Choice(name="Монеты", value="coins"),
    app_commands.Choice(name="Гемы", value="gems"),
])
async def admin_take(interaction, пользователь: discord.User, валюта: str, количество: int):
    if количество <= 0:
        return await interaction.response.send_message("❌ Количество > 0.", ephemeral=True)
    if not await _resolve_target(interaction, пользователь):
        return
    column = "coins" if валюта == "coins" else "gems"
    async with bot.db.execute(
        f"SELECT {column} FROM players WHERE user_id = ?", (пользователь.id,)
    ) as c:
        current = (await c.fetchone())[0]
    if current < количество:
        return await interaction.response.send_message(
            f"❌ Только {current}.", ephemeral=True
        )
    await bot.db.execute(
        f"UPDATE players SET {column} = {column} - ? WHERE user_id = ?",
        (количество, пользователь.id)
    )
    await bot.db.commit()
    unit = "🪙" if валюта == "coins" else "💎"
    await interaction.response.send_message(
        f"✅ Забрано {количество} {unit} у {пользователь.mention}.", ephemeral=True
    )


@admin_group.command(name="профиль", description="Полный профиль игрока")
@app_commands.describe(пользователь="Чей профиль")
async def admin_profile(interaction, пользователь: discord.User):
    if not await _resolve_target(interaction, пользователь):
        return
    async with bot.db.execute("""
        SELECT coins, gems, catalysts, grid_size, income_bonus,
               total_crafts, total_successes, last_collected, last_gem_collected
        FROM players WHERE user_id = ?
    """, (пользователь.id,)) as c:
        row = await c.fetchone()
    (coins, gems, catalysts, grid_size, bonus,
     total_crafts, total_successes, last_coins, last_gems) = row

    async with bot.db.execute("""
        SELECT inv.location, inv.slot, i.name, i.emoji
        FROM inventory inv JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? ORDER BY inv.location, inv.slot
    """, (пользователь.id,)) as c:
        inv_rows = await c.fetchall()

    profile_items = [f"`{s}` {e} {n}" for loc, s, n, e in inv_rows if loc == "profile"]
    storage_items = [f"`{s}` {e} {n}" for loc, s, n, e in inv_rows if loc == "storage"]

    async with bot.db.execute(
        "SELECT COUNT(*) FROM player_achievements WHERE user_id = ?", (пользователь.id,)
    ) as c:
        ach_count = (await c.fetchone())[0]

    async with bot.db.execute(
        "SELECT upgrade_id FROM player_upgrades WHERE user_id = ?", (пользователь.id,)
    ) as c:
        upgrades = [r[0] for r in await c.fetchall()]

    embed = discord.Embed(title=f"🛡️ Профиль {пользователь.name}", color=0xe74c3c)
    embed.set_thumbnail(url=пользователь.display_avatar.url)
    embed.add_field(name="ID", value=f"`{пользователь.id}`", inline=False)
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
    await interaction.response.send_message(embed=embed, ephemeral=True)


@admin_group.command(name="изменить", description="Изменить поле профиля")
@app_commands.describe(пользователь="Чей", поле="Какое", значение="Новое")
@app_commands.choices(поле=[
    app_commands.Choice(name="Монеты", value="coins"),
    app_commands.Choice(name="Гемы", value="gems"),
    app_commands.Choice(name="Катализаторы", value="catalysts"),
    app_commands.Choice(name="Сетка (36/49/64/81/100)", value="grid_size"),
    app_commands.Choice(name="Бонус (0.0–0.45)", value="income_bonus"),
])
async def admin_edit(interaction, пользователь: discord.User, поле: str, значение: str):
    if not await _resolve_target(interaction, пользователь):
        return
    try:
        if поле == "income_bonus":
            parsed = float(значение)
            if parsed < 0 or parsed > 1:
                raise ValueError("Бонус от 0 до 1")
        elif поле == "grid_size":
            parsed = int(значение)
            if parsed not in (36, 49, 64, 81, 100):
                raise ValueError("Сетка 36/49/64/81/100")
        else:
            parsed = int(значение)
            if parsed < 0:
                raise ValueError("Не может быть отрицательным")
    except ValueError as e:
        return await interaction.response.send_message(f"❌ {e}", ephemeral=True)

    await bot.db.execute(
        f"UPDATE players SET {поле} = ? WHERE user_id = ?", (parsed, пользователь.id)
    )
    await bot.db.commit()
    await interaction.response.send_message(
        f"✅ `{поле}` = **{parsed}**.", ephemeral=True
    )


@admin_group.command(name="сбросить", description="Сбросить прогресс игрока")
@app_commands.describe(пользователь="Кого", подтверждение="Введите 'ДА'")
async def admin_reset(interaction, пользователь: discord.User, подтверждение: str):
    if подтверждение.strip().upper() != "ДА":
        return await interaction.response.send_message("❌ Введите `ДА`.", ephemeral=True)
    if not await _resolve_target(interaction, пользователь):
        return
    uid = пользователь.id
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
    """, (START_COINS, uid))
    await bot.db.execute("DELETE FROM inventory WHERE user_id = ?", (uid,))
    await bot.db.execute("DELETE FROM player_achievements WHERE user_id = ?", (uid,))
    await bot.db.execute("DELETE FROM player_upgrades WHERE user_id = ?", (uid,))
    await bot.db.execute("DELETE FROM craft_log WHERE user_id = ?", (uid,))
    await bot.db.commit()
    await interaction.response.send_message(
        f"🗑️ Прогресс {пользователь.mention} сброшен.", ephemeral=True
    )


@admin_group.command(name="выдать_предмет", description="Выдать предмет")
@app_commands.describe(пользователь="Кому", item_id="ID", количество="Сколько", куда="Куда")
@app_commands.choices(куда=[
    app_commands.Choice(name="В замок", value="profile"),
    app_commands.Choice(name="В хранилище", value="storage"),
])
async def admin_give_item(
    interaction, пользователь: discord.User, item_id: str, количество: int = 1, куда: str = "profile"
):
    if количество <= 0:
        return await interaction.response.send_message("❌ Количество > 0.", ephemeral=True)
    if not await _resolve_target(interaction, пользователь):
        return
    async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (item_id,)) as c:
        item = await c.fetchone()
    if not item:
        return await interaction.response.send_message(f"❌ `{item_id}` не найден.", ephemeral=True)

    name, emoji = item
    grid_size = await get_grid_size(пользователь.id)
    async with bot.db.execute(
        "SELECT slot FROM inventory WHERE user_id = ? AND location = ?", (пользователь.id, куда)
    ) as c:
        used = {r[0] for r in await c.fetchall()}
    free = [s for s in range(grid_size) if s not in used]
    if len(free) < количество:
        return await interaction.response.send_message(f"❌ Только {len(free)} слотов.", ephemeral=True)

    for i in range(количество):
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location) VALUES (?, ?, ?, ?)",
            (пользователь.id, free[i], item_id, куда)
        )
    await bot.db.commit()
    await interaction.response.send_message(
        f"✅ Выдано {количество}×{emoji} {name}.", ephemeral=True
    )


bot.tree.add_command(admin_group)


# ============================================================
#  🚀 ЗАПУСК
# ============================================================

if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN", "ТВОЙ_ТОКЕН")
    bot.run(token)
