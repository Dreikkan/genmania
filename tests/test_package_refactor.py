import asyncio
import importlib.util
import pathlib
import sys

from gen_mania.config import (
    CONTENT_VERSION,
    DEFAULT_START_COINS,
    SCHEMA_VERSION,
)
from gen_mania.db.transaction import TransactionRuntime
from gen_mania.metrics import METRICS, MetricsRegistry
from gen_mania.repositories.clans import ClanRuntime
from gen_mania.repositories.inventory import InventoryRuntime
from gen_mania.repositories.market import MarketRuntime
from gen_mania.repositories.players import PlayerRuntime
from gen_mania.repositories.raids import RaidRuntime
from gen_mania.repositories.settings import (
    SETTING_COLUMNS as REPOSITORY_SETTING_COLUMNS,
)
from gen_mania.repositories.settings import SettingsRuntime
from gen_mania.services.auction import AuctionRuntime
from gen_mania.services.bank import BankRuntime
from gen_mania.services.clan_wars import ClanWarRuntime
from gen_mania.services.giveaways import GiveawayRuntime
from gen_mania.services.leaderboards import LeaderboardRuntime
from gen_mania.services.market import (
    SHOP_MARKET_MIN_RATIO,
    market_price_bounds,
)
from gen_mania.services.prestige import PrestigeRuntime
from gen_mania.services.progress import ProgressRuntime
from gen_mania.services.pvp import PvpRuntime
from gen_mania.services.raid_combat import RaidCombatRuntime
from gen_mania.services.taxes import TaxRuntime
from gen_mania.services.top_exclusion import TopExclusionRuntime

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "gen_mania_package_refactor_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_package_config_and_metrics_reexports():
    assert m.SCHEMA_VERSION == SCHEMA_VERSION == 17
    assert m.CONTENT_VERSION == CONTENT_VERSION == 6
    assert m.DEFAULT_START_COINS == DEFAULT_START_COINS
    assert m.MetricsRegistry is MetricsRegistry
    assert m.METRICS is METRICS


def test_services_use_shared_runtime_state():
    assert m.SETTING_COLUMNS is REPOSITORY_SETTING_COLUMNS
    assert isinstance(m.DB_RUNTIME, TransactionRuntime)
    assert isinstance(m.SETTINGS_RUNTIME, SettingsRuntime)
    assert isinstance(m.TAX_RUNTIME, TaxRuntime)
    assert isinstance(m.PLAYER_RUNTIME, PlayerRuntime)
    assert isinstance(m.INVENTORY_RUNTIME, InventoryRuntime)
    assert isinstance(m.MARKET_RUNTIME, MarketRuntime)
    assert isinstance(m.CLAN_RUNTIME, ClanRuntime)
    assert isinstance(m.RAID_RUNTIME, RaidRuntime)
    assert isinstance(m.GIVEAWAY_RUNTIME, GiveawayRuntime)
    assert isinstance(m.PROGRESS_RUNTIME, ProgressRuntime)
    assert isinstance(m.LEADERBOARD_RUNTIME, LeaderboardRuntime)
    assert isinstance(m.RAID_COMBAT_RUNTIME, RaidCombatRuntime)
    assert isinstance(m.TOP_EXCLUSION_RUNTIME, TopExclusionRuntime)
    assert isinstance(m.PRESTIGE_RUNTIME, PrestigeRuntime)
    assert isinstance(m.CLAN_WAR_RUNTIME, ClanWarRuntime)
    assert m.LEADERBOARD_RUNTIME.cache is m._top_cache
    assert isinstance(m.AUCTION_RUNTIME, AuctionRuntime)
    assert isinstance(m.BANK_RUNTIME, BankRuntime)
    assert isinstance(m.PVP_RUNTIME, PvpRuntime)
    assert m.market_price_bounds is market_price_bounds
    assert m.SHOP_MARKET_MIN_RATIO == SHOP_MARKET_MIN_RATIO
    assert m._settings_cache is m.SETTINGS_RUNTIME.settings_cache
    assert m._tax_rate_cache is m.SETTINGS_RUNTIME.tax_cache
    assert m._tax_rate_cache is m.TAX_RUNTIME.tax_cache


def test_runtime_cache_getters_follow_reassigned_globals(monkeypatch):
    new_settings_cache = {}
    new_tax_cache = {}
    monkeypatch.setattr(m, "_settings_cache", new_settings_cache)
    monkeypatch.setattr(m, "_tax_rate_cache", new_tax_cache)

    assert m.SETTINGS_RUNTIME.settings_cache is new_settings_cache
    assert m.SETTINGS_RUNTIME.tax_cache is new_tax_cache
    assert m.TAX_RUNTIME.tax_cache is new_tax_cache


def test_player_runtime_uses_current_services(monkeypatch):
    async def fake_settings(guild_id):
        return {"start_coins": 77}

    async def fake_status_bonus(user_id):
        return 0.5

    monkeypatch.setattr(m, "get_settings", fake_settings)
    monkeypatch.setattr(m, "get_status_bonus", fake_status_bonus)

    assert asyncio.run(m.PLAYER_RUNTIME.get_settings(1)) == {"start_coins": 77}
    assert asyncio.run(m.PLAYER_RUNTIME.get_status_bonus(1)) == 0.5
