import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_mechanics_update_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.done = False

    def is_done(self):
        return self.done

    async def defer(self, *args, **kwargs):
        self.done = True

    async def send_message(self, *args, **kwargs):
        self.done = True


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.data = {"values": values or []}
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.edited = []

    async def edit_original_response(self, **kwargs):
        self.edited.append(kwargs)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_bank_loan_beats_deposit_arbitrage():
    deposit_yield = (1 + m.BANK_DAILY_RATE) ** m.BANK_LOAN_TERM_DAYS - 1
    assert m.BANK_LOAN_INTEREST > deposit_yield


def test_reward_scale_caps():
    assert m.reward_scale(0) == 1.0
    assert m.reward_scale(10) == 2.0
    assert m.reward_scale(100) == 3.0


def test_daily_reward_scales_with_prestige():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, prestige_points) "
                "VALUES (1, 0, 10)"
            )
            await db.commit()
            result = await m.claim_daily(1)
            assert result["ok"]
            assert result["coins"] == int(m.DAILY_REWARDS[1][0] * 2)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_achievement_reward_scales_with_prestige():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players "
                "(user_id, total_crafts, prestige_points) VALUES (1, 1, 10)"
            )
            await db.commit()
            unlocked = await m.check_achievements(1)
            first = next(item for item in unlocked if item[1] == "Первый синтез")
            assert first[2] == 10
            async with db.execute(
                "SELECT gems FROM players WHERE user_id = 1"
            ) as c:
                assert (await c.fetchone())[0] == 10
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_main_menu_more_select_opens_guide():
    async def run():
        view = m.MainMenuView(1)
        select = next(
            child for child in view.children if isinstance(child, m.discord.ui.Select)
        )
        interaction = FakeInteraction(1, ["guide"])
        await select.callback(interaction)
        assert interaction.edited
        assert isinstance(interaction.edited[0]["view"], m.GuideView)
    asyncio.run(run())


def test_main_menu_more_select_all_actions():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000)"
            )
            await db.commit()
            for value in (
                "exchange",
                "season",
                "prestige",
                "guide",
                "notifications",
                "onboarding",
            ):
                view = m.MainMenuView(1)
                select = next(
                    child
                    for child in view.children
                    if isinstance(child, m.discord.ui.Select)
                )
                interaction = FakeInteraction(1, [value])
                await select.callback(interaction)
                assert interaction.edited, value

            original_deny = m.deny_if_disabled

            async def deny(*args):
                return True

            m.deny_if_disabled = deny
            try:
                for value in ("exchange", "prestige"):
                    view = m.MainMenuView(1)
                    select = next(
                        child
                        for child in view.children
                        if isinstance(child, m.discord.ui.Select)
                    )
                    interaction = FakeInteraction(1, [value])
                    await select.callback(interaction)
                    assert not interaction.edited, value
            finally:
                m.deny_if_disabled = original_deny
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_premium_track_total_is_220_gems():
    total = sum(
        m.season_reward(level, True)["gems"] for level in range(1, 31)
    )
    assert total == 220


def test_start_coins_modal_rejects_above_cap():
    async def run():
        original_owner = m.is_global_owner

        async def owner_true(interaction):
            return True

        m.is_global_owner = owner_true
        try:
            modal = m.EditStartCoinsModal(1)
            modal.value._value = str(m.MAX_START_COINS + 1)
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
        finally:
            m.is_global_owner = original_owner

    asyncio.run(run())


def test_buyable_survives_reinit():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "UPDATE items SET buyable = 0 WHERE id = 'basic_gen'"
            )
            await db.commit()
            await m.bot.init_db()
            async with db.execute(
                "SELECT buyable FROM items WHERE id = 'basic_gen'"
            ) as c:
                assert (await c.fetchone())[0] == 0
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_status_expiry_backfill_runs_once():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "DELETE FROM schema_migrations "
                "WHERE name = 'status_expiry_backfill_v1'"
            )
            await db.execute(
                "INSERT INTO player_upgrades (user_id, upgrade_id, expires_at) "
                "VALUES (1, 'vip', NULL)"
            )
            await db.commit()
            await m.bot.init_db()
            async with db.execute(
                "SELECT expires_at FROM player_upgrades "
                "WHERE user_id = 1 AND upgrade_id = 'vip'"
            ) as c:
                assert (await c.fetchone())[0] is not None

            await db.execute(
                "UPDATE player_upgrades SET expires_at = NULL "
                "WHERE user_id = 1 AND upgrade_id = 'vip'"
            )
            await db.commit()
            await m.bot.init_db()
            async with db.execute(
                "SELECT expires_at FROM player_upgrades "
                "WHERE user_id = 1 AND upgrade_id = 'vip'"
            ) as c:
                assert (await c.fetchone())[0] is None
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_local_admin_view_only_has_giveaways():
    view = m.LocalAdminView(1)
    labels = {child.label for child in view.children}
    assert "Розыгрыши" in labels
    assert "В меню" in labels


def test_market_runtime_placeholder_match():
    async def run():
        runtime = m.MarketOrderRuntime()
        assert await runtime.match_market_orders("basic_gen") is None

    asyncio.run(run())


def test_guide_select_opens_section():
    async def run():
        db = await _init()
        try:
            view = m.GuideView(1)
            select = next(
                child
                for child in view.children
                if isinstance(child, m.discord.ui.Select)
            )
            interaction = FakeInteraction(1, ["economy"])
            await select.callback(interaction)
            assert interaction.edited
            assert isinstance(
                interaction.edited[0]["view"], m.GuideSectionView
            )
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())

def test_init_db_rejects_newer_schema():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await db.execute(f"PRAGMA user_version = {m.SCHEMA_VERSION + 1}")
            try:
                await m.bot.init_db()
            except RuntimeError as exc:
                assert "более новой" in str(exc)
            else:
                raise AssertionError("init_db должен отклонять новую схему")
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_analytics_details_toggle():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 100, 10)"
            )
            await db.execute(
                "INSERT INTO bank_loans "
                "(user_id, amount, interest_rate, due_time, collateral_item) "
                "VALUES (1, 100, 0.25, '2026-12-01T00:00:00', 'basic_gen')"
            )
            await db.commit()
            view = m.AnalyticsView(1)
            assert any(
                getattr(child, "label", None) == "Подробнее"
                for child in view.children
            )
            interaction = FakeInteraction(1)
            await view.btn_details(interaction, None)
            assert interaction.edited
            embed = interaction.edited[0]["embed"]
            names = [field.name for field in embed.fields]
            assert any("Экономика" in name for name in names)
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_plural_helper():
    assert m.plural_ru(1, "штука", "штуки", "штук") == "штука"
    assert m.plural_ru(2, "штука", "штуки", "штук") == "штуки"
    assert m.plural_ru(5, "штука", "штуки", "штук") == "штук"
    assert m.plural_ru(11, "штука", "штуки", "штук") == "штук"
    assert m.plural_ru(21, "штука", "штуки", "штук") == "штука"
    assert m.plural_ru("bad", "штука", "штуки", "штук") == "штук"
