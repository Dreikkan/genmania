#!/usr/bin/env python3
"""Загружает кастомные эмодзи из production-кода в тестовое приложение.

Берёт пары (name, id) из BOT_BTN_EMOJIS, скачивает PNG/GIF с CDN
и создаёт application emojis у dev-бота. Токен не печатается.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import discord

from run_dev import ENV_FILE, load_env

API = "https://discord.com/api/v10"
BOT_PATH = Path(__file__).resolve().parent.parent / "bot.py"


def api(method: str, path: str, token: str, payload: dict | None = None):
    data = None
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "GenManiaDevEmoji/1.0",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        API + path, data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        return json.loads(body) if body else None


def download_emoji(partial: discord.PartialEmoji) -> tuple[bytes, str] | None:
    extension = "gif" if partial.animated else "png"
    url = f"https://cdn.discordapp.com/emojis/{partial.id}.{extension}?size=64"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "image/png")
            return response.read(), content_type
    except urllib.error.HTTPError:
        # Fallback: у статичных эмодзи GIF может не быть.
        url = f"https://cdn.discordapp.com/emojis/{partial.id}.png?size=64"
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.read(), "image/png"
        except urllib.error.HTTPError:
            return None


def load_button_emojis() -> dict[str, discord.PartialEmoji]:
    spec = importlib.util.spec_from_file_location("gen_mania_emoji_source", BOT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result: dict[str, discord.PartialEmoji] = {}
    for value in module.BOT_BTN_EMOJIS.values():
        if isinstance(value, discord.PartialEmoji) and value.name and value.id:
            result.setdefault(value.name, value)
    return result


def main() -> int:
    load_env(ENV_FILE)
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        print("❌ Нет токена.")
        return 2

    try:
        me = api("GET", "/users/@me", token)
        app_id = me["id"]
        existing_raw = api("GET", f"/applications/{app_id}/emojis", token)
        if isinstance(existing_raw, dict):
            existing = existing_raw.get("items", [])
        else:
            existing = existing_raw or []
        existing_names = {
            emoji["name"] for emoji in existing if isinstance(emoji, dict)
        }
        print(f"✅ Приложение {app_id}: уже есть {len(existing_names)} эмодзи.")

        source = load_button_emojis()
        print(f"✅ В коде найдено {len(source)} уникальных имён.")

        uploaded = 0
        skipped = 0
        failed = 0
        for name, partial in sorted(source.items()):
            if name in existing_names:
                skipped += 1
                continue
            downloaded = download_emoji(partial)
            if downloaded is None:
                print(f"⚠️  Не удалось скачать {name} ({partial.id})")
                failed += 1
                continue
            image_bytes, content_type = downloaded
            if content_type not in ("image/png", "image/gif"):
                content_type = "image/png"
            encoded = base64.b64encode(image_bytes).decode("ascii")
            payload = {
                "name": name,
                "image": f"data:{content_type};base64,{encoded}",
            }
            try:
                api("POST", f"/applications/{app_id}/emojis", token, payload)
                uploaded += 1
                print(f"✅ {name}")
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    retry_after = 2.0
                    try:
                        body = json.loads(exc.read())
                        retry_after = float(body.get("retry_after", retry_after))
                    except Exception:
                        pass
                    print(f"⏳ rate limit, ждём {retry_after:.1f}с")
                    time.sleep(retry_after)
                    try:
                        api("POST", f"/applications/{app_id}/emojis", token, payload)
                        uploaded += 1
                        print(f"✅ {name} (после retry)")
                    except Exception as retry_exc:
                        print(f"❌ {name}: {retry_exc}")
                        failed += 1
                else:
                    print(f"❌ {name}: HTTP {exc.code}")
                    failed += 1
            time.sleep(0.25)

        print(
            f"\nИтого: загружено {uploaded}, уже было {skipped}, "
            f"ошибок {failed}."
        )
        return 0 if failed == 0 else 1
    except urllib.error.HTTPError as exc:
        print(f"❌ Discord API: HTTP {exc.code}")
        return 1
    except Exception as exc:  # noqa: BLE001 - диагностический скрипт
        print(f"❌ Ошибка: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
