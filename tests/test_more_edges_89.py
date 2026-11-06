import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_more_edges_89_test", BOT_PATH
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

    async def edit_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeMessage:
    def __init__(self, fail=False):
        self.edits = []
        self.fail = fail

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


async def _submit(modal, **fields):
    interaction = FakeInteraction()
    for name, value in fields.items():
        getattr(modal, name)._value = str(value)
    await modal.on_submit(interaction)
    return interaction


def test_raid_invite_modal_all_guards():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id) VALUES (?)",
                [(1,), (2,), (3,), (4,), (5,), (6,)],
            )
            await db.execute(
                "INSERT INTO raid_parties (id, leader_id, member2_id, member3_id) "
                "VALUES (1, 1, NULL, NULL), (2, 6, NULL, NULL)"
            )
            await db.commit()

            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="bad")
            assert interaction.followup.sent
            interaction = await _submit(m.RaidInviteModal(9, 99), target_id="2")
            assert interaction.followup.sent

            await db.execute(
                "UPDATE raid_parties SET leader_id = 2, member2_id = 1 WHERE id = 1"
            )
            await db.commit()
            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="3")
            assert interaction.followup.sent

            await db.execute(
                "UPDATE raid_parties SET leader_id = 1, member2_id = NULL WHERE id = 1"
            )
            await db.commit()
            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="1")
            assert interaction.followup.sent

            await db.execute(
                "UPDATE raid_parties SET member2_id = 2 WHERE id = 1"
            )
            await db.commit()
            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="2")
            assert interaction.followup.sent

            await db.execute(
                "UPDATE raid_parties SET member2_id = 2, member3_id = 3 WHERE id = 1"
            )
            await db.commit()
            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="4")
            assert interaction.followup.sent

            await db.execute(
                "UPDATE raid_parties SET member2_id = NULL, member3_id = NULL WHERE id = 1"
            )
            await db.commit()
            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="999")
            assert interaction.followup.sent
            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="6")
            assert interaction.followup.sent

            await db.executemany(
                "INSERT INTO raid_party_invites (party_id, inviter_id, target_id) "
                "VALUES (1, 1, ?)",
                [(2,), (3,), (4,)],
            )
            await db.commit()
            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="5")
            assert interaction.followup.sent
            await db.execute("DELETE FROM raid_party_invites WHERE party_id = 1")
            await db.commit()

            interaction = await _submit(m.RaidInviteModal(1, 1), target_id="5")
            interaction.channel = SimpleNamespace()
            await m.RaidInviteModal(1, 1).on_submit(interaction)
            assert interaction.followup.sent

            class Channel:
                def __init__(self, fail=False):
                    self.fail = fail

                async def send(self, *args, **kwargs):
                    if self.fail:
                        raise m.discord.HTTPException.__new__(
                            m.discord.HTTPException
                        )
                    return FakeMessage()

            original_messageable = m.discord.abc.Messageable
            try:
                m.discord.abc.Messageable = Channel
                interaction = await _submit(m.RaidInviteModal(1, 1), target_id="5")
                interaction.channel = Channel(fail=True)
                await m.RaidInviteModal(1, 1).on_submit(interaction)
                assert interaction.followup.sent

                interaction = await _submit(m.RaidInviteModal(1, 1), target_id="5")
                interaction.channel = Channel()
                await m.RaidInviteModal(1, 1).on_submit(interaction)
                assert interaction.followup.sent
            finally:
                m.discord.abc.Messageable = original_messageable
        finally:
            await _close(db)

    asyncio.run(run())


def test_clan_confirm_build_main_guide_and_toggle():
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
                [(1, "leader"), (2, "veteran"), (3, "member"), (4, "deputy")],
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0)"
            )
            await db.executemany(
                "INSERT INTO onboarding_progress (user_id, step) VALUES (1, ?)",
                [(step,) for step in m.ONBOARDING_STEPS],
            )
            await db.commit()

            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "promote", 1), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "promote", 4), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "kick", 1), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "kick", 99), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "transfer", 1), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(3, 1, "transfer", 2), confirm="ДА"
            )
            assert interaction.followup.sent
            interaction = await _submit(
                m.ClanTargetConfirmModal(1, 1, "promote", 2), confirm="ДА"
            )
            assert interaction.followup.sent

            m.bot._onboarding_complete_cache = None
            try:
                embed = await m.build_main_embed(FakeInteraction(1))
                assert embed.title
                assert m.bot._onboarding_complete_cache is not None
            finally:
                if hasattr(m.bot, "_onboarding_complete_cache"):
                    del m.bot._onboarding_complete_cache

            pages = m._split_guide_text("a" * 10 + "\n\n" + "b" * 10, 6)
            assert len(pages) > 1

            ok, state, message = await m.toggle_item_lock(
                1, "storage", 99, "basic_gen", 0
            )
            assert not ok and state == 0
        finally:
            await _close(db)

    asyncio.run(run())


def test_tiny_branch_calls():
    async def run():
        db = await _init()
        try:
            original_deny = m.deny_if_disabled

            async def deny_true(*args):
                return True

            m.deny_if_disabled = deny_true
            try:
                view = m.UserProfileView(1)
                interaction = FakeInteraction(1)
                await view.btn_achievements.callback(interaction)
                interaction = FakeInteraction(1)
                await view.btn_analytics.callback(interaction)
            finally:
                m.deny_if_disabled = original_deny

            async def noop(*args, **kwargs):
                return None

            view = m.SafeView()
            view.back_to_home = noop
            interaction = FakeInteraction(1)
            await view._home_callback(interaction)
        finally:
            await _close(db)

    asyncio.run(run())


def test_content_selected_empty():
    async def run():
        db = await _init()
        try:
            view = m.ContentItemsView(1, [], 0, 1)
            assert view._selected() is None
            view = m.ContentAchievementsView(1, [], 0, 1)
            assert view._selected() is None
        finally:
            await _close(db)

    asyncio.run(run())


def test_cosmetics_clan_menu_applications_and_exchange():
    async def run():
        db = await _init()
        try:
            await db.executemany(
                "INSERT INTO players (user_id, coins, gems) VALUES (?, ?, ?)",
                [(1, 1000, 100), (2, 0, 0)],
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, treasury) "
                "VALUES (1, 'Alpha', 1, 0)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader')"
            )
            await db.commit()

            original_deny = m.deny_if_disabled
            original_role = m.get_clan_role
            original_perm = m.has_clan_permission
            original_upgrades = m.build_clan_upgrades_embed
            original_cosmetics = m.build_cosmetics_embed
            original_war = m.get_active_clan_war
            original_start = m.start_clan_war
            original_build_war = m.build_clan_war_embed

            async def deny_false(*args):
                return False

            async def role(*args):
                return "leader"

            async def noop(*args, **kwargs):
                return None

            async def embed(*args):
                return m.BotEmbed(title="X")

            m.deny_if_disabled = deny_false
            m.get_clan_role = role
            m.has_clan_permission = lambda role, action: True
            m.build_clan_upgrades_embed = embed
            m.build_cosmetics_embed = embed
            m.build_clan_war_embed = embed
            try:
                view = m.CosmeticsView(1, "hub")
                interaction = FakeInteraction(1)
                await view.reset.callback(interaction)
                assert interaction.edited
                interaction = FakeInteraction(1)
                await view.back.callback(interaction)
                assert interaction.edited

                view = m.CosmeticsView(1, "main")
                view.back_to_main = noop
                interaction = FakeInteraction(1)
                await view.back.callback(interaction)

                menu = m.ClanMenuView(1, 1)
                interaction = FakeInteraction(1)
                await menu.btn_invite.callback(interaction)
                assert interaction.edited
                interaction = FakeInteraction(1)
                await menu.btn_upgrades.callback(interaction)
                assert interaction.edited

                async def no_war(clan_id):
                    return None

                m.get_active_clan_war = no_war
                interaction = FakeInteraction(1)
                await menu.btn_war.callback(interaction)
                assert interaction.followup.sent

                await db.execute(
                    "INSERT INTO clans (id, name, leader_id, treasury) "
                    "VALUES (2, 'Beta', 2, 0)"
                )
                await db.commit()

                async def start_fail(*args):
                    raise ValueError("bad war")

                m.start_clan_war = start_fail
                interaction = FakeInteraction(1)
                await menu.btn_war.callback(interaction)
                assert interaction.followup.sent

                async def start_ok(*args):
                    return 1

                async def war(clan_id):
                    return (1, 1, 2, "start", "active", 100, 100)

                m.start_clan_war = start_ok
                m.get_active_clan_war = war
                interaction = FakeInteraction(1)
                await menu.btn_war.callback(interaction)
                assert interaction.edited
            finally:
                m.deny_if_disabled = original_deny
                m.get_clan_role = original_role
                m.has_clan_permission = original_perm
                m.build_clan_upgrades_embed = original_upgrades
                m.build_cosmetics_embed = original_cosmetics
                m.get_active_clan_war = original_war
                m.start_clan_war = original_start
                m.build_clan_war_embed = original_build_war

            view = m.ClanApplicationsView(
                1,
                1,
                [m.discord.SelectOption(label="X", value="1")],
            )
            interaction = FakeInteraction(1, ["1"])
            await view.select(interaction)
            assert interaction.response.messages

            modal = m.GemsToCoinsModal(2)
            modal.amount._value = "1"
            interaction = FakeInteraction(2)
            await modal.on_submit(interaction)
            assert interaction.followup.sent
        finally:
            await _close(db)

    asyncio.run(run())


def test_star_confirm_craft_edges_and_transaction():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO players (user_id, coins, gems) VALUES (1, 1000, 1000)"
            )
            await db.execute(
                "INSERT INTO inventory (user_id, slot, item_id, location, stars) "
                "VALUES (1, 0, 'basic_gen', 'profile', 0), "
                "(1, 1, 'basic_gen', 'profile', 0), "
                "(1, 2, 'basic_gen', 'profile', 0)"
            )
            await db.commit()

            original_chance = m.get_star_chance

            async def chance(*args):
                return 1.0, 0, True

            m.get_star_chance = chance
            try:
                view = m.StarConfirmView(1, 0, "basic_gen", 1, 2, "profile")
                interaction = FakeInteraction(1)
                await view.confirm.callback(interaction)
                assert interaction.edited

                view = m.StarConfirmView(1, 10, "basic_gen", 0, 1, "profile")
                interaction = FakeInteraction(1)
                await view.confirm.callback(interaction)
                assert interaction.edited
            finally:
                m.get_star_chance = original_chance

            original_craft_chance = m.get_craft_chance
            original_place = m.place_items
            original_random = m.random.random
            original_build_profile = m.build_profile_embed
            original_quests = m.update_quest_progress
            original_story = m.update_story_quests
            original_achievements = m.check_achievements
            original_onboarding = m.complete_onboarding_step

            async def craft_chance(*args):
                return 1.0, 0, True

            async def place_fail(*args, **kwargs):
                raise ValueError("no space")

            async def noop(*args, **kwargs):
                return None

            async def profile(interaction):
                return m.BotEmbed(title="Profile")

            async def achievements(user_id):
                return []

            m.get_craft_chance = craft_chance
            m.place_items = place_fail
            m.random.random = lambda: 1.0
            m.build_profile_embed = profile
            m.update_quest_progress = noop
            m.update_story_quests = noop
            m.check_achievements = achievements
            m.complete_onboarding_step = noop
            try:
                interaction = FakeInteraction(1)
                await m.CraftConfirmView(1, "basic_gen").do_craft(interaction, False)
                assert interaction.edited
            finally:
                m.get_craft_chance = original_craft_chance
                m.place_items = original_place
                m.random.random = original_random
                m.build_profile_embed = original_build_profile
                m.update_quest_progress = original_quests
                m.update_story_quests = original_story
                m.check_achievements = original_achievements
                m.complete_onboarding_step = original_onboarding
        finally:
            await _close(db)

    asyncio.run(run())
