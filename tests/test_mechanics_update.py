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
        self.followup = SimpleNamespace(send=self._followup)
        self.edited = []

    async def _followup(self, *args, **kwargs):
        return None

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
