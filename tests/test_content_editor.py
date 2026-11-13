import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_content_editor_test", BOT_PATH)
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


class FakeInteraction:
    def __init__(self, user_id=1, guild_id=1):
        self.user = SimpleNamespace(id=user_id, name="Tester")
        self.guild_id = guild_id
        self.guild = None
        self.message = SimpleNamespace()
        self.response = FakeResponse()
        self.embed = None
        self.view = None

    async def edit_original_response(self, embed=None, view=None, **kwargs):
        self.embed = embed
        self.view = view


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute("INSERT INTO players (user_id, coins) VALUES (1, 100)")
    await db.commit()
    return db


async def _status_row(db, key):
    async with db.execute(
        "SELECT value FROM content_meta WHERE key = ?", (key,)
    ) as c:
        row = await c.fetchone()
    return row[0] if row else None


def _flatten_embed(embed) -> str:
    parts = [embed.title or "", embed.description or ""]
    parts.extend(field.name or "" for field in embed.fields)
    parts.extend(field.value or "" for field in embed.fields)
    return "\n".join(parts)


def test_content_helpers():
    assert m.normalize_content_id("basic_gen") == "basic_gen"
    assert m.normalize_content_id("Basic Gen") is None
    assert m.normalize_content_id("x") is None
    assert m.normalize_content_name("  Тест  ") == "Тест"
    assert m.normalize_content_name("") is None
    assert m.parse_content_int("123") == 123
    assert m.parse_content_int("-1") is None
    assert m.parse_content_int("1.5") is None
    assert m.parse_content_float("1,5") == 1.5
    assert m.parse_content_float("nan") is None
    assert m.parse_content_float("-0.1") is None
    assert m.format_content_number(0.00041666) == "0.00041666"
    assert m.format_content_number(5.0) == "5"


def test_content_editor_embed_shows_version_and_counts():
    async def run():
        db = await _init()
        try:
            embed = await m.build_content_editor_embed()
            text = _flatten_embed(embed)
            assert "Код" in text and str(m.CONTENT_VERSION) in text
            assert "Ручная ревизия" in text
            assert "Предметы" in text
            assert "Достижения" in text
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_update_item_content_bumps_revision_and_audits():
    async def run():
        db = await _init()
        try:
            ok, message = await m.update_item_content(
                1,
                "basic_gen",
                "Новый генератор",
                "123",
                "0.5",
                "0.01",
                "rare",
            )
            assert ok, message
            async with db.execute(
                "SELECT name, price, income_per_hour, income_gems_per_hour, "
                "rarity FROM items WHERE id = 'basic_gen'"
            ) as c:
                row = await c.fetchone()
            assert row == (
                "Новый генератор",
                123,
                0.5 / 3600,
                0.01 / 3600,
                "rare",
            )

            status = await m.get_content_status()
            assert status["manual_revision"] == 1
            assert status["last_editor_id"] == 1

            async with db.execute(
                "SELECT action, details FROM admin_log "
                "WHERE action = 'content_item_edit' ORDER BY id DESC LIMIT 1"
            ) as c:
                log_row = await c.fetchone()
            assert log_row is not None
            assert "basic_gen" not in log_row[1]  # details содержит поля, не ID
            assert "price=123" in log_row[1]
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_invalid_item_update_does_not_change_content():
    async def run():
        db = await _init()
        try:
            async with db.execute(
                "SELECT name, price, rarity FROM items WHERE id = 'basic_gen'"
            ) as c:
                before = await c.fetchone()

            ok, _ = await m.update_item_content(
                1, "basic_gen", "Плохой", "-5", "0.5", "0", "rare"
            )
            assert ok is False
            ok, _ = await m.update_item_content(
                1, "basic_gen", "Плохой", "5", "0.5", "0", "unknown"
            )
            assert ok is False
            ok, _ = await m.update_item_content(
                1, "missing_item", "Плохой", "5", "0.5", "0", "rare"
            )
            assert ok is False

            async with db.execute(
                "SELECT name, price, rarity FROM items WHERE id = 'basic_gen'"
            ) as c:
                assert await c.fetchone() == before
            assert await _status_row(db, "manual_revision") is None
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_set_item_income_is_atomic():
    async def run():
        db = await _init()
        try:
            async with db.execute(
                "SELECT income_per_hour, income_gems_per_hour "
                "FROM items WHERE id = 'basic_gen'"
            ) as c:
                before = await c.fetchone()

            ok, message = await m.set_item_income(
                1, "basic_gen", "999", "not-a-number"
            )
            assert ok is False
            assert "гемов" in message
            async with db.execute(
                "SELECT income_per_hour, income_gems_per_hour "
                "FROM items WHERE id = 'basic_gen'"
            ) as c:
                assert await c.fetchone() == before
            assert await _status_row(db, "manual_revision") is None

            ok, _ = await m.set_item_income(1, "basic_gen", "0.6", "0.02")
            assert ok is True
            async with db.execute(
                "SELECT income_per_hour, income_gems_per_hour "
                "FROM items WHERE id = 'basic_gen'"
            ) as c:
                assert await c.fetchone() == (0.6 / 3600, 0.02 / 3600)
            assert await _status_row(db, "manual_revision") == "1"
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_item_appearance_validation():
    async def run():
        db = await _init()
        try:
            ok, _ = await m.update_item_appearance(1, "basic_gen", "🔥", "0")
            assert ok is True
            async with db.execute(
                "SELECT emoji, buyable FROM items WHERE id = 'basic_gen'"
            ) as c:
                assert await c.fetchone() == ("🔥", 0)

            ok, _ = await m.update_item_appearance(1, "basic_gen", "abc", "0")
            assert ok is False
            ok, _ = await m.update_item_appearance(1, "basic_gen", "🔥", "2")
            assert ok is False
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_add_generator_content_respects_shop_policy():
    async def run():
        db = await _init()
        try:
            ok, message = await m.add_generator_content(
                1, "test_common_gen", "Тестовый", "100", "0.1", "0", "⚙️", "common"
            )
            assert ok, message
            ok, message = await m.add_generator_content(
                1, "test_epic_gen", "Эпический", "100", "0.1", "0", "🔮", "epic"
            )
            assert ok, message

            async with db.execute(
                "SELECT buyable FROM items WHERE id = 'test_common_gen'"
            ) as c:
                assert (await c.fetchone())[0] == 1
            async with db.execute(
                "SELECT buyable FROM items WHERE id = 'test_epic_gen'"
            ) as c:
                assert (await c.fetchone())[0] == 0

            ok, _ = await m.add_generator_content(
                1, "test_common_gen", "Дубликат", "100", "0.1", "0", "⚙️", "common"
            )
            assert ok is False
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_achievement_crud_and_revision():
    async def run():
        db = await _init()
        try:
            ok, message = await m.add_achievement_content(
                1, "test_ach", "Тест", "Описание", "5", "🏆"
            )
            assert ok, message

            ok, _ = await m.add_achievement_content(
                1, "test_ach", "Дубликат", "Описание", "5", "🏆"
            )
            assert ok is False

            ok, message = await m.update_achievement_content(
                1, "test_ach", "Тест 2", "Новое описание", "7", "🏆"
            )
            assert ok, message

            await db.execute(
                "INSERT INTO player_achievements (user_id, achievement_id) "
                "VALUES (1, 'test_ach')"
            )
            await db.commit()

            ok, _ = await m.delete_achievement_content(1, "test_ach", False)
            assert ok is False
            ok, message = await m.delete_achievement_content(
                1, "test_ach", True
            )
            assert ok, message

            async with db.execute(
                "SELECT COUNT(*) FROM achievements WHERE id = 'test_ach'"
            ) as c:
                assert (await c.fetchone())[0] == 0
            async with db.execute(
                "SELECT COUNT(*) FROM player_achievements "
                "WHERE achievement_id = 'test_ach'"
            ) as c:
                assert (await c.fetchone())[0] == 0

            assert await _status_row(db, "manual_revision") == "3"
            async with db.execute(
                "SELECT action FROM admin_log WHERE action LIKE "
                "'content_achievement_%' ORDER BY id"
            ) as c:
                actions = [row[0] for row in await c.fetchall()]
            assert actions == [
                "content_achievement_create",
                "content_achievement_edit",
                "content_achievement_delete",
            ]
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_validate_content_detects_bad_rows():
    async def run():
        db = await _init()
        try:
            assert await m.validate_content_data() == []
            await db.execute(
                "UPDATE items SET name = '', price = -1, rarity = 'weird', "
                "emoji = 'abc' WHERE id = 'basic_gen'"
            )
            await db.execute(
                "INSERT INTO achievements "
                "(id, name, description, reward_gems, emoji) "
                "VALUES ('bad_ach', '', '', -1, 'abc')"
            )
            await db.commit()

            issues = await m.validate_content_data()
            text = "\n".join(issues)
            assert "basic_gen" in text
            assert "bad_ach" in text
            assert "цена" in text
            assert "редкость" in text
            assert "эмодзи" in text

            embed = await m.build_content_validation_embed()
            assert "найдены проблемы" in embed.title
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_content_pages_and_buttons():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction()
            await m.open_content_items(interaction, 1, 0)
            assert isinstance(interaction.view, m.ContentItemsView)
            assert "Предметы" in interaction.embed.title
            labels = [
                getattr(child, "label", None)
                for child in interaction.view.children
            ]
            assert "Новый генератор" in labels
            assert "Назад" in labels

            interaction = FakeInteraction()
            await m.open_content_item(interaction, 1, "basic_gen", 0)
            assert isinstance(interaction.view, m.ContentItemDetailView)
            assert "basic_gen" in interaction.embed.description

            interaction = FakeInteraction()
            await m.open_content_achievements(interaction, 1, 0)
            assert isinstance(interaction.view, m.ContentAchievementsView)
            assert "Достижения" in interaction.embed.title

            interaction = FakeInteraction()
            await m.open_content_achievement(interaction, 1, "first_craft", 0)
            assert isinstance(interaction.view, m.ContentAchievementDetailView)
            assert "Первый синтез" in interaction.embed.title
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_content_editor_view_and_owner_button():
    view = m.ContentEditorView(1)
    labels = [child.label for child in view.children]
    for label in ("Предметы", "Достижения", "Проверить", "Назад"):
        assert label in labels

    panel = m.AdminPanelPage2(1)
    assert "Контент" not in [child.label for child in panel.children]

    token = m._CURRENT_IS_BOT_OWNER.set(True)
    try:
        panel = m.AdminPanelPage2(1)
        assert "Контент" in [child.label for child in panel.children]
    finally:
        m._CURRENT_IS_BOT_OWNER.reset(token)


def test_content_modals_construct_with_valid_labels():
    item = ("basic_gen", "Медный генератор", 100, 0.5, 0.01, "⚙️", "common", 1)
    edit = m.ContentItemEditModal(1, item)
    assert edit.rarity.label == "Редкость"
    assert edit.name.default == "Медный генератор"
    assert edit.income_coins.default == "1800"
    assert len(edit.rarity.label) <= 45

    appearance = m.ContentItemAppearanceModal(1, item)
    assert appearance.emoji.default == "⚙️"
    assert appearance.buyable.default == "1"

    achievement = ("first_craft", "Первый синтез", "Сделай синтез", 5, "🏆")
    ach_edit = m.EditAchievementRewardModal(1, achievement)
    assert ach_edit.ach_id.default == "first_craft"
    assert ach_edit.name.default == "Первый синтез"

    delete = m.DeleteAchievementModal(1, "first_craft")
    assert delete.ach_id.default == "first_craft"


def test_content_owner_guard():
    async def run():
        db = await _init()
        original = m.is_global_owner
        try:
            interaction = FakeInteraction()
            interaction.guild = SimpleNamespace(
                owner_id=1,
                get_member=lambda uid: SimpleNamespace(
                    guild_permissions=SimpleNamespace(administrator=False),
                    roles=(),
                ),
            )
            view = m.ContentEditorView(1)
            assert await view.interaction_check(interaction) is False
            assert interaction.response.messages
            assert "владельцу бота" in interaction.response.messages[0][0]

            async def fake_owner(_interaction):
                return True

            m.is_global_owner = fake_owner
            interaction = FakeInteraction()
            interaction.guild = SimpleNamespace(
                owner_id=1,
                get_member=lambda uid: SimpleNamespace(
                    guild_permissions=SimpleNamespace(administrator=False),
                    roles=(),
                ),
            )
            assert await view.interaction_check(interaction) is True
        finally:
            m.is_global_owner = original
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_achievement_admin_requires_bot_owner():
    async def run():
        db = await _init()
        original = m.is_global_owner
        try:
            guild = SimpleNamespace(
                owner_id=1,
                get_member=lambda uid: SimpleNamespace(
                    guild_permissions=SimpleNamespace(administrator=False),
                    roles=(),
                ),
            )

            async def not_owner(_interaction):
                return False

            async def owner(_interaction):
                return True

            m.is_global_owner = not_owner
            view = m.SettingsAchievementsView(1)
            interaction = FakeInteraction()
            interaction.guild = guild
            assert await view.interaction_check(interaction) is False
            assert interaction.response.messages

            settings_view = m.SettingsView(1)
            interaction = FakeInteraction()
            interaction.guild = guild
            await settings_view.achievements.callback(interaction)
            assert interaction.response.messages
            assert interaction.view is None

            m.is_global_owner = owner
            interaction = FakeInteraction()
            interaction.guild = guild
            await settings_view.achievements.callback(interaction)
            assert isinstance(interaction.view, m.SettingsAchievementsView)
        finally:
            m.is_global_owner = original
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_content_option_labels_fit_discord_limits():
    long_name = "Очень длинное название предмета " * 5
    option = m.build_content_item_option(
        ("long_item", long_name, 100, "common", 1, "📦")
    )
    assert len(option.label) <= 100
    assert len(option.description) <= 100
    assert option.value == "long_item"

    ach_option = m.build_content_achievement_option(
        ("long_ach", long_name, 999, "🏆")
    )
    assert len(ach_option.label) <= 100
    assert len(ach_option.description) <= 100
    assert ach_option.value == "long_ach"
