import importlib.util
import pathlib
import sys

from gen_mania.config import (
    CONTENT_VERSION,
    DEFAULT_START_COINS,
    SCHEMA_VERSION,
)
from gen_mania.metrics import METRICS, MetricsRegistry

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
