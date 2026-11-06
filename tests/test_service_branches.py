import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_service_branches_test", BOT_PATH
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
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


def test_profile_builders_cover_empty_and_rich_states():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(1)
            stats = await m.build_stats_embed(interaction)
            assert "нет ни одного синтеза" in stats.description

            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 100, 10)"
            )
            await db.execute(
                "INSERT INTO craft_log "
                "(user_id, item_id, success, gems_spent, catalyst_used) "
                "VALUES (1, 'basic_gen', 1, 20, 2), "
                "(1, 'basic_gen', 0, 10, 0)"
            )
            await db.commit()
            stats = await m.build_stats_embed(interaction)
            assert "2" in stats.fields[0].value

            missing = await m.build_user_profile_embed(FakeInteraction(99))
            assert "не найден" in missing.title

            await db.execute(
                "UPDATE players SET title = 'Строитель', "
                "catalysts = 2, total_crafts = 4, total_successes = 3, "
                "grid_size = 9, active_pet = 'cat' WHERE user_id = 1"
            )
            await db.execute(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level) "
                "VALUES (1, 'cat', 3)"
            )
            await db.execute(
                "INSERT INTO autocollectors (user_id, level) VALUES (1, 2)"
            )
            await db.execute(
                "INSERT INTO user_cosmetics "
                "(user_id, embed_color, bg_url, castle_icon) "
                "VALUES (1, 123, 'https://example.com/bg.png', '🏰')"
            )
            await db.commit()

            profile = await m.build_user_profile_embed(interaction)
            names = "\n".join(field.name for field in profile.fields)
            values = "\n".join(field.value for field in profile.fields)
            assert "Питомец" in names
            assert "Автосборщик" in names
            assert "Строитель" in values
            assert profile.image.url == "https://example.com/bg.png"

            public = await m.build_public_profile_embed(1, detailed=True)
            assert "Питомец" in "\n".join(
                field.value for field in public.fields
            )
            not_found = await m.build_public_profile_embed(99)
            assert "не найден" in not_found.title
        finally:
            await _close(db)

    asyncio.run(run())


def test_profile_embed_gem_income_clan_and_empty_filter():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 50, 0)"
            )
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "income_gems_per_hour, emoji, rarity, buyable) "
                "VALUES ('gem_gen', 'Gem', 100, 1, 0.5, '💎', 'rare', 1)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (1, 0, 'gem_gen', 'profile')"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, bonus) "
                "VALUES (1, 'Alpha', 2, 0.05)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'member')"
            )
            await db.execute(
                "INSERT INTO autocollectors (user_id, level) VALUES (1, 1)"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            embed = await m.build_profile_embed(interaction, "locked")
            text = "\n".join(field.value for field in embed.fields)
            assert "Gem" in text
            assert "/час" in text
            assert "Автосборщик" in "\n".join(
                field.name for field in embed.fields
            )
            assert "По выбранному фильтру" in embed.description
        finally:
            await _close(db)

    asyncio.run(run())


def test_shop_achievements_page():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO achievements "
                "(id, name, description, reward_gems, emoji) "
                "VALUES ('a1', 'First', 'Do it', 5, '🏆'), "
                "('a2', 'Second', 'Do more', 10, '⭐')"
            )
            await db.execute(
                "INSERT INTO player_achievements (user_id, achievement_id) "
                "VALUES (1, 'a1')"
            )
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 0)"
            )
            await db.commit()

            embed, pages = await m.build_achievements_page(
                FakeInteraction(1), 0
            )
            assert pages >= 1
            assert "Открыто: 1/" in embed.description
            text = "\n".join(field.value for field in embed.fields)
            assert "Открыто" in text
            assert "Закрыто" in text
        finally:
            await _close(db)

    asyncio.run(run())


def test_autocollector_buy_and_upgrade_branches():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 0, ?)",
                [(1, 0), (2, 1000), (3, 1000), (4, 1000), (5, 0), (6, 1000)],
            )
            await db.execute(
                "INSERT INTO autocollectors (user_id, level) VALUES (2, 1)"
            )
            await db.execute(
                "INSERT INTO autocollectors (user_id, level) VALUES (3, 3)"
            )
            await db.execute(
                "INSERT INTO autocollectors (user_id, level) VALUES (4, 1)"
            )
            await db.execute(
                "INSERT INTO autocollectors (user_id, level) VALUES (5, 1)"
            )
            await db.commit()

            ok, message = await m.buy_autocollector(1)
            assert not ok and "Нужно" in message
            ok, message = await m.buy_autocollector(2)
            assert not ok and "уже есть" in message
            ok, _ = await m.buy_autocollector(6)
            assert ok
            assert await m.get_autocollector(6) is not None

            ok, message = await m.upgrade_autocollector(99)
            assert not ok and "Сначала купи" in message
            ok, message = await m.upgrade_autocollector(3)
            assert not ok and "максимального" in message
            ok, message = await m.upgrade_autocollector(4)
            assert ok
            assert (await m.get_autocollector(4))[0] == 2
            ok, message = await m.upgrade_autocollector(5)
            assert not ok and "Нужно" in message

            plain = await m.build_autocollector_embed(FakeInteraction(1))
            assert "Цена" in plain.description
            rich = await m.build_autocollector_embed(FakeInteraction(4))
            assert "Уровень" in rich.description
            assert "Улучшение" in rich.description
            top = await m.build_autocollector_embed(FakeInteraction(3))
            assert "Максимальный уровень" in top.description
        finally:
            await _close(db)

    asyncio.run(run())
