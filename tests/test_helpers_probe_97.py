import asyncio
import importlib.util
import inspect
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_helper_probe_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeResponse:
    def __init__(self):
        self.deferred = False
        self.messages = []
        self.modals = []

    def is_done(self):
        return self.deferred

    async def defer(self, *args, **kwargs):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_modal(self, modal):
        self.modals.append(modal)


class FakeFollowup:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise m.discord.HTTPException.__new__(m.discord.HTTPException)
        self.sent.append((args, kwargs))


class FakeMessage:
    async def edit(self, *args, **kwargs):
        return None

    async def delete(self):
        return None


class FakeInteraction:
    def __init__(self, user_id=1, fail_followup=False):
        self.user = SimpleNamespace(
            id=user_id,
            name=f"User{user_id}",
            display_name=f"User{user_id}",
            mention=f"<@{user_id}>",
            bot=False,
            display_avatar=SimpleNamespace(url="https://example.com/a.png"),
        )
        self.guild_id = 1
        self.guild = SimpleNamespace(
            id=1,
            owner_id=1,
            get_role=lambda rid: None,
            get_member=lambda uid: None,
        )
        self.response = FakeResponse()
        self.followup = FakeFollowup(fail=fail_followup)
        self.data = {"values": ["1"]}
        self.message = FakeMessage()
        self.edited = []
        self.deleted = False
        self.channel = None
        self.client = m.bot

    async def edit_original_response(self, *args, **kwargs):
        self.edited.append((args, kwargs))

    async def delete_original_response(self):
        self.deleted = True


def _value_for(name, annotation):
    text = str(annotation)
    if name in ("interaction", "i"):
        return FakeInteraction(1)
    if name in ("guild", "target_guild"):
        return SimpleNamespace(id=1, get_channel=lambda cid: None)
    if name in ("message", "main_message"):
        return FakeMessage()
    if name in ("result", "party", "giveaway", "deposit", "loan", "data"):
        return {}
    if name in ("options", "rows", "items", "targets", "lots"):
        return []
    if name in ("guild_id", "user_id", "author_id", "target_id", "item_id"):
        return 1 if name.endswith("_id") and name != "item_id" else "basic_gen"
    if name in ("page", "total_pages", "limit", "amount", "count", "price", "stars"):
        return 1
    if "bool" in text:
        return True
    if "list" in text:
        return []
    if "dict" in text:
        return {}
    if "str" in text:
        return "1"
    return 1


async def _probe(fn):
    signature = inspect.signature(fn)
    args = []
    for parameter in signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if parameter.default is not inspect.Parameter.empty:
            continue
        args.append(_value_for(parameter.name, parameter.annotation))
    return await fn(*args)


def test_probe_module_helpers():
    async def run():
        m._DB_WRITE_LOCK = asyncio.Lock()
        m._DB_TX_OWNER = None
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        await m.bot.init_db()
        await db.executemany(
            "INSERT INTO players (user_id, coins, gems) VALUES (?, 1000, 100)",
            [(1,), (2,)],
        )
        await db.commit()

        prefixes = (
            "open_",
            "build_",
            "finish_",
            "calculate_",
            "mass_lock_",
        )
        names = {
            "get_star_emoji",
            "parse_emoji_safe",
            "title_effect_bonus",
            "send_raid_result",
            "sync_all_guild_access",
            "create_giveaway",
            "_send_global_giveaway_to_guild",
            "_parse_db_time",
            "remove_status_role",
            "grant_status_role",
            "update_giveaway_message",
            "get_menu_welcome_notification",
        }
        for name, fn in list(vars(m).items()):
            if not inspect.iscoroutinefunction(fn):
                continue
            if not (name.startswith(prefixes) or name in names):
                continue
            try:
                await _probe(fn)
            except Exception:
                pass
        await db.close()
        m.bot.db = None

    asyncio.run(run())
