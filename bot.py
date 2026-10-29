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

# Цепочка синтеза: из 5 предметов → 1 следующего
CRAFT_CHAIN = {
    "basic_gen": "wood_gen",
    "wood_gen":  "stone_gen",
    "stone_gen": "iron_gen",
    "iron_gen":  "gold_gen",
    "gold_gen":  "gem_gen",
}

CRAFT_COST = 5

# Параметры синтеза: шанс успеха и стоимость в гемах
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

# Пул ежедневных заданий: id -> (описание, цель, награда гемами)
QUEST_POOL = {
    "craft_3":        ("Сделай 3 синтеза", 3, 5),
    "craft_5":        ("Сделай 5 синтезов", 5, 10),
    "success_2":      ("Успешно синтезируй 2 раза", 2, 8),
    "buy_3":          ("Купи 3 предмета в магазине", 3, 5),
    "move_2":         ("Перемести 2 предмета между профилем и хранилищем", 2, 5),
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
        # --- Игроки ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                coins INTEGER DEFAULT 3,
                gems INTEGER DEFAULT 0,
                last_collected TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- Инвентарь ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                user_id INTEGER,
                slot INTEGER,
                item_id TEXT,
                location TEXT DEFAULT 'profile',
                PRIMARY KEY (user_id, location, slot)
            )
        """)

        # --- Предметы ---
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

        # --- Миграции players ---
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

        # --- Миграции items ---
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

        # --- Лог синтеза ---
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

        # --- Достижения ---
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

        # --- Настройки сервера ---
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                bot_name TEXT DEFAULT 'Castle Mania',
                custom_emojis TEXT DEFAULT '{}'
            )
        """)

        # --- Магазин за гемы ---
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

        # --- Заполняем предметы ---
        # id, name, price, income_coins, emoji, rarity, buyable, income_gems
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

        # --- Заполняем достижения ---
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

        # --- Заполняем магазин за гемы ---
        gem_items = [
            ("grid_7x7",   "Сетка 7x7",   "Увеличивает профиль до 49 слотов",   50,  "📐", "upgrade", 1),
            ("grid_8x8",   "Сетка 8x8",   "Увеличивает профиль до 64 слотов",  150,  "📐", "upgrade", 1),
            ("grid_9x9",   "Сетка 9x9",   "Увеличивает профиль до 81 слота",   400,  "📐", "upgrade", 1),
            ("grid_10x10", "Сетка 10x10", "Увеличивает профиль до 100 слотов",750,  "📐", "upgrade", 1),
            ("vip",        "VIP-статус",  "+15% к доходу навсегда (% не складывается, действует по самому высокому статусу)",             100,  "⭐", "status", 1),
            ("platinum",   "Платинум",    "+25% к доходу навсегда (% не складывается, действует по самому высокому статусу)",             300,  "💠", "status", 1),
            ("gold",       "Голд",        "+35% к доходу навсегда (% не складывается, действует по самому высокому статусу)",             700,  "🥇", "status", 1),
            ("diamond",    "Даймонд",     "+45% к доходу навсегда (% не складывается, действует по самому высокому статусу)",            1500,  "💎", "status", 1),
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


if not row:
        # Создаём нового игрока с 10 монетами
        await bot.db.execute(
            "INSERT OR IGNORE INTO players (user_id, coins) VALUES (?, 10)",
            (user_id,)
        )
        await bot.db.commit()
        return 36, 0.0, 0, 10

    return row[0] or 36, row[1] or 0.0, row[2] or 0, row[3] or 0


async def get_grid_size(user_id: int) -> int:
    size, _, _, _ = await get_player_stats(user_id)
    return size


async def get_income_bonus(user_id: int) -> float:
    _, bonus, _, _ = await get_player_stats(user_id)
    return bonus


async def get_item_emoji(guild_id: int, item_id: str, default: str) -> str:
    if not guild_id:
        return default
    async with bot.db.execute(
        "SELECT custom_emojis FROM guild_settings WHERE guild_id = ?", (guild_id,)
    ) as c:
        row = await c.fetchone()
    if row and row[0]:
        try:
            custom = json.loads(row[0])
            return custom.get(item_id, default)
        except Exception:
            return default
    return default


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

    # Монеты
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

    # Гемы
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


async def collect_income(user_id: int, channel: discord.abc.Messageable):
    """Начисляет пассивный доход и отправляет самоудаляющееся уведомление."""
    coins_earned, gems_earned = await calculate_passive_income(user_id)
    if coins_earned <= 0 and gems_earned <= 0:
        return

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

    msg = "💰 Генераторы принесли: " + ", ".join(filter(None, [
        f"🪙 +{coins_earned}" if coins_earned else "",
        f"💎 +{gems_earned}" if gems_earned else "",
    ]))
    await channel.send(msg, delete_after=10)

    # Прогресс задания на сбор дохода
    await update_quest_progress(user_id, "collect_income")


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

    # Суммарно использованных катализаторов
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
#  👤 ПРОФИЛЬ
# ============================================================

@bot.tree.command(name="профиль", description="Посмотреть свой замок")
async def profile(interaction: discord.Interaction):
    user_id = interaction.user.id
    guild_id = interaction.guild_id

    await collect_income(user_id, interaction.channel)

    grid_size, bonus, gems, coins = await get_player_stats(user_id)

    async with bot.db.execute("""
        SELECT inv.slot, i.id, i.emoji FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'profile'
    """, (user_id,)) as c:
        rows = await c.fetchall()

    items = {}
    for slot, item_id, default_emoji in rows:
        emoji = await get_item_emoji(guild_id, item_id, default_emoji) if guild_id else default_emoji
        items[slot] = emoji

    width = int(grid_size ** 0.5)

    embed = discord.Embed(title=f"🏰 Замок {interaction.user.name}", color=0x00ff00)
    embed.add_field(name="Кошелёк", value=f"🪙 {coins} | 💎 {gems}", inline=False)
    embed.add_field(name="Бонус дохода", value=f"+{int(bonus * 100)}%", inline=True)
    embed.add_field(name="Сетка", value=f"{width}x{width} ({grid_size} слотов)", inline=True)

    grid_str = ""
    for slot in range(grid_size):
        grid_str += f"{items.get(slot, '⬛')} "
        if (slot + 1) % width == 0:
            grid_str += "\n"

    embed.add_field(
        name="Профиль — генераторы работают",
        value=f"```\n{grid_str}\n```",
        inline=False
    )
    await interaction.response.send_message(embed=embed)


# ============================================================
#  🎒 ХРАНИЛИЩЕ
# ============================================================

@bot.tree.command(name="хранилище", description="Посмотреть своё хранилище")
async def storage(interaction: discord.Interaction):
    user_id = interaction.user.id
    guild_id = interaction.guild_id
    grid_size = await get_grid_size(user_id)

    async with bot.db.execute("""
        SELECT inv.slot, i.id, i.emoji FROM inventory inv
        JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? AND inv.location = 'storage'
    """, (user_id,)) as c:
        rows = await c.fetchall()

    items = {}
    for slot, item_id, default_emoji in rows:
        emoji = await get_item_emoji(guild_id, item_id, default_emoji) if guild_id else default_emoji
        items[slot] = emoji

    width = int(grid_size ** 0.5)
    embed = discord.Embed(title=f"🎒 Хранилище {interaction.user.name}", color=0x808080)

    grid_str = ""
    for slot in range(grid_size):
        grid_str += f"{items.get(slot, '⬛')} "
        if (slot + 1) % width == 0:
            grid_str += "\n"

    embed.add_field(
        name="Предметы (эффекты отключены)",
        value=f"```\n{grid_str}\n```",
        inline=False
    )
    await interaction.response.send_message(embed=embed)


# ============================================================
#  🛒 МАГАЗИН
# ============================================================

@bot.tree.command(name="магазин", description="Посмотреть доступные предметы")
async def shop(interaction: discord.Interaction):
    guild_id = interaction.guild_id

    async with bot.db.execute(
        "SELECT id, name, price, income_per_hour, emoji, rarity, income_gems_per_hour "
        "FROM items WHERE buyable = 1"
    ) as c:
        rows = await c.fetchall()

    grouped = {}
    for row in rows:
        grouped.setdefault(row[5], []).append(row)

    order = ["common", "uncommon", "rare", "epic", "legendary", "mythic"]
    embeds = []
    for rarity in order:
        if rarity not in grouped:
            continue
        embed = discord.Embed(
            title=f"🛒 Магазин — {RARITY_NAMES[rarity]}",
            color=RARITY_COLORS[rarity]
        )
        for item_id, name, price, income_coins, default_emoji, _, income_gems in grouped[rarity]:
            emoji = await get_item_emoji(guild_id, item_id, default_emoji) if guild_id else default_emoji

            income_str = ""
            if income_coins > 0:
                income_str += f"🪙 {income_coins}/час"
            if income_gems > 0:
                income_str += f" 💎 {income_gems}/час"
            if not income_str:
                income_str = "без дохода"

            if item_id in CRAFT_CHAIN:
                s = CRAFT_SETTINGS.get(item_id, {"chance": 1.0, "gems": 0})
                craft_info = f"\n⚗️ Синтез: {int(s['chance'] * 100)}%"
                if s["gems"] > 0:
                    craft_info += f", 💎 {s['gems']} гемов"
            else:
                craft_info = "\n⚗️ Максимальный уровень"

            embed.add_field(
                name=f"{emoji} {name} (`{item_id}`)",
                value=f"Цена: 🪙 {price} | {income_str}{craft_info}",
                inline=False
            )
        embeds.append(embed)

    await interaction.response.send_message(embeds=embeds)


@bot.tree.command(name="купить", description="Купить предмет")
@app_commands.describe(item_id="ID предмета", quantity="Количество")
async def buy(interaction: discord.Interaction, item_id: str, quantity: int = 1):
    user_id = interaction.user.id

    if quantity < 1:
        return await interaction.response.send_message(
            "❌ Количество должно быть больше нуля.", ephemeral=True
        )

    async with bot.db.execute(
        "SELECT price, name, buyable FROM items WHERE id = ?", (item_id,)
    ) as c:
        item = await c.fetchone()

    if not item:
        return await interaction.response.send_message("❌ Предмет не найден.", ephemeral=True)

    price, name, buyable = item
    if not buyable:
        return await interaction.response.send_message(
            f"❌ **{name}** нельзя купить в магазине (только синтез).", ephemeral=True
        )

    total_cost = price * quantity

    async with bot.db.execute(
        "SELECT coins FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        balance = (await c.fetchone())[0]

    if balance < total_cost:
        return await interaction.response.send_message(
            f"❌ Не хватает монет. Нужно {total_cost}.", ephemeral=True
        )

    grid_size = await get_grid_size(user_id)

    async with bot.db.execute(
        "SELECT slot FROM inventory WHERE user_id = ? AND location = 'profile'",
        (user_id,)
    ) as c:
        used_slots = {row[0] for row in await c.fetchall()}

    free_slots = [s for s in range(grid_size) if s not in used_slots]
    if len(free_slots) < quantity:
        return await interaction.response.send_message(
            f"❌ В профиле нет места! (Максимум {grid_size} слотов).", ephemeral=True
        )

    await bot.db.execute(
        "UPDATE players SET coins = coins - ? WHERE user_id = ?",
        (total_cost, user_id)
    )
    for i in range(quantity):
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location) VALUES (?, ?, ?, 'profile')",
            (user_id, free_slots[i], item_id)
        )
    await bot.db.commit()

    await update_quest_progress(user_id, "buy_3", quantity)
    unlocked = await check_achievements(user_id)

    msg = f"✅ Куплено **{name}** x{quantity} за {total_cost} монет."
    if unlocked:
        msg += "\n\n🏆 **Новые достижения:**\n" + "\n".join(
            f"{emoji} {n} (+💎 {r})" for emoji, n, r in unlocked
        )
    await interaction.response.send_message(msg, delete_after=10)


@bot.tree.command(name="продать", description="Продать генератор за 15% от цены магазина")
@app_commands.describe(item_id="ID предмета", quantity="Сколько продать")
async def sell(interaction: discord.Interaction, item_id: str, quantity: int = 1):
    user_id = interaction.user.id

    if quantity < 1:
        return await interaction.response.send_message(
            "❌ Количество должно быть больше нуля.", ephemeral=True
        )

    async with bot.db.execute(
        "SELECT name, price, buyable FROM items WHERE id = ?", (item_id,)
    ) as c:
        item = await c.fetchone()

    if not item:
        return await interaction.response.send_message("❌ Предмет не найден.", ephemeral=True)

    name, price, buyable = item
    if not buyable and price == 0:
        return await interaction.response.send_message(
            f"❌ **{name}** нельзя продать (нет рыночной цены).", ephemeral=True
        )

    sell_price = int(price * SELL_RATE) * quantity

    async with bot.db.execute(
        "SELECT location, slot FROM inventory WHERE user_id = ? AND item_id = ?",
        (user_id, item_id)
    ) as c:
        owned = await c.fetchall()

    if len(owned) < quantity:
        return await interaction.response.send_message(
            f"❌ У тебя только {len(owned)} × **{name}**.", ephemeral=True
        )

    for location, slot in owned[:quantity]:
        await bot.db.execute(
            "DELETE FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
            (user_id, location, slot)
        )

    await bot.db.execute(
        "UPDATE players SET coins = coins + ? WHERE user_id = ?",
        (sell_price, user_id)
    )
    await bot.db.commit()

    await interaction.response.send_message(
        f"💰 Продано **{quantity}** × **{name}** за 🪙 **{sell_price}**.",
        delete_after=10
    )


# ============================================================
#  🔀 ПЕРЕМЕЩЕНИЕ
# ============================================================

@bot.tree.command(name="переместить", description="Переместить предмет между профилем и хранилищем")
@app_commands.describe(slot="Номер слота", to="Куда переместить")
@app_commands.choices(to=[
    app_commands.Choice(name="В профиль (работает)", value="profile"),
    app_commands.Choice(name="В хранилище (не работает)", value="storage"),
])
async def move(interaction: discord.Interaction, slot: int, to: str):
    user_id = interaction.user.id
    grid_size = await get_grid_size(user_id)

    if slot < 0 or slot >= grid_size:
        return await interaction.response.send_message(
            f"❌ Слот должен быть от 0 до {grid_size - 1}.", ephemeral=True
        )

    async with bot.db.execute(
        "SELECT item_id, location FROM inventory WHERE user_id = ? AND slot = ?",
        (user_id, slot)
    ) as c:
        row = await c.fetchone()

    if not row:
        return await interaction.response.send_message(
            "❌ В этом слоте нет предмета.", ephemeral=True
        )

    item_id, current_location = row

    if current_location == to:
        return await interaction.response.send_message(
            "❌ Предмет уже находится в этой локации.", ephemeral=True
        )

    async with bot.db.execute(
        "SELECT 1 FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
        (user_id, to, slot)
    ) as c:
        if await c.fetchone():
            return await interaction.response.send_message(
                "❌ В целевой локации этот слот уже занят.", ephemeral=True
            )

    await bot.db.execute(
        "DELETE FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
        (user_id, current_location, slot)
    )
    await bot.db.execute(
        "INSERT INTO inventory (user_id, slot, item_id, location) VALUES (?, ?, ?, ?)",
        (user_id, slot, item_id, to)
    )
    await bot.db.commit()

    await update_quest_progress(user_id, "move_2")

    await interaction.response.send_message(
        f"✅ Предмет перемещён в **{'профиль' if to == 'profile' else 'хранилище'}**.",
        delete_after=8
    )


# ============================================================
#  ⚗️ СИНТЕЗ
# ============================================================

@bot.tree.command(name="синтез", description="Синтезировать 5 предметов в 1 предмет следующего уровня")
@app_commands.describe(
    item_id="ID предмета для синтеза (например, basic_gen)",
    use_catalyst="Использовать катализатор (+15% к шансу)"
)
async def craft(interaction: discord.Interaction, item_id: str, use_catalyst: bool = False):
    user_id = interaction.user.id

    if item_id not in CRAFT_CHAIN:
        return await interaction.response.send_message(
            "❌ Этот предмет нельзя синтезировать.", ephemeral=True
        )

    next_id = CRAFT_CHAIN[item_id]
    settings = CRAFT_SETTINGS.get(item_id, {"chance": 1.0, "gems": 0})
    base_chance = settings["chance"]
    gem_cost = settings["gems"]

    async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (item_id,)) as c:
        src = await c.fetchone()
    async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (next_id,)) as c:
        dst = await c.fetchone()

    if not src or not dst:
        return await interaction.response.send_message(
            "❌ Ошибка конфигурации предметов.", ephemeral=True
        )

    src_name, src_emoji = src
    dst_name, dst_emoji = dst

    async with bot.db.execute(
        "SELECT location, slot FROM inventory WHERE user_id = ? AND item_id = ?",
        (user_id, item_id)
    ) as c:
        owned = await c.fetchall()

    if len(owned) < CRAFT_COST:
        return await interaction.response.send_message(
            f"❌ Нужно {CRAFT_COST} × {src_emoji} **{src_name}**, у тебя только {len(owned)}.",
            ephemeral=True
        )

    async with bot.db.execute(
        "SELECT gems, catalysts FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        gems, catalysts = await c.fetchone()

    if gems < gem_cost:
        return await interaction.response.send_message(
            f"❌ Не хватает гемов. Нужно 💎 {gem_cost}, у тебя {gems}.", ephemeral=True
        )

    if use_catalyst and catalysts < 1:
        return await interaction.response.send_message(
            "❌ У тебя нет катализаторов. Купи через `/катализатор`.", ephemeral=True
        )

    grid_size = await get_grid_size(user_id)
    async with bot.db.execute(
        "SELECT slot FROM inventory WHERE user_id = ? AND location = 'profile'",
        (user_id,)
    ) as c:
        used = {row[0] for row in await c.fetchall()}
    free = [s for s in range(grid_size) if s not in used]

    if not free:
        return await interaction.response.send_message(
            f"❌ В профиле нет свободного слота! (Максимум {grid_size})", ephemeral=True
        )

    if gem_cost > 0:
        await bot.db.execute(
            "UPDATE players SET gems = gems - ? WHERE user_id = ?",
            (gem_cost, user_id)
        )

    catalyst_used = 0
    if use_catalyst:
        await bot.db.execute(
            "UPDATE players SET catalysts = catalysts - 1 WHERE user_id = ?",
            (user_id,)
        )
        catalyst_used = 1

    to_remove = owned[:CRAFT_COST]
    for location, slot in to_remove:
        await bot.db.execute(
            "DELETE FROM inventory WHERE user_id = ? AND location = ? AND slot = ?",
            (user_id, location, slot)
        )

    final_chance = min(1.0, base_chance + (CATALYST_BONUS if use_catalyst else 0))
    success = random.random() < final_chance

    await bot.db.execute(
        "INSERT INTO craft_log (user_id, item_id, success, gems_spent, catalyst_used) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, item_id, int(success), gem_cost, catalyst_used)
    )

    if success:
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location) VALUES (?, ?, ?, 'profile')",
            (user_id, free[0], next_id)
        )

    await bot.db.execute(
        "UPDATE players SET total_crafts = total_crafts + 1, "
        "total_successes = total_successes + ? WHERE user_id = ?",
        (int(success), user_id)
    )
    await bot.db.commit()

    await update_quest_progress(user_id, "craft_3")
    await update_quest_progress(user_id, "craft_5")
    if success:
        await update_quest_progress(user_id, "success_2")
    if use_catalyst:
        await update_quest_progress(user_id, "use_catalyst")

    unlocked = await check_achievements(user_id)

    chance_str = f"🎲 Шанс: {int(final_chance * 100)}%"
    if use_catalyst:
        chance_str += f" (база {int(base_chance * 100)}% + 🧪 {int(CATALYST_BONUS * 100)}%)"
    gem_str = f" | 💎 Потрачено гемов: {gem_cost}" if gem_cost > 0 else ""

    if success:
        msg = (
            f"⚗️ **Синтез успешен!** {CRAFT_COST} × {src_emoji} **{src_name}** → "
            f"1 × {dst_emoji} **{dst_name}**\n{chance_str}{gem_str}"
        )
    else:
        msg = (
            f"💥 **Синтез провален!** {CRAFT_COST} × {src_emoji} **{src_name}** сгорели.\n"
            f"{chance_str}{gem_str} (не возвращаются)"
        )

    if unlocked:
        msg += "\n\n🏆 **Новые достижения:**\n" + "\n".join(
            f"{emoji} {n} (+💎 {r})" for emoji, n, r in unlocked
        )

    await interaction.response.send_message(msg, delete_after=15)


# ============================================================
#  🧪 КАТАЛИЗАТОР
# ============================================================

@bot.tree.command(name="катализатор", description="Купить катализатор (+15% к шансу следующего синтеза)")
@app_commands.describe(quantity="Сколько катализаторов купить")
async def buy_catalyst(interaction: discord.Interaction, quantity: int = 1):
    user_id = interaction.user.id

    if quantity < 1:
        return await interaction.response.send_message(
            "❌ Количество должно быть больше нуля.", ephemeral=True
        )

    total_cost = CATALYST_PRICE * quantity

    async with bot.db.execute(
        "SELECT gems, catalysts FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        gems, owned = await c.fetchone()

    if gems < total_cost:
        return await interaction.response.send_message(
            f"❌ Не хватает гемов. Нужно 💎 {total_cost}, у тебя {gems}.", ephemeral=True
        )

    await bot.db.execute(
        "UPDATE players SET gems = gems - ?, catalysts = catalysts + ? WHERE user_id = ?",
        (total_cost, quantity, user_id)
    )
    await bot.db.commit()

    await interaction.response.send_message(
        f"🧪 Куплено **{quantity}** катализатор(ов) за 💎 {total_cost}.\n"
        f"Всего катализаторов: **{owned + quantity}**.",
        delete_after=10
    )


# ============================================================
#  📊 СТАТИСТИКА СИНТЕЗА
# ============================================================

@bot.tree.command(name="статистика_синтеза", description="Посмотреть свою статистику синтеза")
async def craft_stats(interaction: discord.Interaction):
    user_id = interaction.user.id

    async with bot.db.execute("""
        SELECT COUNT(*), SUM(success), SUM(gems_spent), SUM(catalyst_used)
        FROM craft_log WHERE user_id = ?
    """, (user_id,)) as c:
        total, successes, gems_spent, catalysts_used = await c.fetchone()

    if not total:
        return await interaction.response.send_message(
            "📊 У тебя пока нет ни одного синтеза.", ephemeral=True
        )

    successes = successes or 0
    failures = total - successes
    gems_spent = gems_spent or 0
    catalysts_used = catalysts_used or 0
    winrate = (successes / total) * 100

    embed = discord.Embed(title=f"📊 Статистика синтеза — {interaction.user.name}", color=0x9b59b6)
    embed.add_field(name="Всего попыток", value=str(total), inline=True)
    embed.add_field(name="✅ Успехов", value=str(successes), inline=True)
    embed.add_field(name="💥 Провалов", value=str(failures), inline=True)
    embed.add_field(name="Винрейт", value=f"{winrate:.1f}%", inline=True)
    embed.add_field(name="💎 Потрачено гемов", value=str(gems_spent), inline=True)
    embed.add_field(name="🧪 Использовано катализаторов", value=str(catalysts_used), inline=True)

    async with bot.db.execute("""
        SELECT item_id, COUNT(*), SUM(success)
        FROM craft_log WHERE user_id = ?
        GROUP BY item_id ORDER BY COUNT(*) DESC
    """, (user_id,)) as c:
        per_item = await c.fetchall()

    detail = ""
    for item_id, item_total, item_success in per_item:
        item_success = item_success or 0
        wr = (item_success / item_total) * 100 if item_total else 0
        detail += f"`{item_id}`: {item_success}/{item_total} ({wr:.0f}%)\n"

    if detail:
        embed.add_field(name="По предметам (успех/всего)", value=detail, inline=False)

    await interaction.response.send_message(embed=embed)


# ============================================================
#  🏆 ДОСТИЖЕНИЯ (КОМАНДА)
# ============================================================

@bot.tree.command(name="достижения", description="Посмотреть все достижения и свой прогресс")
async def achievements_list(interaction: discord.Interaction):
    user_id = interaction.user.id

    async with bot.db.execute(
        "SELECT id, name, description, reward_gems, emoji FROM achievements ORDER BY reward_gems ASC"
    ) as c:
        all_ach = await c.fetchall()

    async with bot.db.execute(
        "SELECT achievement_id FROM player_achievements WHERE user_id = ?", (user_id,)
    ) as c:
        unlocked = {r[0] for r in await c.fetchall()}

    embed = discord.Embed(title=f"🏆 Достижения — {interaction.user.name}", color=0xf1c40f)
    embed.set_footer(text=f"Открыто: {len(unlocked)}/{len(all_ach)}")

    for ach_id, name, desc, reward, emoji in all_ach:
        status = "✅ Открыто" if ach_id in unlocked else "🔒 Закрыто"
        embed.add_field(
            name=f"{emoji} {name}",
            value=f"{desc}\nНаграда: 💎 {reward} — {status}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)


# ============================================================
#  📅 ЗАДАНИЯ
# ============================================================

@bot.tree.command(name="задания", description="Посмотреть ежедневные задания и забрать награду")
async def daily_quests(interaction: discord.Interaction):
    user_id = interaction.user.id
    quests, progress, claimed = await get_or_create_daily_quests(user_id)

    embed = discord.Embed(title="📅 Ежедневные задания", color=0x3498db)
    for qid in quests:
        desc, target, reward = QUEST_POOL[qid]
        done = progress[qid] >= target
        status = "✅ Получено" if qid in claimed else ("🎁 Готово к получению!" if done else "⏳ В процессе")
        embed.add_field(
            name=desc,
            value=f"Прогресс: {progress[qid]}/{target}\nНаграда: 💎 {reward}\n{status}",
            inline=False
        )
    embed.set_footer(text="Задания обновляются раз в 24 часа. Забрать награду: /забрать <id>")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="забрать", description="Забрать награду за выполненное задание")
@app_commands.describe(quest_id="ID задания (например, craft_3)")
async def claim_quest(interaction: discord.Interaction, quest_id: str):
    user_id = interaction.user.id
    quests, progress, claimed = await get_or_create_daily_quests(user_id)

    if quest_id not in quests:
        return await interaction.response.send_message(
            "❌ Этого задания нет в сегодняшнем списке.", ephemeral=True
        )
    if quest_id in claimed:
        return await interaction.response.send_message(
            "❌ Награда уже получена.", ephemeral=True
        )

    desc, target, reward = QUEST_POOL[quest_id]
    if progress[quest_id] < target:
        return await interaction.response.send_message(
            f"❌ Задание не выполнено: {progress[quest_id]}/{target}.", ephemeral=True
        )

    claimed.append(quest_id)
    await bot.db.execute(
        "UPDATE players SET daily_quest_claimed = ?, gems = gems + ? WHERE user_id = ?",
        (json.dumps(claimed), reward, user_id)
    )
    await bot.db.commit()

    await interaction.response.send_message(
        f"🎁 Награда получена: 💎 **{reward}** гемов за «{desc}»!",
        delete_after=10
    )


# ============================================================
#  💎 МАГАЗИН ЗА ГЕМЫ
# ============================================================

@bot.tree.command(name="гем_магазин", description="Магазин за гемы")
async def gem_shop_cmd(interaction: discord.Interaction):
    async with bot.db.execute(
        "SELECT id, name, description, price_gems, emoji, category FROM gem_shop "
        "ORDER BY category, price_gems"
    ) as c:
        rows = await c.fetchall()

    async with bot.db.execute(
        "SELECT upgrade_id FROM player_upgrades WHERE user_id = ?", (interaction.user.id,)
    ) as c:
        owned = {r[0] for r in await c.fetchall()}

    embed = discord.Embed(title="🛒 Магазин за гемы", color=0x9b59b6)
    for gid, name, desc, price, emoji, category in rows:
        status = "✅ Куплено" if gid in owned else "🔒 Не куплено"
        embed.add_field(
            name=f"{emoji} {name}",
            value=f"{desc}\nЦена: 💎 {price}\n{status}",
            inline=False
        )
    embed.set_footer(text="Купить: /купить_гем <id>")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="купить_гем", description="Купить улучшение за гемы")
@app_commands.describe(upgrade_id="ID улучшения (например, vip или grid_7x7)")
async def buy_gem_upgrade(interaction: discord.Interaction, upgrade_id: str):
    user_id = interaction.user.id

    async with bot.db.execute(
        "SELECT name, price_gems, emoji, category FROM gem_shop WHERE id = ?",
        (upgrade_id,)
    ) as c:
        item = await c.fetchone()

    if not item:
        return await interaction.response.send_message(
            "❌ Улучшение не найдено.", ephemeral=True
        )

    name, price, emoji, category = item

    async with bot.db.execute(
        "SELECT 1 FROM player_upgrades WHERE user_id = ? AND upgrade_id = ?",
        (user_id, upgrade_id)
    ) as c:
        if await c.fetchone():
            return await interaction.response.send_message(
                f"❌ **{name}** уже куплено.", ephemeral=True
            )

    async with bot.db.execute(
        "SELECT gems FROM players WHERE user_id = ?", (user_id,)
    ) as c:
        gems = (await c.fetchone())[0]

    if gems < price:
        return await interaction.response.send_message(
            f"❌ Не хватает гемов. Нужно 💎 {price}, у тебя {gems}.", ephemeral=True
        )

    await bot.db.execute(
        "UPDATE players SET gems = gems - ? WHERE user_id = ?", (price, user_id)
    )
    await bot.db.execute(
        "INSERT INTO player_upgrades (user_id, upgrade_id) VALUES (?, ?)",
        (user_id, upgrade_id)
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

    await bot.db.commit()

    await interaction.response.send_message(
        f"✅ Куплено **{emoji} {name}** за 💎 {price}!",
        delete_after=10
    )


# ============================================================
#  ⚙️ НАСТРОЙКИ СЕРВЕРА
# ============================================================

@bot.tree.command(name="настройки", description="Настройки бота (только для админов)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    название="Новое название бота на сервере",
    предмет="ID предмета для смены эмодзи",
    эмодзи="Новый эмодзи для предмета"
)
async def settings(
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
        embed.set_footer(text="Использование: /настройки название:<...> предмет:<id> эмодзи:<emoji>")
        return await interaction.response.send_message(embed=embed)

    await interaction.response.send_message(
        "✅ Настройки обновлены:\n" + "\n".join(changes),
        delete_after=10
    )


@bot.tree.command(name="добавить_генератор", description="Добавить новый генератор (админ)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    id="Уникальный ID (латиницей, без пробелов)",
    название="Название",
    цена="Цена в монетах",
    доход_монет="Доход монет в час (0 если нет)",
    доход_гемов="Доход гемов в час (0 если нет)",
    эмодзи="Эмодзи",
    редкость="common/uncommon/rare/epic/legendary/mythic"
)
async def add_generator(
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
            "❌ ID должен быть латиницей в нижнем регистре, без пробелов.", ephemeral=True
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
        f"✅ Генератор **{эмодзи} {название}** (`{id}`) добавлен в магазин.",
        delete_after=10
    )

# ============================================================
#  🛡️ МЕНЮ АДМИНИСТРАЦИИ
# ============================================================

admin_group = app_commands.Group(
    name="админ",
    description="Меню администрации (только для админов)",
    default_permissions=discord.Permissions(administrator=True)
)


async def _resolve_target(interaction: discord.Interaction, target: discord.User):
    """Проверяет, что у игрока есть запись в БД. Возвращает True/False."""
    async with bot.db.execute(
        "SELECT 1 FROM players WHERE user_id = ?", (target.id,)
    ) as c:
        exists = await c.fetchone()
    if not exists:
        await interaction.response.send_message(
            f"❌ У пользователя {target.mention} ещё нет профиля (он не заходил в бота).",
            ephemeral=True
        )
        return False
    return True


# --- /админ начислить ---

@admin_group.command(name="начислить", description="Начислить монеты или гемы игроку")
@app_commands.describe(
    пользователь="Кому начислить",
    валюта="Что начислить",
    количество="Сколько начислить"
)
@app_commands.choices(валюта=[
    app_commands.Choice(name="Монеты", value="coins"),
    app_commands.Choice(name="Гемы", value="gems"),
])
async def admin_grant(
    interaction: discord.Interaction,
    пользователь: discord.User,
    валюта: str,
    количество: int
):
    if количество <= 0:
        return await interaction.response.send_message(
            "❌ Количество должно быть больше нуля.", ephemeral=True
        )

    if not await _resolve_target(interaction, пользователь):
        return

    column = "coins" if валюта == "coins" else "gems"
    await bot.db.execute(
        f"UPDATE players SET {column} = {column} + ? WHERE user_id = ?",
        (количество, пользователь.id)
    )
    await bot.db.commit()

    unit = "🪙 монет" if валюта == "coins" else "💎 гемов"
    await interaction.response.send_message(
        f"✅ Начислено **{количество}** {unit} пользователю {пользователь.mention}.",
        delete_after=10
    )


# --- /админ забрать ---

@admin_group.command(name="забрать", description="Забрать монеты или гемы у игрока")
@app_commands.describe(
    пользователь="У кого забрать",
    валюта="Что забрать",
    количество="Сколько забрать"
)
@app_commands.choices(валюта=[
    app_commands.Choice(name="Монеты", value="coins"),
    app_commands.Choice(name="Гемы", value="gems"),
])
async def admin_take(
    interaction: discord.Interaction,
    пользователь: discord.User,
    валюта: str,
    количество: int
):
    if количество <= 0:
        return await interaction.response.send_message(
            "❌ Количество должно быть больше нуля.", ephemeral=True
        )

    if not await _resolve_target(interaction, пользователь):
        return

    column = "coins" if валюта == "coins" else "gems"

    async with bot.db.execute(
        f"SELECT {column} FROM players WHERE user_id = ?", (пользователь.id,)
    ) as c:
        current = (await c.fetchone())[0]

    if current < количество:
        return await interaction.response.send_message(
            f"❌ У пользователя только {current}. Нельзя забрать {количество}.",
            ephemeral=True
        )

    await bot.db.execute(
        f"UPDATE players SET {column} = {column} - ? WHERE user_id = ?",
        (количество, пользователь.id)
    )
    await bot.db.commit()

    unit = "🪙 монет" if валюта == "coins" else "💎 гемов"
    await interaction.response.send_message(
        f"✅ Забрано **{количество}** {unit} у {пользователь.mention}.",
        delete_after=10
    )


# --- /админ профиль ---

@admin_group.command(name="профиль", description="Посмотреть полный профиль игрока")
@app_commands.describe(пользователь="Чей профиль посмотреть")
async def admin_profile(interaction: discord.Interaction, пользователь: discord.User):
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

    # Инвентарь
    async with bot.db.execute("""
        SELECT inv.location, inv.slot, i.name, i.emoji
        FROM inventory inv JOIN items i ON inv.item_id = i.id
        WHERE inv.user_id = ? ORDER BY inv.location, inv.slot
    """, (пользователь.id,)) as c:
        inv_rows = await c.fetchall()

    profile_items = []
    storage_items = []
    for location, slot, name, emoji in inv_rows:
        entry = f"`{slot}` {emoji} {name}"
        if location == "profile":
            profile_items.append(entry)
        else:
            storage_items.append(entry)

    # Достижения
    async with bot.db.execute(
        "SELECT COUNT(*) FROM player_achievements WHERE user_id = ?", (пользователь.id,)
    ) as c:
        ach_count = (await c.fetchone())[0]

    # Апгрейды
    async with bot.db.execute(
        "SELECT upgrade_id FROM player_upgrades WHERE user_id = ?", (пользователь.id,)
    ) as c:
        upgrades = [r[0] for r in await c.fetchall()]

    embed = discord.Embed(
        title=f"🛡️ Профиль {пользователь.name}",
        color=0xe74c3c
    )
    embed.set_thumbnail(url=пользователь.display_avatar.url)
    embed.add_field(name="ID", value=f"`{пользователь.id}`", inline=False)
    embed.add_field(name="Кошелёк", value=f"🪙 {coins} | 💎 {gems}", inline=True)
    embed.add_field(name="Катализаторы", value=f"🧪 {catalysts}", inline=True)
    embed.add_field(name="Сетка", value=f"{int(grid_size ** 0.5)}x{int(grid_size ** 0.5)} ({grid_size})", inline=True)
    embed.add_field(name="Бонус дохода", value=f"+{int(bonus * 100)}%", inline=True)
    embed.add_field(name="Синтезы", value=f"{total_crafts} (успешно: {total_successes})", inline=True)
    embed.add_field(name="Достижения", value=f"{ach_count}", inline=True)
    embed.add_field(name="Апгрейды", value=", ".join(upgrades) if upgrades else "нет", inline=False)
    embed.add_field(name="Последний сбор монет", value=last_coins or "—", inline=True)
    embed.add_field(name="Последний сбор гемов", value=last_gems or "—", inline=True)
    embed.add_field(
        name=f"Профиль ({len(profile_items)} предм.)",
        value="\n".join(profile_items) if profile_items else "пусто",
        inline=False
    )
    embed.add_field(
        name=f"Хранилище ({len(storage_items)} предм.)",
        value="\n".join(storage_items) if storage_items else "пусто",
        inline=False
    )

    await interaction.response.send_message(embed=embed)


# --- /админ изменить ---

@admin_group.command(name="изменить", description="Изменить конкретное поле профиля игрока")
@app_commands.describe(
    пользователь="Чей профиль изменить",
    поле="Какое поле изменить",
    значение="Новое значение"
)
@app_commands.choices(поле=[
    app_commands.Choice(name="Монеты", value="coins"),
    app_commands.Choice(name="Гемы", value="gems"),
    app_commands.Choice(name="Катализаторы", value="catalysts"),
    app_commands.Choice(name="Размер сетки (36/49/64/81/100)", value="grid_size"),
    app_commands.Choice(name="Бонус дохода (0.0–0.45)", value="income_bonus"),
])
async def admin_edit(
    interaction: discord.Interaction,
    пользователь: discord.User,
    поле: str,
    значение: str
):
    if not await _resolve_target(interaction, пользователь):
        return

    # Парсим значение в зависимости от поля
    try:
        if поле == "income_bonus":
            parsed = float(значение)
            if parsed < 0 or parsed > 1:
                raise ValueError("Бонус должен быть от 0.0 до 1.0")
        elif поле == "grid_size":
            parsed = int(значение)
            if parsed not in (36, 49, 64, 81, 100):
                raise ValueError("Сетка должна быть 36, 49, 64, 81 или 100")
        else:
            parsed = int(значение)
            if parsed < 0:
                raise ValueError("Значение не может быть отрицательным")
    except ValueError as e:
        return await interaction.response.send_message(
            f"❌ Неверное значение: {e}", ephemeral=True
        )

    await bot.db.execute(
        f"UPDATE players SET {поле} = ? WHERE user_id = ?",
        (parsed, пользователь.id)
    )
    await bot.db.commit()

    await interaction.response.send_message(
        f"✅ Поле `{поле}` пользователя {пользователь.mention} изменено на **{parsed}**.",
        delete_after=10
    )


# --- /админ сбросить ---

@admin_group.command(name="сбросить", description="Полностью сбросить прогресс игрока")
@app_commands.describe(
    пользователь="Кого сбросить",
    подтверждение="Введите 'ДА' для подтверждения"
)
async def admin_reset(
    interaction: discord.Interaction,
    пользователь: discord.User,
    подтверждение: str
):
    if подтверждение.strip().upper() != "ДА":
        return await interaction.response.send_message(
            "❌ Сброс отменён. Введите `ДА` заглавными, чтобы подтвердить.",
            ephemeral=True
        )

    if not await _resolve_target(interaction, пользователь):
        return

    uid = пользователь.id

    # Сбрасываем players
    await bot.db.execute("""
        UPDATE players SET
            coins = 3, gems = 0, catalysts = 0,
            grid_size = 36, income_bonus = 0.0,
            total_crafts = 0, total_successes = 0,
            last_collected = CURRENT_TIMESTAMP,
            last_gem_collected = CURRENT_TIMESTAMP,
            daily_quest_date = NULL,
            daily_quest_progress = '{}',
            daily_quest_claimed = '[]'
        WHERE user_id = ?
    """, (uid,))

    # Удаляем инвентарь, достижения, апгрейды, лог
    await bot.db.execute("DELETE FROM inventory WHERE user_id = ?", (uid,))
    await bot.db.execute("DELETE FROM player_achievements WHERE user_id = ?", (uid,))
    await bot.db.execute("DELETE FROM player_upgrades WHERE user_id = ?", (uid,))
    await bot.db.execute("DELETE FROM craft_log WHERE user_id = ?", (uid,))

    await bot.db.commit()

    await interaction.response.send_message(
        f"🗑️ Прогресс пользователя {пользователь.mention} полностью сброшен.",
        delete_after=15
    )


# --- /админ выдать_предмет ---

@admin_group.command(name="выдать_предмет", description="Выдать предмет игроку (в обход магазина)")
@app_commands.describe(
    пользователь="Кому выдать",
    item_id="ID предмета (например, gold_gen)",
    количество="Сколько выдать",
    куда="Куда положить"
)
@app_commands.choices(куда=[
    app_commands.Choice(name="В профиль", value="profile"),
    app_commands.Choice(name="В хранилище", value="storage"),
])
async def admin_give_item(
    interaction: discord.Interaction,
    пользователь: discord.User,
    item_id: str,
    количество: int = 1,
    куда: str = "profile"
):
    if количество <= 0:
        return await interaction.response.send_message(
            "❌ Количество должно быть больше нуля.", ephemeral=True
        )

    if not await _resolve_target(interaction, пользователь):
        return

    async with bot.db.execute("SELECT name, emoji FROM items WHERE id = ?", (item_id,)) as c:
        item = await c.fetchone()

    if not item:
        return await interaction.response.send_message(
            f"❌ Предмет `{item_id}` не найден.", ephemeral=True
        )

    name, emoji = item
    grid_size = await get_grid_size(пользователь.id)

    async with bot.db.execute(
        "SELECT slot FROM inventory WHERE user_id = ? AND location = ?",
        (пользователь.id, куда)
    ) as c:
        used = {row[0] for row in await c.fetchall()}

    free = [s for s in range(grid_size) if s not in used]
    if len(free) < количество:
        return await interaction.response.send_message(
            f"❌ В локации `{куда}` только {len(free)} свободных слотов, а нужно {количество}.",
            ephemeral=True
        )

    for i in range(количество):
        await bot.db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location) VALUES (?, ?, ?, ?)",
            (пользователь.id, free[i], item_id, куда)
        )
    await bot.db.commit()

    loc = "профиль" if куда == "profile" else "хранилище"
    await interaction.response.send_message(
        f"✅ Выдано **{количество}** × {emoji} **{name}** пользователю {пользователь.mention} в {loc}.",
        delete_after=10
    )


# Регистрируем группу
bot.tree.add_command(admin_group)

# ============================================================
#  🚀 ЗАПУСК
# ============================================================

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_BOT_TOKEN"))
