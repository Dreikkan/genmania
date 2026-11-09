import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_ui_button_regressions", BOT_PATH
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


class FakeMessage:
    async def edit(self, *args, **kwargs):
        return None

    async def delete(self):
        return None


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_name=f"User{user_id}",
            mention=f"<@{user_id}>",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(
            id=1,
            owner_id=1,
            get_role=lambda rid: None,
            get_member=lambda uid: None,
        )
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.message = FakeMessage()
        self.edited = []
        self.channel = None

    async def edit_original_response(self, *args, **kwargs):
        self.edited.append((args, kwargs))


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players (user_id, coins, gems, grid_size) "
        "VALUES (1, 10000, 1000, 16)"
    )
    await db.execute(
        "INSERT OR IGNORE INTO grid_shop "
        "(id, name, description, price_coins, size, emoji) "
        "VALUES ('probe_grid', 'Probe Grid', '', 500, 25, 'X')"
    )
    await db.execute(
        "INSERT OR IGNORE INTO gem_shop "
        "(id, name, description, price_gems, emoji, category) "
        "VALUES ('probe_status', 'Probe Status', '', 50, 'X', 'status')"
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


async def _fake_main_embed(interaction):
    return m.BotEmbed(title="Main")


def test_upgrades_buy_select_pagination_uses_six_columns():
    async def run():
        db = await _init()
        original_main = m.build_main_embed
        m.build_main_embed = _fake_main_embed
        try:
            view = m.UpgradesBuySelectView(1, [], page=1, total_pages=2)
            interaction = FakeInteraction(1)
            await view.prev_page(interaction)
            assert interaction.response.deferred
            assert interaction.edited
            edited_view = interaction.edited[-1][1]["view"]
            assert isinstance(edited_view, m.UpgradesBuySelectView)
            assert edited_view.page == 0

            interaction = FakeInteraction(1)
            await view.next_page(interaction)
            assert interaction.response.deferred
            assert interaction.edited
            edited_view = interaction.edited[-1][1]["view"]
            assert isinstance(edited_view, m.UpgradesBuySelectView)
            assert edited_view.page == 1
        finally:
            m.build_main_embed = original_main
            await _close(db)

    asyncio.run(run())


def test_back_buttons_navigate_to_main_menu():
    async def run():
        db = await _init()
        original_main = m.build_main_embed
        m.build_main_embed = _fake_main_embed
        try:
            cosmetics = m.CosmeticsView(1, "main")
            interaction = FakeInteraction(1)
            await cosmetics.back.callback(interaction)
            assert interaction.response.deferred
            assert isinstance(interaction.edited[-1][1]["view"], m.MainMenuView)

            prestige = m.PrestigeView(1)
            interaction = FakeInteraction(1)
            await prestige.btn_back.callback(interaction)
            assert interaction.response.deferred
            assert isinstance(interaction.edited[-1][1]["view"], m.MainMenuView)

            for view in (
                m.DailyView(1, "profile"),
                m.StoryQuestsView(1, "profile"),
                m.QuestsView(1, "profile"),
            ):
                interaction = FakeInteraction(1)
                await view.back.callback(interaction)
                assert interaction.response.deferred
                assert isinstance(
                    interaction.edited[-1][1]["view"], m.MainMenuView
                )
        finally:
            m.build_main_embed = original_main
            await _close(db)

    asyncio.run(run())


def test_weekend_season_event_branches():
    async def run():
        db = await _init()
        import gen_mania.services.seasons as seasons

        original_mult = m.SEASON_RUNTIME._weekend_mult_getter
        original_date = seasons.datetime.date

        class FakeDate(original_date):
            @classmethod
            def today(cls):
                return original_date(2026, 11, 7)

        m.SEASON_RUNTIME._weekend_mult_getter = lambda: 1.5
        seasons.datetime.date = FakeDate
        try:
            assert m.SeasonRuntime.weekend_mult is not None
            assert m.season_event_multiplier() == 1.5
            assert "50%" in m.season_event_label()
            embed, _data = await m.build_season_embed(1)
            assert any("50%" in (field.value or "") for field in embed.fields)
        finally:
            m.SEASON_RUNTIME._weekend_mult_getter = original_mult
            seasons.datetime.date = original_date
            await _close(db)

    asyncio.run(run())
