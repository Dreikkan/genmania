#!/usr/bin/env python3
"""Безопасная проверка dev-токена через Discord REST API.

Печатает только имя/id бота и список серверов. Токен не выводится.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"


def api_get(path: str, token: str):
    request = urllib.request.Request(
        API + path,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "GenManiaDevProbe/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def main() -> int:
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        print("❌ DISCORD_BOT_TOKEN не задан.")
        return 2

    try:
        me = api_get("/users/@me", token)
        print(
            f"✅ Бот: {me['username']}#{me.get('discriminator', '0')} "
            f"(id={me['id']})"
        )
        guilds = api_get("/users/@me/guilds", token)
        print(f"✅ Серверов: {len(guilds)}")
        for guild in guilds:
            print(f"   - {guild['name']} (id={guild['id']})")

        commands = api_get(f"/applications/{me['id']}/commands", token)
        print(f"✅ Глобальных slash-команд: {len(commands)}")
        for command in commands[:15]:
            print(f"   - /{command['name']}")
        if len(commands) > 15:
            print(f"   ... ещё {len(commands) - 15}")
    except urllib.error.HTTPError as exc:
        print(f"❌ Discord API: HTTP {exc.code}. Проверь токен и intents.")
        return 1
    except Exception as exc:  # noqa: BLE001 - диагностический скрипт
        print(f"❌ Ошибка проверки: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
