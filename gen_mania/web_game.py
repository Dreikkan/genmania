"""Fast command bridge for the web game tab.

The site enqueues commands in its own SQLite database. This module polls the
dashboard every few seconds, executes commands through the bot handler and
posts results back. It is separate from the slower statistics sync.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Awaitable, Callable

import aiohttp

log = logging.getLogger("gen_mania.web_game")


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


class WebGameBridge:
    def __init__(
        self,
        bot: Any,
        handler: Callable[[dict], Awaitable[dict]] | None = None,
    ):
        self.bot = bot
        self.handler = handler
        self.token = (
            os.getenv("DASHBOARD_GAME_TOKEN", "").strip()
            or os.getenv("DASHBOARD_SYNC_TOKEN", "").strip()
        )
        sync_url = os.getenv("DASHBOARD_SYNC_URL", "").strip()
        explicit = os.getenv("DASHBOARD_GAME_URL", "").strip()
        if explicit:
            self.poll_url = explicit
            self.result_url = explicit.replace("game_poll.php", "game_result.php")
        elif sync_url:
            self.poll_url = sync_url.replace("ingest.php", "game_poll.php")
            self.result_url = sync_url.replace("ingest.php", "game_result.php")
        else:
            self.poll_url = ""
            self.result_url = ""
        self.interval = _env_int("DASHBOARD_GAME_INTERVAL", 5, 2, 60)
        self.enabled = bool(
            self.poll_url and self.result_url and self.token and self.handler
        )
        if not self.enabled:
            log.info(
                "WEB_GAME: выключено (нужны DASHBOARD_SYNC_URL/TOKEN и обработчик)"
            )

    async def run(self) -> None:
        if not self.enabled:
            return
        await self.bot.wait_until_ready()
        headers = {
            "Accept": "application/json",
            "User-Agent": "GenManiaBot/1.0",
            "X-Game-Token": self.token,
        }
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while not self.bot.is_closed():
                started = time.monotonic()
                try:
                    async with session.post(
                        self.poll_url,
                        json={"limit": 10},
                        headers=headers,
                    ) as response:
                        body = await response.text()
                        if response.status != 200:
                            raise RuntimeError(
                                f"game_poll вернул {response.status}: {body[:160]}"
                            )
                        data = await self._decode(body)
                    commands = data.get("commands") if isinstance(data, dict) else None
                    if not isinstance(commands, list):
                        commands = []
                    for command in commands:
                        if not isinstance(command, dict) or not command.get("id"):
                            continue
                        await self._execute(session, command, headers)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("WEB_GAME: ошибка опроса команд")

                elapsed = time.monotonic() - started
                await asyncio.sleep(max(0.5, self.interval - elapsed))

    async def _execute(
        self,
        session: aiohttp.ClientSession,
        command: dict,
        headers: dict,
    ) -> None:
        command_id = str(command.get("id"))
        try:
            result = await self.handler(command)  # type: ignore[misc]
            error = None
        except Exception as exception:
            log.exception("WEB_GAME: команда %s упала", command_id)
            result = None
            error = f"{exception.__class__.__name__}: {exception}"

        payload = {"id": command_id, "result": result, "error": error}
        try:
            async with session.post(
                self.result_url,
                json=payload,
                headers=headers,
            ) as response:
                body = await response.text()
                if response.status != 200:
                    log.warning(
                        "WEB_GAME: game_result %s вернул %s: %s",
                        command_id,
                        response.status,
                        body[:160],
                    )
        except Exception:
            log.exception("WEB_GAME: не удалось вернуть результат %s", command_id)

    @staticmethod
    async def _decode(body: str) -> dict:
        if not body:
            return {}
        try:
            decoded = json.loads(body)
        except ValueError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
