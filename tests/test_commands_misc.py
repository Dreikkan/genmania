import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_commands_misc_test", BOT_PATH
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

    async def edit_original_response(self, embed=None, view=None):
        self.embed = embed
        self.view = view


def test_commands_and_misc_screens():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems, streak_days) "
                "VALUES (?, 1000, 1000, 0)",
                [(1,), (2,)],
            )
            await db.execute(
                "INSERT OR REPLACE INTO market_prices "
                "(item_id, base_price, current_price, demand, supply) "
                "VALUES ('basic_gen', 100, 100, 0, 0)"
            )
            await db.execute(
                "INSERT INTO market_orders "
                "(user_id, side, item_id, stars, price, quantity, filled, "
                " status, expires_at) "
                "VALUES (2, 'sell', 'basic_gen', 0, 100, 1, 0, 'active', ?)",
                (
                    (
                        datetime.datetime.now()
                        + datetime.timedelta(hours=1)
                    ).isoformat(),
                ),
            )
            await db.execute(
                "INSERT INTO user_pets_v2 "
                "(user_id, pet_id, level, last_fed) "
                "VALUES (1, 'cat', 1, NULL)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id) "
                "VALUES (1, 'Alpha', 1)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader'), (2, 1, 'veteran')"
            )
            await db.commit()

            interaction = FakeInteraction(1)
            await m.main_menu.callback(interaction)
            assert interaction.response.messages

            original_owner = m.is_global_owner
            original_snapshot = m.bot.build_health_snapshot

            async def owner(interaction):
                return True

            async def snapshot(deep=True):
                return {
                    "uptime_seconds": 10,
                    "gateway_latency_ms": 5,
                    "guilds": 1,
                    "db_size_bytes": 100,
                    "db_quick_check": "ok",
                    "commands_total": 1,
                    "command_errors": 0,
                    "command_avg_ms": 1,
                    "command_p95_ms": 2,
                    "db_tx_total": 1,
                    "db_tx_errors": 0,
                    "db_tx_avg_ms": 1,
                    "db_tx_p95_ms": 2,
                    "slow_db_tx": 0,
                    "tasks": [],
                    "tasks_alive": 0,
                }

            m.is_global_owner = owner
            m.bot.build_health_snapshot = snapshot
            try:
                interaction = FakeInteraction(1)
                await m.health_cmd.callback(interaction)
                assert interaction.followup.sent
            finally:
                m.is_global_owner = original_owner
                m.bot.build_health_snapshot = original_snapshot

            interaction = FakeInteraction(1)
            await m.open_admin_giveaways(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            await m.open_order_book_select(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            modal = m.SettingsStatusRoleModal(1)
            modal.status._value = "vip"
            modal.role_id._value = "123"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminSeasonPremiumModal(1)
            modal.user_id._value = "2"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            modal = m.AdminCancelMarketOrderModal(1)
            modal.order_id._value = "1"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            await m.open_shop_buy_select(
                interaction, 1, [("basic_gen", "Basic", 15, "⚙️")], 0
            )
            assert interaction.embed is not None

            m.GiveawayCreateTypeView(1)

            pets = m.PetsView(1)
            switch = next(
                item
                for item in pets.children
                if getattr(item, "label", None) == "Сменить активного"
            )
            interaction = FakeInteraction(1)
            await switch.callback(interaction)
            assert interaction.embed is not None

            for pet_id in m.PET_TYPES:
                await db.execute(
                    "INSERT OR IGNORE INTO user_pets_v2 "
                    "(user_id, pet_id, level, last_fed) "
                    "VALUES (1, ?, 1, NULL)",
                    (pet_id,),
                )
            await db.commit()
            interaction = FakeInteraction(1)
            await m.open_pets_shop(interaction, 1)
            assert interaction.embed is not None

            interaction = FakeInteraction(1)
            modal = m.EspionageIdModal(1)
            modal.user_id._value = "2"
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            daily = m.DailyView(1)
            claim = next(
                item
                for item in daily.children
                if getattr(item, "label", None) == "Забрать"
            )
            interaction = FakeInteraction(1)
            await claim.callback(interaction)
            assert interaction.embed is not None

            clan_role = m.ClanRoleModal(1, 1, "demote")
            clan_role.user_id._value = "2"
            interaction = FakeInteraction(1)
            await clan_role.on_submit(interaction)
            assert interaction.followup.sent

            await db.execute(
                "INSERT INTO notification_fallback "
                "(user_id, notif_type, title, body) "
                "VALUES (1, 'daily_ready', 'Дейли', 'Забери награду')"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            await m.notifications_cmd.callback(interaction)
            assert interaction.response.messages

            social = m.SocialView(1)
            tax_btn = next(
                (
                    item
                    for item in social.children
                    if "налог" in str(getattr(item, "label", "")).lower()
                ),
                None,
            )
            if tax_btn:
                interaction = FakeInteraction(1)
                await tax_btn.callback(interaction)
                assert interaction.embed is not None or interaction.followup.sent
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
