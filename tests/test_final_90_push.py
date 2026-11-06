import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_final_90_push_test", BOT_PATH
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
        self.deleted = False
        self.edits = []

    async def delete(self):
        self.deleted = True

    async def edit(self, *args, **kwargs):
        self.edits.append((args, kwargs))


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


def test_background_task_error_branches():
    async def run():
        db = await _init()
        try:
            original_backup = m.bot.backup_database

            async def backup_fail(reason):
                raise RuntimeError("backup fail")

            m.bot.backup_database = backup_fail
            try:
                await _run_once(m.bot.backup_task)
            finally:
                m.bot.backup_database = original_backup

            original_db = m.bot.db

            class BrokenDB:
                async def execute(self, *args, **kwargs):
                    raise RuntimeError("db fail")

                async def commit(self):
                    return None

            m.bot.db = BrokenDB()
            try:
                await _run_once(m.bot.retention_task)
            finally:
                m.bot.db = original_db

            original_income = m.calculate_full_passive_income

            async def income_fail(user_id):
                raise RuntimeError("income fail")

            m.calculate_full_passive_income = income_fail
            try:
                await _run_once(m.bot.autocollector_task)
            finally:
                m.calculate_full_passive_income = original_income
        finally:
            await _close(db)

    asyncio.run(run())


def test_clan_invites_browser_and_target_confirm():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, ?)",
                [(1, 1000), (2, 1000), (3, 1000), (4, 1000)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 0)"
            )
            await db.executemany(
                "INSERT INTO clan_members (user_id, clan_id, role) VALUES (?, 1, ?)",
                [(1, "leader"), (2, "leader"), (3, "member"), (4, "deputy")],
            )
            await db.execute(
                "INSERT INTO clan_invites (id, clan_id, inviter_id, target_id) "
                "VALUES (1, 1, 1, 2)"
            )
            await db.commit()

            option = m.discord.SelectOption(label="X", value="1:1")
            original_capacity = m.get_clan_capacity
            original_count = m.get_clan_member_count

            async def capacity(clan_id):
                return 10

            async def count(clan_id):
                return 0

            m.get_clan_capacity = capacity
            m.get_clan_member_count = count
            try:
                view = m.ClanInvitesView(2, [option])
                interaction = FakeInteraction(2, ["1:999"])
                await view.select(interaction)
                assert interaction.followup.sent

                m.get_clan_capacity = lambda clan_id: 1
                m.get_clan_member_count = lambda clan_id: 1
                interaction = FakeInteraction(2, ["1:1"])
                await view.select(interaction)
                assert interaction.followup.sent

                m.get_clan_capacity = capacity
                m.get_clan_member_count = count
                interaction = FakeInteraction(2, ["999:1"])
                await view.select(interaction)
                assert interaction.followup.sent
            finally:
                m.get_clan_capacity = original_capacity
                m.get_clan_member_count = original_count

            original_apply = m.apply_to_clan
            original_detail = m.open_clan_detail

            async def apply(*args):
                return True, "ok"

            async def detail(*args):
                return None

            m.apply_to_clan = apply
            m.open_clan_detail = detail
            try:
                view = m.ClanBrowserDetailView(2, 1, 0, "", True)
                interaction = FakeInteraction(2)
                await view.apply.callback(interaction)
                assert interaction.followup.sent
            finally:
                m.apply_to_clan = original_apply
                m.open_clan_detail = original_detail

            original_perm = m.has_clan_permission
            original_role = m.get_clan_role

            async def role(user_id, clan_id):
                return "member" if user_id == 3 else "leader"

            m.get_clan_role = role
            m.has_clan_permission = lambda role, action: True
            try:
                interaction = await _submit(
                    m.ClanTargetConfirmModal(2, 1, "promote", 2), confirm="ДА"
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.ClanTargetConfirmModal(2, 1, "kick", 2), confirm="ДА"
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.ClanTargetConfirmModal(2, 1, "transfer", 2), confirm="ДА"
                )
                assert interaction.followup.sent
                interaction = await _submit(
                    m.ClanTargetConfirmModal(3, 1, "transfer", 4), confirm="ДА"
                )
                assert interaction.followup.sent
            finally:
                m.has_clan_permission = original_perm
                m.get_clan_role = original_role
        finally:
            await _close(db)

    asyncio.run(run())


def test_auction_closer_giveaway_raid_and_bulk_edges():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, ?)",
                [(1, 0), (2, 0)],
            )
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "emoji, rarity, buyable) "
                "VALUES ('common_gen', 'Common', 100, 1, '⚙️', 'common', 1)"
            )
            ended = (
                datetime.datetime.now() - datetime.timedelta(minutes=1)
            ).isoformat()
            await db.executemany(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, stars, current_bid, current_bidder, "
                "end_time, status) VALUES (?, 1, 'basic_gen', 0, 0, ?, ?, 'active')",
                [(1, None, ended), (2, 2, ended)],
            )
            await db.commit()

            original_grant = m.grant_item_or_compensation

            async def grant_ok(*args):
                return None

            async def grant_fail(*args):
                raise RuntimeError("grant fail")

            m.grant_item_or_compensation = grant_ok
            try:
                await _run_once(m.bot.auction_closer)
            finally:
                m.grant_item_or_compensation = original_grant

            await db.execute(
                "INSERT INTO auctions "
                "(id, seller_id, item_id, stars, current_bid, current_bidder, "
                "end_time, status) VALUES (3, 1, 'basic_gen', 0, 10, 2, ?, 'active')",
                (ended,),
            )
            await db.commit()
            m.grant_item_or_compensation = grant_fail
            try:
                await _run_once(m.bot.auction_closer)
            finally:
                m.grant_item_or_compensation = original_grant

            original_insert = m._insert_giveaway_record
            original_send = m.send_giveaway_message
            original_commit = m.commit_if_needed
            original_log = m.log_admin_action

            async def insert(*args):
                return 1

            async def send(*args):
                return FakeMessage()

            async def commit_fail():
                raise RuntimeError("commit fail")

            async def log(*args, **kwargs):
                return None

            m._insert_giveaway_record = insert
            m.send_giveaway_message = send
            m.commit_if_needed = commit_fail
            m.log_admin_action = log
            try:
                ok, message = await m.create_giveaway(
                    1,
                    1,
                    SimpleNamespace(id=10),
                    "coins",
                    None,
                    1,
                    1,
                    24,
                )
                assert not ok
            finally:
                m._insert_giveaway_record = original_insert
                m.send_giveaway_message = original_send
                m.commit_if_needed = original_commit
                m.log_admin_action = original_log

            ok, message, count, total = await m.perform_bulk_sell(1, "dupes")
            assert not ok

            await db.executemany(
                "INSERT INTO raid_parties (id, leader_id, member2_id, member3_id) "
                "VALUES (1, 1, NULL, NULL)",
                (),
            )
            await db.execute(
                "INSERT INTO raid_parties (id, leader_id, member2_id, member3_id) "
                "VALUES (1, 1, NULL, NULL)"
            )
            await db.executemany(
                "INSERT INTO raid_party_invites (party_id, inviter_id, target_id) "
                "VALUES (1, 1, ?)",
                [(2,), (3,), (4,), (5,), (6,)],
            )
            await db.commit()
            interaction = await _submit(
                m.RaidInviteModal(1, 1), target_id="7"
            )
            assert interaction.followup.sent
            await db.execute("DELETE FROM raid_party_invites WHERE party_id = 1")
            await db.commit()

            class Channel:
                async def send(self, *args, **kwargs):
                    raise m.discord.HTTPException.__new__(
                        m.discord.HTTPException
                    )

            original_messageable = m.discord.abc.Messageable
            try:
                m.discord.abc.Messageable = Channel
                interaction = await _submit(
                    m.RaidInviteModal(1, 1), target_id="5"
                )
                interaction.channel = Channel()
                await m.RaidInviteModal(1, 1).on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.discord.abc.Messageable = original_messageable
        finally:
            await _close(db)

    asyncio.run(run())


async def _submit(modal, **fields):
    interaction = FakeInteraction()
    for name, value in fields.items():
        getattr(modal, name)._value = str(value)
    await modal.on_submit(interaction)
    return interaction
