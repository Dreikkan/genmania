import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_ui_polish_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


def test_admin_panel_split():
    token = m._CURRENT_IS_BOT_OWNER.set(False)
    try:
        local = m.AdminPanelView(1)
        labels = {
            item.label
            for item in local.children
            if isinstance(item, m.discord.ui.Button)
        }
        assert "Владелец" not in labels
        assert "Добавить генератор" not in labels
        assert "Бэкап" not in labels
    finally:
        m._CURRENT_IS_BOT_OWNER.reset(token)

    token = m._CURRENT_IS_BOT_OWNER.set(True)
    try:
        owner = m.AdminPanelView(1)
        labels = {
            item.label
            for item in owner.children
            if isinstance(item, m.discord.ui.Button)
        }
        assert "Владелец" in labels
    finally:
        m._CURRENT_IS_BOT_OWNER.reset(token)


def test_onboarding_button_removed_after_completion():
    m.bot._onboarding_complete_cache = {1}
    try:
        view = m.MainMenuView(1)
        labels = {
            item.label
            for item in view.children
            if isinstance(item, m.discord.ui.Button)
        }
        assert "Первые шаги" not in labels
    finally:
        m.bot._onboarding_complete_cache.clear()


def test_clan_capacity_enforced():
    async def run():
        db = await _init()
        try:
            await db.execute(
                "INSERT INTO clans (id, name, leader_id, capacity) "
                "VALUES (1, 'Alpha', 1, 10)"
            )
            for uid in range(1, 11):
                await db.execute(
                    "INSERT INTO clan_members (user_id, clan_id, role) "
                    "VALUES (?, 1, 'member')",
                    (uid,),
                )
            await db.execute("INSERT INTO players (user_id) VALUES (11)")
            await db.commit()

            ok, message = await m.apply_to_clan(11, 1)
            assert ok is False and "заполнен" in message.lower(), message
            await db.execute("UPDATE clans SET capacity = 15 WHERE id = 1")
            await db.commit()
            ok, message = await m.apply_to_clan(11, 1)
            assert ok is True, message
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_local_top_scope_filters_members():
    async def run():
        db = await _init()
        try:
            await db.execute("INSERT INTO players (user_id, coins) VALUES (1, 100), (2, 50)")
            await db.commit()

            class FakeGuild:
                members = [SimpleNamespace(id=1)]

            original_get_guild = m.bot.get_guild
            m.bot.get_guild = lambda guild_id: FakeGuild()
            try:
                local = await m.get_top_players("coins", 10, guild_id=1)
                global_rows = await m.get_top_players("coins", 10, guild_id=None)
            finally:
                m.bot.get_guild = original_get_guild

            assert [row[0] for row in local] == [1], local
            assert len(global_rows) == 2, global_rows
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())
