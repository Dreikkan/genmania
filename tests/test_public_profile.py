import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_public_profile_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_public_profile_grid_and_power():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, title, grid_size) "
                "VALUES (1, 100, 10, 'Богач', 9), "
                "(2, 500, 20, 'Алхимик', 9)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (2, 0, 'basic_gen', 'profile', 0)"
            )
            await db.commit()

            minimal = await m.build_public_profile_embed(2, detailed=False)
            assert "Профиль" in minimal.title
            minimal_names = "\n".join(f.name for f in minimal.fields)
            assert "Мощь" not in minimal_names
            assert "Топ генераторов" not in minimal_names
            assert "Энергостанция" in minimal_names
            assert "Коллекция" in minimal_names
            assert "Достижения" in minimal_names
            grid_field = next(
                field for field in minimal.fields
                if field.name.startswith("Энергостанция · сетка")
            )
            assert "🟦" in grid_field.value
            assert "basic_gen" not in grid_field.value

            detailed = await m.build_public_profile_embed(2, detailed=True)
            assert "Шпионаж" in detailed.title
            detailed_names = "\n".join(f.name for f in detailed.fields)
            assert "Мощь" in detailed_names
            assert "Топ генераторов" in detailed_names
            text = "\n".join(f.value for f in detailed.fields)
            assert "500" in text
            assert "Алхимик" in text
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_profile_and_details_show_power():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 0, 0)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0)"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            profile = await m.build_profile_embed(interaction)
            assert "Мощь" in "\n".join(f.name for f in profile.fields)
            details, _ = await m.build_generator_details_embed(interaction, 0)
            assert "Мощь" in "\n".join(f.value for f in details.fields)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_espionage_cooldown_and_views():
    async def run():
        db = await _init()
        try:
            assert await m.get_espionage_cooldown_seconds(1) == 0
            await m.set_espionage_cooldown(1)
            assert await m.get_espionage_cooldown_seconds(1) > 850
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())

    for view in (m.EspionageTargetSelectView(1), m.ProfileTargetSelectView(1)):
        assert any(isinstance(child, m.discord.ui.UserSelect) for child in view.children)
        assert any(
            isinstance(child, m.discord.ui.Button)
            and child.label == "Ввести ID"
            for child in view.children
        )
