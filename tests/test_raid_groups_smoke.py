import asyncio
import importlib.util
import pathlib
import sys

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_raid_test", BOT_PATH)
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


async def main():
    db = await aiosqlite.connect(":memory:")
    try:
        await run_checks(db)
    finally:
        await db.close()


async def run_checks(db):
    await db.executescript(SCHEMA)
    await db.commit()
    m.bot.db = db

    # 1. Три атакующих и цель. У всех по генератору за 1000.
    for uid in (1, 2, 3, 4, 5, 6):
        await db.execute(
            "INSERT INTO players (user_id, coins) VALUES (?, ?)",
            (uid, 20000 if uid == 6 else 10000 if uid == 4 else 1000),
        )
        await db.execute(
            "INSERT INTO inventory (user_id, slot, item_id, location) VALUES (?, 0, 'gen', 'profile')",
            (uid,),
        )
    await db.execute(
        "INSERT INTO items (id, name, price) VALUES ('gen', 'Генератор', 1000)"
    )
    await db.execute(
        "INSERT INTO items (id, name, price) VALUES ('weak', 'Слабый', 500)"
    )
    await db.execute("UPDATE inventory SET item_id = 'weak' WHERE user_id = 6")
    await db.commit()

    # 2. Отряд: лидер 1 + участники 2 и 3.
    party_id = await m.create_raid_party(1)
    await m.join_raid_party(party_id, 2)
    await m.join_raid_party(party_id, 3)
    party = await m.get_raid_party(1)
    assert party and m.party_member_ids(party) == [1, 2, 3], party

    # Повторное вступление запрещено.
    try:
        await m.join_raid_party(party_id, 2)
        raise AssertionError("повторное вступление не запрещено")
    except ValueError:
        pass

    # 3. Групповой рейд. Форсируем успех, чтобы проверить добычу.
    original_randint = m.random.randint
    m.random.randint = lambda a, b: b
    try:
        result, error = await m.perform_raid([1, 2, 3], 4)
    finally:
        m.random.randint = original_randint

    assert error is None, error
    assert result["success"] is True
    assert result["team_power"] == 3600, result["team_power"]  # 3000 * 1.2
    assert sum(result["loot"].values()) == 798, result["loot"]
    assert set(result["loot"]) == {1, 2, 3}, result["loot"]

    async with db.execute("SELECT coins FROM players WHERE user_id = 4") as c:
        target_coins = (await c.fetchone())[0]
    assert target_coins == 9202, target_coins

    async with db.execute(
        "SELECT user_id, amount FROM raid_loot_log ORDER BY user_id"
    ) as c:
        logs = await c.fetchall()
    assert [row[1] for row in logs] == [266, 266, 266], logs

    # 4. Все участники и цель получили кулдаун.
    for uid in (1, 2, 3):
        assert await m.get_raid_cooldown_seconds(uid) > 3500, uid
    async with db.execute(
        "SELECT last_attacked_time FROM raid_cooldowns WHERE user_id = 4"
    ) as c:
        assert (await c.fetchone())[0]

    # 5. Повторный рейд блокируется кулдауном.
    result2, error2 = await m.perform_raid([1, 2, 3], 4)
    assert result2 is None and "Кулдаун" in error2, (result2, error2)

    # 6. Щит цели блокирует атаку другим отрядом.
    result3, error3 = await m.perform_raid([5], 4)
    assert result3 is None and "щит" in error3, (result3, error3)

    # 7. Одиночный рейд и дневной лимит.
    original_randint = m.random.randint
    m.random.randint = lambda a, b: b
    try:
        result4, error4 = await m.perform_raid([5], 6)
    finally:
        m.random.randint = original_randint

    assert error4 is None, error4
    assert result4["loot"] == {5: 1000}, result4["loot"]
    assert 5 in result4["capped"], result4
    async with db.execute("SELECT coins FROM players WHERE user_id = 6") as c:
        assert (await c.fetchone())[0] == 19000

    # 8. Выход участника и передача лидерства.
    status = await m.leave_raid_party(1)
    assert status == "transferred", status
    party = await m.get_raid_party(2)
    assert party and party[1] == 2 and m.party_member_ids(party) == [2, 3], party

    # 8. Роспуск отряда при выходе последнего участника.
    assert await m.leave_raid_party(3) == "left"
    assert await m.leave_raid_party(2) == "disbanded"
    assert await m.get_raid_party(2) is None

    # 9. Детект игрока из отряда при сбросе прогресса.
    party_id = await m.create_raid_party(1)
    await m.join_raid_party(party_id, 2)
    await db.execute(
        "INSERT INTO raid_party_invites (party_id, inviter_id, target_id) VALUES (?, 1, 5)",
        (party_id,),
    )
    await db.commit()
    async with m.db_transaction():
        await m.detach_user_from_raid_party(1)
    party = await m.get_raid_party(2)
    assert party and party[1] == 2 and m.party_member_ids(party) == [2], party
    async with db.execute(
        "SELECT COUNT(*) FROM raid_party_invites WHERE inviter_id = 1 OR target_id = 5"
    ) as c:
        assert (await c.fetchone())[0] == 0
    await m.leave_raid_party(2)

    # 10. UI-эмбеды отряда различают лидера и участника.
    party_id = await m.create_raid_party(1)
    await m.join_raid_party(party_id, 2)
    leader_embed = await m.build_raid_party_embed(party_id, 1)
    member_embed = await m.build_raid_party_embed(party_id, 2)
    assert "Ты лидер" in leader_embed.description
    assert "Ты участник" in member_embed.description
    assert "Мощь отряда" in [field.name for field in leader_embed.fields]
    await m.leave_raid_party(2)
    await m.leave_raid_party(1)

    # 11. Свежее приглашение не удаляется, старое — удаляется.
    party_id = await m.create_raid_party(1)
    fresh = m.datetime.datetime.now().isoformat()
    await db.execute(
        "INSERT INTO raid_party_invites "
        "(party_id, inviter_id, target_id, created_at) VALUES (?, 1, 5, ?)",
        (party_id, fresh),
    )
    await db.commit()
    await m.cleanup_expired_raid_invites()
    async with db.execute(
        "SELECT COUNT(*) FROM raid_party_invites WHERE party_id = ?", (party_id,)
    ) as c:
        assert (await c.fetchone())[0] == 1
    old = (m.datetime.datetime.now() - m.datetime.timedelta(minutes=10)).isoformat()
    await db.execute(
        "UPDATE raid_party_invites SET created_at = ? WHERE party_id = ?",
        (old, party_id),
    )
    await db.commit()
    await m.cleanup_expired_raid_invites()
    async with db.execute(
        "SELECT COUNT(*) FROM raid_party_invites WHERE party_id = ?", (party_id,)
    ) as c:
        assert (await c.fetchone())[0] == 0
    await m.leave_raid_party(1)

    # 12. Просроченный отряд и приглашения очищаются.
    party_id = await m.create_raid_party(1)
    await db.execute(
        "INSERT INTO raid_party_invites (party_id, inviter_id, target_id) VALUES (?, 1, 5)",
        (party_id,),
    )
    await db.execute(
        "UPDATE raid_parties SET updated_at = ? WHERE id = ?",
        ((m.datetime.datetime.now() - m.datetime.timedelta(hours=2)).isoformat(), party_id),
    )
    await db.commit()
    assert await m.get_raid_party(1) is None
    async with db.execute("SELECT COUNT(*) FROM raid_parties WHERE id = ?", (party_id,)) as c:
        assert (await c.fetchone())[0] == 0
    async with db.execute(
        "SELECT COUNT(*) FROM raid_party_invites WHERE party_id = ?", (party_id,)
    ) as c:
        assert (await c.fetchone())[0] == 0

    print("RAID GROUP SMOKE TEST: OK")


def test_smoke():
    asyncio.run(main())
