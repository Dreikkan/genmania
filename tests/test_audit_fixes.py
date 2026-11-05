import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_audit_fixes_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, text=None, **kwargs):
        self.messages.append((text, kwargs))


class FakeResponse:
    async def defer(self, *args, **kwargs):
        return None

    async def send_message(self, *args, **kwargs):
        return None


class FakeInteraction:
    def __init__(self, user_id=1, guild_id=None):
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = guild_id
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.message = None


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._top_cache.clear()
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems) VALUES "
        "(1, 1000, 1000), (2, 100, 100)"
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None
    m._DB_TX_OWNER = None
    m._settings_cache.clear()
    m._top_cache.clear()


def test_members_intent_enabled():
    assert m.intents.members is True


def test_battle_pass_labels_match_actions():
    assert "story_quest" in m.SEASON_XP_ACTIONS
    assert "achievement" not in m.SEASON_XP_ACTIONS
    assert any("Сюжетный квест: +200" in line for line in m.SEASON_XP_HELP_LINES)
    assert any("Достижение: +100" in line for line in m.SEASON_XP_HELP_LINES)


def test_top_excludes_flagged_admins_and_empty_local_scope():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "UPDATE players SET top_excluded = 1 WHERE user_id = 1"
            )
            await db.commit()
            rows = await m.get_top_players("coins")
            assert rows == [(2, 100)]
            assert await m.get_top_players("coins", guild_id=999999) == []
        finally:
            await _close(db)

    asyncio.run(run())


def test_top_power_uses_combat_power_bonuses():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (?, 0, 'basic_gen', 'profile', 0)",
                [(1,), (2,)],
            )
            await db.execute(
                "UPDATE players SET active_pet = 'dragon' WHERE user_id = 1"
            )
            await db.execute(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level, last_fed) "
                "VALUES (1, 'dragon', 1, NULL)"
            )
            await db.commit()
            rows = await m.get_top_players("power")
            assert rows[0][0] == 1
            assert rows[0][1] == await m.get_combat_power(1)
        finally:
            await _close(db)

    asyncio.run(run())


def test_admin_self_grant_marks_top_exclusion_and_notifies():
    async def run():
        db = await _init()
        try:
            modal = m.AdminGrantValuesModal(1, "coins")
            modal.user_id._value = "1"
            modal.amount._value = "50"
            interaction = FakeInteraction(user_id=1)
            await modal.on_submit(interaction)
            assert interaction.followup.messages
            text = " ".join(
                msg[0] or "" for msg in interaction.followup.messages
            )
            assert "исключён из топов" in text
            async with db.execute(
                "SELECT top_excluded, coins FROM players WHERE user_id = 1"
            ) as c:
                excluded, coins = await c.fetchone()
            assert excluded == 1
            assert coins == 1050
        finally:
            await _close(db)

    asyncio.run(run())


def test_enforce_top_exclusion_flags_and_notifies():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(user_id=1)
            changed = await m.enforce_top_exclusion(
                interaction, 1, "test:self_grant"
            )
            assert changed is True
            assert interaction.followup.messages
            assert "исключён из топов" in interaction.followup.messages[-1][0]
            async with db.execute(
                "SELECT top_excluded FROM players WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 1
        finally:
            await _close(db)

    asyncio.run(run())


def test_buyout_without_space_uses_mailbox_not_full_price():
    async def run():
        db = await _init()
        original_place = m.place_items
        try:
            async def no_space(*args, **kwargs):
                raise ValueError("no space")

            m.place_items = no_space
            await db.execute(
                "INSERT INTO auctions "
                "(seller_id, item_id, stars, start_price, current_bid, "
                "buyout_price, end_time, status) "
                "VALUES (1, 'basic_gen', 0, 1, 0, 2, ?, 'active')",
                ((datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat(),),
            )
            await db.commit()
            ok, _msg, compensation = await m.buyout_auction(2, 1)
            assert ok is True
            assert compensation == 0
            async with db.execute(
                "SELECT coins FROM players WHERE user_id = 2"
            ) as c:
                assert (await c.fetchone())[0] == 98
            async with db.execute(
                "SELECT COUNT(*) FROM mailbox WHERE user_id = 2"
            ) as c:
                assert (await c.fetchone())[0] == 1
        finally:
            m.place_items = original_place
            await _close(db)

    asyncio.run(run())


def test_expired_sell_order_without_space_goes_to_mailbox():
    async def run():
        db = await _init()
        original_place = m.place_items
        try:
            async def no_space(*args, **kwargs):
                raise ValueError("no space")

            m.place_items = no_space
            await db.execute(
                "INSERT INTO market_orders "
                "(user_id, side, item_id, stars, price, quantity, filled, "
                "status, expires_at) "
                "VALUES (1, 'sell', 'basic_gen', 0, 10, 2, 0, 'active', ?)",
                ((datetime.datetime.now() - datetime.timedelta(minutes=1)).isoformat(),),
            )
            await db.commit()
            await m.expire_market_orders()
            async with db.execute(
                "SELECT status FROM market_orders"
            ) as c:
                assert (await c.fetchone())[0] == "expired"
            async with db.execute(
                "SELECT COUNT(*), SUM(quantity) FROM mailbox WHERE user_id = 1"
            ) as c:
                count, qty = await c.fetchone()
            assert count == 1 and qty == 2
        finally:
            m.place_items = original_place
            await _close(db)

    asyncio.run(run())


def test_self_reset_blocks_active_market_order():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO market_orders "
                "(user_id, side, item_id, stars, price, quantity, filled, "
                "status, expires_at) "
                "VALUES (1, 'buy', 'basic_gen', 0, 10, 1, 0, 'active', ?)",
                ((datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat(),),
            )
            await db.commit()
            modal = m.UserResetModal(1)
            modal.confirm._value = "СБРОСИТЬ"
            interaction = FakeInteraction(user_id=1)
            await modal.on_submit(interaction)
            assert interaction.followup.messages
            assert "ордера биржи" in interaction.followup.messages[-1][0]
            async with db.execute(
                "SELECT COUNT(*) FROM market_orders WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 1
        finally:
            await _close(db)

    asyncio.run(run())
