"""Tests for the web game command bridge."""
from __future__ import annotations

import asyncio

from gen_mania.web_game import WebGameBridge


class FakeBot:
    def __init__(self, closed=False):
        self._closed = closed

    async def wait_until_ready(self):
        return None

    def is_closed(self):
        return self._closed


def test_bridge_disabled_without_env(monkeypatch):
    monkeypatch.delenv("DASHBOARD_SYNC_URL", raising=False)
    monkeypatch.delenv("DASHBOARD_GAME_URL", raising=False)
    monkeypatch.delenv("DASHBOARD_SYNC_TOKEN", raising=False)
    bridge = WebGameBridge(FakeBot(), handler=lambda _command: None)  # type: ignore[arg-type]
    assert bridge.enabled is False


def test_bridge_derives_urls(monkeypatch):
    monkeypatch.setenv(
        "DASHBOARD_SYNC_URL", "https://example.test/api/ingest.php"
    )
    monkeypatch.setenv("DASHBOARD_SYNC_TOKEN", "0123456789abcdef")

    async def handler(_command):
        return {"ok": True}

    bridge = WebGameBridge(FakeBot(), handler=handler)
    assert bridge.enabled is True
    assert bridge.poll_url.endswith("/api/game_poll.php")
    assert bridge.result_url.endswith("/api/game_result.php")


def test_decode():
    assert asyncio.run(WebGameBridge._decode("")) == {}
    assert asyncio.run(WebGameBridge._decode("not json")) == {}
    assert asyncio.run(WebGameBridge._decode('{"ok":true}')) == {"ok": True}


def test_execute_posts_result(monkeypatch, tmp_path):
    calls = []

    class FakeResponse:
        status = 200

        async def text(self):
            return "ok"

    class FakePost:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *_args):
            return None

    class FakeSession:
        def post(self, *_args, **_kwargs):
            calls.append((_args, _kwargs))
            return FakePost()

    async def handler(command):
        return {"ok": True, "id": command["id"]}

    bridge = WebGameBridge(FakeBot(), handler=handler)
    bridge.result_url = "https://example.test/api/game_result.php"
    command = {"id": "cmd-1", "action": "state"}
    asyncio.run(bridge._execute(FakeSession(), command, {}))  # type: ignore[arg-type]
    assert calls
    assert calls[0][1]["json"]["id"] == "cmd-1"
    assert calls[0][1]["json"]["result"]["ok"] is True

    async def broken(_command):
        raise RuntimeError("boom")

    bridge.handler = broken
    asyncio.run(bridge._execute(FakeSession(), command, {}))  # type: ignore[arg-type]
    assert calls[-1][1]["json"]["error"].startswith("RuntimeError")


def test_run_disabled():
    async def handler(_command):
        return {"ok": True}

    bridge = WebGameBridge(FakeBot())
    asyncio.run(bridge.run())
    assert bridge.enabled is False
