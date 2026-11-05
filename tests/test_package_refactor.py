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
from gen_mania.repositories.settings import (
    SETTING_COLUMNS as REPOSITORY_SETTING_COLUMNS,
)
from gen_mania.repositories.settings import SettingsRuntime
from gen_mania.services.taxes import TaxRuntime

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
