import ast
import importlib.util
import pathlib
import re
import sys

PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]+"
)
ALLOWED_LABEL_CHARS = {"★", "☆", "️"}


def kw(call, name):
    for item in call.keywords:
        if item.arg == name:
            return item.value
    return None


def is_attr(node, attr, parent_attr=None):
    if not isinstance(node, ast.Attribute) or node.attr != attr:
        return False
    if parent_attr is None:
        return True
    return isinstance(node.value, ast.Attribute) and node.value.attr == parent_attr


def is_ui_call(node, attr):
    return isinstance(node, ast.Call) and is_attr(node.func, attr, "ui")


def is_select_option(node):
    return isinstance(node, ast.Call) and (
        is_attr(node.func, "SelectOption", "ui") or is_attr(node.func, "SelectOption")
    )


def label_has_emoji(node):
    if node is None:
        return False
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        found = EMOJI_RE.findall(node.value)
        return any(ch not in ALLOWED_LABEL_CHARS for ch in found)
    if isinstance(node, ast.JoinedStr):
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found = EMOJI_RE.findall(value.value)
                if any(ch not in ALLOWED_LABEL_CHARS for ch in found):
                    return True
    return False


source = PATH.read_text(encoding="utf-8")
tree = ast.parse(source)

errors = []

# 1. Все embed'ы должны создаваться через BotEmbed.
if "discord.Embed(" in source:
    errors.append("Есть вызовы discord.Embed( — они обходят автозамену эмодзи.")
if "class BotEmbed(discord.Embed)" not in source:
    errors.append("Не найден класс BotEmbed.")

# 2. Все кнопки и SelectOption должны иметь emoji=.
entries = []
for node in ast.walk(tree):
    if is_ui_call(node, "Button"):
        entries.append(("Button", node.lineno, node))
    elif is_select_option(node):
        entries.append(("SelectOption", node.lineno, node))
    elif isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and is_attr(dec.func, "button", "ui"):
                entries.append(("DecoratedButton", dec.lineno, dec))

for kind, line, call in entries:
    emoji_node = kw(call, "emoji")
    if emoji_node is None:
        errors.append(f"{line}: {kind} без emoji=")
    elif isinstance(emoji_node, ast.Constant) and emoji_node.value is None:
        errors.append(f"{line}: {kind} с emoji=None")
    elif isinstance(emoji_node, ast.Constant) and isinstance(emoji_node.value, str):
        if EMOJI_RE.search(emoji_node.value):
            errors.append(
                f"{line}: {kind} использует юникод-эмодзи {emoji_node.value!r} вместо get_emoji()"
            )

    if label_has_emoji(kw(call, "label")):
        errors.append(f"{line}: {kind} держит эмодзи в label вместо emoji=")

# 3. Рантайм-проверка BotEmbed и замены текста.
spec = importlib.util.spec_from_file_location("gen_mania_emoji_coverage", PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

if not m.USE_CUSTOM_EMOJIS:
    errors.append("USE_CUSTOM_EMOJIS выключен.")
if set(m.BOT_BTN_EMOJIS) - set(m.ENABLED_CUSTOM_EMOJIS):
    errors.append("Есть эмодзи, которые не включены в ENABLED_CUSTOM_EMOJIS.")
if set(m.ENABLED_CUSTOM_EMOJIS) - set(m.UNICODE_EMOJIS):
    errors.append("Для части кастомных эмодзи нет Unicode-fallback.")

for unicode_emoji, key in m.EMOJI_TEXT_KEYS.items():
    custom = m.get_emoji(key)
    if not str(custom).startswith("<:"):
        errors.append(f"{unicode_emoji!r} -> {key}: get_emoji вернул не кастомный эмодзи")
    replaced = m.replace_emojis_in_text(unicode_emoji)
    if replaced != str(custom):
        errors.append(f"{unicode_emoji!r} -> {key}: замена в тексте не сработала")

embed = m.BotEmbed(title="🪙 Тест", description="💰 и 🏰")
embed.add_field(name="🏆", value="💎")
embed.set_footer(text="⚗️")
for value, label in (
    (embed.title, "title"),
    (embed.description, "description"),
    (embed.fields[0].name, "field.name"),
    (embed.fields[0].value, "field.value"),
    (embed.footer.text, "footer"),
):
    if EMOJI_RE.search(value or ""):
        errors.append(f"BotEmbed.{label}: остался юникод-эмодзи {value!r}")

if errors:
    print("EMOJI COVERAGE TEST: FAIL")
    for error in errors:
        print(f"  - {error}")
    raise SystemExit(1)

print(f"EMOJI COVERAGE TEST: OK ({len(entries)} buttons/options checked)")
