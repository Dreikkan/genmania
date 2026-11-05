import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_duel_lobby_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.done = False
        self.messages = []
        self.edited = None
        self.modal = None

    def is_done(self):
        return self.done

    async def defer(self, *args, **kwargs):
        self.done = True

    async def send_message(self, text=None, **kwargs):
        self.messages.append((text, kwargs))
        self.done = True

    async def edit_message(self, **kwargs):
        self.edited = kwargs
        self.done = True

    async def send_modal(self, modal):
        self.modal = modal
        self.done = True


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, text=None, **kwargs):
        self.messages.append((text, kwargs))


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = 1
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.edited = None

    async def edit_original_response(self, **kwargs):
        self.edited = kwargs


async def _init():
    db = await aiosqlite.connect(":memory:")
    m.bot.db = db
    await m.bot.init_db()
    return db


async def _add_power(db, user_id, price, coins):
    item_id = f"gen_{user_id}"
    await db.execute(
        "INSERT INTO items (id, name, price, income_per_hour) VALUES (?, ?, ?, 0)",
        (item_id, f"Generator {user_id}", price),
    )
    await db.execute(
        "INSERT INTO players (user_id, coins) VALUES (?, ?)",
        (user_id, coins),
    )
    await db.execute(
        "INSERT INTO inventory (user_id, slot, item_id, location) "
        "VALUES (?, 0, ?, 'profile')",
        (user_id, item_id),
    )


def test_power_duel_tolerance_is_inclusive():
    assert m.power_duel_allowed(100, 85) is True
    assert m.power_duel_allowed(100, 115) is True
    assert m.power_duel_allowed(100, 84) is False
    assert m.power_duel_allowed(100, 116) is False
    assert m.power_duel_allowed(0, 0) is False

    async def run():
        db = await _init()
        try:
            await _add_power(db, 1, 100, 1000)
            await _add_power(db, 2, 85, 1000)
            await _add_power(db, 3, 115, 1000)
            await _add_power(db, 4, 84, 1000)
            await _add_power(db, 5, 116, 1000)
            await db.commit()

            allowed, reason = await m.validate_power_duel(1, 2)
            assert allowed is True, reason
            allowed, reason = await m.validate_power_duel(1, 3)
            assert allowed is True, reason
            allowed, reason = await m.validate_power_duel(1, 4)
            assert allowed is False and "диапазоне" in reason, (allowed, reason)
            allowed, reason = await m.validate_power_duel(1, 5)
            assert allowed is False and "диапазоне" in reason, (allowed, reason)

            ok, message = await m.resolve_duel(1, 5, 100, "power")
            assert ok is False and "диапазоне" in message, message
            ok, message = await m.resolve_duel(1, 3, 100, "power")
            assert ok is True, message
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_duel_lobby_calculates_max_bet_and_presets():
    async def run():
        db = await _init()
        try:
            await _add_power(db, 1, 100, 10000)
            await _add_power(db, 2, 100, 5000)
            await db.commit()

            interaction = FakeInteraction(1)
            await m.open_duel_lobby(interaction, 1, 2)
            embed = interaction.edited["embed"]
            view = interaction.edited["view"]

            assert isinstance(view, m.DuelLobbyView)
            assert "Максимальная ставка" in embed.description
            assert "**500**" in embed.description, embed.description
            assert "доступен" in embed.description
            assert view.max_bet == 500
            assert view.btn_call.disabled is True

            view._select_bet(100)
            assert view.selected_bet == 100
            assert view.btn_call.disabled is False

            view._select_bet(10000)
            assert view.selected_bet == 500

            view._select_bet(0)
            assert view.selected_bet == 1
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_duel_lobby_blocks_power_mode_for_out_of_range_target():
    async def run():
        db = await _init()
        try:
            await _add_power(db, 1, 100, 5000)
            await _add_power(db, 2, 20, 5000)
            await db.commit()

            interaction = FakeInteraction(1)
            await m.open_duel_lobby(interaction, 1, 2)
            embed = interaction.edited["embed"]
            view = interaction.edited["view"]

            assert "недоступен" in embed.description
            assert view.can_power is False
            assert view.btn_power.disabled is True

            view._select_bet(100)
            view.mode = "power"
            blocked = FakeInteraction(1)
            await view.btn_call.callback(blocked)
            assert blocked.response.messages
            assert "Power-режим недоступен" in blocked.response.messages[0][0]
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_duel_lobby_toggles_mode():
    async def run():
        db = await _init()
        try:
            await _add_power(db, 1, 100, 5000)
            await _add_power(db, 2, 105, 5000)
            await db.commit()

            interaction = FakeInteraction(1)
            await m.open_duel_lobby(interaction, 1, 2)
            view = interaction.edited["view"]
            assert view.can_power is True
            assert view.btn_power.disabled is False
            assert view.mode == "dice"

            await view.btn_power.callback(FakeInteraction(1))
            assert view.mode == "power"
            assert view.btn_power.label == "Режим: power"

            await view.btn_power.callback(FakeInteraction(1))
            assert view.mode == "dice"
            assert view.btn_power.label == "Режим: dice"
        finally:
            await db.close()
            m.bot.db = None

    asyncio.run(run())


def test_target_board_view_states_and_user_select():
    targets = [
        {
            "user_id": 2,
            "coins": 1000,
            "power": 100,
            "raid_cd": 0,
            "shield": 0,
            "duel_cd": 0,
        },
        {
            "user_id": 3,
            "coins": 1000,
            "power": 100,
            "raid_cd": 0,
            "shield": 3600,
            "duel_cd": 0,
        },
        {
            "user_id": 4,
            "coins": 1000,
            "power": 100,
            "raid_cd": 600,
            "shield": 0,
            "duel_cd": 0,
        },
        {
            "user_id": 5,
            "coins": 1000,
            "power": 100,
            "raid_cd": 0,
            "shield": 0,
            "duel_cd": 300,
        },
    ]
    view = m.PvPTargetsView(1, targets, "raid")
    assert any(
        isinstance(child, m.discord.ui.UserSelect) for child in view.children
    )
    assert any(
        isinstance(child, m.discord.ui.Button) and child.label == "Ввести ID"
        for child in view.children
    )
    assert view.btn_attack.disabled and view.btn_duel.disabled
    assert view.btn_profile.disabled

    async def select(target_id):
        interaction = FakeInteraction(1)
        interaction.data = {"values": [str(target_id)]}
        await view.select_target(interaction)
        return interaction

    asyncio.run(select(2))
    assert view.selected["user_id"] == 2
    assert view.btn_attack.disabled is False
    assert view.btn_duel.disabled is False
    assert view.btn_profile.disabled is False

    asyncio.run(select(3))
    assert view.btn_attack.disabled is True
    assert view.btn_duel.disabled is False

    asyncio.run(select(4))
    assert view.btn_attack.disabled is True
    assert view.btn_duel.disabled is False

    asyncio.run(select(5))
    assert view.btn_attack.disabled is False
    assert view.btn_duel.disabled is True


def test_target_board_disables_actions_on_viewer_cooldowns():
    targets = [
        {
            "user_id": 2,
            "coins": 1000,
            "power": 100,
            "raid_cd": 0,
            "shield": 0,
            "duel_cd": 0,
        }
    ]
    view = m.PvPTargetsView(
        1, targets, "raid", viewer_raid_cd=600, viewer_duel_cd=300
    )
    interaction = FakeInteraction(1)
    interaction.data = {"values": ["2"]}
    asyncio.run(view.select_target(interaction))
    assert view.btn_attack.disabled is True
    assert view.btn_duel.disabled is True
    assert view.btn_profile.disabled is False


def test_battle_log_rematch_buttons_respect_cooldowns():
    view = m.BattleLogView(1, "all", None, None)
    assert view.btn_duel_rematch.disabled is True
    assert view.btn_raid_rematch.disabled is True

    ready = m.BattleLogView(1, "all", 2, 3, rematch_duel_mode="power")
    assert ready.btn_duel_rematch.disabled is False
    assert ready.btn_raid_rematch.disabled is False
    assert ready.rematch_duel_mode == "power"

    cooling = m.BattleLogView(
        1, "all", 2, 3, viewer_duel_cd=100, viewer_raid_cd=100
    )
    assert cooling.btn_duel_rematch.disabled is True
    assert cooling.btn_raid_rematch.disabled is True


def test_duel_lobby_uses_rematch_mode():
    power_view = m.DuelLobbyView(1, 2, 100, True, initial_mode="power")
    assert power_view.mode == "power"
    assert power_view.btn_power.label == "Режим: power"

    weak_view = m.DuelLobbyView(1, 2, 100, False, initial_mode="power")
    assert weak_view.mode == "dice"
    assert weak_view.btn_power.label == "Режим: dice"

    dice_view = m.DuelLobbyView(1, 2, 100, True, initial_mode="unknown")
    assert dice_view.mode == "dice"
