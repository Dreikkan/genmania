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
