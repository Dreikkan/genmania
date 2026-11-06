import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_last_90_push_test", BOT_PATH
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

    async def edit(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.edits.append((args, kwargs))

    async def delete(self):
        return None


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
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _close(db):
    await db.close()
    m.bot.db = None


def test_status_price_unknown():
    assert m.status_price("bad", 7) is None


def test_settings_sell_profile_and_season_callbacks():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 100)"
            )
            await db.execute(
                "INSERT INTO items (id, name, price, income_per_hour, "
                "emoji, rarity, buyable) "
                "VALUES ('epic_gen', 'Epic', 100, 1, '⚙️', 'epic', 0)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'epic_gen', 'storage', 0), "
                "(1, 1, 'basic_gen', 'storage', 0)"
            )
            await db.commit()

            original_settings = m.get_settings

            async def settings(guild_id):
                return {"disabled_commands": []}

            m.get_settings = settings
            try:
                view = m.SettingsView(1)
                interaction = FakeInteraction(1)
                await view.commands.callback(interaction)
                assert interaction.edited

                view = m.SettingsEconomyView(1)
                original_owner = m.is_global_owner

                async def owner_false(interaction):
                    return False

                m.is_global_owner = owner_false
                try:
                    interaction = FakeInteraction(1)
                    await view.price.callback(interaction)
                    assert interaction.response.messages
                    interaction = FakeInteraction(1)
                    await view.income.callback(interaction)
                    assert interaction.response.messages
                finally:
                    m.is_global_owner = original_owner
            finally:
                m.get_settings = original_settings

            view = m.SellSelectView(
                1,
                [m.discord.SelectOption(label="X", value="0:basic_gen:0")],
                0,
                1,
            )
            interaction = FakeInteraction(1, ["0:missing:0"])
            await view.item_select(interaction)
            assert interaction.followup.sent
            interaction = FakeInteraction(1, ["0:epic_gen:0"])
            await view.item_select(interaction)
            assert interaction.followup.sent

            original_claim = m.claim_season_rewards
            original_open_season = m.open_season_view

            async def claim(user_id):
                return True, "ok", (1, 2)

            async def open_season(*args):
                return None

            m.claim_season_rewards = claim
            m.open_season_view = open_season
            try:
                view = m.SeasonView(
                    1,
                    {
                        "premium": False,
                        "claimable_free": True,
                        "claimable_premium": False,
                    },
                )
                interaction = FakeInteraction(1)
                await view.btn_claim.callback(interaction)
                assert interaction.followup.sent
            finally:
                m.claim_season_rewards = original_claim
                m.open_season_view = original_open_season

            original_profile = m.build_profile_embed
            original_public = m.build_public_profile_embed

            async def profile(interaction, mode="all"):
                return m.BotEmbed(title="Profile")

            async def public(target_id, detailed=False):
                return m.BotEmbed(title="Public")

            m.build_profile_embed = profile
            m.build_public_profile_embed = public
            try:
                view = m.ProfileView(1)
                interaction = FakeInteraction(1, ["common"])
                await view.select_filter(interaction)
                assert interaction.edited

                view = m.ProfileTargetSelectView(1)
                interaction = FakeInteraction(1, ["2"])
                await view.select_target(interaction)
                assert interaction.edited
            finally:
                m.build_profile_embed = original_profile
                m.build_public_profile_embed = original_public
        finally:
            await _close(db)

    asyncio.run(run())


def test_on_ready_titles_and_raid_invite_accept():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins) VALUES (1, 1000), (2, 1000)"
            )
            await db.commit()

            original_sync = m.sync_all_guild_access

            async def sync():
                return None

            m.sync_all_guild_access = sync
            m.bot._guild_access_synced = False
            try:
                await m.on_ready()
                assert m.bot._guild_access_synced is True
                await m.on_ready()
            finally:
                m.sync_all_guild_access = original_sync
                if hasattr(m.bot, "_guild_access_synced"):
                    del m.bot._guild_access_synced

            option = m.discord.SelectOption(label="X", value="x")
            view = m.TitlesView(1, [option], 0, 2)
            assert view.total_pages == 2

            original_join = m.join_raid_party

            async def join_fail(party_id, user_id):
                raise ValueError("bad join")

            async def join_ok(party_id, user_id):
                return None

            view = m.RaidInviteView(1, 1, 2)
            view.message = FakeMessage(fail=True)
            m.join_raid_party = join_fail
            try:
                interaction = FakeInteraction(2)
                await view.accept.callback(interaction)
                assert view.resolved
            finally:
                m.join_raid_party = original_join

            view = m.RaidInviteView(1, 1, 2)
            view.message = FakeMessage(fail=True)
            m.join_raid_party = join_ok
            try:
                interaction = FakeInteraction(2)
                await view.accept.callback(interaction)
                assert view.resolved
            finally:
                m.join_raid_party = original_join
        finally:
            await _close(db)

    asyncio.run(run())
