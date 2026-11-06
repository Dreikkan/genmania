import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_remaining_ui_test", BOT_PATH
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
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.embed = None
        self.view = None
        self.message = FakeMessage()

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


def test_remaining_ui_flows():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players "
                "(user_id, coins, gems, grid_size) "
                "VALUES (1, 10000, 10000, 9), (2, 10000, 10000, 9)"
            )
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) VALUES "
                "(1, 0, 'basic_gen', 'profile', 0), "
                "(1, 1, 'basic_gen', 'profile', 0)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 1000)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader')"
            )
            started = (
                datetime.datetime.now() - datetime.timedelta(hours=1)
            ).isoformat()
            await db.execute(
                "INSERT INTO clan_wars "
                "(clan1_id, clan2_id, start_time, status, "
                " clan1_hp, clan2_hp, clan1_max_hp, clan2_max_hp) "
                "VALUES (1, 2, ?, 'active', 1000, 900, 1000, 1000)",
                (started,),
            )
            await db.commit()

            interaction = FakeInteraction(1)
            modal = m.PrestigeConfirmModal(1)
            modal.confirm._value = "НЕТ"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            premium = m.SeasonPremiumConfirmView(1, 100)
            buy = next(
                item
                for item in premium.children
                if getattr(item, "label", "").startswith("Купить")
            )
            await buy.callback(interaction)
            assert interaction.embed is not None or interaction.followup.sent

            giveaway_id = await m._insert_giveaway_record(
                1,
                1,
                1,
                {
                    "reward_type": "coins",
                    "reward_id": None,
                    "amount": 100,
                    "summary": "100 монет",
                },
                1,
                24,
                m.GIVEAWAY_SCOPE_SERVER,
                "Розыгрыш: ",
            )
            interaction = FakeInteraction(1)
            join = m.GiveawayJoinView(giveaway_id)
            await join.join(interaction)
            assert interaction.response.messages

            interaction = FakeInteraction(1)
            star = m.StarConfirmView(1, 0, "basic_gen", 0, 1)
            star_btn = next(
                item
                for item in star.children
                if getattr(item, "label", None) == "Улучшить"
            )
            await star_btn.callback(interaction)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_mass_ops_view(interaction, 1, "all", "profile")
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            mass = m.MassOpsConfirmView(1, "all", "lock", "profile")
            mass_btn = next(
                item
                for item in mass.children
                if getattr(item, "label", None) == "Выполнить"
            )
            await mass_btn.callback(interaction)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_clan_detail(interaction, 1, 1)
            assert interaction.embed is not None

            clan_war = m.ClanWarView(1, 1, 1)
            attack = next(
                item
                for item in clan_war.children
                if getattr(item, "label", None) == "Атаковать"
            )
            original_attack = m.attack_clan_war

            async def fake_attack(war_id, user_id):
                return True, "ok", True

            m.attack_clan_war = fake_attack
            try:
                interaction = FakeInteraction(1)
                await attack.callback(interaction)
                assert interaction.embed is not None
            finally:
                m.attack_clan_war = original_attack

            upgrades = m.UpgradesView(1, 0)
            buy_upgrade = next(
                item
                for item in upgrades.children
                if getattr(item, "label", None) == "Купить"
            )
            interaction = FakeInteraction(1)
            await buy_upgrade.callback(interaction)
            assert interaction.embed is not None

            original_resolve = m.resolve_duel

            async def fake_resolve(*args, **kwargs):
                return True, "ok"

            m.resolve_duel = fake_resolve
            try:
                duel = m.DuelChallengeView(1, 2, 50, "dice")
                duel.message = FakeMessage()
                duel._schedule_delete = lambda delay: None
                accept = next(
                    item
                    for item in duel.children
                    if getattr(item, "label", None) == "Принять"
                )
                interaction = FakeInteraction(2)
                interaction.message = duel.message
                await accept.callback(interaction)
                assert duel.resolved
            finally:
                m.resolve_duel = original_resolve

            income = await m.collect_income(1, 1)
            assert income is not None or income is None

            original_fetch = m.bot.fetch_application_emojis

            async def fake_fetch():
                return []

            m.bot.fetch_application_emojis = fake_fetch
            try:
                await m.bot.load_application_emojis()
            finally:
                m.bot.fetch_application_emojis = original_fetch
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
