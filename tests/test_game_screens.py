import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_game_screens_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.message = SimpleNamespace(id=123)
        self.embed = None
        self.view = None

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems, grid_size) "
        "VALUES (1, 1000, 1000, 9)"
    )
    await db.execute(
        "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
        "VALUES (1, 0, 'basic_gen', 'storage', 0), "
        "(1, 0, 'basic_gen', 'profile', 0)"
    )
    await db.execute(
        "INSERT OR REPLACE INTO market_prices "
        "(item_id, base_price, current_price, demand, supply) "
        "VALUES ('basic_gen', 100, 110, 2, 3)"
    )
    await db.execute(
        "INSERT INTO market_orders "
        "(user_id, side, item_id, stars, price, quantity, filled, "
        " status, expires_at) "
        "VALUES (1, 'sell', 'basic_gen', 0, 120, 1, 0, 'active', ?)",
        (
            (
                __import__("datetime").datetime.now()
                + __import__("datetime").timedelta(hours=1)
            ).isoformat(),
        ),
    )
    await db.commit()
    return db


def test_game_screens_render():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(1)
            await m.open_market_history_select(
                interaction, 1, edit=True
            )
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_market_orders(interaction, 1, selected_order=1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_market_my_orders(
                interaction, 1, selected_order=1
            )
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_market_order_create(interaction, 1, "sell")
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_market_order_create(interaction, 1, "buy")
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_market_buy_select(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_market_sell_select(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_titles_view(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_pets_shop(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_sell_view(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_move_view(interaction, "storage", 1)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            await m.open_bulk_sell_view(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_upgrades_buy_select(
                interaction,
                1,
                [
                    ("grid_4x4", "Сетка 4x4", 100, "🔲", "coins", 16),
                    ("vip", "VIP", 50, "⭐", "gems", 0),
                ],
                set(),
                0,
            )
            assert interaction.embed is not None
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
