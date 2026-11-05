#!/usr/bin/env python3
"""Live smoke-тест: отправляет одно сообщение в первый текстовый канал.

Использует токен из dev/.env. Токен не печатается.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from run_dev import ENV_FILE, load_env

API = "https://discord.com/api/v10"


def api(method: str, path: str, token: str, payload: dict | None = None):
    data = None
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "GenManiaDevSmoke/1.0",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        API + path, data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def main() -> int:
    load_env(ENV_FILE)
    import os

    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        print("❌ Нет токена.")
        return 2

    try:
        guilds = api("GET", "/users/@me/guilds", token)
        if not guilds:
            print("❌ Бот не состоит ни на одном сервере.")
            return 1
        guild = guilds[0]
        channels = api("GET", f"/guilds/{guild['id']}/channels", token)
        text_channels = [
            channel
            for channel in channels
            if channel.get("type") == 0 and not channel.get("nsfw", False)
        ]
        if not text_channels:
            print("❌ Нет текстовых каналов.")
            return 1
        channel = text_channels[0]
        message = api(
            "POST",
            f"/channels/{channel['id']}/messages",
            token,
            {"content": "✅ Gen Mania Dev: live-стенд подключён. Это тестовое сообщение."},
        )
        print(f"✅ Сообщение отправлено в #{channel['name']} (id={message['id']})")
    except urllib.error.HTTPError as exc:
        print(f"❌ Discord API: HTTP {exc.code}")
        return 1
    except Exception as exc:  # noqa: BLE001 - диагностический скрипт
        print(f"❌ Ошибка: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
