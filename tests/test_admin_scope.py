import importlib.util
import pathlib
import sys

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("genmania_admin_scope_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_only_giveaway_views_are_available_to_local_admins():
    assert m.LocalAdminView.owner_only is False
    assert m.AdminGiveawaysView.owner_only is False
    assert m.AdminPanelView.owner_only is True
    assert m.SettingsView.owner_only is True
    assert m.AdminPlayerSelectView.owner_only is True
    assert m.AdminPlayerCardView.owner_only is True


def test_local_admin_panel_has_no_global_actions():
    view = m.LocalAdminView(1)
    labels = {
        child.label
        for child in view.children
        if isinstance(child, m.discord.ui.Button)
    }
    assert labels == {"Розыгрыши", "В меню"}
