import asyncio
import importlib.util
import inspect
import pathlib
import sys
from types import SimpleNamespace

import aiosqlite

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_nav_probe_test", BOT_PATH)
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

    async def edit_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeMessage:
    async def edit(self, *args, **kwargs):
        return None

    async def delete(self):
        return None


class FakeInteraction:
    def __init__(self, user_id=1):
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
        self.followup = FakeFollowup()
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


def _options():
    return [
        m.discord.SelectOption(label="1", value="1"),
        m.discord.SelectOption(label="2", value="2"),
    ]


def _value_for(name, annotation):
    text = str(annotation)
    if name == "options":
        return _options()
    if name in ("rarity", "query", "main_message", "selected_lot", "selected_order"):
        return None
    if name in ("lots", "rows", "targets", "items"):
        return []
    if name == "data":
        return {
            "premium": True,
            "level": 1,
            "xp": 0,
            "claimed_free": [],
            "claimed_premium": [],
            "claimable_free": True,
            "claimable_premium": True,
        }
    if name == "summary":
        return {}
    if name == "disabled":
        return []
    if name in ("mode", "side", "side_filter", "sort", "location", "return_to", "source"):
        return "profile"
    if name in ("filter_type", "status_id", "key"):
        return "1"
    if name == "action":
        return "promote"
    if name == "item_id":
        return "basic_gen"
    if name == "query":
        return None
    if "bool" in text:
        return True
    if "list" in text:
        return _options()
    if "dict" in text:
        return {}
    if "str" in text:
        return "1"
    return 1


def _make_view(cls):
    signature = inspect.signature(cls.__init__)
    args = []
    for parameter in signature.parameters.values():
        if parameter.name == "self":
            continue
        if parameter.default is not inspect.Parameter.empty:
            continue
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            continue
        args.append(_value_for(parameter.name, parameter.annotation))
    return cls(*args)


def _collect_views():
    views = []
    for _, cls in vars(m).items():
        if not isinstance(cls, type):
            continue
        if not issubclass(cls, m.discord.ui.View):
            continue
        if getattr(cls, "__module__", None) != spec.name:
            continue
        if cls in (m.SafeView, m.BaseView):
            continue
        try:
            views.append(_make_view(cls))
        except Exception:
            continue
    return views


async def _exercise(view):
    for other in (1, 2):
        try:
            await view.interaction_check(FakeInteraction(other))
        except Exception:
            pass
    for child in list(view.children):
        callback = getattr(child, "callback", None)
        if callback is None:
            continue
        for user_id in (1, 2):
            try:
                await callback(FakeInteraction(user_id))
            except Exception:
                pass


def test_probe_all_views_and_modals():
    async def run():
        m._DB_WRITE_LOCK = asyncio.Lock()
        m._DB_TX_OWNER = None
        db = await aiosqlite.connect(":memory:")
        m.bot.db = db
        await m.bot.init_db()
        await db.executemany(
            "INSERT INTO players (user_id, coins, gems, catalysts) VALUES (?, 1000, 100, 10)",
            [(1,), (2,), (100,), (101,)],
        )
        await db.execute(
            "INSERT INTO clans (id, name, leader_id, treasury, capacity) "
            "VALUES (1, 'Probe', 1, 100000, 10)"
        )
        await db.execute(
            "INSERT INTO clan_members (user_id, clan_id, role) VALUES (1, 1, 'leader')"
        )
        await db.commit()

        original_owner = m.is_global_owner
        original_admin = m.has_admin_access
        original_deny = m.deny_if_disabled
        original_perm = m.has_clan_permission
        original_role = m.get_clan_role
        original_get_clan = m.get_clan
        original_get_user = m.bot.get_user
        original_fetch_user = m.bot.fetch_user

        async def owner_true(interaction):
            return True

        async def owner_false(interaction):
            return False

        def admin_true(user_id):
            return True

        def admin_false(user_id):
            return False

        async def deny_false(*args, **kwargs):
            return False

        async def deny_true(*args, **kwargs):
            return True

        def perm_true(role, action):
            return True

        def perm_false(role, action):
            return False

        async def role_leader(user_id, clan_id):
            return "leader"

        async def role_none(user_id, clan_id):
            return "none"

        async def get_clan_real(user_id):
            if user_id == 1:
                return (1, "Probe", 1, 100000, 0, None, 1, 0, 10)
            return None

        async def get_clan_none(user_id):
            return None

        async def fetch_user(user_id):
            return SimpleNamespace(
                id=user_id,
                name=f"User{user_id}",
                display_name=f"User{user_id}",
                display_avatar=SimpleNamespace(url="https://example.com/a.png"),
            )

        passes = [
            (owner_true, admin_true, deny_false, perm_true, role_leader, get_clan_real),
            (owner_false, admin_false, deny_true, perm_false, role_none, get_clan_none),
        ]
        try:
            for condition_set in passes:
                (
                    owner,
                    admin,
                    deny,
                    perm,
                    role,
                    get_clan,
                ) = condition_set
                m.is_global_owner = owner
                m.has_admin_access = admin
                m.deny_if_disabled = deny
                m.has_clan_permission = perm
                m.get_clan_role = role
                m.get_clan = get_clan
                m.bot.get_user = lambda user_id: None
                m.bot.fetch_user = fetch_user
                for view in _collect_views():
                    await _exercise(view)
                    for attr, value in (
                        ("selected_lot", 1),
                        ("selected_order", 1),
                        ("selected", {"user_id": 2}),
                        ("selected_item", "basic_gen"),
                        ("selected_achievement", "ach"),
                        ("page", 1),
                    ):
                        if hasattr(view, attr):
                            old = getattr(view, attr)
                            try:
                                setattr(view, attr, value)
                                await _exercise(view)
                            except Exception:
                                pass
                            finally:
                                try:
                                    setattr(view, attr, old)
                                except Exception:
                                    pass

            for _, cls in vars(m).items():
                if not isinstance(cls, type):
                    continue
                if not issubclass(cls, m.discord.ui.Modal):
                    continue
                if getattr(cls, "__module__", None) != spec.name:
                    continue
                try:
                    modal = _make_view(cls)
                except Exception:
                    continue
                fields = [
                    child
                    for child in getattr(modal, "children", [])
                    if hasattr(child, "_value")
                ]
                for values in (
                    ["1", "ДА", "basic_gen", "👑", "999"],
                    ["0", "нет", "missing", "abc", "2"],
                ):
                    for index, field in enumerate(fields):
                        try:
                            field._value = values[index % len(values)]
                        except Exception:
                            pass
                    interaction = FakeInteraction(1)
                    try:
                        await modal.on_submit(interaction)
                    except Exception:
                        pass
        finally:
            m.is_global_owner = original_owner
            m.has_admin_access = original_admin
            m.deny_if_disabled = original_deny
            m.has_clan_permission = original_perm
            m.get_clan_role = original_role
            m.get_clan = original_get_clan
            m.bot.get_user = original_get_user
            m.bot.fetch_user = original_fetch_user
            await db.close()
            m.bot.db = None

    asyncio.run(run())
