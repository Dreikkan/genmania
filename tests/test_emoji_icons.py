import importlib.util
import pathlib
import sys

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_emoji_icons_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


NEW_ICONS = {
    "_synthesis": (1567601966782218290, "synthesis"),
    "_storage": (1567601963267268708, "storage"),
    "_market": (1567601961497268304, "stockmarket"),
    "_profile": (1567601959878271197, "profile"),
    "_mail": (1567601958037094450, "mail"),
    "_history": (1567601956527280128, "history"),
    "_guide": (1567601954941575238, "guide"),
    "_espionage": (1567601953222164510, "espionage"),
    "_collection": (1567601951011643412, "collection"),
    "_generators": (1567601947886747748, "buygenerators"),
    "_bank": (1567601946322538497, "bank"),
    "_auction": (1567601944384639047, "auction"),
}


def test_new_icon_ids_and_names_are_mapped():
    for key, (emoji_id, name) in NEW_ICONS.items():
        emoji = m.BOT_BTN_EMOJIS[key]
        assert emoji.id == emoji_id, key
        assert emoji.name == name, key
        assert key in m.ENABLED_CUSTOM_EMOJIS, key
        assert str(emoji_id) in m.get_emoji(key), key


def test_custom_icon_ids_and_names_are_unique():
    ids = [
        emoji.id
        for emoji in m.BOT_BTN_EMOJIS.values()
        if getattr(emoji, "id", None)
    ]
    assert len(ids) == len(set(ids))

    names = [
        emoji.name
        for emoji in m.BOT_BTN_EMOJIS.values()
        if getattr(emoji, "name", None)
    ]
    assert len(names) == len(set(names))
