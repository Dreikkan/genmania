import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_shop_market_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.done = False
        self.messages = []

    def is_done(self):
        return self.done

    async def defer(self, *args, **kwargs):
        self.done = True

    async def send_message(self, text=None, **kwargs):
        self.messages.append((text, kwargs))
        self.done = True

    async def edit_message(self, **kwargs):
        self.done = True


class FakeFollowup:
    async def send(self, *args, **kwargs):
        return None


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.data = {}
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.edited = None

    async def edit_original_response(self, **kwargs):
        self.edited = kwargs


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _basic_item_at(db, price=100):
    await db.execute(
        "UPDATE items SET price = ?, buyable = 1 WHERE id = 'basic_gen'",
        (price,),
    )
    await db.execute(
        "UPDATE market_prices SET base_price = ?, current_price = ? "
        "WHERE item_id = 'basic_gen'",
        (price, price),
    )


def test_market_price_bounds_and_starter_math():
    assert m.market_price_bounds(100, True) == (80, 120)
    assert m.market_price_bounds(100, False) == (50, 200)
    assert m.market_order_price_bounds(100, True) == (80, 100)
    assert m.market_order_price_bounds(100, False) == (50, 200)
    assert m.clamp_market_price(500, 100, True) == 120
    assert m.clamp_market_price(10, 100, True) == 80
    assert m.starter_shop_total(15, 1) == 7
    assert m.starter_shop_total(15, 3) == 37
    assert m.starter_shop_total(15, 0) == 0


def test_market_initial_prices_match_shop():
    async def run():
        db = await _init()
        try:
            async with db.execute(
                "SELECT i.id, i.price, mp.base_price, mp.current_price "
                "FROM items i JOIN market_prices mp ON mp.item_id = i.id"
            ) as c:
                rows = await c.fetchall()
            assert rows
            for item_id, shop_price, base_price, current_price in rows:
                assert base_price == shop_price, item_id
                assert current_price == shop_price, item_id
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_starter_discount_is_only_for_new_players():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 20), (2, 20)"
            )
            await db.commit()
            assert await m.is_starter_shop_purchase(1, "basic_gen") is True

            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0)"
            )
            await db.commit()
            assert await m.is_starter_shop_purchase(1, "basic_gen") is False

            await m.complete_onboarding_step(2, "buy_generator")
            assert await m.is_starter_shop_purchase(2, "basic_gen") is False
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_first_shop_purchase_uses_discount_once():
    async def run():
        db = await _init()
        try:
            await db.execute("INSERT INTO players (user_id, coins) VALUES (1, 20)")
            await db.execute(
                "UPDATE items SET price = 15, buyable = 1 WHERE id = 'basic_gen'"
            )
            await db.commit()

            view = m.BuyItemQuantityView(1, "basic_gen")
            first = FakeInteraction(1)
            first.data = {"values": ["1"]}
            await view.quantity_select(first)
            # 20 - 7 (скидка 50%) + 50 (награда онбординга) = 63.
            async with db.execute("SELECT coins FROM players WHERE user_id = 1") as c:
                coins_after_first = (await c.fetchone())[0]
            assert coins_after_first == 63, coins_after_first

            second_view = m.BuyItemQuantityView(1, "basic_gen")
            second = FakeInteraction(1)
            second.data = {"values": ["1"]}
            await second_view.quantity_select(second)
            # Вторая покупка уже полная: 63 - 15 = 48.
            async with db.execute("SELECT coins FROM players WHERE user_id = 1") as c:
                assert (await c.fetchone())[0] == 48
            async with db.execute(
                "SELECT COUNT(*) FROM inventory WHERE user_id = 1 "
                "AND item_id = 'basic_gen'"
            ) as c:
                assert (await c.fetchone())[0] == 2
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_market_buy_clamps_inflated_price():
    async def run():
        db = await _init()
        try:
            await db.execute("INSERT INTO players (user_id, coins) VALUES (1, 10000)")
            await _basic_item_at(db, 100)
            await db.execute(
                "UPDATE market_prices SET current_price = 500 "
                "WHERE item_id = 'basic_gen'"
            )
            await db.commit()

            ok, message = await m.buy_market_item(1, "basic_gen", 1)
            assert ok is True, message
            async with db.execute("SELECT coins FROM players WHERE user_id = 1") as c:
                assert (await c.fetchone())[0] == 9880
            async with db.execute(
                "SELECT current_price FROM market_prices WHERE item_id = 'basic_gen'"
            ) as c:
                assert (await c.fetchone())[0] == 120
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_market_sell_cannot_beat_shop_price():
    async def run():
        db = await _init()
        try:
            await db.execute("INSERT INTO players (user_id, coins) VALUES (1, 1000)")
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'storage', 0)"
            )
            await _basic_item_at(db, 100)
            await db.execute(
                "UPDATE market_prices SET current_price = 500 "
                "WHERE item_id = 'basic_gen'"
            )
            await db.commit()

            ok, message = await m.sell_market_item(1, "basic_gen", 1)
            assert ok is True, message
            async with db.execute("SELECT coins FROM players WHERE user_id = 1") as c:
                assert (await c.fetchone())[0] == 1084
            async with db.execute(
                "SELECT current_price FROM market_prices WHERE item_id = 'basic_gen'"
            ) as c:
                assert (await c.fetchone())[0] <= 120
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_market_orders_enforce_corridor_and_synthesis_only():
    async def run():
        db = await _init()
        try:
            await db.execute("INSERT INTO players (user_id, coins) VALUES (1, 1000)")
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'storage', 0)"
            )
            await _basic_item_at(db, 100)
            await db.commit()

            ok, message = await m.create_market_order(
                1, "sell", "basic_gen", 1, 150
            )
            assert ok is False and "коридор" in message.lower(), message

            ok, message = await m.create_market_order(
                1, "sell", "basic_gen", 1, 100
            )
            assert ok is True, message

            ok, message = await m.create_market_order(
                1, "sell", "space_gen", 1, 100
            )
            assert ok is False and "только синтез" in message.lower(), message
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_shop_shows_market_price_and_synthesis_only():
    async def run():
        db = await _init()
        try:
            await db.execute("INSERT INTO players (user_id, coins) VALUES (1, 1000)")
            await _basic_item_at(db, 15)
            await db.execute(
                "UPDATE market_prices SET current_price = 500 "
                "WHERE item_id = 'basic_gen'"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            fields = {}
            for page in range(4):
                embed, total_pages = await m.build_shop_page(interaction, page)
                for field in embed.fields:
                    fields[field.name] = field.value
                if page >= total_pages - 1:
                    break

            basic = next(v for k, v in fields.items() if "basic_gen" in k)
            space = next(v for k, v in fields.items() if "space_gen" in k)
            ruby = next(v for k, v in fields.items() if "ruby_gen" in k)

            assert "Цена:" in basic and "Биржа:" in basic
            assert " 18 " in basic, basic
            assert "Только синтез" in space and "Биржа:" not in space
            assert "Покупка на бирже/аукционе" in ruby
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_market_view_hides_synthesis_only():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(1)
            fields = []
            for page in range(10):
                embed, total_pages = await m.build_market_embed(
                    interaction, "mythic", "name", page
                )
                fields.extend(embed.fields)
                if page >= total_pages - 1:
                    break
            names = "\n".join(field.name for field in fields)
            assert "Пространственный" not in names
            assert "Божественный" not in names
            assert "Легендарный" not in names
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
