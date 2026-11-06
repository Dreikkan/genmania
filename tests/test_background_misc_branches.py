import asyncio
import datetime
import importlib.util
import pathlib
import sys
import tempfile
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_background_misc_test", BOT_PATH
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


class FakeMessage:
    def __init__(self):
        self.id = 1
        self.edits = []
        self.jump_url = "https://example.com/m"

    async def edit(self, *args, **kwargs):
        self.edits.append((args, kwargs))

    async def delete(self):
        return None


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(id=user_id, name=f"User{user_id}")
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.edited = []
        self.channel = None
        self.message = FakeMessage()
        self.data = {"values": []}

    async def edit_original_response(self, *args, **kwargs):
        self.edited.append((args, kwargs))


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


async def _run_once(task, **patches):
    original_wait = m.bot.wait_until_ready
    original_closed = m.bot.is_closed
    original_sleep = m.asyncio.sleep
    state = {"closed": False}

    async def ready():
        return None

    def is_closed():
        if state["closed"]:
            return True
        state["closed"] = True
        return False

    async def no_sleep(*args, **kwargs):
        return None

    m.bot.wait_until_ready = ready
    m.bot.is_closed = is_closed
    m.asyncio.sleep = no_sleep
    originals = {}
    try:
        for name, value in patches.items():
            originals[name] = getattr(m, name)
            setattr(m, name, value)
        await task()
    finally:
        m.bot.wait_until_ready = original_wait
        m.bot.is_closed = original_closed
        m.asyncio.sleep = original_sleep
        for name, value in originals.items():
            setattr(m, name, value)


def test_background_task_wrappers_and_edges():
    async def run():
        db = await _init()
        try:
            async def noop(*args, **kwargs):
                return None

            await _run_once(
                m.bot.market_order_closer,
                expire_market_orders=noop,
                match_market_orders=noop,
            )
            await _run_once(
                m.bot.bank_loan_closer, expire_bank_loans=noop
            )
            await _run_once(
                m.bot.giveaway_closer, finish_due_giveaways=noop
            )
            await _run_once(
                m.bot.notification_task, run_notification_cycle=noop
            )

            async def expire_fail():
                raise RuntimeError("boom")

            await _run_once(
                m.bot.market_order_closer,
                expire_market_orders=expire_fail,
                match_market_orders=noop,
            )
            await _run_once(
                m.bot.bank_loan_closer, expire_bank_loans=expire_fail
            )
            await _run_once(
                m.bot.giveaway_closer, finish_due_giveaways=expire_fail
            )
            await _run_once(
                m.bot.notification_task, run_notification_cycle=expire_fail
            )

            await db.execute(
                "INSERT INTO giveaways "
                "(id, guild_id, channel_id, message_id, creator_id, title, "
                "reward_type, amount, winners_count, status, ends_at, scope) "
                "VALUES (1, 1, 10, 20, 1, 'G', 'coins', 1, 1, 'active', ?, 'server')",
                ((datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat(),),
            )
            await db.execute(
                "INSERT INTO giveaway_messages "
                "(giveaway_id, guild_id, channel_id, message_id) "
                "VALUES (1, 1, 10, 20)"
            )
            await db.commit()
            original_add_view = m.bot.add_view
            calls = []

            def add_view(view, message_id=None):
                calls.append(message_id)
                if message_id == 20:
                    raise RuntimeError("bad view")

            m.bot.add_view = add_view
            try:
                await m.bot.restore_giveaway_views()
            finally:
                m.bot.add_view = original_add_view
            assert calls == [20, 20]

            now = datetime.datetime.now()
            await db.executemany(
                "INSERT INTO players (user_id, coins, last_tax_time) "
                "VALUES (?, ?, ?)",
                [
                    (1, 1000, now.isoformat()),
                    (2, 0, None),
                ],
            )
            await db.commit()

            async def rates():
                return {1: 0.1, 2: 0.1}

            await _run_once(m.bot.tax_collector, get_tax_rate_map=rates)
            rows = await db.execute_fetchall(
                "SELECT user_id, coins FROM players ORDER BY user_id"
            )
            assert rows[0] == (1, 1000)
            assert rows[1] == (2, 0)
        finally:
            await _close(db)

    asyncio.run(run())


def test_war_closer_edges_and_backup_guards():
    async def run():
        db = await _init()
        try:
            async def noop(*args, **kwargs):
                return None

            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'A', 1, 0), (2, 'B', 2, 0), (3, 'C', 3, 0)"
            )
            old = (
                datetime.datetime.now()
                - datetime.timedelta(hours=m.CLAN_WAR_DURATION_HOURS + 1)
            ).isoformat()
            await db.execute(
                "INSERT INTO clan_wars "
                "(id, clan1_id, clan2_id, start_time, status, "
                "clan1_hp, clan2_hp, clan1_damage, clan2_damage) "
                "VALUES (1, 1, 2, ?, 'active', 0, 0, 0, 0), "
                "(2, 1, 4, ?, 'active', 100, 100, 0, 0), "
                "(3, 1, 2, ?, 'active', 100, 100, 0, 0)",
                (old, old, datetime.datetime.now().isoformat()),
            )
            await db.commit()

            async def power(clan_id):
                return 10 if clan_id == 1 else 5

            await _run_once(
                m.bot.war_closer,
                get_clan_power=power,
                log_clan=noop,
                update_clan_quest=noop,
                add_clan_xp=noop,
            )
            rows = await db.execute_fetchall(
                "SELECT id, status, winner_id FROM clan_wars ORDER BY id"
            )
            assert rows[0][1:] == ("finished", 1)
            assert rows[1][1:] == ("finished", None)
            assert rows[2][1] == "active"

            async def broken_power(clan_id):
                raise RuntimeError("boom")

            await _run_once(
                m.bot.war_closer,
                get_clan_power=broken_power,
                log_clan=noop,
                update_clan_quest=noop,
                add_clan_xp=noop,
            )

            bot = m.bot
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = pathlib.Path(tmp)
                db_file = tmp_path / "castle.db"
                db_file.write_bytes(b"x" * 2048)
                original = (
                    bot.db,
                    bot.db_path,
                    bot.backup_dir,
                    m._DB_TX_OWNER,
                )
                try:
                    bot.db = None
                    assert await bot.backup_database() is None
                    bot.db = db
                    bot.db_path = None
                    assert await bot.backup_database() is None
                    bot.db_path = str(db_file)
                    bot.backup_dir = tmp_path / "backups"
                    bot.backup_dir.mkdir()
                    m._DB_TX_OWNER = object()
                    assert await bot.backup_database() is None

                    m._DB_TX_OWNER = None
                    bot.db_path = str(tmp_path / "missing.db")
                    assert await bot.backup_database() is None

                    bad_dir = tmp_path / "not_a_dir"
                    bad_dir.write_text("x", encoding="utf-8")
                    bot.db_path = str(db_file)
                    bot.backup_dir = bad_dir
                    assert await bot.backup_database() is None

                    bot.backup_dir = None
                    bot._rotate_backups()

                    bot.db_path = str(db_file)
                    bot.data_dir = tmp_path
                    snapshot = await bot.build_health_snapshot()
                    assert snapshot["db_size_bytes"] >= 2048
                    snapshot = await bot.build_health_snapshot(deep=True)
                    assert "db_quick_check" in snapshot
                finally:
                    (
                        bot.db,
                        bot.db_path,
                        bot.backup_dir,
                        m._DB_TX_OWNER,
                    ) = original
        finally:
            await _close(db)

    asyncio.run(run())


def test_giveaway_helpers_and_join_view():
    async def run():
        db = await _init()
        try:
            now = datetime.datetime.now()
            await db.execute(
                "INSERT INTO giveaways "
                "(id, guild_id, channel_id, message_id, creator_id, title, "
                "reward_type, reward_id, amount, winners_count, status, "
                "ends_at, scope) "
                "VALUES (1, 1, 10, 20, 1, 'G', 'coins', NULL, 1, 1, 'active', ?, 'server')",
                ((now - datetime.timedelta(hours=1)).isoformat(),),
            )
            await db.execute(
                "INSERT INTO giveaways "
                "(id, guild_id, channel_id, message_id, creator_id, title, "
                "reward_type, reward_id, amount, winners_count, status, "
                "ends_at, scope) "
                "VALUES (2, 1, 10, 20, 1, 'Bad', 'coins', NULL, 1, 1, 'active', ?, 'server')",
                ("bad",),
            )
            await db.commit()

            finished = []

            async def finish(giveaway_id):
                finished.append(giveaway_id)
                if giveaway_id == 2:
                    raise RuntimeError("boom")

            original_finish = m.finish_giveaway
            m.finish_giveaway = finish
            try:
                await m.finish_due_giveaways()
            finally:
                m.finish_giveaway = original_finish
            assert 1 in finished

            await m.update_giveaway_message(999)

            original_get_channel = m.bot.get_channel
            original_get_guild = m.bot.get_guild
            m.bot.get_channel = lambda channel_id: None
            m.bot.get_guild = lambda guild_id: SimpleNamespace(
                get_channel=lambda channel_id: None
            )
            try:
                await m.update_giveaway_message(1)
            finally:
                m.bot.get_channel = original_get_channel
                m.bot.get_guild = original_get_guild

            class Channel:
                async def fetch_message(self, message_id):
                    raise RuntimeError("no message")

            m.bot.get_channel = lambda channel_id: Channel()
            try:
                await m.update_giveaway_message(1)
            finally:
                m.bot.get_channel = original_get_channel

            async def join_false(*args):
                return False, "no"

            original_join = m.join_giveaway
            original_get = m.get_giveaway
            original_build = m.build_giveaway_embed
            m.join_giveaway = join_false
            try:
                view = m.GiveawayJoinView(1)
                interaction = FakeInteraction(1)
                await view.join(interaction)
                assert interaction.response.messages
            finally:
                m.join_giveaway = original_join

            async def join_true(*args):
                return True, "ok"

            async def get_giveaway(giveaway_id):
                return (1, 1, 10, 20, 1, "G", "coins", None, 1, 1, "active", "", "", "", "", "server")

            async def build_embed(giveaway):
                return m.BotEmbed(title="G")

            m.join_giveaway = join_true
            m.get_giveaway = get_giveaway
            m.build_giveaway_embed = build_embed
            try:
                view = m.GiveawayJoinView(1)
                interaction = FakeInteraction(1)
                await view.join(interaction)
                assert interaction.message.edits
            finally:
                m.join_giveaway = original_join
                m.get_giveaway = original_get
                m.build_giveaway_embed = original_build

            async def broken_get(giveaway_id):
                raise RuntimeError("boom")

            m.join_giveaway = join_true
            m.get_giveaway = broken_get
            try:
                view = m.GiveawayJoinView(1)
                interaction = FakeInteraction(1)
                await view.join(interaction)
            finally:
                m.join_giveaway = original_join
                m.get_giveaway = original_get

            for reward_type in (
                "generator",
                "pet",
                "pet_level",
                "status",
                "coins",
            ):
                modal = m.GiveawayCreateModal(1, reward_type)
                assert modal.reward_type == reward_type

            interaction = FakeInteraction(1)
            await m.open_admin_giveaways(interaction, 1)
            assert interaction.edited
        finally:
            await _close(db)

    asyncio.run(run())


def test_open_helpers_and_status_role_removal():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000)"
            )
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "emoji, rarity, buyable) "
                "VALUES ('buy_gen', 'Buy', 10, 1, '⚙️', 'common', 1)"
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader')"
            )
            await db.execute(
                "INSERT INTO clan_invites "
                "(clan_id, inviter_id, target_id) VALUES (1, 2, 1)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (1, 0, 'basic_gen', 'profile')"
            )
            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, current_bid, buyout_price, "
                "end_time, status) "
                "VALUES (1, 2, 'basic_gen', 10, 100, ?, 'active')",
                ((datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat(),),
            )
            await db.execute(
                "INSERT INTO admin_log "
                "(admin_id, target_id, action, details, timestamp) "
                "VALUES (1, 2, 'grant', 'x', ?)",
                (datetime.datetime.now().isoformat(),),
            )
            await db.commit()

            interaction = FakeInteraction(1)
            await m.open_clan_buy_select(interaction, 1, 1)
            assert interaction.edited

            interaction = FakeInteraction(1)
            await m.open_clan_invites(interaction, 1)
            assert interaction.edited

            interaction = FakeInteraction(1)
            await m.open_raid_party(interaction, 1)
            assert interaction.edited

            interaction = FakeInteraction(1)
            await m.open_admin_logs(interaction, 1)
            assert interaction.edited

            original_build_battle = m.build_battle_log_embed
            original_last_duel = m.get_last_duel
            original_last_raid = m.get_last_raid_target
            original_duel_cd = m.get_duel_cooldown_seconds
            original_raid_cd = m.get_raid_cooldown_seconds

            async def embed(*args):
                return m.BotEmbed(title="Battle")

            async def last_duel(user_id):
                return (2, "dice")

            async def last_raid(user_id):
                return 3

            async def zero(user_id):
                return 0

            m.build_battle_log_embed = embed
            m.get_last_duel = last_duel
            m.get_last_raid_target = last_raid
            m.get_duel_cooldown_seconds = zero
            m.get_raid_cooldown_seconds = zero
            try:
                interaction = FakeInteraction(1)
                await m.open_battle_log(interaction, 1)
                assert interaction.edited
            finally:
                m.build_battle_log_embed = original_build_battle
                m.get_last_duel = original_last_duel
                m.get_last_raid_target = original_last_raid
                m.get_duel_cooldown_seconds = original_duel_cd
                m.get_raid_cooldown_seconds = original_raid_cd

            interaction = FakeInteraction(1)
            await m.open_mass_ops_confirm(
                interaction, 1, "all", "move_zero", "profile"
            )
            assert interaction.edited

            interaction = FakeInteraction(1)
            await m.open_star_emoji_select(interaction, 1)
            assert interaction.edited

            interaction = FakeInteraction(1)
            await m.open_auction_buyout_confirm(interaction, 1, 1)
            assert interaction.edited

            interaction = FakeInteraction(1)
            await m.open_auction_buyout_confirm(interaction, 1, 999)
            assert interaction.followup.sent

            class Member:
                def __init__(self):
                    self.removed = []

                async def remove_roles(self, role, reason=None):
                    self.removed.append(role)

            class Guild:
                id = 1

                def __init__(self):
                    self.member = Member()

                def get_member(self, user_id):
                    return self.member

                def get_role(self, role_id):
                    return SimpleNamespace(id=role_id)

            original_guilds = type(m.bot).guilds
            original_settings = m.get_settings

            async def settings(guild_id):
                return {"status_roles": {"vip": 10}}

            # settings are fetched via runtime, patch module getter.
            m.get_settings = settings
            m._settings_cache.clear()
            try:
                type(m.bot).guilds = property(lambda self: [Guild()])
                await m.remove_status_role(1, "vip")
            finally:
                type(m.bot).guilds = original_guilds
                m.get_settings = original_settings
        finally:
            await _close(db)

    asyncio.run(run())
