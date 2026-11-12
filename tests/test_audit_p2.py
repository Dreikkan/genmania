import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_audit_p2_test", BOT_PATH
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
    def __init__(self, user_id=1, owner_id=1):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(id=1, owner_id=owner_id)
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": []}
        self.edited = []
        self.message = None

    async def edit_original_response(self, *args, **kwargs):
        self.edited.append((args, kwargs))


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    await db.execute(
        "INSERT INTO players "
        "(user_id, coins, gems, catalysts, total_crafts, total_successes) "
        "VALUES (1, 1000, 10, 2, 10, 6)"
    )
    await db.execute(
        "INSERT INTO player_achievements (user_id, achievement_id) "
        "VALUES (1, 'probe')"
    )
    await db.commit()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


def test_admin_modal_guard_and_branch_edges():
    async def run():
        db = await _init()
        try:
            denied = FakeInteraction(1, owner_id=2)
            modal = m.AdminGrantValuesModal(1, "coins")
            modal.user_id._value = "1"
            modal.amount._value = "10"
            await modal.on_submit(denied)
            assert denied.response.messages
            assert not denied.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminRemoveAchievementModal(1)
            modal.user_id._value = "1"
            modal.ach_id._value = "missing"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminRemoveDepositModal(1)
            modal.user_id._value = "1"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            for cls in (m.AdminGrantValuesModal, m.AdminTakeValuesModal):
                interaction = FakeInteraction(1)
                modal = cls(1, "bad")
                modal.user_id._value = "1"
                modal.amount._value = "10"
                await modal.on_submit(interaction)
                assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminProfileModal(1)
            modal.user_id._value = "999"
            await modal.on_submit(interaction)
            assert interaction.followup.sent
        finally:
            await _close(db)

    asyncio.run(run())


def test_guild_sync_events_handle_errors():
    async def run():
        original = m.sync_guild_access

        async def fail(*args, **kwargs):
            raise RuntimeError("probe")

        m.sync_guild_access = fail
        try:
            await m.on_guild_join(SimpleNamespace(id=1))
            await m.on_guild_role_update(
                SimpleNamespace(id=1),
                SimpleNamespace(guild=SimpleNamespace(id=1)),
            )
            await m.on_guild_role_delete(
                SimpleNamespace(guild=SimpleNamespace(id=1))
            )
        finally:
            m.sync_guild_access = original

    asyncio.run(run())


def test_profile_exposes_stats_and_high_tier_limits():
    async def run():
        db = await _init()
        try:
            embed = await m.build_user_profile_embed(FakeInteraction(1))
            field_names = {field.name for field in embed.fields}
            assert any("Достижения" in name for name in field_names)
            assert any("Успешность синтеза" in name for name in field_names)
        finally:
            await _close(db)

    asyncio.run(run())

    assert m.BANK_MAX_DEPOSIT >= 1_000_000
    assert m.BANK_LOAN_MAX >= 500_000
    assert m.MARKET_MAX_ORDER_VALUE >= 10**18
    assert m.MARKET_MAX_DAILY_VOLUME >= 5 * 10**18
    assert m.MAX_GENERATOR_ITEM_PRICE == 10**18

    for tier in range(1, 10):
        source, _ = m.generator_price_income(tier)
        result, _ = m.generator_price_income(tier + 1)
        craft = m.CRAFT_COST * m.round_price(source)
        assert craft <= int(m.round_price(result) * 0.85), tier


def test_top_exclusion_already_excluded_branch():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "UPDATE players SET top_excluded = 1 WHERE user_id = 1"
            )
            await db.commit()
            assert (
                await m.enforce_top_exclusion(
                    FakeInteraction(1), 1, "probe"
                )
                is False
            )
        finally:
            await _close(db)

    asyncio.run(run())
