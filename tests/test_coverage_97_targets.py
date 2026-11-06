import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_coverage_97_targets", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.messages = []
        self.modals = []

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_modal(self, modal):
        self.modals.append(modal)


class FakeFollowup:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.sent.append((args, kwargs))


class FakeMessage:
    def __init__(self, delete_fail=False):
        self.id = 10
        self.jump_url = "https://example.com/msg"
        self.delete_fail = delete_fail

    async def edit(self, *args, **kwargs):
        return None

    async def delete(self):
        if self.delete_fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)


class FakeInteraction:
    def __init__(self, user_id=1, values=None, fail_followup=False):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_name=f"User{user_id}",
            mention=f"<@{user_id}>",
            bot=False,
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
        self.followup = FakeFollowup(fail=fail_followup)
        self.data = {"values": values or ["1"]}
        self.message = FakeMessage()
        self.edited = []
        self.deleted = False
        self.channel = None
        self.client = m.bot

    async def edit_original_response(self, *args, **kwargs):
        self.edited.append((args, kwargs))

    async def delete_original_response(self):
        self.deleted = True


async def _init():
    m._DB_WRITE_LOCK = asyncio.Lock()
    m._DB_TX_OWNER = None
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

    def closed():
        if state["closed"]:
            return True
        state["closed"] = True
        return False

    async def no_sleep(*args, **kwargs):
        return None

    m.bot.wait_until_ready = ready
    m.bot.is_closed = closed
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


def test_status_passive_and_parse_helpers():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, 1000, 100)",
                [(1,), (2,), (999,), (1000,), (1001,), (1002,), (1003,), (1004,)],
            )
            now = m.datetime.datetime.now()
            await db.execute(
                "UPDATE players SET last_collected = ?, last_gem_collected = ? "
                "WHERE user_id = 2",
                (
                    (now - m.datetime.timedelta(hours=1)).isoformat(),
                    (now - m.datetime.timedelta(hours=1)).isoformat(),
                ),
            )
            await db.commit()

            original_settings = m.get_settings
            original_passive = m.calculate_passive_income
            original_per_sec = m.get_per_second_income
            original_guilds = getattr(m.bot, "guilds", [])

            async def settings(guild_id):
                return {"status_roles": {}}

            async def settings_raise(guild_id):
                raise RuntimeError("settings fail")

            try:
                m.get_settings = settings
                await m.grant_status_role(FakeInteraction(1), 1, "vip")

                calls = {"count": 0}

                async def settings_sequence(guild_id):
                    calls["count"] += 1
                    if calls["count"] == 2:
                        raise RuntimeError("boom")
                    return {"status_roles": {}}

                m.get_settings = settings_sequence
                old_guilds = m.bot._connection._guilds
                m.bot._connection._guilds = {
                    1: SimpleNamespace(id=1),
                    2: SimpleNamespace(id=2),
                }
                try:
                    await m.remove_status_role(1, "vip")
                finally:
                    m.bot._connection._guilds = old_guilds
            finally:
                m.get_settings = original_settings

            class Member:
                async def add_roles(self, *args, **kwargs):
                    raise m.discord.HTTPException.__new__(
                        m.discord.HTTPException
                    )

            class Guild:
                id = 1

                def get_member(self, user_id):
                    return Member()

                def get_role(self, role_id):
                    return SimpleNamespace(id=role_id)

            async def status_settings(guild_id):
                return {"status_roles": {"vip": 10}}

            m.get_settings = status_settings
            try:
                interaction = FakeInteraction(1)
                interaction.guild = Guild()
                await m.grant_status_role(interaction, 1, "vip")
            finally:
                m.get_settings = original_settings

            assert await m.get_menu_welcome_notification(999) is None
            await db.execute(
                "UPDATE players SET last_collected = ? WHERE user_id = 1",
                (now.isoformat(),),
            )
            await db.commit()
            assert await m.get_menu_welcome_notification(1) is None
            await db.execute(
                "UPDATE players SET last_collected = ? WHERE user_id = 1",
                ((now - m.datetime.timedelta(minutes=31)).isoformat(),),
            )
            await db.commit()

            async def passive(user_id, guild_id=None):
                return 1, 0

            m.calculate_passive_income = passive
            try:
                assert await m.get_menu_welcome_notification(1)
            finally:
                m.calculate_passive_income = original_passive

            assert await m.calculate_full_passive_income(999) == (0, 0)

            async def per_sec(user_id):
                return 0, 0.001

            m.get_per_second_income = per_sec
            try:
                coins, gems = await m.calculate_full_passive_income(2)
                assert coins == 0 and gems >= 0
            finally:
                m.get_per_second_income = original_per_sec

            assert m.title_effect_bonus(None, "income") == 0.0
            assert m.title_effect_bonus("Нет такого", "income") == 0.0
            assert m.parse_emoji_safe(None) is None
            emoji = m.discord.PartialEmoji(name="x", id=1, animated=False)
            assert m.parse_emoji_safe(emoji) is emoji
        finally:
            await _close(db)

    asyncio.run(run())


def test_content_market_and_menu_helpers():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, grid_size) "
                "VALUES (1, 10000, 10000, 20)"
            )
            await db.commit()

            await m.open_content_item(FakeInteraction(1), 1, "missing")
            await m.open_content_achievement(FakeInteraction(1), 1, "missing")

            original_clan = m.get_clan
            original_clan_embed = m.build_clan_embed

            async def clan(user_id):
                return (1, "Probe", 1, 0, 0)

            async def clan_embed(interaction, clan_row):
                return m.BotEmbed(title="Clan")

            m.get_clan = clan
            m.build_clan_embed = clan_embed
            try:
                interaction = FakeInteraction(1)
                await m.open_nav_route(interaction, 1, "clans")
                assert interaction.edited
            finally:
                m.get_clan = original_clan
                m.build_clan_embed = original_clan_embed

            original_party = m.get_raid_party
            original_touch = m.touch_raid_party
            original_commit = m.commit_if_needed
            original_party_embed = m.build_raid_party_embed

            async def party(user_id):
                return (1, 1, None, None)

            async def noop(*args, **kwargs):
                return None

            async def none_embed(*args, **kwargs):
                return None

            m.get_raid_party = party
            m.touch_raid_party = noop
            m.commit_if_needed = noop
            m.build_raid_party_embed = none_embed
            try:
                interaction = FakeInteraction(1)
                await m.open_raid_party(interaction, 1)
                assert interaction.edited
            finally:
                m.get_raid_party = original_party
                m.touch_raid_party = original_touch
                m.commit_if_needed = original_commit
                m.build_raid_party_embed = original_party_embed

            original_statuses = m.get_active_statuses

            async def statuses(user_id):
                return []

            m.get_active_statuses = statuses
            try:
                rows = [("grid_4x4", "Grid", 100, "⚙️", "coins", 16)]
                interaction = FakeInteraction(1)
                await m.open_upgrades_buy_select(interaction, 1, rows, set(), 0)
                assert interaction.edited
            finally:
                m.get_active_statuses = original_statuses

            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0)"
            )
            await db.execute(
                "CREATE TRIGGER trg_mass_lock_abort BEFORE UPDATE ON inventory "
                "BEGIN SELECT RAISE(ABORT, 'lock fail'); END"
            )
            await db.commit()
            ok, message, count = await m.mass_lock_location(
                1, "profile", "all", 1
            )
            assert not ok
            await db.execute("DROP TRIGGER trg_mass_lock_abort")
            await db.commit()

            assert await m.calculate_deposit_interest(999) == 0
            now = m.datetime.datetime.now().isoformat()
            await db.execute(
                "INSERT INTO bank_deposits "
                "(user_id, amount, interest_rate, start_time, end_time) "
                "VALUES (1000, 100, 0.1, ?, ?)",
                (now, now),
            )
            await db.commit()
            assert await m.calculate_deposit_interest(1000) == 100

            await db.execute(
                "UPDATE items SET emoji_by_star = 'bad' WHERE id = 'basic_gen'"
            )
            await db.commit()
            assert await m.get_star_emoji("basic_gen", 0, "⚙️")
            assert "2" in await m.get_star_emoji("basic_gen", 2, "⚙️")

            await db.execute(
                "INSERT OR REPLACE INTO content_meta (key, value) "
                "VALUES ('last_content_editor_id', '1')"
            )
            await db.execute(
                "INSERT OR REPLACE INTO content_meta (key, value) "
                "VALUES ('last_content_edit_at', '2026-01-01')"
            )
            await db.commit()
            embed = await m.build_content_editor_embed()
            assert embed

            original_settings = m.get_settings

            async def settings(guild_id):
                return {"battlepass_enabled": False}

            m.get_settings = settings
            try:
                interaction = FakeInteraction(1)
                await m.open_season_view(interaction, 1)
                assert interaction.edited
            finally:
                m.get_settings = original_settings

            original_preview = m.build_season_preview_embed

            async def preview(user_id, page=0):
                return m.BotEmbed(title="Preview"), 1

            m.build_season_preview_embed = preview
            try:
                interaction = FakeInteraction(1)
                await m.open_season_preview(interaction, 1)
                assert interaction.edited
            finally:
                m.build_season_preview_embed = original_preview

            original_power = m.get_combat_power
            original_targets = m.get_pvp_targets
            original_raid_cd = m.get_raid_cooldown_seconds
            original_duel_cd = m.get_duel_cooldown_seconds

            async def power(user_id):
                return 100

            async def targets(user_id, mode):
                return []

            async def raid_cd(user_id):
                return 60

            async def duel_cd(user_id):
                return 120

            m.get_combat_power = power
            m.get_pvp_targets = targets
            m.get_raid_cooldown_seconds = raid_cd
            m.get_duel_cooldown_seconds = duel_cd
            try:
                embed = await m.build_pvp_targets_embed(1)
                assert embed
            finally:
                m.get_combat_power = original_power
                m.get_pvp_targets = original_targets
                m.get_raid_cooldown_seconds = original_raid_cd
                m.get_duel_cooldown_seconds = original_duel_cd

            await db.execute("DELETE FROM items WHERE id = 'copper_gen'")
            await db.commit()
            interaction = FakeInteraction(1)
            await m.open_craft_view(interaction, 1)
            await db.execute("DELETE FROM items")
            await db.commit()
            interaction = FakeInteraction(1)
            await m.open_craft_view(interaction, 1)
            assert interaction.followup.sent
        finally:
            await _close(db)

    asyncio.run(run())


def test_giveaway_and_health_helpers():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, 1000)",
                [(1,), (2,)],
            )
            await db.commit()

            original_owner = m.is_global_owner
            original_snapshot = m.bot.build_health_snapshot

            async def owner_false(interaction):
                return False

            m.is_global_owner = owner_false
            try:
                interaction = FakeInteraction(1)
                await m.health_cmd.callback(interaction)
                assert interaction.response.messages
            finally:
                m.is_global_owner = original_owner

            async def owner_true(interaction):
                return True

            async def snapshot(deep=False):
                return {
                    "uptime_seconds": 1,
                    "gateway_latency_ms": 1,
                    "guilds": 1,
                    "db_size_bytes": 1,
                    "db_quick_check": "ok",
                    "commands_total": 0,
                    "command_errors": 0,
                    "command_avg_ms": 0,
                    "command_p95_ms": 0,
                    "db_tx_total": 0,
                    "db_tx_errors": 0,
                    "db_tx_avg_ms": 0,
                    "db_tx_p95_ms": 0,
                    "slow_db_tx": 0,
                    "tasks": [{"name": "dead", "done": True}],
                    "tasks_alive": 0,
                }

            m.is_global_owner = owner_true
            m.bot.build_health_snapshot = snapshot
            try:
                interaction = FakeInteraction(1)
                await m.health_cmd.callback(interaction)
                assert interaction.followup.sent
            finally:
                m.is_global_owner = original_owner
                m.bot.build_health_snapshot = original_snapshot

            original_sync = m.sync_guild_access
            old_guilds = m.bot._connection._guilds

            async def sync_fail(*args, **kwargs):
                raise RuntimeError("sync fail")

            m.bot._connection._guilds = {1: SimpleNamespace(id=1)}
            m.sync_guild_access = sync_fail
            try:
                await m.sync_all_guild_access()
            finally:
                m.bot._connection._guilds = old_guilds
                m.sync_guild_access = original_sync

            original_finalize = m.finalize_raid
            original_raid_embed = m.build_raid_result_embed

            async def finalize(result):
                return None

            def raid_embed(result):
                return m.BotEmbed(title="Raid")

            m.finalize_raid = finalize
            m.build_raid_result_embed = raid_embed
            try:
                interaction = FakeInteraction(1, fail_followup=True)
                await m.send_raid_result(interaction, {})
            finally:
                m.finalize_raid = original_finalize
                m.build_raid_result_embed = original_raid_embed

            original_disabled = m.is_command_disabled
            original_channel = m.select_giveaway_channel

            async def disabled(guild_id, command):
                return True

            def no_channel(guild):
                return None

            m.is_command_disabled = disabled
            assert (
                await m._send_global_giveaway_to_guild(
                    SimpleNamespace(id=1), 1
                )
                is False
            )
            m.is_command_disabled = lambda guild_id, command: _false()
            m.select_giveaway_channel = no_channel
            try:
                assert (
                    await m._send_global_giveaway_to_guild(
                        SimpleNamespace(id=2), 1
                    )
                    is False
                )
            finally:
                m.is_command_disabled = original_disabled
                m.select_giveaway_channel = original_channel

            original_insert = m._insert_giveaway_record
            original_send = m.send_giveaway_message
            original_log = m.log_admin_action

            async def insert(*args, **kwargs):
                return 1

            async def send(*args, **kwargs):
                return FakeMessage(delete_fail=True)

            async def log(*args, **kwargs):
                return None

            m._insert_giveaway_record = insert
            m.send_giveaway_message = send
            m.log_admin_action = log
            await db.execute(
                "INSERT INTO giveaways "
                "(id, guild_id, channel_id, message_id, creator_id, title, "
                "reward_type, reward_id, amount, winners_count, status, "
                "created_at, ends_at, winner_ids, scope) "
                "VALUES (1, 1, 1, 1, 1, 'x', 'coins', NULL, 1, 1, "
                "'active', 'now', 'later', '[]', 'server')"
            )
            await db.commit()
            await db.execute(
                "CREATE TRIGGER trg_giveaway_update_abort BEFORE UPDATE ON giveaways "
                "BEGIN SELECT RAISE(ABORT, 'update fail'); END"
            )
            await db.execute(
                "CREATE TRIGGER trg_giveaway_delete_abort BEFORE DELETE ON giveaways "
                "BEGIN SELECT RAISE(ABORT, 'delete fail'); END"
            )
            await db.commit()
            try:
                ok, message = await m.create_giveaway(
                    1, 1, SimpleNamespace(id=1), "coins", None, 100, 1, 1
                )
                assert not ok
            finally:
                m._insert_giveaway_record = original_insert
                m.send_giveaway_message = original_send
                m.log_admin_action = original_log
                await db.execute("DROP TRIGGER trg_giveaway_update_abort")
                await db.execute("DROP TRIGGER trg_giveaway_delete_abort")
                await db.commit()

            await m.finish_giveaway(999)
            now = m.datetime.datetime.now().isoformat()
            await db.execute(
                "INSERT INTO giveaways "
                "(id, guild_id, channel_id, message_id, creator_id, title, "
                "reward_type, reward_id, amount, winners_count, status, "
                "created_at, ends_at, winner_ids, scope) "
                "VALUES (50, 1, 1, 1, 1, 'x', 'pet', 'missing', 1, 1, "
                "'active', ?, ?, '[]', 'server')",
                (now, now),
            )
            await db.commit()
            await m.finish_giveaway(50)

            original_finish = m.finish_giveaway

            async def finish_fail(giveaway_id):
                raise RuntimeError("finish fail")

            m.finish_giveaway = finish_fail
            try:
                await db.execute(
                    "INSERT INTO giveaways "
                    "(id, guild_id, channel_id, message_id, creator_id, title, "
                    "reward_type, reward_id, amount, winners_count, status, "
                    "created_at, ends_at, winner_ids, scope) "
                    "VALUES (51, 1, 1, 1, 1, 'x', 'coins', NULL, 1, 1, "
                    "'active', ?, ?, '[]', 'server')",
                    (now, "2000-01-01T00:00:00"),
                )
                await db.commit()
                await m.finish_due_giveaways()
            finally:
                m.finish_giveaway = original_finish
        finally:
            await _close(db)

    asyncio.run(run())


async def _false():
    return False


def test_background_health_and_migrations(tmp_path):
    async def run():
        db = await _init()
        original_snapshot = m.bot.build_health_snapshot
        original_expire = m.expire_statuses
        original_fetch = m.bot.fetch_application_emojis
        original_emoji = m.BOT_BTN_EMOJIS.get("__probe__")
        try:
            class BrokenCtx:
                async def __aenter__(self):
                    raise aiosqlite.OperationalError("db fail")

                async def __aexit__(self, *args):
                    return None

            class BrokenDB:
                def execute(self, *args, **kwargs):
                    return BrokenCtx()

            fake_self = object.__new__(m.CastleBot)
            fake_self.db = BrokenDB()
            fake_self.db_path = None
            fake_self.background_tasks = []
            snapshot = await m.CastleBot.build_health_snapshot(
                fake_self, deep=True
            )
            assert snapshot["db_quick_check"].startswith("error")

            state = {"closed": False}

            async def ready():
                return None

            def closed():
                if state["closed"]:
                    return True
                state["closed"] = True
                return False

            async def no_sleep(*args, **kwargs):
                return None

            async def snapshot_fail(deep=False):
                raise RuntimeError("health fail")

            fake_health = object.__new__(m.CastleBot)
            fake_health.data_dir = tmp_path
            fake_health.wait_until_ready = ready
            fake_health.is_closed = closed
            fake_health.build_health_snapshot = snapshot_fail
            original_sleep = m.asyncio.sleep
            m.asyncio.sleep = no_sleep
            try:
                await m.CastleBot.health_writer(fake_health)
            finally:
                m.asyncio.sleep = original_sleep

            async def market_fail(*args, **kwargs):
                raise RuntimeError("market fail")

            fake_market = object.__new__(m.CastleBot)
            fake_market.db = BrokenDB()
            fake_market.wait_until_ready = ready
            fake_market.is_closed = closed

            async def market_once():
                state["closed"] = False
                fake_market.is_closed = lambda: _closed_after(state)

                async def closed_once():
                    if state["closed"]:
                        return True
                    state["closed"] = True
                    return False

                fake_market.is_closed = closed_once
                await m.CastleBot.market_updater(fake_market)

            m.asyncio.sleep = no_sleep
            try:
                await market_once()
            finally:
                m.asyncio.sleep = original_sleep

            async def expire_ok():
                return ["vip"]

            m.expire_statuses = expire_ok
            await _run_once(m.bot.status_expirer, expire_statuses=expire_ok)

            async def expire_fail():
                raise RuntimeError("expire fail")

            await _run_once(m.bot.status_expirer, expire_statuses=expire_fail)

            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'A', 1, 0), (2, 'B', 2, 0)"
            )
            await db.execute(
                "INSERT INTO clan_wars "
                "(id, clan1_id, clan2_id, start_time, status) "
                "VALUES (1, 1, 2, 'bad', 'active')"
            )
            await db.commit()
            fake_war = object.__new__(m.CastleBot)
            fake_war.db = db
            original_sleep = m.asyncio.sleep
            m.asyncio.sleep = no_sleep
            state["closed"] = False
            fake_war.wait_until_ready = ready
            fake_war.is_closed = closed
            try:
                await m.CastleBot.war_closer(fake_war)
            finally:
                m.asyncio.sleep = original_sleep

            await db.execute(
                "CREATE TABLE user_pets (user_id INTEGER, pet_id TEXT, "
                "level INTEGER, last_fed TEXT)"
            )
            await db.execute(
                "INSERT INTO user_pets VALUES (77, 'cat', 1, NULL)"
            )
            await db.execute(
                "UPDATE market_prices SET current_price = 999999 "
                "WHERE item_id = 'basic_gen'"
            )
            await db.commit()
            await m.bot.init_db()

            async def fetch_emojis():
                return [SimpleNamespace(id=123, name="probe")]

            m.bot.fetch_application_emojis = fetch_emojis
            m.BOT_BTN_EMOJIS["__probe__"] = "<:probe:123>"
            await m.bot.load_application_emojis()

            await db.execute(
                "INSERT OR REPLACE INTO content_meta (key, value) "
                "VALUES ('content_version', 'bad')"
            )
            await db.execute(
                "CREATE TRIGGER trg_content_abort BEFORE UPDATE ON guild_settings "
                "BEGIN SELECT RAISE(ABORT, 'content fail'); END"
            )
            await db.commit()
            await m.bot.apply_content_migrations([], [], [], [], [])
            await db.execute("DROP TRIGGER trg_content_abort")
            await db.commit()
        finally:
            m.bot.build_health_snapshot = original_snapshot
            m.expire_statuses = original_expire
            m.bot.fetch_application_emojis = original_fetch
            if original_emoji is None:
                m.BOT_BTN_EMOJIS.pop("__probe__", None)
            else:
                m.BOT_BTN_EMOJIS["__probe__"] = original_emoji
            await _close(db)

    asyncio.run(run())


def _closed_after(state):
    if state["closed"]:
        return True
    state["closed"] = True
    return False


def test_upgrades_select_rowcounts():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems, grid_size) "
                "VALUES (1, 10000, 10000, 9)"
            )
            await db.commit()
            option = m.discord.SelectOption(label="X", value="grid_7x7")
            view = m.UpgradesBuySelectView(1, [option])

            await db.execute(
                "CREATE TRIGGER trg_upgrade_insert_ignore "
                "BEFORE INSERT ON player_upgrades "
                "WHEN NEW.user_id = 1 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(1, ["grid_7x7"])
            await view.upgrade_select(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_upgrade_insert_ignore")
            await db.commit()

            await db.execute(
                "CREATE TRIGGER trg_upgrade_update_ignore "
                "BEFORE UPDATE OF gems ON players "
                "WHEN OLD.user_id = 1 AND NEW.gems < OLD.gems "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(1, ["grid_8x8"])
            await view.upgrade_select(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_upgrade_update_ignore")
            await db.commit()
        finally:
            await _close(db)

    asyncio.run(run())


def test_extra_small_helpers():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "UPDATE items SET emoji = '', emoji_by_star = 'bad' "
                "WHERE id = 'basic_gen'"
            )
            await db.commit()

            assert m.status_daily_price("bad", 7) is None
            assert await m.get_storage_size(999) == m.STORAGE_SIZE
            assert await m.get_star_emoji("basic_gen", 0, "") == ""
            assert "2" in await m.get_star_emoji("basic_gen", 2, "")
            assert m.get_next_onboarding_step(set(m.ONBOARDING_STEPS)) == (
                None,
                None,
            )

            now = m.datetime.datetime.now()
            assert m._parse_db_time(now) is now
            assert m._parse_db_time("   ") is None

            event, day = m.get_active_advent_event(m.datetime.date(2026, 1, 5))
            assert event is not None and day >= 1

            original_pity = m.get_star_pity

            async def pity(user_id, item_id, target_star):
                return m.STAR_HARD_PITY - 1

            m.get_star_pity = pity
            try:
                chance, value, guaranteed = await m.get_star_chance(
                    1, "basic_gen", 1
                )
                assert guaranteed and chance == 1.0
            finally:
                m.get_star_pity = original_pity

            original_sync = m.sync_guild_access

            async def sync(*args, **kwargs):
                return None

            m.sync_guild_access = sync
            try:
                await m.on_guild_join(SimpleNamespace(id=1))
            finally:
                m.sync_guild_access = original_sync
        finally:
            await _close(db)

    asyncio.run(run())
