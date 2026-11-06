import asyncio
import datetime
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_extra_embeds_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(id=user_id, name="Tester")
        self.guild_id = 1


def test_extra_profile_embeds():
    async def run():
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        try:
            await m.bot.init_db()
            await db.execute(
                "INSERT INTO players "
                "(user_id, coins, gems, last_daily, streak_days, "
                " last_collected) "
                "VALUES (1, 100, 10, NULL, 2, ?)",
                (
                    (
                        datetime.datetime.now()
                        - datetime.timedelta(hours=3)
                    ).isoformat(),
                ),
            )
            await db.execute(
                "INSERT INTO clans (id, name, leader_id) "
                "VALUES (1, 'Alpha', 1)"
            )
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) "
                "VALUES (1, 1, 'leader')"
            )
            await db.execute(
                "INSERT INTO mailbox "
                "(user_id, item_id, quantity, stars) "
                "VALUES (1, 'basic_gen', 1, 0)"
            )
            await db.commit()
            interaction = FakeInteraction(1)

            daily = await m.build_daily_embed(interaction)
            assert "Ежедневный вход" in daily.title

            story = await m.build_story_quests_embed(interaction)
            assert "Сюжетные квесты" in story.title

            cosmetics = await m.build_cosmetics_embed(interaction)
            assert "Косметика" in cosmetics.title

            notifications = await m.build_notifications_embed(interaction)
            assert "Уведомления" in notifications.title

            onboarding = await m.build_onboarding_embed(interaction)
            assert "Первые шаги" in onboarding.title

            original_get_user = m.bot.get_user
            m.bot.get_user = lambda uid: SimpleNamespace(
                id=uid, name=f"User{uid}"
            )
            try:
                members, page, pages = await m.build_clan_members_embed(1)
            finally:
                m.bot.get_user = original_get_user
            assert "Участники клана" in members.title
            assert page == 0 and pages == 1

            mailbox, count = await m.build_mailbox_embed(1)
            assert "Почта" in mailbox.title
            assert count == 1

            original_income = m.calculate_passive_income

            async def fake_income(uid, guild_id=None):
                return 100, 5

            m.calculate_passive_income = fake_income
            try:
                welcome = await m.get_menu_welcome_notification(1, 1)
                assert welcome and "С возвращением" in welcome
            finally:
                m.calculate_passive_income = original_income
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
