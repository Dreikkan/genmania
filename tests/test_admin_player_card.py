import importlib.util
import pathlib
import sys

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location(
    "genmania_admin_player_card_test", BOT_PATH
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_player_card_has_merged_actions():
    view = m.AdminPlayerCardView(1, 2)
    labels = {
        child.label
        for child in view.children
        if isinstance(child, m.discord.ui.Button)
    }
    assert {
        "Обновить",
        "Монеты +",
        "Монеты −",
        "Изменить",
        "Сбросить",
        "Предмет",
        "Назад",
    } <= labels


def test_player_card_modals_prefill_user_id():
    assert m.AdminGrantValuesModal(1, "coins", 2).user_id.default == "2"
    assert m.AdminTakeValuesModal(1, "coins", 2).user_id.default == "2"
    assert m.AdminEditModal(1, 2).user_id.default == "2"
    assert m.AdminResetModal(1, 2).user_id.default == "2"
    assert m.AdminGiveItemModal(1, 2).user_id.default == "2"
