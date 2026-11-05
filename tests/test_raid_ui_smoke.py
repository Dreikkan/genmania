import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite
import discord

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_raid_ui_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


SCHEMA = """
CREATE TABLE players (
    user_id INTEGER PRIMARY KEY,
    coins INTEGER DEFAULT 0,
    gems INTEGER DEFAULT 0,
    catalysts INTEGER DEFAULT 0,
    total_crafts INTEGER DEFAULT 0,
    total_successes INTEGER DEFAULT 0,
    total_coins_earned INTEGER DEFAULT 0,
    total_gems_earned INTEGER DEFAULT 0,
    income_bonus REAL DEFAULT 0,
    grid_size INTEGER DEFAULT 9,
    storage_size INTEGER DEFAULT 36,
    title TEXT DEFAULT 'Новичок',
    active_pet TEXT DEFAULT NULL,
    raid_wins INTEGER DEFAULT 0,
    prestige_points INTEGER DEFAULT 0
);
CREATE TABLE items (
    id TEXT PRIMARY KEY,
    name TEXT,
    price INTEGER,
    income_per_hour INTEGER DEFAULT 0,
    income_gems_per_hour REAL DEFAULT 0,
    emoji TEXT DEFAULT '📦',
    rarity TEXT DEFAULT 'common',
    buyable INTEGER DEFAULT 1,
    emoji_by_star TEXT DEFAULT '{}'
);
CREATE TABLE inventory (
    user_id INTEGER,
    slot INTEGER,
    item_id TEXT,
    location TEXT DEFAULT 'profile',
    stars INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, location, slot)
);
CREATE TABLE user_pets_v2 (
    user_id INTEGER,
    pet_id TEXT,
    level INTEGER DEFAULT 1,
    last_fed TIMESTAMP DEFAULT NULL,
    PRIMARY KEY (user_id, pet_id)
);
CREATE TABLE raid_parties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    leader_id INTEGER,
    member2_id INTEGER DEFAULT NULL,
    member3_id INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NULL
);
CREATE TABLE raid_party_invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    party_id INTEGER,
    inviter_id INTEGER,
    target_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (party_id, target_id)
);
CREATE TABLE raid_cooldowns (
    user_id INTEGER PRIMARY KEY,
    last_raid_time TIMESTAMP,
    last_attacked_time TIMESTAMP
);
CREATE TABLE raid_loot_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    target_id INTEGER,
    amount INTEGER,
    date TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class FakeMessage:
    def __init__(self):
        self.edited = None
        self.deleted = False

    async def edit(self, **kwargs):
        self.edited = kwargs

    async def delete(self):
        self.deleted = True


class FakeResponse:
    def __init__(self):
        self.done = False
        self.modal = None
        self.messages = []

    def is_done(self):
        return self.done

    async def defer(self, ephemeral=False):
        self.done = True
        self.ephemeral = ephemeral

    async def send_message(self, content=None, embed=None, view=None, ephemeral=False):
        self.messages.append(
            {"content": content, "embed": embed, "view": view, "ephemeral": ephemeral}
        )

    async def send_modal(self, modal):
        self.modal = modal


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, content=None, embed=None, view=None, ephemeral=False):
        message = FakeMessage()
        self.messages.append(
            {
                "content": content,
                "embed": embed,
                "view": view,
                "ephemeral": ephemeral,
                "message": message,
            }
        )
        return message


class FakeChannel(discord.abc.Messageable):
    def __init__(self):
        self.messages = []

    async def send(self, content=None, embed=None, view=None):
        message = FakeMessage()
        message.content = content
        message.embed = embed
        message.view = view
        self.messages.append(message)
        return message


class FakeInteraction:
    def __init__(self, user_id, channel=None):
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = 1
        self.channel = channel or FakeChannel()
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.message = FakeMessage()
        self.edits = []

    async def edit_original_response(self, **kwargs):
        self.edits.append(kwargs)


async def main():
    db = await aiosqlite.connect(":memory:")
    try:
        await run_checks(db)
    finally:
        await db.close()


async def run_checks(db):
    await db.executescript(SCHEMA)
    for uid in (1, 2, 3, 4):
        await db.execute(
            "INSERT INTO players (user_id, coins) VALUES (?, ?)",
            (uid, 10000 if uid == 3 else 1000),
        )
        await db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location) "
            "VALUES (?, 0, ?, 'profile')",
            (uid, "gen"),
        )
    await db.execute(
        "INSERT INTO items (id, name, price) VALUES ('gen', 'Генератор', 1000)"
    )
    await db.execute(
        "INSERT INTO items (id, name, price) VALUES ('weak', 'Слабый', 500)"
    )
    await db.commit()
    m.bot.db = db

    # finalize/delete не проверяем здесь — их покрывает SQLite-тест.
    async def noop_finalize(result):
        return None

    async def noop_delete(message, delay):
        return None

    m.finalize_raid = noop_finalize
    m.delete_message_later = noop_delete

    leader = FakeInteraction(1)
    member = FakeInteraction(2, channel=leader.channel)

    # 1. Меню рейда.
    await m.open_raid_menu(leader, 1)
    assert "Подготовка к рейду" in leader.edits[-1]["embed"].title

    # 2. Создание отряда.
    menu_view = m.RaidMenuView(1)
    await menu_view.btn_party.callback(leader)
    party = await m.get_raid_party(1)
    assert party and party[1] == 1
    party_id = party[0]

    # 3. Приглашение участника через модалку.
    party_view = m.RaidPartyView(1, party_id)
    await party_view.btn_invite.callback(leader)
    invite_modal = leader.response.modal
    assert isinstance(invite_modal, m.RaidInviteModal)
    invite_modal.target_id._value = "2"
    await invite_modal.on_submit(leader)

    invite_message = leader.channel.messages[-1]
    assert invite_message.view is not None
    assert "Приглашение в отряд" in invite_message.embed.title

    # 4. Принятие приглашения.
    member.message = invite_message
    await invite_message.view.accept.callback(member)
    party = await m.get_raid_party(1)
    assert m.party_member_ids(party) == [1, 2], party
    assert "принято" in invite_message.edited["embed"].title.lower()

    # 5. Участник не может начать рейд.
    member_view = m.RaidPartyView(2, party_id)
    await member_view.btn_start.callback(member)
    assert member.response.messages
    assert "Только лидер" in member.response.messages[-1]["content"]

    # 6. Лидер начинает рейд; random форсирует успех.
    leader_view = m.RaidPartyView(1, party_id)
    await leader_view.btn_start.callback(leader)
    start_modal = leader.response.modal
    assert isinstance(start_modal, m.RaidTargetModal)
    start_modal.target_id._value = "3"

    original_randint = m.random.randint
    m.random.randint = lambda a, b: b
    try:
        await start_modal.on_submit(leader)
    finally:
        m.random.randint = original_randint

    assert leader.followup.messages, "результат рейда не отправлен"
    result_embed = leader.followup.messages[-1]["embed"]
    assert "Успешный рейд" in result_embed.description

    # 7. Кулдаун у обоих участников.
    assert await m.get_raid_cooldown_seconds(1) > 3000
    assert await m.get_raid_cooldown_seconds(2) > 3000

    print("RAID UI SMOKE TEST: OK")


def test_smoke():
    asyncio.run(main())
