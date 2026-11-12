import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_generator_ui_extensions", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.messages = []

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_modal(self, modal):
        self.messages.append((modal,))


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(
            id=1, owner_id=1, get_role=lambda rid: None
        )
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": ["1"]}
        self.message = None
        self.edited = []

    async def edit_original_response(self, *args, **kwargs):
        self.edited.append((args, kwargs))


async def _init(grid_size=16, storage_size=50):
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players "
        "(user_id, coins, gems, catalysts, grid_size, storage_size) "
        "VALUES (1, 100000, 10000, 20, ?, ?)",
        (grid_size, storage_size),
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


async def _add_inventory(db, entries, location="profile"):
    await db.executemany(
        "INSERT INTO inventory "
        "(user_id, slot, item_id, location, stars) "
        "VALUES (1, ?, ?, ?, ?)",
        [
            (slot, item_id, location, stars)
            for slot, item_id, stars in entries
        ],
    )
    await db.commit()


async def _delete_inventory(db):
    await db.execute("DELETE FROM inventory WHERE user_id = 1")
    await db.commit()


def test_starred_craft_and_target_selection():
    async def run():
        db = await _init()
        original_random = m.random.random
        m.random.random = lambda: 0.0
        try:
            await _add_inventory(
                db,
                [(slot, "copper_gen", 2) for slot in range(3)],
            )
            result = await m.craft_attempt(
                1, "copper_gen", False, use_starred=True
            )
            assert result["ok"], result
            assert result["success"]
            assert result["result_stars"] == 0
            async with db.execute(
                "SELECT item_id, stars FROM inventory WHERE user_id = 1"
            ) as c:
                rows = await c.fetchall()
            assert ("bronze_gen", 0) in rows

            await _delete_inventory(db)
            await _add_inventory(
                db,
                [(slot, "copper_gen", 2) for slot in range(3)],
            )
            rejected = await m.craft_attempt(
                1, "copper_gen", False, use_starred=False
            )
            assert not rejected["ok"]

            await _delete_inventory(db)
            await _add_inventory(
                db,
                [
                    (0, "basic_gen", 0),
                    (1, "basic_gen", 0),
                    (2, "basic_gen", 0),
                ],
            )
            stats = await m.mass_craft_all(
                1, 1, False, max_result_id="copper_gen"
            )
            assert stats["attempts"] == 1
            assert stats["crafted"][0]["item_id"] == "copper_gen"
            async with db.execute(
                "SELECT COUNT(*) FROM inventory "
                "WHERE user_id = 1 AND item_id = 'bronze_gen'"
            ) as c:
                assert (await c.fetchone())[0] == 0

            await _delete_inventory(db)
            await _add_inventory(
                db,
                [
                    (0, "basic_gen", 0),
                    (1, "basic_gen", 0),
                    (2, "basic_gen", 0),
                    (3, "copper_gen", 2),
                    (4, "copper_gen", 2),
                    (5, "copper_gen", 2),
                ],
            )
            interaction = FakeInteraction(1)
            await m.show_mass_craft_confirm(interaction, 1)
            view = interaction.edited[-1][1]["view"]
            embed = interaction.edited[-1][1]["embed"]
            assert "Звёздных копий" in embed.description
            assert view.starred_count >= 3

            select_interaction = FakeInteraction(1)
            select_interaction.data["values"] = ["copper_gen"]
            await view.select_target(select_interaction)
            assert view.target_id == "copper_gen"
            select_interaction = FakeInteraction(1)
            select_interaction.data["values"] = ["__all__"]
            await view.select_target(select_interaction)
            assert view.target_id is None

            toggle_interaction = FakeInteraction(1)
            await view.starred_toggle.callback(toggle_interaction)
            assert view.use_starred
            assert toggle_interaction.followup.sent

            result_interaction = FakeInteraction(1)
            await view._run(result_interaction, False)
            result_embed = result_interaction.edited[-1][1]["embed"]
            assert "Сделано" in result_embed.description
            assert "0★" in result_embed.description
        finally:
            m.random.random = original_random
            await _close(db)

    asyncio.run(run())


def test_single_craft_starred_toggle():
    async def run():
        db = await _init()
        original_random = m.random.random
        m.random.random = lambda: 0.0
        try:
            await _add_inventory(
                db,
                [(slot, "copper_gen", 2) for slot in range(3)],
            )
            view = m.CraftConfirmView(1, "copper_gen")
            toggle_interaction = FakeInteraction(1)
            await view.toggle_starred.callback(toggle_interaction)
            assert view.use_starred
            assert toggle_interaction.followup.sent
            assert toggle_interaction.edited

            craft_interaction = FakeInteraction(1)
            await view.no_catalyst.callback(craft_interaction)
            assert craft_interaction.edited
            async with db.execute(
                "SELECT item_id, stars FROM inventory WHERE user_id = 1"
            ) as c:
                rows = await c.fetchall()
            assert ("bronze_gen", 0) in rows
        finally:
            m.random.random = original_random
            await _close(db)

    asyncio.run(run())


def test_mass_temp_move_and_confirmation():
    async def run():
        db = await _init()
        try:
            await _add_inventory(
                db,
                [(slot, "basic_gen", slot % 6) for slot in range(5)],
                location="temp",
            )
            moved, remaining = await m.mass_move_temp_items(1, "storage")
            assert (moved, remaining) == (5, 0)
            moved, remaining = await m.mass_move_temp_items(1, "bad")
            assert (moved, remaining) == (0, 0)

            await _delete_inventory(db)
            await _add_inventory(
                db,
                [(slot, "basic_gen", 0) for slot in range(20)],
                location="temp",
            )
            moved, remaining = await m.mass_move_temp_items(1, "profile")
            assert moved == 16
            assert remaining == 4

            await _delete_inventory(db)
            await _add_inventory(
                db,
                [(slot, "basic_gen", 0) for slot in range(5)],
                location="temp",
            )
            storage_view = m.TempStorageView(1)
            interaction = FakeInteraction(1)
            await storage_view.btn_mass_move.callback(interaction)
            confirm_view = interaction.edited[-1][1]["view"]
            assert isinstance(confirm_view, m.MassTempMoveConfirmView)

            move_interaction = FakeInteraction(1)
            await confirm_view.to_storage.callback(move_interaction)
            assert move_interaction.edited
            async with db.execute(
                "SELECT location, COUNT(*) FROM inventory "
                "WHERE user_id = 1 GROUP BY location"
            ) as c:
                locations = dict(await c.fetchall())
            assert locations.get("storage") == 5

            await _delete_inventory(db)
            interaction = FakeInteraction(1)
            await storage_view.btn_mass_move.callback(interaction)
            assert interaction.followup.sent

            await _add_inventory(
                db,
                [(slot, "basic_gen", 0) for slot in range(20)],
                location="temp",
            )
            confirm_view = m.MassTempMoveConfirmView(1)
            partial_interaction = FakeInteraction(1)
            await confirm_view.to_profile.callback(partial_interaction)
            partial_embed = partial_interaction.edited[-1][1]["embed"]
            assert "Осталось" in partial_embed.description

            await _delete_inventory(db)
            await _add_inventory(
                db,
                [(slot, "basic_gen", 0) for slot in range(16)],
            )
            await _add_inventory(
                db,
                [(0, "basic_gen", 0)],
                location="temp",
            )
            full_view = m.MassTempMoveConfirmView(1)
            full_interaction = FakeInteraction(1)
            await full_view.to_profile.callback(full_interaction)
            full_embed = full_interaction.edited[-1][1]["embed"]
            assert "Не удалось" in full_embed.description
        finally:
            await _close(db)

    asyncio.run(run())


def test_custom_buy_quantity():
    async def run():
        db = await _init()
        try:
            view = m.BuyItemQuantityView(1, "basic_gen", 0)
            modal_interaction = FakeInteraction(1)
            await view.custom_quantity(modal_interaction)
            modal = modal_interaction.response.messages[-1][0]
            assert isinstance(modal, m.CustomBuyQuantityModal)

            modal.quantity._value = "100"
            submit_interaction = FakeInteraction(1)
            await modal.on_submit(submit_interaction)
            async with db.execute(
                "SELECT COUNT(*) FROM inventory "
                "WHERE user_id = 1 AND item_id = 'basic_gen'"
            ) as c:
                assert (await c.fetchone())[0] == 100
            if not submit_interaction.edited:
                raise AssertionError("purchase did not edit response")

            invalid_modal = m.CustomBuyQuantityModal(1, "basic_gen")
            invalid_modal.quantity._value = "0"
            invalid_interaction = FakeInteraction(1)
            await invalid_modal.on_submit(invalid_interaction)
            assert invalid_interaction.response.messages
        finally:
            await _close(db)

    asyncio.run(run())


def test_mass_star_notification_lists_upgrades():
    async def run():
        db = await _init()
        original_random = m.random.random
        m.random.random = lambda: 0.0
        try:
            await _add_inventory(
                db,
                [(slot, "copper_gen", 0) for slot in range(4)],
            )
            stats = await m.mass_star_upgrade_all(1)
            assert stats["upgraded"]
            assert any(
                entry["item_id"] == "copper_gen" and entry["stars"] >= 2
                for entry in stats["upgraded"]
            )

            await _delete_inventory(db)
            await _add_inventory(
                db,
                [(slot, "copper_gen", 0) for slot in range(2)],
            )
            view = m.MassStarConfirmView(1)
            interaction = FakeInteraction(1)
            await view.confirm.callback(interaction)
            embed = interaction.edited[-1][1]["embed"]
            assert "Улучшено" in embed.description
            assert "1★" in embed.description
        finally:
            m.random.random = original_random
            await _close(db)

    asyncio.run(run())


class _ZeroCursor:
    rowcount = 0

    def __await__(self):
        async def _inner():
            return self
        return _inner().__await__()


class _ZeroGemsDB:
    def __init__(self, real):
        self.real = real

    def __getattr__(self, name):
        return getattr(self.real, name)

    def execute(self, sql, params=()):
        if "UPDATE players SET gems = gems - ?" in sql:
            return _ZeroCursor()
        return self.real.execute(sql, params)


def test_craft_gem_guards():
    async def run():
        db = await _init()
        original_random = m.random.random
        m.random.random = lambda: 0.0
        try:
            await _add_inventory(
                db,
                [(slot, "gold_gen", 0) for slot in range(3)],
            )
            await db.execute(
                "UPDATE players SET gems = 0 WHERE user_id = 1"
            )
            await db.commit()
            result = await m.craft_attempt(1, "gold_gen", False)
            assert not result["ok"]
            assert "1" in result["message"]
            assert "0" in result["message"]

            await db.execute(
                "UPDATE players SET gems = 100 WHERE user_id = 1"
            )
            await db.commit()
            m.bot.db = _ZeroGemsDB(db)
            try:
                result = await m.craft_attempt(1, "gold_gen", False)
            finally:
                m.bot.db = db
            assert not result["ok"]
            assert "гемов" in result["message"]
        finally:
            m.random.random = original_random
            await _close(db)

    asyncio.run(run())
