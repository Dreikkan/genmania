import asyncio
import importlib.util
import pathlib
import sys
from types import SimpleNamespace

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_view_timeout_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class FakeMessage:
    def __init__(self):
        self.edited = None

    async def edit(self, **kwargs):
        self.edited = kwargs


class FakeResponse:
    def __init__(self):
        self.done = False
        self.sent = None

    def is_done(self):
        return self.done

    async def send_message(self, text, **kwargs):
        self.sent = (text, kwargs)
        self.done = True


def test_safe_view_timeout_edits_message():
    async def run():
        view = m.SafeView()
        view.message = FakeMessage()
        await view.on_timeout()
        assert view.message.edited is not None
        assert "устарело" in view.message.edited["content"]
        assert view.message.edited["view"] is None

    asyncio.run(run())


def test_owner_check_always_responds():
    async def run():
        view = m.BaseView(1)
        response = FakeResponse()
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=2),
            response=response,
            message=SimpleNamespace(),
        )
        allowed = await view.interaction_check(interaction)
        assert allowed is False
        assert response.sent is not None
        assert response.sent[1].get("ephemeral") is True

    asyncio.run(run())


def test_all_view_classes_are_safe():
    missing = []
    for name, obj in vars(m).items():
        if not isinstance(obj, type):
            continue
        if obj.__module__ != m.__name__:
            continue
        if issubclass(obj, m.SafeView):
            continue
        if issubclass(obj, m.discord.ui.View):
            missing.append(name)
    assert not missing, missing
