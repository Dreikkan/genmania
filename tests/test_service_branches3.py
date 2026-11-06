import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_service_branches3_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    m._top_cache.clear()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._top_cache.clear()


def test_giveaway_reward_variants():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems, catalysts) "
                "VALUES (?, 0, 0, 0)",
                [(1,), (2,), (3,), (4,), (5,), (6,)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury, level) "
                "VALUES (1, 'Alpha', 1, 0, 1)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader')"
            )
            await db.commit()

            assert not await m.grant_status_reward(1, "bad", 7)
            assert not await m.grant_status_reward(1, "vip", 5)
            assert await m.grant_status_reward(1, "vip", 7)
            assert await m.grant_status_reward(1, "vip", 7)

            await db.execute(
                "INSERT INTO player_upgrades "
                "(user_id, upgrade_id, level, expires_at) "
                "VALUES (2, 'gold', 1, 'bad')"
            )
            await db.commit()
            assert await m.grant_status_reward(2, "gold", 7)

            original_sync = m.GIVEAWAY_RUNTIME.sync_status_bonus

            async def broken_sync(user_id):
                raise RuntimeError("broken")

            m.GIVEAWAY_RUNTIME.sync_status_bonus = broken_sync
            try:
                assert not await m.grant_status_reward(3, "vip", 7)
            finally:
                m.GIVEAWAY_RUNTIME.sync_status_bonus = original_sync

            def giveaway(reward_type, reward_id, amount):
                return (
                    1, 1, 1, 1, 1, "title",
                    reward_type, reward_id, amount, 1, "finished",
                    "", "", "", "", "global",
                )

            assert await m.giveaway_grant_reward(
                1, giveaway("coins", None, 10)
            )
            assert await m.giveaway_grant_reward(
                1, giveaway("gems", None, 10)
            )
            assert await m.giveaway_grant_reward(
                1, giveaway("catalysts", None, 10)
            )

            compensated = []

            async def fake_compensation(*args):
                compensated.append(args)

            original_compensation = m.GIVEAWAY_RUNTIME.grant_compensation
            m.GIVEAWAY_RUNTIME.grant_compensation = fake_compensation
            try:
                assert await m.giveaway_grant_reward(
                    1, giveaway("generator", "basic_gen", 1)
                )
            finally:
                m.GIVEAWAY_RUNTIME.grant_compensation = original_compensation
            assert compensated

            assert await m.giveaway_grant_reward(
                1, giveaway("pet", "cat", 1)
            )
            assert await m.giveaway_grant_reward(
                1, giveaway("pet_level", "cat", 2)
            )
            assert await m.giveaway_grant_reward(
                1, giveaway("status", "vip", 7)
            )
            assert await m.giveaway_grant_reward(
                1, giveaway("clan_level", None, 1)
            )
            assert not await m.giveaway_grant_reward(
                99, giveaway("clan_level", None, 1)
            )
            assert not await m.giveaway_grant_reward(
                1, giveaway("unknown", None, 1)
            )
        finally:
            await _close(db)

    asyncio.run(run())


def test_status_purchase_branches():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, gems) VALUES (?, ?)",
                [(1, 0), (2, 1000), (3, 1000)],
            )
            await db.commit()

            ok, message = await m.purchase_status(1, "bad", 7)
            assert not ok and "Неизвестный" in message
            ok, message = await m.purchase_status(1, "vip", 5)
            assert not ok and "срок" in message

            original_price = m.STATUS_RUNTIME.status_price
            m.STATUS_RUNTIME.status_price = lambda status_id, days: None
            try:
                ok, message = await m.purchase_status(1, "vip", 7)
                assert not ok and "цена" in message.lower()
            finally:
                m.STATUS_RUNTIME.status_price = original_price

            ok, message = await m.purchase_status(99, "vip", 7)
            assert not ok and "Профиль" in message
            ok, message = await m.purchase_status(1, "vip", 7)
            assert not ok and "Нужно" in message

            await db.execute(
                "INSERT INTO player_upgrades "
                "(user_id, upgrade_id, level, expires_at) "
                "VALUES (2, 'vip', 1, 'bad')"
            )
            await db.commit()
            ok, message = await m.purchase_status(2, "vip", 7)
            assert ok and "VIP" in message
            ok, message = await m.purchase_status(3, "vip", 7)
            assert ok
        finally:
            await _close(db)

    asyncio.run(run())


def test_market_order_errors_and_fill_paths():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) "
                "VALUES (1, 0, 0), (2, 100000, 0), (3, 100000, 0)"
            )
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "emoji, rarity, buyable) "
                "VALUES ('epic_gen', 'Epic', 100, 1, '⚙️', 'epic', 0), "
                "('weird_gen', 'Weird', 100, 1, '⚙️', 'special', 1)"
            )
            await db.execute(
                "INSERT OR REPLACE INTO market_prices "
                "(item_id, base_price, current_price) "
                "VALUES ('basic_gen', 100, 100), ('epic_gen', 100, 100), "
                "('weird_gen', 100, 100)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (2, 0, 'basic_gen', 'storage'), "
                "(2, 1, 'basic_gen', 'storage')"
            )
            await db.commit()

            ok, message = await m.buy_market_item(2, "basic_gen", 0)
            assert not ok and "больше нуля" in message
            ok, message = await m.buy_market_item(2, "legendary_gen", 1)
            assert not ok and "синтез" in message
            ok, message = await m.buy_market_item(2, "missing", 1)
            assert not ok and "не найден" in message
            ok, message = await m.buy_market_item(1, "basic_gen", 1)
            assert not ok and "Нужно" in message
            ok, message = await m.buy_market_item(2, "basic_gen", 1)
            assert ok and "Куплено" in message

            ok, message = await m.sell_market_item(2, "basic_gen", 0)
            assert not ok and "больше нуля" in message
            ok, message = await m.sell_market_item(2, "legendary_gen", 1)
            assert not ok and "синтез" in message
            ok, message = await m.sell_market_item(2, "missing", 1)
            assert not ok and "не найден" in message
            ok, message = await m.sell_market_item(2, "epic_gen", 1)
            assert not ok and "аукцион" in message
            ok, message = await m.sell_market_item(2, "basic_gen", 99)
            assert not ok and "хранилище" in message
            ok, message = await m.sell_market_item(2, "basic_gen", 1)
            assert ok and "Продано" in message

            ok, message = await m.create_market_order(
                2, "bad", "basic_gen", 1, 80
            )
            assert not ok and "сторона" in message
            ok, message = await m.create_market_order(
                2, "sell", "basic_gen", 0, 80
            )
            assert not ok and "больше нуля" in message
            ok, message = await m.create_market_order(
                2, "sell", "missing", 1, 80
            )
            assert not ok and "не найден" in message
            ok, message = await m.create_market_order(
                2, "sell", "legendary_gen", 1, 80
            )
            assert not ok and "синтез" in message
            ok, message = await m.create_market_order(
                2, "sell", "epic_gen", 1, 80
            )
            assert not ok and "хранилище" in message
            ok, message = await m.create_market_order(
                2, "sell", "weird_gen", 1, 80
            )
            assert not ok and "редкости" in message
            ok, message = await m.create_market_order(
                2, "sell", "basic_gen", 1, 1
            )
            assert not ok and "коридора" in message
            ok, message = await m.create_market_order(
                2, "sell", "basic_gen", 101, 13
            )
            assert not ok and "Максимум" in message
            ok, message = await m.create_market_order(
                2, "sell", "basic_gen", 1, 13
            )
            assert ok and "создан" in message

            await db.executemany(
                "INSERT INTO market_orders "
                "(id, user_id, side, item_id, price, quantity, filled, "
                "status, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (100, 1, "sell", "basic_gen", 80, 1, 0, "closed",
                     datetime.datetime.now().isoformat()),
                    (101, 1, "sell", "basic_gen", 80, 1, 0, "active",
                     (datetime.datetime.now()
                      - datetime.timedelta(hours=1)).isoformat()),
                    (102, 1, "sell", "basic_gen", 80, 1, 0, "active",
                     (datetime.datetime.now()
                      + datetime.timedelta(hours=1)).isoformat()),
                    (103, 1, "sell", "missing", 80, 1, 0, "active",
                     (datetime.datetime.now()
                      + datetime.timedelta(hours=1)).isoformat()),
                    (104, 2, "sell", "basic_gen", 80, 1, 0, "active",
                     (datetime.datetime.now()
                      + datetime.timedelta(hours=1)).isoformat()),
                ],
            )
            await db.commit()

            ok, message = await m.fill_market_order(999, 2)
            assert not ok and "не найден" in message
            ok, message = await m.fill_market_order(100, 2)
            assert not ok and "закрыт" in message
            ok, message = await m.fill_market_order(101, 2)
            assert not ok and "истёк" in message
            ok, message = await m.fill_market_order(102, 1)
            assert not ok and "свой" in message
            ok, message = await m.fill_market_order(103, 2)
            assert not ok and "не найден" in message
            ok, message = await m.fill_market_order(104, 2)
            assert not ok and "свой" in message

            await db.execute(
                "INSERT INTO market_orders "
                "(user_id, side, item_id, price, quantity, filled, status, "
                "expires_at) VALUES "
                "(1, 'sell', 'basic_gen', 80, 1, 0, 'active', ?), "
                "(2, 'sell', 'basic_gen', 100, 1, 0, 'active', ?), "
                "(3, 'buy', 'basic_gen', 80, 1, 0, 'active', ?), "
                "(3, 'buy', 'missing', 80, 1, 0, 'active', ?), "
                "(3, 'buy', 'basic_gen', 1, 1, 1, 'active', ?)",
                tuple(
                    (datetime.datetime.now() + datetime.timedelta(hours=1))
                    .isoformat()
                    for _ in range(5)
                ),
            )
            await db.commit()
            trades = await m.match_market_orders()
            assert isinstance(trades, list)
        finally:
            await _close(db)

    asyncio.run(run())


def test_bank_loan_and_embed_branches():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, 0)",
                [(1,), (2,), (3,)],
            )
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "emoji, rarity, buyable) "
                "VALUES ('expensive_gen', 'Expensive', 10000, 1, '⚙️', "
                "'rare', 1), ('weird_gen', 'Weird', 100, 1, '⚙️', "
                "'special', 1)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (3, 0, 'expensive_gen', 'profile')"
            )
            await db.execute(
                "INSERT INTO bank_loans (user_id, amount) VALUES (1, 100)"
            )
            await db.commit()

            ok, message = await m.take_bank_loan(1, "expensive_gen", 0, 100)
            assert not ok and "уже есть" in message
            ok, message = await m.take_bank_loan(2, "basic_gen", 0, 100)
            assert not ok and "дешёвый" in message
            ok, message = await m.take_bank_loan(3, "expensive_gen", 0, 100)
            assert ok and "Кредит" in message

            now = datetime.datetime.now()
            await db.execute(
                "INSERT INTO bank_deposits "
                "(user_id, amount, interest_rate, start_time, end_time) "
                "VALUES (2, 1000, 0.05, ?, ?)",
                (
                    now.isoformat(),
                    (now + datetime.timedelta(days=3)).isoformat(),
                ),
            )
            await db.execute(
                "INSERT INTO bank_loans "
                "(user_id, amount, interest_rate, due_time, collateral_item, "
                "collateral_stars, status) "
                "VALUES (2, 500, 0.1, ?, 'basic_gen', 2, 'active')",
                ((now + datetime.timedelta(days=7)).isoformat(),),
            )
            await db.commit()
            embed, has_deposit, has_loan = await m.build_bank_embed(2)
            names = "\n".join(field.name for field in embed.fields)
            text = "\n".join(field.value for field in embed.fields)
            assert has_deposit and has_loan
            assert "При завершении" in text
            assert "basic_gen" in text
            assert "Кредит" in names
        finally:
            await _close(db)

    asyncio.run(run())


def test_clan_war_attack_branches():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id) VALUES (?)",
                [(1,), (2,), (3,)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury, level) "
                "VALUES (1, 'Alpha', 1, 1000, 1), "
                "(2, 'Beta', 2, 1000, 1), (3, 'Gamma', 3, 1000, 1)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 2, 'leader'), "
                "(3, 3, 'leader')"
            )
            await db.execute(
                "INSERT INTO clan_wars "
                "(id, clan1_id, clan2_id, start_time, status, "
                "clan1_hp, clan2_hp, clan1_max_hp, clan2_max_hp) "
                "VALUES (1, 1, 2, ?, 'active', 1000, 1000, 1000, 1000), "
                "(2, 1, 3, ?, 'active', 1000, 1000, 1000, 1000)",
                (
                    datetime.datetime.now().isoformat(),
                    datetime.datetime.now().isoformat(),
                ),
            )
            await db.execute(
                "INSERT INTO clan_war_attacks "
                "(war_id, attacker_id, attacker_clan_id, damage, timestamp) "
                "VALUES (1, 1, 1, 1, ?)",
                (datetime.datetime.now().isoformat(),),
            )
            await db.commit()

            ok, message, finished = await m.attack_clan_war(1, 99)
            assert not ok and "не в клане" in message
            ok, message, finished = await m.attack_clan_war(999, 1)
            assert not ok and "не найдена" in message
            ok, message, finished = await m.attack_clan_war(2, 2)
            assert not ok and "не участвует" in message
            ok, message, finished = await m.attack_clan_war(1, 1)
            assert not ok and "доступна" in message
            ok, message, finished = await m.attack_clan_war(1, 2)
            assert not ok and "генераторов" in message

            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location) "
                "VALUES (2, 0, 'basic_gen', 'profile')"
            )
            await db.commit()
            ok, message, finished = await m.attack_clan_war(1, 2)
            assert ok and not finished
            assert "Удар" in message
        finally:
            await _close(db)

    asyncio.run(run())


def test_raid_finalize_updates_progress():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 0)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader')"
            )
            await db.commit()
            await m.finalize_raid({"members": [1], "success": True})
            await m.finalize_raid({"members": [1], "success": False})
        finally:
            await _close(db)

    asyncio.run(run())


def test_notification_dm_failures_and_cycle_edges():
    async def run():
        db = await _init()
        original_get_user = m.bot.get_user
        original_fetch_user = m.bot.fetch_user
        try:
            m.bot.get_user = lambda user_id: None

            async def no_user(user_id):
                return None

            m.bot.fetch_user = no_user
            assert not await m.send_dm_notification(1, "daily_ready", "hi")

            async def fetch_user(user_id):
                return SimpleNamespace(id=user_id)

            m.bot.fetch_user = fetch_user

            class ForbiddenUser:
                async def send(self, *args, **kwargs):
                    raise m.discord.Forbidden.__new__(m.discord.Forbidden)

            m.bot.get_user = lambda user_id: ForbiddenUser()
            assert not await m.send_dm_notification(
                1, "daily_ready", "hi"
            )
            rows = await db.execute_fetchall(
                "SELECT body FROM notification_fallback WHERE user_id = 1"
            )
            assert rows and rows[0][0] == "hi"

            class NotFoundUser:
                async def send(self, *args, **kwargs):
                    raise m.discord.NotFound.__new__(m.discord.NotFound)

            m.bot.get_user = lambda user_id: NotFoundUser()
            assert not await m.send_dm_notification(
                1, "daily_ready", "hi"
            )

            class HTTPUser:
                async def send(self, *args, **kwargs):
                    raise m.discord.HTTPException.__new__(
                        m.discord.HTTPException
                    )

            m.bot.get_user = lambda user_id: HTTPUser()
            assert not await m.send_dm_notification(
                1, "daily_ready", "hi"
            )

            m.bot.get_user = lambda user_id: None

            async def fetch_ok(user_id):
                return SimpleNamespace(id=user_id, send=AsyncMockSend())

            m.bot.fetch_user = fetch_ok
            now = datetime.datetime.now()
            await db.execute(
                "INSERT INTO players (user_id) VALUES (1), (2)"
            )
            await db.execute(
                "INSERT INTO user_pets_v2 "
                "(user_id, pet_id, level, last_fed) "
                "VALUES (1, 'cat', 10, NULL), (2, 'cat', 1, NULL)"
            )
            await db.execute(
                "UPDATE players SET active_pet = 'cat' WHERE user_id IN (1, 2)"
            )
            await db.execute(
                "UPDATE players SET last_daily = ? WHERE user_id = 2",
                (now.isoformat(),),
            )
            await db.execute(
                "INSERT INTO autocollectors "
                "(user_id, level, last_auto) VALUES (1, 1, NULL)"
            )
            await db.execute(
                "INSERT INTO user_notifications "
                "(user_id, notif_type, last_sent) "
                "VALUES (2, 'autocollect', ?)",
                ((now + datetime.timedelta(hours=1)).isoformat(),),
            )
            await db.execute(
                "INSERT INTO auctions "
                "(seller_id, item_id, current_bid, end_time, status) "
                "VALUES (1, 'basic_gen', 10, ?, 'active')",
                ((now + datetime.timedelta(hours=5)).isoformat(),),
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 0), (2, 'Beta', 2, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 2, 'leader')"
            )
            await db.execute(
                "INSERT INTO clan_wars "
                "(clan1_id, clan2_id, start_time, status) "
                "VALUES (1, 2, ?, 'active')",
                (now.isoformat(),),
            )
            await db.commit()

            original_max = m.NOTIFICATION_RUNTIME.max_sent_per_cycle
            m.NOTIFICATION_RUNTIME.max_sent_per_cycle = 0
            try:
                assert await m.run_notification_cycle() == 0
            finally:
                m.NOTIFICATION_RUNTIME.max_sent_per_cycle = original_max
        finally:
            m.bot.get_user = original_get_user
            m.bot.fetch_user = original_fetch_user
            await _close(db)

    asyncio.run(run())


class AsyncMockSend:
    async def __call__(self, *args, **kwargs):
        return None

    async def send(self, *args, **kwargs):
        return None
