import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_mass_generator_actions", BOT_PATH
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


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


async def _add_player(db, gems=1000, catalysts=5, grid_size=16):
    await db.execute(
        "INSERT INTO players "
        "(user_id, coins, gems, catalysts, grid_size) "
        "VALUES (1, 10000, ?, ?, ?)",
        (gems, catalysts, grid_size),
    )
    await db.commit()


async def _add_inventory(db, entries):
    await db.executemany(
        "INSERT INTO inventory "
        "(user_id, slot, item_id, location, stars) VALUES (1, ?, ?, ?, ?)",
        entries,
    )
    await db.commit()


def test_grid_size_parser_and_gem_grid_blocking():
    async def run():
        db = await _init()
        try:
            await _add_player(db, grid_size=64)
            rows = [
                ("grid_7x7", "Grid 7x7", 400, "X", "gems", 0),
                ("grid_9x9", "Grid 9x9", 1100, "X", "gems", 0),
                ("grid_4x4", "Grid 4x4", 500, "X", "coins", 16),
                ("vip", "VIP", 500, "X", "gems", 0),
            ]
            interaction = FakeInteraction(1)
            await m.open_upgrades_buy_select(
                interaction, 1, rows, set(), 0
            )
            view = interaction.edited[-1][1]["view"]
            select = next(
                child
                for child in view.children
                if isinstance(child, m.discord.ui.Select)
            )
            options = {option.value: option for option in select.options}

            assert m.grid_size_from_upgrade_id("grid_7x7") == 49
            assert m.grid_size_from_upgrade_id("grid_bad") == 0
            assert m.grid_size_from_upgrade_id("not_a_grid") == 0

            assert "grid_7x7" not in options
            assert "grid_4x4" not in options
            assert "grid_9x9" in options
            assert "vip" in options

            blocked = FakeInteraction(1)
            await m.open_upgrades_buy_select(
                blocked,
                1,
                [("grid_7x7", "Grid 7x7", 400, "X", "gems", 0)],
                set(),
                0,
            )
            assert blocked.followup.sent
        finally:
            await _close(db)

    asyncio.run(run())


def test_mass_craft_success_and_confirm_view():
    async def run():
        db = await _init()
        original_random = m.random.random
        m.random.random = lambda: 0.0
        try:
            await _add_player(db)
            await _add_inventory(
                db,
                [
                    (0, "basic_gen", "profile", 0),
                    (1, "basic_gen", "profile", 0),
                    (2, "basic_gen", "storage", 0),
                ],
            )

            interaction = FakeInteraction(1)
            await m.show_mass_craft_confirm(interaction, 1, 0)
            confirm_view = interaction.edited[-1][1]["view"]
            assert isinstance(confirm_view, m.MassCraftConfirmView)
            assert not confirm_view.with_catalyst.disabled

            result_interaction = FakeInteraction(1)
            await confirm_view.with_catalyst.callback(result_interaction)
            embed = result_interaction.edited[-1][1]["embed"]
            assert "Успешно" in embed.description
            assert "Неудачно" in embed.description

            await _add_inventory(
                db,
                [
                    (3, "basic_gen", "profile", 0),
                    (4, "basic_gen", "profile", 0),
                    (5, "basic_gen", "profile", 0),
                ],
            )
            stats = await m.mass_craft_all(1, 1, False)
            assert stats["attempts"] == 1
            assert stats["successes"] == 1
            assert stats["failures"] == 0

            missing = await m.craft_attempt(1, "legendary_gen", False)
            assert not missing["ok"]
        finally:
            m.random.random = original_random
            await _close(db)

    asyncio.run(run())


def test_mass_craft_failure_and_clan_progress():
    async def run():
        db = await _init()
        original_random = m.random.random
        m.random.random = lambda: 1.0
        try:
            await _add_player(db, gems=1000, catalysts=5)
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Clan', 1, 1000)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader')"
            )
            await db.commit()
            await _add_inventory(
                db,
                [
                    (slot, "steel_gen", "profile" if slot < 4 else "storage", 0)
                    for slot in range(7)
                ],
            )

            stats = await m.mass_craft_all(1, 1, True)
            assert stats["attempts"] == 3
            assert stats["failures"] == 3
            assert stats["successes"] == 0
            assert stats["catalysts_used"] == 3
            assert stats["gems_spent"] == 6
        finally:
            m.random.random = original_random
            await _close(db)

    asyncio.run(run())


def test_mass_star_success_failure_and_guards():
    async def run():
        db = await _init()
        original_random = m.random.random
        original_attempt = m.star_upgrade_attempt
        m.random.random = lambda: 0.0
        try:
            await _add_player(db, gems=1000)
            await _add_inventory(
                db,
                [(slot, "copper_gen", "profile", 0) for slot in range(4)],
            )
            stats = await m.mass_star_upgrade_all(1)
            assert stats["attempts"] == 3
            assert stats["successes"] == 3

            await db.execute("DELETE FROM inventory")
            await _add_inventory(
                db,
                [(slot, "steel_gen", "profile", 0) for slot in range(3)],
            )
            m.random.random = lambda: 1.0
            stats = await m.mass_star_upgrade_all(1)
            assert stats["attempts"] == 2
            assert stats["failures"] == 2
            assert stats["successes"] == 0

            too_high = await m.star_upgrade_attempt(1, "copper_gen", 5)
            assert not too_high["ok"]

            await db.execute("DELETE FROM inventory")
            await db.execute("UPDATE players SET gems = 0 WHERE user_id = 1")
            await _add_inventory(
                db,
                [(slot, "copper_gen", "profile", 4) for slot in range(2)],
            )
            await db.commit()
            stats = await m.mass_star_upgrade_all(1)
            assert stats["attempts"] == 0

            await db.execute("DELETE FROM inventory")
            await db.execute("UPDATE players SET gems = 1000 WHERE user_id = 1")
            await _add_inventory(
                db,
                [(slot, "copper_gen", "profile", 0) for slot in range(2)],
            )
            await db.commit()

            async def fail_attempt(*args, **kwargs):
                return {"ok": False, "message": "probe"}

            m.star_upgrade_attempt = fail_attempt
            stats = await m.mass_star_upgrade_all(1)
            assert stats["attempts"] == 0
            m.star_upgrade_attempt = original_attempt
            m.random.random = lambda: 0.0

            interaction = FakeInteraction(1)
            await m.show_mass_star_confirm(interaction, 1)
            confirm_view = interaction.edited[-1][1]["view"]
            assert isinstance(confirm_view, m.MassStarConfirmView)
            result_interaction = FakeInteraction(1)
            await confirm_view.confirm.callback(result_interaction)
            embed = result_interaction.edited[-1][1]["embed"]
            assert "Успешно" in embed.description
            assert "Неудачно" in embed.description
        finally:
            m.random.random = original_random
            m.star_upgrade_attempt = original_attempt
            await _close(db)

    asyncio.run(run())


def test_mass_buttons_open_confirmation_views():
    async def run():
        db = await _init()
        try:
            await _add_player(db)
            await _add_inventory(
                db,
                [
                    (0, "basic_gen", "profile", 0),
                    (1, "basic_gen", "profile", 0),
                    (2, "basic_gen", "profile", 0),
                    (3, "copper_gen", "profile", 0),
                    (4, "copper_gen", "profile", 0),
                ],
            )

            craft = m.CraftSelectView(
                1,
                [m.discord.SelectOption(label="Probe", value="basic_gen")],
                0,
                1,
            )
            interaction = FakeInteraction(1)
            await craft.mass_craft(interaction)
            assert isinstance(
                interaction.edited[-1][1]["view"], m.MassCraftConfirmView
            )

            star = m.StarSelectView(
                1,
                [
                    m.discord.SelectOption(
                        label="Probe", value="profile:3:copper_gen:0"
                    )
                ],
                0,
                1,
            )
            interaction = FakeInteraction(1)
            await star.mass_upgrade(interaction)
            assert isinstance(
                interaction.edited[-1][1]["view"], m.MassStarConfirmView
            )
        finally:
            await _close(db)

    asyncio.run(run())
