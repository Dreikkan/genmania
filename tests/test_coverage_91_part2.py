import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_coverage_91_part2_test", BOT_PATH
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
    def __init__(self, fail=False):
        self.fail = fail
        self.edits = []
        self.deleted = False

    async def edit(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.edits.append((args, kwargs))

    async def delete(self):
        self.deleted = True


class FakeInteraction:
    def __init__(self, user_id=1, values=None):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(get_role=lambda rid: None)
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
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


async def _submit(modal, **fields):
    interaction = FakeInteraction()
    for name, value in fields.items():
        getattr(modal, name)._value = str(value)
    await modal.on_submit(interaction)
    return interaction


def test_swap_and_craft_branches():
    async def run():
        db = await _init()
        original_quest = m.update_quest_progress
        original_story = m.update_story_quests
        original_achievements = m.check_achievements
        original_profile = m.build_profile_embed
        original_storage = m.build_storage_embed
        original_chance = m.get_craft_chance
        original_random = m.random.random
        original_place = m.place_items

        async def noop(*args, **kwargs):
            return None

        async def profile(interaction):
            return m.BotEmbed(title="Profile")

        async def storage(interaction):
            return m.BotEmbed(title="Storage")

        m.update_quest_progress = noop
        m.update_story_quests = noop
        m.check_achievements = lambda user_id: _list()
        m.build_profile_embed = profile
        m.build_storage_embed = storage
        try:
            await db.executemany(
                "INSERT INTO players "
                "(user_id, coins, gems, catalysts, grid_size, storage_size) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(1, 1000, 100, 1, 1, 1), (2, 1000, 0, 0, 3, 1)],
            )
            await db.executemany(
                "INSERT OR IGNORE INTO items "
                "(id, name, price, income_per_hour, emoji, rarity, buyable) "
                "VALUES (?, ?, 100, 1, '⚙️', 'common', 1)",
                [
                    ("basic_gen", "Basic"),
                    ("copper_gen", "Copper"),
                    ("steel_gen", "Steel"),
                    ("silver_gen", "Silver"),
                ],
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (2, 0, 'basic_gen', 'storage', 0), "
                "(2, 2, 'basic_gen', 'storage', 1)"
            )
            await db.commit()

            embed, view, error = await m._build_swap_second_page(
                "storage", 2, 0, 1
            )
            assert error and embed is None and view is None

            await db.execute(
                "UPDATE players SET storage_size = 3 WHERE user_id = 2"
            )
            await db.commit()
            embed, view, error = await m._build_swap_second_page(
                "storage", 2, 0, 1
            )
            assert embed and view and error is None

            await db.execute(
                "DELETE FROM inventory WHERE user_id = 2 AND location = 'storage'"
            )
            await db.commit()

            await db.execute(
                "DELETE FROM inventory WHERE user_id = 2 AND location = 'profile'"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (2, 0, 'basic_gen', 'profile', 0)"
            )
            await db.commit()
            main_message = FakeMessage()
            view = m.SwapSecondView(2, "profile", 0, [m.discord.SelectOption(label="X", value="1")], 0, 1, main_message)
            interaction = FakeInteraction(2, ["1"])
            await view.second_select(interaction)
            assert interaction.response.deferred and interaction.edited
            assert main_message.edits

            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (2, 1, 'copper_gen', 'storage', 0)"
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = 2 AND location = 'storage'"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (2, 0, 'basic_gen', 'storage', 0), "
                "(2, 1, 'copper_gen', 'storage', 0)"
            )
            await db.commit()
            failing = FakeMessage(fail=True)
            view = m.SwapSecondView(2, "storage", 0, [m.discord.SelectOption(label="X", value="1")], 0, 1, failing)
            interaction = FakeInteraction(2, ["1"])
            await view.second_select(interaction)
            assert interaction.edited

            await db.execute(
                "DELETE FROM inventory WHERE user_id = 2 AND location = 'profile'"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (2, 0, 'basic_gen', 'profile', 0)"
            )
            await db.commit()
            await db.execute(
                "CREATE TRIGGER trg_swap_empty_ignore BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 2 AND OLD.location = 'profile' AND OLD.slot = 0 "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            view = m.SwapSecondView(2, "profile", 0, [m.discord.SelectOption(label="X", value="1")], 0, 1)
            interaction = FakeInteraction(2, ["1"])
            await view.second_select(interaction)
            assert interaction.edited
            await db.execute("DROP TRIGGER trg_swap_empty_ignore")
            await db.commit()

            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (2, 1, 'copper_gen', 'profile', 0)"
            )
            await db.commit()
            await db.execute(
                "CREATE TRIGGER trg_swap_filled_ignore BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 2 AND OLD.location = 'profile' AND OLD.slot = 1 "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            view = m.SwapSecondView(2, "profile", 0, [m.discord.SelectOption(label="X", value="1")], 0, 1)
            interaction = FakeInteraction(2, ["1"])
            await view.second_select(interaction)
            assert interaction.edited
            await db.execute("DROP TRIGGER trg_swap_filled_ignore")
            await db.commit()

            await db.execute(
                "DELETE FROM inventory WHERE user_id = 2 AND location = 'profile'"
            )
            await db.executemany(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (2, ?, 'steel_gen', 'profile', 0)",
                [(0,), (1,), (2,)],
            )
            await db.commit()
            await db.execute(
                "CREATE TRIGGER trg_craft_gem_ignore BEFORE UPDATE OF gems ON players "
                "WHEN OLD.user_id = 2 AND NEW.gems < OLD.gems "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(2)
            await m.CraftConfirmView(2, "steel_gen").do_craft(interaction, False)
            assert interaction.edited
            await db.execute("DROP TRIGGER trg_craft_gem_ignore")
            await db.commit()

            await db.execute(
                "DELETE FROM inventory WHERE user_id = 2 AND location = 'profile'"
            )
            await db.executemany(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (2, ?, 'basic_gen', 'profile', 0)",
                [(0,), (1,), (2,)],
            )
            await db.commit()
            await db.execute(
                "CREATE TRIGGER trg_craft_cat_ignore BEFORE UPDATE OF catalysts ON players "
                "WHEN OLD.user_id = 2 AND NEW.catalysts < OLD.catalysts "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = FakeInteraction(2)
            await m.CraftConfirmView(2, "basic_gen").do_craft(interaction, True)
            assert interaction.edited
            await db.execute("DROP TRIGGER trg_craft_cat_ignore")
            await db.commit()

            async def chance(*args):
                return 0.0, 0, False

            async def fail_place(*args, **kwargs):
                raise ValueError("no space")

            m.get_craft_chance = chance
            m.random.random = lambda: 1.0
            m.place_items = fail_place
            try:
                interaction = FakeInteraction(2)
                await m.CraftConfirmView(2, "basic_gen").do_craft(interaction, False)
                assert interaction.edited
            finally:
                m.get_craft_chance = original_chance
                m.random.random = original_random
                m.place_items = original_place
        finally:
            m.update_quest_progress = original_quest
            m.update_story_quests = original_story
            m.check_achievements = original_achievements
            m.build_profile_embed = original_profile
            m.build_storage_embed = original_storage
            await _close(db)

    asyncio.run(run())


async def _list():
    return []


def test_clan_confirm_invites_and_menu_branches():
    async def run():
        db = await _init()
        original_perm = m.has_clan_permission
        original_capacity = m.get_clan_capacity
        original_role = m.get_clan_role
        original_buy = m.open_clan_buy_select
        original_apps = m.open_clan_applications
        original_build = m.build_clan_embed
        original_upgrades = m.build_clan_upgrades_embed
        original_get_user = m.bot.get_user
        original_fetch_user = m.bot.fetch_user

        async def noop(*args, **kwargs):
            return None

        async def embed(*args, **kwargs):
            return m.BotEmbed(title="Clan")

        async def upgrades(clan_id):
            return m.BotEmbed(title="Upgrades")

        async def not_found(user_id):
            raise m.discord.NotFound.__new__(m.discord.NotFound)

        m.open_clan_buy_select = noop
        m.open_clan_applications = noop
        m.build_clan_embed = embed
        m.build_clan_upgrades_embed = upgrades
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, 1000)",
                [(20,), (21,), (30,), (31,), (32,), (40,), (41,), (50,), (51,)],
            )
            await db.executemany(
                "INSERT INTO clans (id, name, leader_id, treasury, capacity) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (1, "Alpha", 30, 0, 10),
                    (2, "Full", 21, 0, 1),
                    (3, "Main", 30, 0, 10),
                    (4, "Up", 40, 0, 10),
                    (5, "Members", 50, 0, 10),
                ],
            )
            await db.executemany(
                "INSERT INTO clan_members (user_id, clan_id, role) VALUES (?, ?, ?)",
                [
                    (21, 2, "leader"),
                    (30, 3, "leader"),
                    (31, 3, "leader"),
                    (32, 3, "member"),
                    (40, 4, "leader"),
                    (41, 4, "leader"),
                    (50, 5, "leader"),
                    (51, 5, "member"),
                ],
            )
            await db.executemany(
                "INSERT INTO clan_invites (id, clan_id, inviter_id, target_id) "
                "VALUES (?, ?, 1, 20)",
                [(1, 1), (2, 2), (3, 3)],
            )
            await db.commit()

            option = m.discord.SelectOption(label="X", value="1:1")
            view = m.ClanInvitesView(20, [option])
            interaction = FakeInteraction(20, ["999:999"])
            await view.select(interaction)
            assert interaction.followup.sent
            interaction = FakeInteraction(20, ["1:2"])
            await view.select(interaction)
            assert interaction.followup.sent
            interaction = FakeInteraction(20, ["999:1"])
            await view.select(interaction)
            assert interaction.followup.sent

            await db.execute(
                "CREATE TRIGGER trg_clan_insert_block BEFORE INSERT ON clan_members "
                "WHEN NEW.user_id = 20 BEGIN SELECT RAISE(ABORT, 'dup'); END"
            )
            await db.commit()
            interaction = FakeInteraction(20, ["1:1"])
            await view.select(interaction)
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_clan_insert_block")
            await db.commit()

            m.has_clan_permission = lambda role, action: True
            interaction = await _submit(
                m.ClanTargetConfirmModal(30, 3, "promote", 31), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(30, 3, "kick", 31), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(30, 3, "transfer", 31), confirm="ДА"
            )
            assert interaction.followup.sent

            await db.execute(
                "CREATE TRIGGER trg_clan_role_ignore BEFORE UPDATE OF role ON clan_members "
                "WHEN NEW.user_id = 32 AND NEW.role != OLD.role "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = await _submit(
                m.ClanTargetConfirmModal(30, 3, "promote", 32), confirm="ДА"
            )
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_clan_role_ignore")
            await db.commit()

            await db.execute(
                "CREATE TRIGGER trg_clan_del_ignore BEFORE DELETE ON clan_members "
                "WHEN OLD.user_id = 32 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = await _submit(
                m.ClanTargetConfirmModal(30, 3, "kick", 32), confirm="ДА"
            )
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_clan_del_ignore")
            await db.commit()

            await db.execute(
                "CREATE TRIGGER trg_clan_demote_ignore BEFORE UPDATE OF role ON clan_members "
                "WHEN NEW.user_id = 30 AND NEW.role = 'member' "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = await _submit(
                m.ClanTargetConfirmModal(30, 3, "transfer", 32), confirm="ДА"
            )
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_clan_demote_ignore")
            await db.commit()

            await db.execute(
                "CREATE TRIGGER trg_clan_promote_ignore BEFORE UPDATE OF role ON clan_members "
                "WHEN NEW.user_id = 32 AND NEW.role = 'leader' "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            interaction = await _submit(
                m.ClanTargetConfirmModal(30, 3, "transfer", 32), confirm="ДА"
            )
            assert interaction.followup.sent
            await db.execute("DROP TRIGGER trg_clan_promote_ignore")
            await db.commit()

            async def capacity(clan_id):
                return 10

            async def capacity_max(clan_id):
                return m.CLAN_MAX_CAPACITY

            m.get_clan_capacity = capacity
            view = m.ClanUpgradesView(40, 4)
            m.has_clan_permission = lambda role, action: False
            interaction = FakeInteraction(40)
            await view.btn_expand.callback(interaction)
            assert interaction.response.messages

            m.has_clan_permission = lambda role, action: True
            m.get_clan_capacity = capacity_max
            interaction = FakeInteraction(40)
            await view.btn_expand.callback(interaction)
            assert interaction.followup.sent

            m.get_clan_capacity = capacity
            interaction = FakeInteraction(40)
            await view.btn_expand.callback(interaction)
            assert interaction.followup.sent

            await db.execute(
                "UPDATE clans SET treasury = 999999 WHERE id = 4"
            )
            await db.commit()
            await db.execute(
                "CREATE TRIGGER trg_clan_capacity_ignore BEFORE UPDATE ON clans "
                "WHEN NEW.id = 4 BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            m.get_clan_capacity = capacity
            try:
                interaction = FakeInteraction(40)
                await view.btn_expand.callback(interaction)
            except ValueError:
                pass
            await db.execute("DROP TRIGGER trg_clan_capacity_ignore")
            await db.commit()

            view = m.ClanMenuView(41, 4)
            interaction = FakeInteraction(41)
            await view.btn_buy.callback(interaction)
            assert interaction.response.deferred
            interaction = FakeInteraction(41)
            await view.btn_applications.callback(interaction)
            assert interaction.response.deferred

            view = m.ClanManageView(41, 4)
            interaction = FakeInteraction(41)
            await view.btn_back.callback(interaction)
            assert interaction.edited

            m.bot.get_user = lambda user_id: None
            m.bot.fetch_user = not_found
            members_embed, page, pages = await m.build_clan_members_embed(5)
            assert members_embed and page == 0 and pages == 1
        finally:
            m.has_clan_permission = original_perm
            m.get_clan_capacity = original_capacity
            m.get_clan_role = original_role
            m.open_clan_buy_select = original_buy
            m.open_clan_applications = original_apps
            m.build_clan_embed = original_build
            m.build_clan_upgrades_embed = original_upgrades
            m.bot.get_user = original_get_user
            m.bot.fetch_user = original_fetch_user
            await _close(db)

    asyncio.run(run())


def test_background_settings_and_raid_branches(tmp_path):
    async def run():
        db = await _init()
        original_wait = m.bot.wait_until_ready
        original_closed = m.bot.is_closed
        original_sleep = m.asyncio.sleep
        original_backup = m.bot.backup_database
        original_income = m.calculate_full_passive_income
        original_client_close = m.discord.ext.commands.Bot.close
        original_connect = m.aiosqlite.connect
        original_exists = m.Path.exists
        original_unlink = m.Path.unlink
        original_settings = m.get_settings
        original_save = m.save_setting
        original_sync = m.sync_all_guild_access
        original_schedule = m.RaidInviteView._schedule_delete

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

        async def noop(*args, **kwargs):
            return None

        async def backup_fail(reason):
            raise RuntimeError("backup fail")

        async def income_fail(user_id):
            raise RuntimeError("income fail")

        async def sync():
            return None

        async def fake_settings(guild_id):
            return {"custom_emojis": {}}

        async def fake_save(*args, **kwargs):
            return None

        try:
            m.bot.wait_until_ready = ready
            m.bot.is_closed = closed
            m.asyncio.sleep = no_sleep
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000), (2, 1000), (3, 1000)"
            )
            await db.execute(
                "INSERT INTO autocollectors (user_id, level, last_auto) "
                "VALUES (1, 1, ?)",
                (m.datetime.datetime.now().isoformat(),),
            )
            await db.commit()

            m.bot.backup_database = backup_fail
            try:
                await m.bot.backup_task()
            finally:
                m.bot.backup_database = original_backup

            await db.execute(
                "INSERT INTO autocollectors (user_id, level, last_auto) "
                "VALUES (2, 1, NULL)"
            )
            await db.commit()
            m.calculate_full_passive_income = income_fail
            try:
                state["closed"] = False
                await m.bot.autocollector_task()
            finally:
                m.calculate_full_passive_income = original_income
                state["closed"] = False

            async def fake_client_close(self):
                return None

            m.discord.ext.commands.Bot.close = fake_client_close
            backup_calls = []

            async def fake_backup(reason):
                backup_calls.append(reason)

            fake_self = object.__new__(m.CastleBot)
            fake_self._closing = True
            await m.CastleBot.close(fake_self)

            fake_self._closing = False
            fake_self.background_tasks = [asyncio.create_task(no_sleep())]
            fake_self.db = None
            await m.CastleBot.close(fake_self)
            assert fake_self.background_tasks == []

            class BrokenDB:
                async def execute(self, *args, **kwargs):
                    raise RuntimeError("db fail")

                async def close(self):
                    return None

            fake_self = object.__new__(m.CastleBot)
            fake_self._closing = False
            fake_self.background_tasks = []
            fake_self.db = BrokenDB()
            fake_self.backup_database = fake_backup
            await m.CastleBot.close(fake_self)
            assert fake_self.db is None and backup_calls == ["shutdown"]

            class FakeCtx:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return None

                async def fetchone(self):
                    return ("bad",)

            class FakeConn:
                async def close(self):
                    return None

                def execute(self, *args, **kwargs):
                    return FakeCtx()

            async def fake_connect(path):
                return FakeConn()

            main_db = tmp_path / "main.db"
            main_db.write_bytes(b"x" * 2048)

            class FakeBackupDB:
                in_transaction = False

                async def execute(self, *args, **kwargs):
                    return None

                async def commit(self):
                    return None

                async def backup(self, target):
                    return None

            def exists(path):
                if str(path).endswith(".tmp"):
                    return True
                return original_exists(path)

            def unlink(path, *args, **kwargs):
                if str(path).endswith(".tmp"):
                    raise OSError("busy")
                return original_unlink(path, *args, **kwargs)

            m.Path.exists = exists
            m.Path.unlink = unlink
            backup_self = object.__new__(m.CastleBot)
            backup_self.db = FakeBackupDB()
            backup_self.db_path = str(main_db)
            backup_self.backup_dir = tmp_path
            assert await m.CastleBot.backup_database(backup_self, "manual") is None

            def exists_missing(path):
                if str(path).endswith(".tmp"):
                    return False
                return original_exists(path)

            m.Path.exists = exists_missing
            m.Path.unlink = original_unlink
            m.aiosqlite.connect = fake_connect
            assert await m.CastleBot.backup_database(backup_self, "manual") is None

            m.aiosqlite.connect = original_connect
            m.Path.exists = original_exists
            m.Path.unlink = original_unlink

            m.sync_all_guild_access = sync
            m.bot._guild_access_synced = False
            try:
                await m.on_ready()
                await m.on_ready()
            finally:
                m.sync_all_guild_access = original_sync
                if hasattr(m.bot, "_guild_access_synced"):
                    del m.bot._guild_access_synced

            m.get_settings = fake_settings
            m.save_setting = fake_save
            try:
                modal = m.SettingsGeneralModal(1)
                modal.bot_name._value = ""
                modal.item_id._value = "basic_gen"
                modal.emoji._value = "abc"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent

                modal = m.SettingsGeneralModal(1)
                modal.bot_name._value = ""
                modal.item_id._value = "missing"
                modal.emoji._value = "👑"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.get_settings = original_settings
                m.save_setting = original_save

            await db.execute(
                "INSERT INTO raid_parties (id, leader_id, member2_id, member3_id) "
                "VALUES (1, 3, NULL, NULL)"
            )
            await db.executemany(
                "INSERT INTO raid_party_invites (party_id, inviter_id, target_id) "
                "VALUES (1, 3, ?)",
                [(4,), (5,), (6,), (7,), (8,)],
            )
            await db.commit()
            interaction = await _submit(m.RaidInviteModal(3, 1), target_id="9")
            assert interaction.followup.sent
            await db.execute("DELETE FROM raid_party_invites WHERE party_id = 1")
            await db.commit()

            class Channel:
                async def send(self, *args, **kwargs):
                    raise m.discord.HTTPException.__new__(m.discord.HTTPException)

            original_messageable = m.discord.abc.Messageable
            try:
                m.discord.abc.Messageable = Channel
                modal = m.RaidInviteModal(3, 1)
                interaction = FakeInteraction(3)
                interaction.channel = Channel()
                modal.target_id._value = "2"
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.discord.abc.Messageable = original_messageable

            original_join = m.join_raid_party
            view = m.RaidInviteView(1, 3, 2)
            view._schedule_delete = lambda delay: None
            interaction = FakeInteraction(2)
            interaction.message = FakeMessage(fail=True)

            async def join_fail(party_id, target_id):
                raise ValueError("bad join")

            async def join_ok(party_id, target_id):
                return None

            m.join_raid_party = join_fail
            try:
                await view.accept.callback(interaction)
                assert view.resolved
            finally:
                m.join_raid_party = original_join

            view = m.RaidInviteView(1, 3, 2)
            view._schedule_delete = lambda delay: None
            interaction = FakeInteraction(2)
            interaction.message = FakeMessage(fail=True)
            m.join_raid_party = join_ok
            try:
                await view.accept.callback(interaction)
                assert view.resolved
            finally:
                m.join_raid_party = original_join
        finally:
            m.bot.wait_until_ready = original_wait
            m.bot.is_closed = original_closed
            m.asyncio.sleep = original_sleep
            m.bot.backup_database = original_backup
            m.calculate_full_passive_income = original_income
            m.discord.ext.commands.Bot.close = original_client_close
            m.aiosqlite.connect = original_connect
            m.Path.exists = original_exists
            m.Path.unlink = original_unlink
            m.get_settings = original_settings
            m.save_setting = original_save
            m.sync_all_guild_access = original_sync
            m.RaidInviteView._schedule_delete = original_schedule
            await _close(db)

    asyncio.run(run())


def test_misc_view_and_open_helpers():
    async def run():
        db = await _init()
        original_parse = m.parse_emoji_safe
        original_build_pets = m.build_pets_embed
        original_profile = m.build_profile_embed
        original_storage = m.build_storage_embed
        original_bulk = m.perform_bulk_sell
        original_income = m.calculate_full_passive_income

        async def noop(*args, **kwargs):
            return None

        async def pets(interaction):
            return m.BotEmbed(title="Pets")

        async def profile(interaction):
            return m.BotEmbed(title="Profile")

        async def storage(interaction):
            return m.BotEmbed(title="Storage")

        async def bulk_sell(user_id, mode):
            return False, "empty", 0, 0

        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems, grid_size, active_pet) "
                "VALUES (?, ?, ?, ?, NULL)",
                [
                    (60, 1000, 100, 3),
                    (61, 1000, 100, 3),
                    (62, 1000, 100, 3),
                    (63, 1000, 100, 1),
                    (64, 1000, 100, 9),
                    (65, 1000, 100, 9),
                    (70, 1000, 100, 9),
                    (71, 1000, 100, 9),
                    (72, 1000, 100, 1),
                    (73, 1000, 100, 9),
                    (74, 1000, 100, 9),
                    (75, 1000, 100, 9),
                ],
            )
            await db.execute(
                "UPDATE players SET storage_size = 1 WHERE user_id IN (63, 72)"
            )
            await db.executemany(
                "INSERT OR IGNORE INTO items "
                "(id, name, price, income_per_hour, emoji, rarity, buyable) "
                "VALUES (?, ?, 100, 1, '⚙️', 'common', 1)",
                [
                    ("basic_gen", "Basic"),
                    ("common_gen", "Common"),
                ],
            )
            await db.executemany(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (?, ?, ?, ?, 0)",
                [
                    (63, 0, "basic_gen", "profile"),
                    (63, 0, "basic_gen", "storage"),
                    (64, 0, "basic_gen", "storage"),
                    (65, 0, "basic_gen", "storage"),
                    (71, 0, "common_gen", "storage"),
                    (72, 0, "basic_gen", "profile"),
                    (72, 0, "basic_gen", "storage"),
                    (73, 0, "basic_gen", "profile"),
                ],
            )
            await db.commit()

            m.parse_emoji_safe = lambda value: None
            m.build_pets_embed = pets
            try:
                interaction = FakeInteraction(60)
                await m.open_pets_shop(interaction, 60)
                assert interaction.edited
                back_view = interaction.edited[-1][1]["view"]
                await back_view.children[0].callback(FakeInteraction(60))
            finally:
                m.parse_emoji_safe = original_parse

            await db.executemany(
                "INSERT INTO user_pets_v2 (user_id, pet_id, level) VALUES (61, ?, 1)",
                [(pet_id,) for pet_id in m.PET_TYPES],
            )
            await db.commit()
            interaction = FakeInteraction(61)
            await m.open_pets_shop(interaction, 61)
            assert interaction.edited
            back_view = interaction.edited[-1][1]["view"]
            await back_view.children[0].callback(FakeInteraction(61))

            view = m.PetSwitchView(
                62, [m.discord.SelectOption(label="Cat", value="cat")], "shop"
            )
            interaction = FakeInteraction(62, ["cat"])
            await view.select(interaction)
            assert interaction.followup.sent

            view = m.MoveView(
                63, "profile", [m.discord.SelectOption(label="X", value="0:basic_gen:0")], 0, 1
            )
            interaction = FakeInteraction(63)
            await view.do_move(interaction, 0, "basic_gen", 0)
            assert interaction.edited

            await db.execute(
                "CREATE TRIGGER trg_move_ignore BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 64 AND OLD.location = 'storage' AND OLD.slot = 0 "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            view = m.MoveView(
                64, "storage", [m.discord.SelectOption(label="X", value="0:basic_gen:0")], 0, 1
            )
            interaction = FakeInteraction(64)
            await view.do_move(interaction, 0, "basic_gen", 0)
            assert interaction.edited
            await db.execute("DROP TRIGGER trg_move_ignore")
            await db.commit()

            m.build_storage_embed = storage
            view = m.MoveView(
                65, "storage", [m.discord.SelectOption(label="X", value="0:basic_gen:0")], 0, 1,
                FakeMessage(fail=True),
            )
            interaction = FakeInteraction(65)
            await view.do_move(interaction, 0, "basic_gen", 0)
            assert interaction.edited

            original_min = m.COIN_EXCHANGE_MIN
            m.COIN_EXCHANGE_MIN = 0
            try:
                modal = m.CoinsToGemsModal(70)
                modal.amount._value = "5"
                interaction = FakeInteraction(70)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.COIN_EXCHANGE_MIN = original_min

            original_fee = m.exchange_fee_rate
            m.exchange_fee_rate = lambda amount, direction: 1.0
            try:
                modal = m.CoinsToGemsModal(70)
                modal.amount._value = "12"
                interaction = FakeInteraction(70)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.exchange_fee_rate = original_fee

            ok, message, count, total = await m.perform_bulk_sell(71, "dupes")
            assert not ok
            await db.execute(
                "CREATE TRIGGER trg_bulk_ignore BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 71 AND OLD.location = 'storage' "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            ok, message, count, total = await m.perform_bulk_sell(71, "common")
            assert not ok
            await db.execute("DROP TRIGGER trg_bulk_ignore")
            await db.commit()

            m.calculate_full_passive_income = original_income
            ok, message, moved = await m.mass_move_zero_star(72, "profile", "storage")
            assert not ok

            await db.execute(
                "CREATE TRIGGER trg_mass_ignore BEFORE DELETE ON inventory "
                "WHEN OLD.user_id = 73 AND OLD.location = 'profile' "
                "BEGIN SELECT RAISE(IGNORE); END"
            )
            await db.commit()
            ok, message, moved = await m.mass_move_zero_star(73, "profile", "storage")
            assert not ok
            await db.execute("DROP TRIGGER trg_mass_ignore")
            await db.commit()

            future = (m.datetime.datetime.now() + m.datetime.timedelta(hours=1)).isoformat()
            await db.executemany(
                "INSERT INTO market_orders "
                "(user_id, side, item_id, stars, price, quantity, filled, status, expires_at) "
                "VALUES (74, ?, 'basic_gen', 0, 100, 2, 0, 'active', ?)",
                [("buy", future), ("sell", future)],
            )
            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, stars, start_price, current_bid, current_bidder, "
                "buyout_price, end_time, status) "
                "VALUES (1, 75, 'basic_gen', 0, 10, 10, NULL, NULL, 'zzz', 'active')"
            )
            await db.commit()

            interaction = FakeInteraction(74)
            await m.open_market_orders(interaction, 74, 0, "buy", 999)
            assert interaction.edited
            interaction = FakeInteraction(74)
            await m.open_market_orders(interaction, 74, 0, "sell", 999)
            assert interaction.edited

            interaction = FakeInteraction(75)
            await m.open_auction_view(interaction, 75, 0, 999)
            assert interaction.edited
            interaction = FakeInteraction(75)
            await m.open_auction_view(interaction, 75, 0, 1)
            assert interaction.edited
        finally:
            m.parse_emoji_safe = original_parse
            m.build_pets_embed = original_build_pets
            m.build_profile_embed = original_profile
            m.build_storage_embed = original_storage
            m.perform_bulk_sell = original_bulk
            m.calculate_full_passive_income = original_income
            await _close(db)

    asyncio.run(run())


def test_small_interaction_checks():
    async def run():
        db = await _init()
        try:
            option = m.discord.SelectOption(label="X", value="x")
            for view in (
                m.ClaimQuestSelectView(1, [option]),
                m.CatalystSelectView(1),
            ):
                interaction = FakeInteraction(2)
                assert await view.interaction_check(interaction) is False
                interaction = FakeInteraction(1)
                assert await view.interaction_check(interaction) is True
        finally:
            await _close(db)

    asyncio.run(run())
