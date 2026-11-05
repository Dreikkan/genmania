import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_safe_sell_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.done = False

    async def defer(self, *args, **kwargs):
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
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.edited = None

    async def edit_original_response(self, **kwargs):
        self.edited = kwargs


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute("INSERT INTO players (user_id, coins) VALUES (1, 0)")
    await db.commit()
    return db


async def _insert(db, slot, item_id, stars=0, location="storage"):
    await db.execute(
        "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
        "VALUES (1, ?, ?, ?, ?)",
        (slot, item_id, location, stars),
    )


def test_bulk_sell_summary_protects_stars_epic_and_profile():
    async def run():
        db = await _init()
        try:
            await _insert(db, 0, "basic_gen", 0)
            await _insert(db, 1, "basic_gen", 0)
            await _insert(db, 2, "basic_gen", 1)
            await _insert(db, 3, "copper_gen", 0)
            await _insert(db, 4, "gold_gen", 0)
            await _insert(db, 5, "ruby_gen", 0)
            await _insert(db, 0, "basic_gen", 0, location="profile")
            await db.commit()

            summary = await m.get_bulk_sell_summary(1)
            assert summary["common"]["count"] == 3, summary
            assert summary["rare"]["count"] == 1, summary
            assert summary["dupes"]["count"] == 1, summary
            assert summary["uncommon"]["count"] == 0, summary

            basic_price = next(
                row[0]
                for row in await (
                    await db.execute(
                        "SELECT price FROM items WHERE id = 'basic_gen'"
                    )
                ).fetchall()
            )
            assert summary["dupes"]["total"] == m.calculate_sell_price(
                basic_price, 0
            ), summary

            interaction = FakeInteraction(1)
            embed = await m.build_storage_embed(interaction)
            assert "Быстрая продажа 0★" in embed.description
            assert "Звёздные" in embed.description
            assert "энергостанции" in embed.description
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_bulk_sell_common_and_double_confirmation():
    async def run():
        db = await _init()
        try:
            await _insert(db, 0, "basic_gen", 0)
            await _insert(db, 1, "basic_gen", 0)
            await _insert(db, 2, "basic_gen", 1)
            await _insert(db, 3, "copper_gen", 0)
            await _insert(db, 4, "gold_gen", 0)
            await _insert(db, 5, "ruby_gen", 0)
            await _insert(db, 0, "basic_gen", 0, location="profile")
            await db.commit()

            summary = await m.get_bulk_sell_summary(1)
            ok, message, count, total = await m.perform_bulk_sell(1, "common")
            assert ok is True, message
            assert count == 3
            assert total == summary["common"]["total"]
            assert "3" in message

            async with db.execute("SELECT coins FROM players WHERE user_id = 1") as c:
                assert (await c.fetchone())[0] == total
            async with db.execute(
                "SELECT item_id, stars, location FROM inventory "
                "WHERE user_id = 1 ORDER BY location, slot"
            ) as c:
                rows = await c.fetchall()
            assert ("basic_gen", 0, "profile") in rows
            assert ("basic_gen", 1, "storage") in rows
            assert ("gold_gen", 0, "storage") in rows
            assert ("ruby_gen", 0, "storage") in rows
            assert not any(
                item_id == "copper_gen" for item_id, _stars, _loc in rows
            )
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_bulk_sell_duplicates_keeps_one_copy():
    async def run():
        db = await _init()
        try:
            await _insert(db, 0, "basic_gen", 0)
            await _insert(db, 1, "basic_gen", 0)
            await _insert(db, 2, "copper_gen", 0)
            await db.commit()

            summary = await m.get_bulk_sell_summary(1)
            assert summary["dupes"]["count"] == 1, summary
            ok, message, count, total = await m.perform_bulk_sell(1, "dupes")
            assert ok is True, message
            assert count == 1
            assert total == summary["dupes"]["total"]

            async with db.execute(
                "SELECT item_id, stars FROM inventory WHERE user_id = 1 "
                "ORDER BY item_id, slot"
            ) as c:
                rows = await c.fetchall()
            assert rows == [("basic_gen", 0), ("copper_gen", 0)], rows
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_storage_filters():
    rows = [
        (0, "a", "🅰️", 0, 10, "common", 0),
        (1, "b", "🅱️", 2, 20, "rare", 1),
        (2, "c", "🇨", 0, 30, "epic", 0),
    ]
    assert m.filter_storage_rows(rows, "all") == rows
    assert [row[0] for row in m.filter_storage_rows(rows, "zero")] == [0, 2]
    assert [row[0] for row in m.filter_storage_rows(rows, "starred")] == [1]
    assert [row[0] for row in m.filter_storage_rows(rows, "locked")] == [1]
    assert [row[0] for row in m.filter_storage_rows(rows, "common")] == [0]
    assert [row[0] for row in m.filter_storage_rows(rows, "epic")] == [2]


def test_locked_items_are_not_bulk_sold():
    async def run():
        db = await _init()
        try:
            await _insert(db, 0, "basic_gen", 0)
            await _insert(db, 1, "copper_gen", 0)
            await db.execute(
                "UPDATE inventory SET is_locked = 1 "
                "WHERE user_id = 1 AND slot = 0"
            )
            await db.commit()

            summary = await m.get_bulk_sell_summary(1)
            assert summary["common"]["count"] == 1, summary
            ok, message, count, _total = await m.perform_bulk_sell(1, "common")
            assert ok is True, message
            assert count == 1

            async with db.execute(
                "SELECT item_id, is_locked FROM inventory "
                "WHERE user_id = 1 AND location = 'storage'"
            ) as c:
                rows = await c.fetchall()
            assert rows == [("basic_gen", 1)], rows
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_toggle_lock_and_lock_view():
    async def run():
        db = await _init()
        try:
            await _insert(db, 0, "basic_gen", 0)
            await db.commit()

            ok, state, message = await m.toggle_item_lock(
                1, "storage", 0, "basic_gen", 0
            )
            assert ok is True and state == 1, message
            async with db.execute(
                "SELECT is_locked FROM inventory WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 1

            interaction = FakeInteraction(1)
            await m.open_lock_view(interaction, 1)
            view = interaction.edited["view"]
            select = next(
                child
                for child in view.children
                if isinstance(child, m.discord.ui.Select)
            )
            assert select.options[0].label.startswith("🔒"), select.options[0].label

            ok, state, message = await m.toggle_item_lock(
                1, "storage", 0, "basic_gen", 0
            )
            assert ok is True and state == 0, message
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_storage_embed_respects_filter():
    async def run():
        db = await _init()
        try:
            await _insert(db, 0, "basic_gen", 0)
            await _insert(db, 1, "gold_gen", 1)
            await db.commit()

            interaction = FakeInteraction(1)
            embed = await m.build_storage_embed(interaction, "zero")
            assert "Фильтр: **0★**" in embed.description
            assert "Показано **1/2**" in embed.description
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_inventory_sorting_renumbers_slots():
    async def run():
        db = await _init()
        try:
            await _insert(db, 0, "basic_gen", 0)
            await _insert(db, 1, "gold_gen", 1)
            await _insert(db, 2, "copper_gen", 0)
            await db.commit()

            for sort_type in (
                "price_desc",
                "price_asc",
                "stars_desc",
                "stars_asc",
                "income_desc",
                "rarity_desc",
                "unknown",
            ):
                await m.sort_inventory_by(1, "storage", sort_type)
                rows = await m.get_inventory_rows(1, "storage")
                assert [row[0] for row in rows] == [0, 1, 2]

            await m.sort_inventory(1, "storage")
            rows = await m.get_inventory_rows(1, "storage")
            assert [row[0] for row in rows] == [0, 1, 2]
            assert [row[5] for row in rows] == sorted(
                (row[5] for row in rows), reverse=True
            )
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_profile_filters():
    rows = [
        (0, "a", "A", "🅰️", 0, 10, "common", 0),
        (1, "b", "B", "🅱️", 2, 20, "rare", 1),
        (2, "c", "C", "🇨", 0, 30, "mythic", 0),
    ]
    assert [row[0] for row in m.filter_profile_rows(rows, "zero")] == [0, 2]
    assert [row[0] for row in m.filter_profile_rows(rows, "starred")] == [1]
    assert [row[0] for row in m.filter_profile_rows(rows, "locked")] == [1]
    assert [row[0] for row in m.filter_profile_rows(rows, "common")] == [0]
    assert [row[0] for row in m.filter_profile_rows(rows, "epic")] == [2]


def test_profile_filter_and_mass_operations():
    async def run():
        db = await _init()
        try:
            await _insert(db, 0, "basic_gen", 0, location="profile")
            await _insert(db, 1, "copper_gen", 1, location="profile")
            await db.execute(
                "UPDATE inventory SET is_locked = 1 "
                "WHERE user_id = 1 AND location = 'profile' AND slot = 1"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            embed = await m.build_profile_embed(interaction, "zero")
            assert "Фильтр: 0★" in embed.footer.text
            assert "Показано 1/2" in embed.footer.text

            ok, message, count = await m.mass_lock_profile(1, "zero", 1)
            assert ok is True, message
            assert count == 1
            async with db.execute(
                "SELECT is_locked FROM inventory "
                "WHERE user_id = 1 AND location = 'profile' AND slot = 0"
            ) as c:
                assert (await c.fetchone())[0] == 1

            ok, message, count = await m.mass_move_zero_star_to_storage(1)
            assert ok is True, message
            assert count == 1
            async with db.execute(
                "SELECT location, is_locked FROM inventory "
                "WHERE user_id = 1 AND item_id = 'basic_gen'"
            ) as c:
                assert (await c.fetchone())[0:2] == ("storage", 1)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_storage_mass_lock_and_move_to_station():
    async def run():
        db = await _init()
        try:
            await _insert(db, 0, "basic_gen", 0)
            await _insert(db, 1, "copper_gen", 1)
            await db.execute(
                "UPDATE inventory SET is_locked = 1 "
                "WHERE user_id = 1 AND slot = 0"
            )
            await db.commit()

            ok, message, count = await m.mass_lock_location(
                1, "storage", "all", 1
            )
            assert ok is True, message
            assert count == 2
            async with db.execute(
                "SELECT COUNT(*) FROM inventory "
                "WHERE user_id = 1 AND location = 'storage' AND is_locked = 1"
            ) as c:
                assert (await c.fetchone())[0] == 2

            ok, message, count = await m.mass_move_zero_star_to_profile(1)
            assert ok is True, message
            assert count == 1
            async with db.execute(
                "SELECT location, is_locked FROM inventory "
                "WHERE user_id = 1 AND item_id = 'basic_gen'"
            ) as c:
                assert (await c.fetchone())[0:2] == ("profile", 1)
            async with db.execute(
                "SELECT location FROM inventory "
                "WHERE user_id = 1 AND item_id = 'copper_gen'"
            ) as c:
                assert (await c.fetchone())[0] == "storage"

            view = m.MassOpsView(
                1, "all", has_visible=True, zero_count=1, location="storage"
            )
            labels = [
                child.label
                for child in view.children
                if isinstance(child, m.discord.ui.Button)
            ]
            assert "0★ на станцию" in labels, labels
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_bulk_sell_view_disables_empty_categories():
    async def run():
        db = await _init()
        try:
            await _insert(db, 0, "basic_gen", 0)
            await db.commit()
            summary = await m.get_bulk_sell_summary(1)
            view = m.BulkSellView(1, summary)
            buttons = {
                child.label: child
                for child in view.children
                if isinstance(child, m.discord.ui.Button)
            }
            assert buttons["Обычные 0★"].disabled is False
            assert buttons["Необычные 0★"].disabled is True
            assert buttons["Редкие 0★"].disabled is True
            assert buttons["Дубликаты 0★"].disabled is True
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
