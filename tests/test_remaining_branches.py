import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_remaining_branches_test", BOT_PATH
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

    async def send_modal(self, *args, **kwargs):
        return None


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeMessage:
    def __init__(self):
        self.edited = False

    async def edit(self, *args, **kwargs):
        self.edited = True

    async def delete(self):
        return None


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(
            id=user_id,
            name="Tester",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = None
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.message = FakeMessage()
        self.embed = None
        self.view = None

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


def test_remaining_commands_and_callbacks():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) "
                "VALUES (1, 1000, 1000), (2, 1000, 1000)"
            )
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'storage', 0)"
            )
            await db.commit()

            assert m._parse_db_time(None) is None
            assert m._parse_db_time("") is None
            assert m._parse_db_time("2025-01-01 12:00:00") is not None
            assert m._parse_db_time("bad") is None

            income = await m.collect_income(1, 1)
            assert income is not None

            original_fetch = m.bot.fetch_application_emojis
            original_emojis = dict(m.BOT_BTN_EMOJIS)

            async def fake_fetch():
                return [SimpleNamespace(name="coin", id=1)]

            m.bot.fetch_application_emojis = fake_fetch
            try:
                await m.bot.load_application_emojis()
            finally:
                m.bot.fetch_application_emojis = original_fetch
                m.BOT_BTN_EMOJIS.clear()
                m.BOT_BTN_EMOJIS.update(original_emojis)

            m.SettingsEmojisView(1)

            interaction = FakeInteraction(2, ["1"])
            espionage = m.EspionageTargetSelectView(1)
            await espionage.select_target(interaction)
            assert (
                interaction.response.messages
                or interaction.followup.sent
                or interaction.embed is not None
            )

            social = m.SocialView(1)
            clan_btn = next(
                item
                for item in social.children
                if getattr(item, "label", None) == "Клан"
            )
            interaction = FakeInteraction(1)
            await clan_btn.callback(interaction)
            assert interaction.embed is not None

            await db.execute(
                "UPDATE players SET coins = 0 WHERE user_id = 1"
            )
            await db.commit()
            interaction = FakeInteraction(1, ["1"])
            quantity = m.BuyItemQuantityView(1, "basic_gen")
            await quantity.quantity_select(interaction)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            deposit = m.BankDepositModal(1)
            deposit.amount._value = "bad"
            deposit.days._value = "7"
            await deposit.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            star = m.StarConfirmView(1, 0, "basic_gen", 0, 1)
            star_btn = next(
                item
                for item in star.children
                if getattr(item, "label", None) == "Улучшить"
            )
            await star_btn.callback(interaction)
            assert interaction.embed is not None

            duel = m.DuelChallengeView(1, 2, 50, "dice")
            duel.message = FakeMessage()
            duel._schedule_delete = lambda delay: None
            decline = next(
                item
                for item in duel.children
                if getattr(item, "label", None) == "Отклонить"
            )
            interaction = FakeInteraction(2)
            interaction.message = duel.message
            await decline.callback(interaction)
            assert duel.resolved

            duel2 = m.DuelChallengeView(1, 2, 50, "dice")
            duel2.message = FakeMessage()
            duel2._schedule_delete = lambda delay: None
            await duel2.on_timeout()
            assert duel2.resolved
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
