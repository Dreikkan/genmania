import asyncio
import datetime
import importlib.util
import os
import pathlib
import sys
import tempfile
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_bot_branch_flows_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.done = False
        self.messages = []
        self.modal = None

    def is_done(self):
        return self.done

    async def defer(self, *args, **kwargs):
        self.done = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_modal(self, modal):
        self.modal = modal


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeMessage:
    def __init__(self, jump_url="https://example.com/msg"):
        self.id = 1
        self.jump_url = jump_url
        self.edits = []
        self.deleted = False

    async def edit(self, *args, **kwargs):
        self.edits.append((args, kwargs))

    async def delete(self):
        self.deleted = True


class FakeInteraction:
    def __init__(self, user_id=1, values=None, channel=None):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.data = {"values": values or []}
        self.channel = channel
        self.message = FakeMessage()
        self.edited = []

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


def test_setup_hook_initializes_runtime():
    async def run():
        data_dir = tempfile.mkdtemp(
            prefix="genmania-setup-",
            dir=tempfile.gettempdir(),
        )
        old = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = data_dir
        bot = m.CastleBot()
        bot.tree.sync = AsyncNoop()
        bot.backup_database = AsyncNoop()
        bot.init_db = AsyncNoop()
        bot.load_application_emojis = AsyncNoop()
        bot.restore_giveaway_views = AsyncNoop()

        spawned = []

        def spawn(name, coro):
            spawned.append(name)
            coro.close()
            return SimpleNamespace(name=name)

        bot._spawn_background = spawn
        try:
            await bot.setup_hook()
            assert bot.data_dir == pathlib.Path(data_dir)
            assert (bot.data_dir / "backups").exists()
            assert bot.db is not None
            assert len(spawned) == 13
        finally:
            if old is None:
                os.environ.pop("DATA_DIR", None)
            else:
                os.environ["DATA_DIR"] = old
            if bot.db is not None:
                await bot.db.close()

    asyncio.run(run())


class AsyncNoop:
    def __init__(self, result=None):
        self.result = result
        self.calls = 0

    async def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.result


def test_collect_income_updates_coins_and_gems():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 0, 0)"
            )
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "income_gems_per_hour, emoji, rarity, buyable) "
                "VALUES ('gem_gen', 'Gem', 10, 1, 1, '💎', 'rare', 1)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location) "
                "VALUES (1, 0, 'basic_gen', 'profile'), "
                "(1, 1, 'gem_gen', 'profile')"
            )
            old = (
                datetime.datetime.now() - datetime.timedelta(hours=2)
            ).isoformat()
            await db.execute(
                "UPDATE players SET last_collected = ?, "
                "last_gem_collected = ? WHERE user_id = 1",
                (old, old),
            )
            await db.commit()

            coins, gems = await m.collect_income(1, None)
            assert coins > 0
            assert gems > 0
        finally:
            await _close(db)

    asyncio.run(run())


def test_create_duel_challenge_branches():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins) VALUES (?, ?)",
                [(1, 1000), (2, 1000), (3, 1)],
            )
            await db.commit()

            class Channel:
                def __init__(self):
                    self.sent = []

                async def send(self, *args, **kwargs):
                    self.sent.append((args, kwargs))
                    return FakeMessage()

            original_cd = m.get_duel_cooldown_seconds

            async def zero(user_id):
                return 0

            async def cooldown(user_id):
                return 20

            interaction = FakeInteraction(1)
            await m.create_duel_challenge(interaction, 1, 1, 10, "dice")
            assert interaction.followup.sent

            m.get_duel_cooldown_seconds = cooldown
            try:
                interaction = FakeInteraction(1)
                await m.create_duel_challenge(
                    interaction, 1, 2, 10, "dice"
                )
                assert interaction.followup.sent
            finally:
                m.get_duel_cooldown_seconds = zero

            interaction = FakeInteraction(1)
            await m.create_duel_challenge(interaction, 1, 3, 10, "dice")
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            await m.create_duel_challenge(
                interaction, 1, 2, 999, "dice"
            )
            assert interaction.followup.sent

            interaction = FakeInteraction(1)
            await m.create_duel_challenge(interaction, 1, 2, 10, "dice")
            assert interaction.followup.sent

            channel = Channel()
            interaction = FakeInteraction(1, channel=channel)
            await m.create_duel_challenge(
                interaction, 1, 2, 10, "dice"
            )
            assert channel.sent
            assert interaction.followup.sent

            m.get_duel_cooldown_seconds = original_cd
        finally:
            await _close(db)

    asyncio.run(run())


def test_create_giveaway_error_and_success_paths():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 0)"
            )
            await db.commit()
            channel = SimpleNamespace(id=10)
            original_insert = m._insert_giveaway_record
            original_send = m.send_giveaway_message
            original_log = m.log_admin_action

            async def log_noop(*args, **kwargs):
                return None

            m.log_admin_action = log_noop
            try:
                ok, message = await m.create_giveaway(
                    1, None, channel, "coins", None, 10, 1, 24
                )
                assert not ok and "сервере" in message

                ok, message = await m.create_giveaway(
                    1, 1, channel, "coins", None, "bad", 1, 24
                )
                assert not ok

                ok, message = await m.create_giveaway(
                    1, 1, channel, "coins", None, 10, 0, 24
                )
                assert not ok

                async def insert_value_error(*args, **kwargs):
                    raise ValueError("bad insert")

                m._insert_giveaway_record = insert_value_error
                ok, message = await m.create_giveaway(
                    1, 1, channel, "coins", None, 10, 1, 24
                )
                assert not ok and "bad insert" in message

                async def insert_runtime_error(*args, **kwargs):
                    raise RuntimeError("boom")

                m._insert_giveaway_record = insert_runtime_error
                ok, message = await m.create_giveaway(
                    1, 1, channel, "coins", None, 10, 1, 24
                )
                assert not ok and "Не удалось создать" in message

                async def insert_ok(*args, **kwargs):
                    return 1

                async def send_fail(*args, **kwargs):
                    raise RuntimeError("send fail")

                m._insert_giveaway_record = insert_ok
                m.send_giveaway_message = send_fail
                ok, message = await m.create_giveaway(
                    1, 1, channel, "coins", None, 10, 1, 24
                )
                assert not ok and "отправить" in message

                async def send_ok(*args, **kwargs):
                    return FakeMessage("https://example.com/1")

                m.send_giveaway_message = send_ok
                ok, message = await m.create_giveaway(
                    1, 1, channel, "coins", None, 10, 1, 24
                )
                assert ok and "Розыгрыш создан" in message
            finally:
                m._insert_giveaway_record = original_insert
                m.send_giveaway_message = original_send
                m.log_admin_action = original_log
        finally:
            await _close(db)

    asyncio.run(run())


def test_load_application_emojis_fallbacks():
    async def run():
        original_fetch = m.bot.fetch_application_emojis
        original_emojis = dict(m.BOT_BTN_EMOJIS)
        keys = list(m.BOT_BTN_EMOJIS)
        try:
            async def failing_fetch():
                raise m.discord.HTTPException.__new__(
                    m.discord.HTTPException
                )

            m.bot.fetch_application_emojis = failing_fetch
            await m.bot.load_application_emojis()

            m.BOT_BTN_EMOJIS[keys[0]] = m.discord.PartialEmoji(
                name="missing_one", id=999999
            )
            m.BOT_BTN_EMOJIS[keys[1]] = "<:missing_two:999998>"

            async def fetch():
                return [
                    SimpleNamespace(name="known", id=1),
                ]

            m.bot.fetch_application_emojis = fetch
            await m.bot.load_application_emojis()

            m.BOT_BTN_EMOJIS[keys[0]] = m.discord.PartialEmoji(
                name="known", id=1
            )
            await m.bot.load_application_emojis()
            assert m.BOT_BTN_EMOJIS[keys[0]].id == 1
        finally:
            m.bot.fetch_application_emojis = original_fetch
            m.BOT_BTN_EMOJIS.clear()
            m.BOT_BTN_EMOJIS.update(original_emojis)

    asyncio.run(run())


def test_raid_party_leave_statuses():
    async def run():
        db = await _init()
        try:
            original = m.leave_raid_party

            async def leave(user_id):
                return leave.status

            for status in ("transferred", "disbanded", "left", "gone"):
                leave.status = status
                m.leave_raid_party = leave
                view = m.RaidPartyView(1, 1)
                interaction = FakeInteraction(1)
                await view.btn_leave.callback(interaction)
                assert interaction.edited
            m.leave_raid_party = original
        finally:
            await _close(db)

    asyncio.run(run())


def test_sell_confirm_error_and_success():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 0)"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            view = m.SellConfirmView(1, 0, "basic_gen", 0, 10, 0)
            await view.confirm.callback(interaction)
            assert interaction.edited

            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'storage', 0)"
            )
            await db.commit()
            interaction = FakeInteraction(1)
            view = m.SellConfirmView(1, 0, "basic_gen", 0, 10, 0)
            await view.confirm.callback(interaction)
            assert interaction.edited
            coins = await db.execute_fetchall(
                "SELECT coins FROM players WHERE user_id = 1"
            )
            assert coins[0][0] > 0
        finally:
            await _close(db)

    asyncio.run(run())


def test_user_reset_modal_paths():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 100)"
            )
            await db.commit()

            modal = m.UserResetModal(1)
            modal.confirm._value = "no"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent

            await db.execute(
                "INSERT INTO bank_deposits (user_id, amount) VALUES (1, 10)"
            )
            await db.commit()
            modal = m.UserResetModal(1)
            modal.confirm._value = "СБРОСИТЬ"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
            await db.execute("DELETE FROM bank_deposits WHERE user_id = 1")
            await db.commit()

            original_release = m.release_active_auction_bids

            async def broken_release(user_id):
                raise RuntimeError("boom")

            m.release_active_auction_bids = broken_release
            try:
                modal = m.UserResetModal(1)
                modal.confirm._value = "СБРОСИТЬ"
                interaction = FakeInteraction(1)
                await modal.on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.release_active_auction_bids = original_release

            modal = m.UserResetModal(1)
            modal.confirm._value = "СБРОСИТЬ"
            interaction = FakeInteraction(1)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
        finally:
            await _close(db)

    asyncio.run(run())


def test_upgrades_buy_select_paths():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems, grid_size) "
                "VALUES (?, ?, ?, 9)",
                [(1, 1000, 1000), (2, 0, 0)],
            )
            await db.execute(
                "INSERT OR REPLACE INTO grid_shop (id, name, price_coins, emoji, size) "
                "VALUES ('grid_11x11', 'Grid 11', 10, '🔲', 121)"
            )
            await db.execute(
                "INSERT OR REPLACE INTO gem_shop "
                "(id, name, price_gems, emoji, category) "
                "VALUES ('vip', 'VIP', 10, '💎', 'status'), "
                "('grid_12x12', 'Gem grid', 10, '💎', 'other')"
            )
            await db.commit()

            options = [m.discord.SelectOption(label="X", value="x")]
            view = m.UpgradesBuySelectView(1, options)
            interaction = FakeInteraction(1, ["missing"])
            await view.upgrade_select(interaction)
            assert interaction.followup.sent

            view = m.UpgradesBuySelectView(1, options)
            interaction = FakeInteraction(1, ["vip"])
            await view.upgrade_select(interaction)
            assert interaction.edited

            view = m.UpgradesBuySelectView(1, options)
            interaction = FakeInteraction(1, ["grid_11x11"])
            await view.upgrade_select(interaction)
            assert any("Куплено" in str(sent) for sent in interaction.followup.sent)

            view = m.UpgradesBuySelectView(1, options)
            interaction = FakeInteraction(1, ["grid_11x11"])
            await view.upgrade_select(interaction)
            assert any("уже" in str(sent) for sent in interaction.followup.sent)

            view = m.UpgradesBuySelectView(2, options)
            interaction = FakeInteraction(2, ["grid_11x11"])
            await view.upgrade_select(interaction)
            assert any("Нужно" in str(sent) for sent in interaction.followup.sent)

            view = m.UpgradesBuySelectView(1, options)
            interaction = FakeInteraction(1, ["grid_12x12"])
            await view.upgrade_select(interaction)
            assert any("Куплено" in str(sent) for sent in interaction.followup.sent)

            original_open = m.open_upgrades_buy_select

            async def open_noop(*args, **kwargs):
                return None

            m.open_upgrades_buy_select = open_noop
            try:
                view = m.UpgradesBuySelectView(1, options, total_pages=2)
                interaction = FakeInteraction(1)
                await view.prev_page(interaction)
                interaction = FakeInteraction(1)
                await view.next_page(interaction)
                interaction = FakeInteraction(1)
                await view.back(interaction)
                assert interaction.edited
            finally:
                m.open_upgrades_buy_select = original_open
        finally:
            await _close(db)

    asyncio.run(run())


def test_swap_second_select_paths():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id) VALUES (1)"
            )
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'storage', 0)"
            )
            await db.commit()

            options = [m.discord.SelectOption(label="1", value="1")]
            view = m.SwapSecondView(1, "storage", 9, options)
            interaction = FakeInteraction(1, ["5"])
            await view.second_select(interaction)
            assert interaction.edited

            view = m.SwapSecondView(1, "storage", 0, options)
            interaction = FakeInteraction(1, ["5"])
            await view.second_select(interaction)
            assert interaction.edited
            rows = await db.execute_fetchall(
                "SELECT slot FROM inventory WHERE user_id = 1"
            )
            assert (5,) in rows

            await db.execute(
                "UPDATE inventory SET slot = 0 WHERE user_id = 1 AND slot = 5"
            )
            await db.execute(
                "INSERT INTO inventory "
                "(user_id, slot, item_id, location, stars) "
                "VALUES (1, 1, 'basic_gen', 'storage', 0)"
            )
            await db.commit()
            main = FakeMessage()
            view = m.SwapSecondView(
                1, "storage", 0, options, main_message=main
            )
            interaction = FakeInteraction(1, ["1"])
            await view.second_select(interaction)
            assert interaction.edited
            assert main.edits
        finally:
            await _close(db)

    asyncio.run(run())
