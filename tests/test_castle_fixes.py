import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_castle_fixes_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.done = False
        self.edited = None
        self.messages = []

    def is_done(self):
        return self.done

    async def defer(self, *args, **kwargs):
        self.done = True

    async def send_message(self, text=None, **kwargs):
        self.messages.append((text, kwargs))
        self.done = True

    async def edit_message(self, **kwargs):
        self.edited = kwargs
        self.done = True

    async def send_modal(self, modal):
        self.done = True


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, text=None, **kwargs):
        self.messages.append((text, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1, data=None):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.data = data or {}
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.edited = None

    async def edit_original_response(self, **kwargs):
        self.edited = kwargs


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems) VALUES (1, 10000, 100)"
    )
    await db.commit()
    return db


def test_shop_labels_for_trade_and_synthesis_only():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(1)
            fields = {}
            for page in range(6):
                embed, total_pages = await m.build_shop_page(interaction, page)
                for field in embed.fields:
                    fields[field.name] = field.value
                if page >= total_pages - 1:
                    break

            basic = next(value for name, value in fields.items() if "basic_gen" in name)
            ruby = next(value for name, value in fields.items() if "ruby_gen" in name)
            space = next(value for name, value in fields.items() if "space_gen" in name)
            divine = next(value for name, value in fields.items() if "divine_gen" in name)
            legendary = next(
                value for name, value in fields.items() if "legendary_gen" in name
            )

            assert "Цена:" in basic
            assert "Покупка на бирже/аукционе" in ruby, ruby
            assert "Только синтез" not in ruby
            for value in (space, divine, legendary):
                assert "Только синтез" in value, value
                assert "Покупка на бирже/аукционе" not in value
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_star_upgrade_consumes_copies_from_castle_and_storage():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0), "
                "(1, 0, 'basic_gen', 'storage', 0)"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            await m.open_star_view(interaction, 1, 0)
            view = interaction.edited["view"]
            select = next(
                child
                for child in view.children
                if isinstance(child, m.discord.ui.Select)
            )
            values = [option.value for option in select.options]
            assert "profile:0:basic_gen:0" in values, values
            assert "storage:0:basic_gen:0" in values, values

            pick = FakeInteraction(1, {"values": ["storage:0:basic_gen:0"]})
            await view.item_select(pick)
            confirm = pick.edited["view"]
            assert isinstance(confirm, m.StarConfirmView)
            assert confirm.location == "storage"

            done = FakeInteraction(1)
            await confirm.confirm.callback(done)
            assert isinstance(done.edited["view"], m.ProfileView)

            async with db.execute(
                "SELECT location, stars FROM inventory "
                "WHERE user_id = 1 AND item_id = 'basic_gen' ORDER BY location"
            ) as c:
                rows = await c.fetchall()
            assert rows == [("storage", 1)], rows
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_synthesis_counts_castle_and_storage():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0), "
                "(1, 1, 'basic_gen', 'profile', 0), "
                "(1, 0, 'basic_gen', 'storage', 0)"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            await m.open_craft_view(interaction, 1, 0)
            view = interaction.edited["view"]
            select = next(
                child
                for child in view.children
                if isinstance(child, m.discord.ui.Select)
            )
            option = next(o for o in select.options if o.value == "basic_gen")
            assert f"(3/{m.craft_cost_for_item('basic_gen')})" in option.label, option.label

            pick = FakeInteraction(1, {"values": ["basic_gen"]})
            await view.item_select(pick)
            confirm = pick.edited["view"]
            assert isinstance(confirm, m.CraftConfirmView)

            done = FakeInteraction(1)
            await confirm.no_catalyst.callback(done)
            assert isinstance(done.edited["view"], m.ProfileView)

            async with db.execute(
                "SELECT item_id, location, stars FROM inventory "
                "WHERE user_id = 1"
            ) as c:
                rows = await c.fetchall()
            assert sum(row[0] == "basic_gen" for row in rows) == 1, rows
            assert any(
                row[0] == "copper_gen" and row[2] == 0 for row in rows
            ), rows
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_social_view_keeps_pvp_hub_and_drops_direct_pvp_buttons():
    view = m.SocialView(1)
    buttons = [
        child for child in view.children if isinstance(child, m.discord.ui.Button)
    ]
    labels = [button.label for button in buttons]
    assert "Рейд" not in labels, labels
    assert "Дуэль" not in labels, labels
    assert "PvP" in labels, labels
    assert labels.count("Назад") == 1
    row0 = [button.label for button in buttons if button.row == 0]
    assert row0 == ["PvP", "Клан", "Топы"], row0
    assert max(button.row for button in buttons) == 3

    hub = m.PvPHubView(1)
    hub_labels = [
        child.label
        for child in hub.children
        if isinstance(child, m.discord.ui.Button)
    ]
    assert "Рейд" in hub_labels and "Дуэль" in hub_labels


def test_profile_layout_and_catalyst_shortcut():
    view = m.ProfileView(1)
    buttons = [
        child for child in view.children if isinstance(child, m.discord.ui.Button)
    ]
    by_row = {}
    for button in buttons:
        by_row.setdefault(button.row, []).append(button.label)

    assert by_row[2][:3] == ["Сортировка", "Детали", "Сеты"], by_row
    assert by_row[3][-2:] == ["Почта", "Назад"], by_row
    assert all(len(labels) <= 3 for labels in by_row.values()), by_row

    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(1)
            await view.catalyst_button.callback(interaction)
            catalyst_view = interaction.edited["view"]
            assert isinstance(catalyst_view, m.CatalystSelectView)
            assert catalyst_view.return_to == "profile"

            back = FakeInteraction(1)
            await catalyst_view.cancel(back)
            assert isinstance(back.edited["view"], m.ProfileView)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_generator_details_back_returns_to_castle():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0)"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            profile = m.ProfileView(1)
            await profile.details_button.callback(interaction)
            details = interaction.edited["view"]
            assert isinstance(details, m.GeneratorDetailView)

            back_button = next(
                child
                for child in details.children
                if isinstance(child, m.discord.ui.Button)
                and child.label == "На энергостанцию"
            )
            done = FakeInteraction(1)
            await back_button.callback(done)
            assert isinstance(done.edited["view"], m.ProfileView)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_fix_embed_emojis_clips_discord_limits():
    async def run():
        embed = m.BotEmbed(title="t" * 300, description="d" * 5000)
        embed.add_field(name="n" * 300, value="v" * 2000)
        fixed = await m.fix_embed_emojis(embed)
        assert len(fixed.title) <= 256
        assert len(fixed.description) <= 4096
        assert len(fixed.fields[0].name) <= 256
        assert len(fixed.fields[0].value) <= 1024

    asyncio.run(run())


def test_upgrades_pagination_uses_five_per_page():
    async def run():
        db = await _init()
        try:
            interaction = FakeInteraction(1)
            embed, total_pages = await m.build_upgrades_page(interaction, 0)
            assert total_pages == 3, total_pages
            assert len(embed.fields) == 5, len(embed.fields)
            assert "Страница 1/3" in embed.description

            embed2, _ = await m.build_upgrades_page(interaction, 1)
            assert len(embed2.fields) == 5, len(embed2.fields)

            embed3, _ = await m.build_upgrades_page(interaction, 2)
            assert len(embed3.fields) == 1, len(embed3.fields)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_generator_details_pagination():
    async def run():
        db = await _init()
        try:
            for slot in range(12):
                await db.execute(
                    "INSERT INTO inventory "
                    "(user_id, slot, item_id, location, stars) "
                    "VALUES (1, ?, 'basic_gen', 'profile', 0)",
                    (slot,),
                )
            await db.commit()

            interaction = FakeInteraction(1)
            embed, total_pages = await m.build_generator_details_embed(
                interaction, 0
            )
            assert total_pages == 2, total_pages
            assert "Страница 1/2" in embed.description, embed.description

            view = m.GeneratorDetailView(1, 0, total_pages)
            buttons = {
                child.label: child
                for child in view.children
                if isinstance(child, m.discord.ui.Button)
            }
            assert buttons["Пред."].disabled is True
            assert buttons["След."].disabled is False

            next_interaction = FakeInteraction(1)
            await buttons["След."].callback(next_interaction)
            next_view = next_interaction.edited["view"]
            assert next_view.page == 1
            assert next_view.total_pages == 2
            assert "Страница 2/2" in next_interaction.edited["embed"].description

            next_buttons = {
                child.label: child
                for child in next_view.children
                if isinstance(child, m.discord.ui.Button)
            }
            assert next_buttons["Пред."].disabled is False
            assert next_buttons["След."].disabled is True

            prev_interaction = FakeInteraction(1)
            await next_buttons["Пред."].callback(prev_interaction)
            prev_view = prev_interaction.edited["view"]
            assert prev_view.page == 0
            assert "Страница 1/2" in prev_interaction.edited["embed"].description
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
