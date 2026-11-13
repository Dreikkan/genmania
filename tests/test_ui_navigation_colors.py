import pathlib
import re

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"


def test_back_and_menu_buttons_are_green():
    text = BOT_PATH.read_text(encoding="utf-8")
    for label in ("Назад", "В меню"):
        for match in re.finditer(rf'label="{label}"', text):
            window = text[match.start():match.start() + 260]
            styles = re.findall(r"ButtonStyle\.(\w+)", window)
            if styles:
                assert styles[0] == "success", (
                    label,
                    styles[0],
                    text[match.start():match.start() + 120],
                )


def test_pagination_edges_are_disabled():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "genmania_nav_state_test", BOT_PATH
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)

    options = [m.discord.SelectOption(label="X", value="x")]
    view = m.ShopBuySelectView(1, options, 0, 2)
    view.apply_navigation_state()
    buttons = {
        item.callback.__name__: item
        for item in view.children
        if isinstance(item, m.discord.ui.Button)
    }
    assert buttons["prev_page"].disabled is True
    assert buttons["next_page"].disabled is False

    view.page = 1
    view.apply_navigation_state()
    assert buttons["prev_page"].disabled is False
    assert buttons["next_page"].disabled is True
