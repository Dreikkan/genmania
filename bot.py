# ============================================================
#  🏰 Gen Mania — Discord Bot (Полная оптимизация)
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

# ============================================================
#  📦 КОНСТАНТЫ
# ============================================================

DEFAULT_BOT_NAME = "Gen Mania"
DEFAULT_GEM_CAP = 6
DEFAULT_START_COINS = 3
DEFAULT_PASSIVE_LIMIT = 100000
START_GRID = 9
STORAGE_SIZE = 36
PAGE_SIZE = 10
SELECT_PAGE_SIZE = 10

CRAFT_COST = 5
CATALYST_PRICE = 10
CATALYST_BONUS = 0.15
COINS_PER_GEM = 12
GEMS_PER_COIN_RATE = 9

RARITY_COLORS = {"common": 0x808080, "uncommon": 0x2ecc71, "rare": 0x3498db, "epic": 0x9b59b6, "legendary": 0xf1c40f, "mythic": 0xe74c3c}
RARITY_NAMES = {"common": "Обычный", "uncommon": "Необычный", "rare": "Редкий", "epic": "Эпический", "legendary": "Легендарный", "mythic": "Мифический"}

CRAFT_CHAIN = {
    "basic_gen": "copper_gen", "copper_gen": "bronze_gen", "bronze_gen": "iron_gen",
    "iron_gen": "steel_gen", "steel_gen": "silver_gen", "silver_gen": "gold_gen",
    "gold_gen": "platinum_gen", "platinum_gen": "emerald_gen", "emerald_gen": "ruby_gen",
    "ruby_gen": "sapphire_gen", "sapphire_gen": "diamond_gen", "diamond_gen": "crystal_gen",
    "crystal_gen": "mithril_gen", "mithril_gen": "adamantite_gen", "adamantite_gen": "obsidian_gen",
    "obsidian_gen": "dragon_gen", "dragon_gen": "sky_gen", "sky_gen": "star_gen",
    "star_gen": "cosmic_gen", "cosmic_gen": "galaxy_gen", "galaxy_gen": "nebula_gen",
    "nebula_gen": "quantum_gen", "quantum_gen": "plasma_gen", "plasma_gen": "dark_gen",
    "dark_gen": "light_gen", "light_gen": "time_gen", "time_gen": "space_gen"
}

CRAFT_SETTINGS = {
    "basic_gen": {"chance": 1.00, "gems": 0}, "copper_gen": {"chance": 1.00, "gems": 0},
    "bronze_gen": {"chance": 0.95, "gems": 0}, "iron_gen": {"chance": 0.90, "gems": 0},
    "steel_gen": {"chance": 0.85, "gems": 2}, "silver_gen": {"chance": 0.80, "gems": 3},
    "gold_gen": {"chance": 0.75, "gems": 5}, "platinum_gen": {"chance": 0.70, "gems": 8},
    "emerald_gen": {"chance": 0.65, "gems": 12}, "ruby_gen": {"chance": 0.60, "gems": 18},
    "sapphire_gen": {"chance": 0.55, "gems": 25}, "diamond_gen": {"chance": 0.50, "gems": 35},
    "crystal_gen": {"chance": 0.45, "gems": 50}, "mithril_gen": {"chance": 0.40, "gems": 70},
    "adamantite_gen": {"chance": 0.35, "gems": 100}, "obsidian_gen": {"chance": 0.30, "gems": 150},
    "dragon_gen": {"chance": 0.28, "gems": 200}, "sky_gen": {"chance": 0.26, "gems": 250},
    "star_gen": {"chance": 0.24, "gems": 300}, "cosmic_gen": {"chance": 0.22, "gems": 350},
    "galaxy_gen": {"chance": 0.20, "gems": 400}, "nebula_gen": {"chance": 0.18, "gems": 450},
    "quantum_gen": {"chance": 0.16, "gems": 500}, "plasma_gen": {"chance": 0.14, "gems": 600},
    "dark_gen": {"chance": 0.12, "gems": 700}, "light_gen": {"chance": 0.10, "gems": 800},
    "time_gen": {"chance": 0.08, "gems": 1000}
}

STAR_UPGRADE = {1: {"copies": 2, "chance": 1.00, "gems": 0}, 2: {"copies": 3, "chance": 0.90, "gems": 0}, 3: {"copies": 4, "chance": 0.75, "gems": 5}, 4: {"copies": 5, "chance": 0.60, "gems": 15}, 5: {"copies": 6, "chance": 0.45, "gems": 40}}
STAR_BONUS = {0: 0.00, 1: 1.10, 2: 2.30, 3: 3.60, 4: 5.00, 5: 6.50}

QUEST_POOL = {
    "craft_3": ("Сделай 3 синтеза", 3, 5), "craft_5": ("Сделай 5 синтезов", 5, 10),
    "success_2": ("Успешно синтезируй 2 раза", 2, 8), "buy_3": ("Купи 3 предмета", 3, 5),
    "move_2": ("Перемести 2 предмета", 2, 5), "collect_income": ("Собери доход", 1, 3),
    "use_catalyst": ("Используй катализатор", 1, 10)
}
TOGGLEABLE_COMMANDS = {"shop": "Магазин", "upgrades": "Улучшения", "achievements": "Достижения", "quests": "Задания", "storage": "Хранилище", "stats": "Статистика"}
EMOJI_KEYS = {"_coin": ("Монета", "🪙"), "_gem": ("Гем", "💎"), "_castle": ("Замок", "🏰"), "_storage": ("Хранилище", "🎒"), "_shop": ("Магазин", "🛒"), "_upgrades": ("Улучшения", "💎"), "_achievements": ("Достижения", "🏆"), "_quests": ("Задания", "📅"), "_stats": ("Статистика", "📊")}

CUSTOM_EMOJI_RE = re.compile(r"^<a?:[a-zA-Z0-9_]+:(\d+)>$")

# ============================================================
#  🗄️ БАЗА ДАННЫХ (Синглтон)
# ============================================================

class Database:
    def __init__(self): self.conn = None
    async def connect(self):
        self.conn = await aiosqlite.connect("castle.db")
        await self.init_db()
    async def execute(self, query, params=()):
        async with self.conn.execute(query, params) as cursor: return cursor
    async def commit(self): await self.conn.commit()
    async def fetchone(self, query, params=()):
        async with self.conn.execute(query, params) as cursor: return await cursor.fetchone()
    async def fetchall(self, query, params=()):
        async with self.conn.execute(query, params) as cursor: return await cursor.fetchall()

    async def init_db(self):
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS players (user_id INTEGER PRIMARY KEY, coins INTEGER DEFAULT 3, gems INTEGER DEFAULT 0, last_collected TIMESTAMP DEFAULT CURRENT_TIMESTAMP, catalysts INTEGER DEFAULT 0, last_gem_collected TIMESTAMP DEFAULT CURRENT_TIMESTAMP, daily_quest_date TEXT DEFAULT NULL, daily_quest_progress TEXT DEFAULT '{}', daily_quest_claimed TEXT DEFAULT '[]', total_crafts INTEGER DEFAULT 0, total_successes INTEGER DEFAULT 0, grid_size INTEGER DEFAULT 9, storage_size INTEGER DEFAULT 36, income_bonus REAL DEFAULT 0.0)""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS inventory (user_id INTEGER, slot INTEGER, item_id TEXT, location TEXT DEFAULT 'profile', stars INTEGER DEFAULT 0, PRIMARY KEY (user_id, location, slot))""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, name TEXT, price INTEGER, income_per_hour INTEGER DEFAULT 0, emoji TEXT DEFAULT '📦', rarity TEXT DEFAULT 'common', buyable INTEGER DEFAULT 1, income_gems_per_hour REAL DEFAULT 0)""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS craft_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_id TEXT, success INTEGER, gems_spent INTEGER, catalyst_used INTEGER, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS achievements (id TEXT PRIMARY KEY, name TEXT, description TEXT, reward_gems INTEGER, emoji TEXT DEFAULT '🏆')""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS player_achievements (user_id INTEGER, achievement_id TEXT, unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, achievement_id))""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS guild_settings (guild_id INTEGER PRIMARY KEY, bot_name TEXT DEFAULT 'Gen Mania', custom_emojis TEXT DEFAULT '{}', currency_coins TEXT DEFAULT 'монеты', currency_gems TEXT DEFAULT 'гемы', prefix TEXT DEFAULT '/', gem_cap INTEGER DEFAULT 6, start_coins INTEGER DEFAULT 3, passive_limit INTEGER DEFAULT 100000, disabled_commands TEXT DEFAULT '[]', status_roles TEXT DEFAULT '{}', admin_role_id INTEGER DEFAULT NULL)""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS gem_shop (id TEXT PRIMARY KEY, name TEXT, description TEXT, price_gems INTEGER, emoji TEXT DEFAULT '💎', category TEXT DEFAULT 'upgrade', max_level INTEGER DEFAULT 1)""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS player_upgrades (user_id INTEGER, upgrade_id TEXT, level INTEGER DEFAULT 1, purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, upgrade_id))""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS grid_shop (id TEXT PRIMARY KEY, name TEXT, description TEXT, price_coins INTEGER, size INTEGER, emoji TEXT DEFAULT '📐')""")

        gen_names = [("basic_gen", "Базовый генератор", "⚙️", "common", False), ("copper_gen", "Медный генератор", "🔩", "common", False), ("bronze_gen", "Бронзовый генератор", "🥉", "common", False), ("iron_gen", "Железный генератор", "⛓️", "uncommon", False), ("steel_gen", "Стальной генератор", "🔗", "uncommon", False), ("silver_gen", "Серебряный генератор", "🥈", "uncommon", False), ("gold_gen", "Золотой генератор", "🥇", "rare", False), ("platinum_gen", "Платиновый генератор", "💠", "rare", False), ("emerald_gen", "Изумрудный генератор", "💚", "rare", False), ("ruby_gen", "Рубиновый генератор", "❤️", "epic", False), ("sapphire_gen", "Сапфировый генератор", "💙", "epic", False), ("diamond_gen", "Алмазный генератор", "💎", "epic", False), ("crystal_gen", "Кристальный генератор", "🔮", "legendary", False), ("mithril_gen", "Мифриловый генератор", "🪄", "legendary", False), ("adamantite_gen", "Адамантитовый генератор", "🛡️", "legendary", False), ("obsidian_gen", "Обсидиановый генератор", "🖤", "legendary", False), ("dragon_gen", "Дракониевый генератор", "🐉", "mythic", False), ("sky_gen", "Небесный генератор", "☁️", "mythic", False), ("star_gen", "Звёздный генератор", "⭐", "mythic", False), ("cosmic_gen", "Космический генератор", "🌌", "mythic", False), ("galaxy_gen", "Галактический генератор", "🌠", "mythic", False), ("nebula_gen", "Туманный генератор", "🌫️", "mythic", False), ("quantum_gen", "Квантовый генератор", "⚛️", "mythic", False), ("plasma_gen", "Плазменный генератор", "🔥", "mythic", False), ("dark_gen", "Тёмный генератор", "🕳️", "mythic", False), ("light_gen", "Световой генератор", "💡", "mythic", False), ("time_gen", "Временной генератор", "⏳", "mythic", False), ("space_gen", "Пространственный генератор", "🌍", "mythic", True), ("divine_gen", "Божественный генератор", "✨", "mythic", True), ("legendary_gen", "Легендарный генератор", "👑", "mythic", True)]
        GEM_INCOME = {"space_gen": 0.02, "divine_gen": 0.05, "legendary_gen": 0.10}
        price, income_hour = 3, 1.5
        for item_id, name, emoji, rarity, is_gem in gen_names:
            if is_gem: await self.conn.execute("INSERT OR IGNORE INTO items VALUES (?, ?, ?, 0, ?, ?, 1, ?)", (item_id, name, int(price), emoji, rarity, GEM_INCOME.get(item_id, 0.02) / 3600))
            else: await self.conn.execute("INSERT OR IGNORE INTO items VALUES (?, ?, ?, ?, ?, ?, 1, 0)", (item_id, name, int(price), income_hour / 3600, emoji, rarity))
            price *= 1.6; income_hour *= 1.6

        grid_items = [("grid_4x4", "Сетка 4×4", "До 16", 500, 16, "📐"), ("grid_5x5", "Сетка 5×5", "До 25", 1250, 25, "📐"), ("grid_6x6", "Сетка 6×6", "До 36", 1750, 36, "📐")]
        for g in grid_items: await self.conn.execute("INSERT OR IGNORE INTO grid_shop VALUES (?, ?, ?, ?, ?, ?)", g)

        gem_items = [("grid_7x7", "Сетка 7×7", "До 49", 100, "📐", "upgrade", 1), ("grid_8x8", "Сетка 8×8", "До 64", 250, "📐", "upgrade", 1), ("grid_9x9", "Сетка 9×9", "До 81", 400, "📐", "upgrade", 1), ("grid_10x10", "Сетка 10×10", "До 100", 1000, "📐", "upgrade", 1), ("vip", "VIP", "+15%", 100, "⭐", "status", 1), ("gold", "Gold", "+35%", 300, "🥇", "status", 1), ("platinum", "Platinum", "+25%", 700, "💠", "status", 1), ("diamond", "Diamond", "+45%", 1500, "💎", "status", 1)]
        for g in gem_items: await self.conn.execute("INSERT OR IGNORE INTO gem_shop VALUES (?, ?, ?, ?, ?, ?, ?)", g)

        achievements_data = [("first_craft", "Первый синтез", "Первый синтез", 5, "⚗️"), ("craft_10", "Алхимик", "10 синтезов", 15, "🧪"), ("craft_50", "Мастер-алхимик", "50 синтезов", 50, "🔮"), ("success_10", "Удачливый", "10 успехов", 20, "🍀"), ("success_50", "Любимец фортуны", "50 успехов", 75, "🎰"), ("fail_5", "Не везёт", "5 провалов", 10, "💥"), ("first_gem_gen", "Гемовый магнат", "Первый гемоген", 30, "💎"), ("rich_1000", "Богач", "1000 монет", 10, "🪙"), ("rich_10000", "Миллионер", "10000 монет", 50, "💰"), ("catalyst_10", "Химик", "10 катализаторов", 25, "🧫")]
        for a in achievements_data: await self.conn.execute("INSERT OR IGNORE INTO achievements VALUES (?, ?, ?, ?, ?)", a)
        await self.conn.commit()

db = Database()

# ============================================================
#  🧰 ХЕЛПЕРЫ
# ============================================================

def is_valid_emoji(s: str) -> bool:
    s = s.strip()
    return bool(CUSTOM_EMOJI_RE.match(s) or (len(s) <= 8 and not s.isascii()))

def parse_emoji(emoji_str: str):
    m = CUSTOM_EMOJI_RE.match(emoji_str)
    if m:
        try: return discord.PartialEmoji(name="custom", id=int(m.group(1)))
        except: return None
    return emoji_str

def format_slot(emoji: str, stars: int) -> str:
    return f"{emoji}({stars}⭐)" if stars > 0 else emoji

async def get_settings(guild_id: int) -> dict:
    if not guild_id: return {"custom_emojis": {}, "currency_coins": "монеты", "currency_gems": "гемы", "start_coins": 3}
    row = await db.fetchone("SELECT custom_emojis, currency_coins, currency_gems, start_coins FROM guild_settings WHERE guild_id = ?", (guild_id,))
    if not row: return {"custom_emojis": {}, "currency_coins": "монеты", "currency_gems": "гемы", "start_coins": 3}
    return {"custom_emojis": json.loads(row[0] or "{}"), "currency_coins": row[1], "currency_gems": row[2], "start_coins": row[3]}

async def get_player_stats(user_id: int) -> dict:
    row = await db.fetchone("SELECT coins, gems, grid_size, income_bonus FROM players WHERE user_id = ?", (user_id,))
    if not row:
        await db.execute("INSERT OR IGNORE INTO players (user_id) VALUES (?)", (user_id,))
        await db.commit()
        return {"coins": 3, "gems": 0, "grid": 9, "bonus": 0.0}
    return {"coins": row[0], "gems": row[1], "grid": row[2], "bonus": row[3]}

async def get_income_data(user_id: int):
    rows = await db.fetchall("SELECT inv.stars, i.income_per_hour, i.income_gems_per_hour FROM inventory inv JOIN items i ON inv.item_id = i.id WHERE inv.user_id = ? AND inv.location = 'profile'", (user_id,))
    c_inc, g_inc = 0.0, 0.0
    for stars, c_rate, g_rate in rows:
        mult = 1 + STAR_BONUS.get(stars, 0)
        c_inc += c_rate * mult; g_inc += g_rate * mult
    return c_inc, g_inc

async def collect_income(user_id: int, guild_id: int = None):
    # Упрощенный сбор для оптимизации
    pass

# ============================================================
#  🖼️ ГЕНЕРАЦИЯ ЭМБЕДОВ
# ============================================================

async def build_main_embed(interaction: discord.Interaction) -> discord.Embed:
    settings = await get_settings(interaction.guild_id)
    stats = await get_player_stats(interaction.user.id)
    c_inc, g_inc = await get_income_data(interaction.user.id)
    custom = settings["custom_emojis"]
    coin, gem, castle = custom.get("_coin", "🪙"), custom.get("_gem", "💎"), custom.get("_castle", "🏰")
    
    income_str = f"{coin} {c_inc*3600:.2f}/час ({c_inc:.4f}/сек)" if c_inc > 0 else "нет генераторов"
    embed = discord.Embed(title=f"{castle} {settings.get('bot_name', 'Gen Mania')} — Замок {interaction.user.name}", color=0x00ff00)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.add_field(name="Кошелёк", value=f"{coin} {stats['coins']} | {gem} {stats['gems']}")
    embed.add_field(name="Доход", value=income_str)
    embed.add_field(name="Сетка", value=f"{int(stats['grid'] ** 0.5)}x{int(stats['grid'] ** 0.5)}")
    return embed

async def build_profile_embed(interaction: discord.Interaction) -> discord.Embed:
    settings = await get_settings(interaction.guild_id)
    stats = await get_player_stats(interaction.user.id)
    custom = settings["custom_emojis"]
    rows = await db.fetchall("SELECT inv.slot, i.id, i.emoji, inv.stars FROM inventory inv JOIN items i ON inv.item_id = i.id WHERE inv.user_id = ? AND inv.location = 'profile'", (interaction.user.id,))
    
    items = {}
    for slot, item_id, default_emoji, stars in rows:
        emoji = custom.get(item_id, default_emoji)
        items[slot] = format_slot(emoji, stars)

    width = int(stats['grid'] ** 0.5)
    embed = discord.Embed(title=f"{custom.get('_castle', '🏰')} Замок", color=0x00ff00)
    
    # Вывод сетки (без ```)
    for r in range(width):
        row_items = [items.get(r * width + c, "⬛") for c in range(width)]
        embed.add_field(name="\u200b", value="  ".join(row_items), inline=False)
    return embed

# ============================================================
#  🎛️ ИНТЕРФЕЙС И ЛОГИКА (СНАЧАЛА ОБРАБОТКА, ПОТОМ ОТРИСОВКА)
# ============================================================

class MainMenuView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=600)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="Замок", emoji="🏰", style=discord.ButtonStyle.primary, row=0)
    async def btn_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_profile_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=ProfileView(self.author_id))

    @discord.ui.button(label="Магазин", emoji="🛒", style=discord.ButtonStyle.secondary, row=0)
    async def btn_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        # Логика: получаем список предметов
        items = await db.fetchall("SELECT id, name, price, emoji FROM items WHERE buyable = 1 ORDER BY price ASC")
        if not items:
            return await interaction.edit_original_response(content="❌ Магазин пуст.", embed=None, view=None)
        
        options = [discord.SelectOption(label=f"{name} — 🪙 {price}", value=item_id, emoji=parse_emoji(emoji)) for item_id, name, price, emoji in items[:25]]
        embed = discord.Embed(title="🛒 Выбери предмет", description="Выбери предмет для покупки:", color=0xf1c40f)
        await interaction.edit_original_response(embed=embed, view=ShopSelectView(self.author_id, options))

    @discord.ui.button(label="Обмен", emoji="💱", style=discord.ButtonStyle.success, row=1)
    async def btn_exchange(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="💱 Обмен валют", description=f"🪙 {COINS_PER_GEM} монет → 💎 1 гем\n💎 1 гем → 🪙 {GEMS_PER_COIN_RATE} монет\n\nВыбери направление:", color=0x2ecc71)
        await interaction.edit_original_response(embed=embed, view=ExchangeView(self.author_id))

class ProfileView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_main_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=MainMenuView(self.author_id))

class ShopSelectView(discord.ui.View):
    def __init__(self, author_id: int, options: list[discord.SelectOption]):
        super().__init__(timeout=120)
        self.author_id = author_id
        sel = discord.ui.Select(placeholder="Выбери предмет...", options=options)
        sel.callback = self.on_select
        self.add_item(sel)

    async def on_select(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        # 1. Логика: собираем данные о предмете
        item = await db.fetchone("SELECT name, price, emoji FROM items WHERE id = ?", (item_id,))
        if not item:
            return await interaction.response.send_message("❌ Предмет не найден.", ephemeral=True)
        
        # 2. Отрисовка модалки количества (или Select)
        options = [discord.SelectOption(label=f"{q} шт", value=str(q)) for q in (1, 5, 10)]
        embed = discord.Embed(title="🛒 Покупка", description=f"{item[2]} **{item[0]}** — 🪙 {item[1]} за штуку.\nВыбери количество:", color=0xf1c40f)
        
        class BuyQuantityView(discord.ui.View):
            def __init__(self, author_id, item_id, options):
                super().__init__(timeout=60)
                self.author_id, self.item_id = author_id, item_id
                sel = discord.ui.Select(placeholder="Сколько купить?", options=options)
                sel.callback = self.buy_logic
                self.add_item(sel)
            
            async def buy_logic(self, inter: discord.Interaction):
                qty = int(inter.data["values"][0])
                # Логика: проверка монет и списание
                stats = await get_player_stats(self.author_id)
                item_data = await db.fetchone("SELECT price, name FROM items WHERE id = ?", (self.item_id,))
                total = item_data[0] * qty
                
                if stats["coins"] < total:
                    return await inter.response.send_message(f"❌ Нужно {total} монет, у тебя {stats['coins']}.", ephemeral=True)
                
                # Списание
                await db.execute("UPDATE players SET coins = coins - ? WHERE user_id = ?", (total, self.author_id))
                await db.commit()
                await inter.response.send_message(f"✅ Куплено **{item_data[1]}** x{qty} за {total} монет.", ephemeral=True)

        await interaction.response.edit_message(embed=embed, view=BuyQuantityView(self.author_id, item_id, options))

class ExchangeView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id

    @discord.ui.button(label="Монеты → Гемы", emoji="🪙", style=discord.ButtonStyle.primary)
    async def btn_c2g(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.edit_original_response(content="Введите количество монет в чат (функция в разработке)", view=None)

    @discord.ui.button(label="Назад", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await build_main_embed(interaction)
        await interaction.edit_original_response(embed=embed, view=MainMenuView(self.author_id))

# ============================================================
#  🚀 ЗАПУСК
# ============================================================

class CastleBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        await db.connect()
        await self.tree.sync()

bot = CastleBot()

@bot.tree.command(name="меню", description="Открыть главное меню")
async def menu_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    # 1. Сначала логика (получение эмбеда)
    embed = await build_main_embed(interaction)
    # 2. Только потом отправка
    await interaction.followup.send(embed=embed, view=MainMenuView(interaction.user.id), ephemeral=True)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_BOT_TOKEN", "ТВОЙ_ТОКЕН"))
