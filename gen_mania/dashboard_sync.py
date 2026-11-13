"""Push aggregated Gen Mania statistics to the web dashboard.

The bot stays the source of truth: this module only reads ``castle.db`` and
Discord caches, builds a small JSON snapshot and sends it to
``DASHBOARD_SYNC_URL`` with a shared token. No player data is exposed
publicly and no dashboard request can modify the bot.

Environment variables:

``DASHBOARD_SYNC_URL``
    Full ingest endpoint, for example ``https://genmania.tech/api/ingest.php``.
``DASHBOARD_SYNC_TOKEN``
    Shared secret. Must match ``ingest_token`` in the dashboard ``config.php``.
``DASHBOARD_SYNC_INTERVAL``
    Seconds between snapshots. Default 300, minimum 60.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import math
import os
import socket
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiohttp
import discord

from .config import BACKUP_INTERVAL_HOURS, UTC
from .metrics import METRICS

log = logging.getLogger("gen_mania.dashboard")

TOP_PLAYERS_LIMIT = 200
TOP_SERVERS_LIMIT = 12
TOP_CLANS_LIMIT = 5
HISTORY_DAYS = 30


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        log.warning("DASHBOARD_SYNC: %s=%r не число, использую %s", name, raw, default)
        return default
    return max(minimum, min(maximum, value))


def _iso(value: Any) -> str:
    """Приводит SQLite/date/datetime к ISO 8601 UTC."""
    if value is None or value == "":
        return ""
    if isinstance(value, dt.datetime):
        current = value
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current.astimezone(UTC).isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return ""
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _percent(current: int | float, previous: int | float) -> float:
    if not previous:
        return 0.0
    return round((current - previous) / previous * 100.0, 1)


class DashboardSync:
    """Collects aggregates and posts them to the dashboard ingest endpoint."""

    def __init__(
        self,
        bot: Any,
        apply_settings: Callable[[dict], Awaitable[dict]] | None = None,
    ):
        self.bot = bot
        self.apply_settings = apply_settings
        self.url = os.getenv("DASHBOARD_SYNC_URL", "").strip()
        self.token = os.getenv("DASHBOARD_SYNC_TOKEN", "").strip()
        self.interval = _env_int("DASHBOARD_SYNC_INTERVAL", 300, 60, 3600)
        self.enabled = bool(self.url and self.token and len(self.token) >= 16)
        self.data_dir = Path(
            str(
                getattr(bot, "data_dir", None)
                or os.getenv("DATA_DIR", "/app/data")
            )
        )
        self.history_path = self.data_dir / "dashboard_history.json"
        self.applied_revision_path = (
            self.data_dir / "dashboard_settings_revision.txt"
        )
        try:
            self._applied_settings_revision = self.applied_revision_path.read_text(
                encoding="utf-8"
            ).strip()
        except OSError:
            self._applied_settings_revision = ""
        self._last_success: dt.datetime | None = None
        self._last_error: dt.datetime | None = None

        if not self.url or not self.token:
            log.info(
                "DASHBOARD_SYNC: выключено (нужны DASHBOARD_SYNC_URL и "
                "DASHBOARD_SYNC_TOKEN)"
            )
        elif len(self.token) < 16:
            log.warning("DASHBOARD_SYNC: токен слишком короткий, выключено")
        elif self.url.startswith("http://") and "localhost" not in self.url:
            log.warning("DASHBOARD_SYNC: используется HTTP вместо HTTPS")

    async def run(self) -> None:
        if not self.enabled:
            return

        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            started = time.monotonic()
            try:
                payload = await self.collect()
                response = await self.push(payload)
                await self._apply_pending_settings(response)
                self._last_success = dt.datetime.now(UTC)
                log.info(
                    "DASHBOARD_SYNC: отправлено (players=%s, guilds=%s)",
                    payload["stats"].get("players"),
                    payload["stats"].get("servers"),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                self._last_error = dt.datetime.now(UTC)
                log.exception("DASHBOARD_SYNC: не удалось отправить статистику")

            elapsed = time.monotonic() - started
            await asyncio.sleep(max(10.0, self.interval - elapsed))

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _fetchone(self, sql: str, params: tuple = ()) -> Any:
        db = getattr(self.bot, "db", None)
        if db is None:
            return None
        try:
            async with db.execute(sql, params) as cursor:
                return await cursor.fetchone()
        except Exception:
            log.debug("DASHBOARD_SYNC: SQL не выполнен: %s", sql[:120], exc_info=True)
            return None

    async def _fetchall(self, sql: str, params: tuple = ()) -> list[Any]:
        db = getattr(self.bot, "db", None)
        if db is None:
            return []
        try:
            async with db.execute(sql, params) as cursor:
                return list(await cursor.fetchall())
        except Exception:
            log.debug("DASHBOARD_SYNC: SQL не выполнен: %s", sql[:120], exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    async def collect(self) -> dict:
        member_map = self._member_map()
        active_ids = await self._active_player_ids()
        stats = await self._collect_stats(member_map)
        players = await self._collect_players(member_map, active_ids)
        servers = await self._collect_guilds(active_ids)
        market, market_volume = await self._collect_market()
        stats["market_volume"] = market_volume
        stats["online"] = len(active_ids)
        stats["online_label"] = "Активны за час"
        stats["servers"] = len(getattr(self.bot, "guilds", []) or [])

        history = self._record_history(stats)
        activity, weekly, growth = self._history_series(history)
        stats["growth"] = growth
        stats["health"] = self._health(stats)

        transactions = await self._collect_transactions(member_map)
        logs = await self._collect_logs(member_map)
        if not logs:
            logs = [
                {
                    "id": "sync-1",
                    "type": "system",
                    "severity": "info",
                    "actor": "system",
                    "action": "Синхронизация с панелью",
                    "target": "dashboard",
                    "details": "статистика обновлена",
                    "at": dt.datetime.now(UTC).isoformat(),
                }
            ]

        economy = await self._collect_economy(stats, weekly)

        return {
            "generated_at": dt.datetime.now(UTC).isoformat(),
            "applied_settings_revision": self._applied_settings_revision,
            "stats": stats,
            "activity": activity,
            "top_players": players[:8],
            "players": players,
            "servers": servers,
            "top_clans": await self._collect_clans(),
            "transactions": transactions,
            "market": market,
            "logs": logs,
            "economy": economy,
            "settings": await self._collect_settings(),
        }

    def _member_map(self) -> dict[int, Any]:
        members: dict[int, Any] = {}
        for guild in getattr(self.bot, "guilds", []) or []:
            try:
                for member in guild.members:
                    members.setdefault(member.id, member)
            except Exception:
                log.debug("DASHBOARD_SYNC: не удалось прочитать guild.members")
        return members

    async def _active_player_ids(self) -> set[int]:
        rows = await self._fetchall(
            "SELECT user_id FROM players "
            "WHERE last_collected >= datetime('now', '-1 hour') "
            "OR last_gem_collected >= datetime('now', '-1 hour') "
            "LIMIT 20000"
        )
        return {
            int(row[0])
            for row in rows
            if row and row[0] is not None
        }

    def _display_name(self, user_id: int, member_map: dict[int, Any]) -> tuple[str, str]:
        member = member_map.get(user_id)
        if member is not None:
            name = getattr(member, "display_name", None) or member.name
            return str(name), str(member.name)
        user = self.bot.get_user(user_id) if hasattr(self.bot, "get_user") else None
        if user is not None:
            name = getattr(user, "global_name", None) or user.name
            return str(name), str(user.name)
        return f"Игрок {user_id}", str(user_id)

    async def _collect_stats(self, member_map: dict[int, Any]) -> dict:
        row = await self._fetchone(
            "SELECT COUNT(*), COALESCE(SUM(coins), 0), "
            "COALESCE(SUM(gems), 0) FROM players"
        )
        if row is None:
            raise RuntimeError("DASHBOARD_SYNC: не удалось прочитать players")
        players = int(row[0] or 0)
        coins = int(row[1] or 0) if row else 0
        gems = int(row[2] or 0) if row else 0

        production_row = await self._fetchone(
            "SELECT COALESCE(SUM(lifetime_production), 0) FROM players"
        )
        production = int(production_row[0] or 0) if production_row else 0

        generators_row = await self._fetchone(
            "SELECT COUNT(*) FROM inventory WHERE location = 'profile'"
        )
        generators = int(generators_row[0] or 0) if generators_row else 0

        clans_row = await self._fetchone("SELECT COUNT(*) FROM clans")
        clans = int(clans_row[0] or 0) if clans_row else 0

        new_players_row = await self._fetchone(
            "SELECT COUNT(DISTINCT user_id) FROM onboarding_progress "
            "WHERE step = 'buy_generator' AND date(completed_at) = date('now')"
        )
        new_players = int(new_players_row[0] or 0) if new_players_row else 0

        transactions_row = await self._fetchone(
            "SELECT COUNT(*) FROM market_orders "
            "WHERE status = 'filled' AND date(created_at) = date('now')"
        )
        transactions_today = (
            int(transactions_row[0] or 0) if transactions_row else 0
        )

        tables_row = await self._fetchone(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        db_tables = int(tables_row[0] or 0) if tables_row else 0

        metrics = METRICS.snapshot()
        latency = getattr(self.bot, "latency", 0.0) or 0.0
        latency_ms = round(latency * 1000, 1) if math.isfinite(latency) else 0.0

        db_size = self._db_size()
        backup = self._latest_backup()

        return {
            "players": players,
            "servers": 0,
            "online": 0,
            "coins": coins,
            "gems": gems,
            "generators": generators,
            "uptime": 100.0,
            "latency": latency_ms,
            "version": getattr(discord, "__version__", "live"),
            "messages_today": 0,
            "commands_today": int(metrics.get("commands_total", 0) or 0),
            "new_players_today": new_players,
            "active_clans": clans,
            "transactions_today": transactions_today,
            "market_volume": 0,
            "maintenance": False,
            "last_backup": backup,
            "lifetime_production": production,
            "db_size_bytes": db_size,
            "db_tables": db_tables,
            "growth": {},
            "health": [],
        }

    async def _collect_players(self, member_map: dict[int, Any], active_ids: set[int]) -> list[dict]:
        rows = await self._fetchall(
            """
            SELECT p.user_id, p.coins, p.gems,
                   COALESCE(p.prestige_points, 0) AS prestige,
                   p.last_collected,
                   COALESCE((
                       SELECT COUNT(*) FROM inventory i
                       WHERE i.user_id = p.user_id AND i.location = 'profile'
                   ), 0) AS generators,
                   COALESCE((
                       SELECT MAX(i.stars) FROM inventory i
                       WHERE i.user_id = p.user_id AND i.location = 'profile'
                   ), 0) AS stars,
                   COALESCE((
                       SELECT SUM(i2.price * (1 + inv.stars * 0.5))
                       FROM inventory inv JOIN items i2 ON i2.id = inv.item_id
                       WHERE inv.user_id = p.user_id AND inv.location = 'profile'
                   ), 0) AS power,
                   c.name AS clan
            FROM players p
            LEFT JOIN clan_members cm ON cm.user_id = p.user_id
            LEFT JOIN clans c ON c.id = cm.clan_id
            WHERE COALESCE(p.top_excluded, 0) = 0
            ORDER BY p.coins DESC
            LIMIT ?
            """,
            (TOP_PLAYERS_LIMIT,),
        )

        result: list[dict] = []
        for row in rows:
            user_id = int(row[0])
            name, handle = self._display_name(user_id, member_map)
            member = member_map.get(user_id)
            status = "online" if user_id in active_ids else "offline"
            joined = ""
            if member is not None:
                joined_at = getattr(member, "joined_at", None)
                if joined_at is not None:
                    joined = joined_at.date().isoformat()

            result.append(
                {
                    "id": f"u-{user_id}",
                    "discord_id": str(user_id),
                    "name": name,
                    "handle": handle,
                    "clan": str(row[8] or "Без клана"),
                    "level": int(row[3] or 0),
                    "coins": int(row[1] or 0),
                    "gems": int(row[2] or 0),
                    "generators": int(row[5] or 0),
                    "stars": int(row[6] or 0),
                    "power": int(row[7] or 0),
                    "status": status,
                    "joined": joined,
                    "last_seen": _iso(row[4]),
                }
            )
        return result

    async def _collect_guilds(self, active_ids: set[int]) -> list[dict]:
        guilds = sorted(
            getattr(self.bot, "guilds", []) or [],
            key=lambda guild: getattr(guild, "member_count", 0) or len(guild.members),
            reverse=True,
        )[:TOP_SERVERS_LIMIT]

        result: list[dict] = []
        for guild in guilds:
            try:
                online = sum(1 for member in guild.members if member.id in active_ids)
            except Exception:
                online = 0
            members = getattr(guild, "member_count", None) or len(guild.members)
            owner = getattr(guild, "owner", None)
            me = getattr(guild, "me", None)
            joined = ""
            if me is not None and getattr(me, "joined_at", None) is not None:
                joined = me.joined_at.date().isoformat()
            features = set(getattr(guild, "features", set()) or set())
            activity = [
                max(0, int(online * (0.72 + 0.28 * math.sin(index / 1.7))))
                for index in range(12)
            ]
            result.append(
                {
                    "id": str(guild.id),
                    "name": str(guild.name),
                    "owner": str(getattr(owner, "display_name", "—") or "—"),
                    "members": int(members),
                    "online": int(online),
                    "plan": "Community" if "COMMUNITY" in features else "Discord",
                    "status": "online",
                    "region": str(getattr(guild, "preferred_locale", "—") or "—"),
                    "boosts": int(getattr(guild, "premium_subscription_count", 0) or 0),
                    "joined": joined,
                    "activity": activity,
                }
            )
        return result

    async def _collect_clans(self) -> list[dict]:
        rows = await self._fetchall(
            """
            SELECT c.id, c.name, COALESCE(c.treasury, 0),
                   (SELECT COUNT(*) FROM clan_members cm WHERE cm.clan_id = c.id),
                   (SELECT COUNT(*) FROM clan_wars w WHERE w.winner_id = c.id)
            FROM clans c
            ORDER BY COALESCE(c.treasury, 0) DESC
            LIMIT ?
            """,
            (TOP_CLANS_LIMIT,),
        )

        result: list[dict] = []
        for clan_id, name, treasury, members, wins in rows:
            power = await self._clan_power(int(clan_id))
            result.append(
                {
                    "name": str(name),
                    "tag": str(name).strip()[:4].upper(),
                    "members": int(members or 0),
                    "power": power,
                    "treasury": int(treasury or 0),
                    "wins": int(wins or 0),
                }
            )
        return result

    async def _clan_power(self, clan_id: int) -> int:
        members_row = await self._fetchone(
            """
            SELECT COALESCE(SUM(power), 0) FROM (
                SELECT SUM(i.price * (1 + inv.stars * 0.5)) AS power
                FROM inventory inv
                JOIN items i ON i.id = inv.item_id
                JOIN clan_members cm ON cm.user_id = inv.user_id
                WHERE cm.clan_id = ? AND inv.location = 'profile'
                GROUP BY inv.user_id
            )
            """,
            (clan_id,),
        )
        clan_row = await self._fetchone(
            """
            SELECT COALESCE(SUM(i.price * (1 + ci.stars * 0.5)), 0)
            FROM clan_inventory ci
            JOIN items i ON i.id = ci.item_id
            WHERE ci.clan_id = ?
            """,
            (clan_id,),
        )
        members_power = int(members_row[0] or 0) if members_row else 0
        clan_inventory_power = int(clan_row[0] or 0) if clan_row else 0
        return members_power + clan_inventory_power

    async def _collect_market(self) -> tuple[list[dict], int]:
        rows = await self._fetchall(
            """
            SELECT mp.item_id, i.name, i.rarity, mp.current_price,
                   COALESCE(mp.demand, 0), COALESCE(mp.supply, 0)
            FROM market_prices mp
            JOIN items i ON i.id = mp.item_id
            ORDER BY mp.current_price DESC
            LIMIT 6
            """
        )
        volume_row = await self._fetchone(
            "SELECT COALESCE(SUM(price * filled), 0) FROM market_orders "
            "WHERE status = 'filled'"
        )
        market_volume = int(volume_row[0] or 0) if volume_row else 0

        result: list[dict] = []
        for item_id, name, rarity, price, demand, supply in rows:
            history_rows = await self._fetchall(
                "SELECT price FROM market_history WHERE item_id = ? "
                "ORDER BY id DESC LIMIT 2",
                (item_id,),
            )
            values = [int(row[0] or 0) for row in history_rows]
            change = 0.0
            if len(values) == 2 and values[1]:
                change = round((values[0] - values[1]) / values[1] * 100.0, 1)
            result.append(
                {
                    "name": str(name),
                    "tier": str(rarity or "common"),
                    "price": int(price or 0),
                    "change": change,
                    "volume": int(demand + supply),
                    "icon": "box",
                }
            )
        return result, market_volume

    async def _collect_transactions(self, member_map: dict[int, Any]) -> list[dict]:
        rows = await self._fetchall(
            """
            SELECT mo.id, mo.user_id, mo.side, mo.item_id, i.name,
                   mo.price, mo.filled, mo.created_at
            FROM market_orders mo
            LEFT JOIN items i ON i.id = mo.item_id
            WHERE mo.status = 'filled'
            ORDER BY mo.id DESC
            LIMIT 8
            """
        )
        result: list[dict] = []
        for order_id, user_id, side, item_id, item_name, price, filled, created in rows:
            name, _handle = self._display_name(int(user_id), member_map)
            amount = int(price or 0) * int(filled or 0)
            result.append(
                {
                    "id": f"tx-{order_id}",
                    "type": str(side or "buy"),
                    "player": name,
                    "item": str(item_name or item_id),
                    "amount": -amount if side == "buy" else amount,
                    "currency": "coins",
                    "at": _iso(created),
                }
            )
        return result

    async def _collect_logs(self, member_map: dict[int, Any]) -> list[dict]:
        rows = await self._fetchall(
            "SELECT id, admin_id, target_id, action, details, timestamp "
            "FROM admin_log ORDER BY id DESC LIMIT 10"
        )
        result: list[dict] = []
        for log_id, admin_id, target_id, action, details, timestamp in rows:
            actor, _ = self._display_name(int(admin_id or 0), member_map)
            target, _ = self._display_name(int(target_id or 0), member_map)
            action_text = str(action or "Действие")
            lowered = action_text.lower()
            if "grant" in lowered or "выда" in lowered or "начис" in lowered:
                kind = "grant"
                severity = "success"
            elif "reset" in lowered or "сброс" in lowered:
                kind = "moderation"
                severity = "warning"
            elif "backup" in lowered or "бэкап" in lowered:
                kind = "backup"
                severity = "success"
            else:
                kind = "settings"
                severity = "info"
            result.append(
                {
                    "id": f"log-{log_id}",
                    "type": kind,
                    "severity": severity,
                    "actor": actor,
                    "action": action_text,
                    "target": target if target_id else "—",
                    "details": str(details or ""),
                    "at": _iso(timestamp),
                }
            )
        return result

    async def _collect_settings(self) -> dict:
        guilds = sorted(
            getattr(self.bot, "guilds", []) or [],
            key=lambda guild: getattr(guild, "member_count", 0) or len(guild.members),
            reverse=True,
        )
        primary = guilds[0] if guilds else None
        if primary is not None:
            row = await self._fetchone(
                "SELECT start_coins, currency_coins, currency_gems, tax_rate, "
                "admin_role_id FROM guild_settings WHERE guild_id = ?",
                (int(primary.id),),
            )
        else:
            row = await self._fetchone(
                "SELECT start_coins, currency_coins, currency_gems, tax_rate, "
                "admin_role_id FROM guild_settings ORDER BY guild_id LIMIT 1"
            )
        start_coins, currency_coins, currency_gems, tax_rate, admin_role_id = (
            row if row else (8, "монеты", "гемы", 0.02, None)
        )
        hours = int(BACKUP_INTERVAL_HOURS)
        if BACKUP_INTERVAL_HOURS == 1:
            interval_text = "1 час"
        elif hours in (6, 12):
            interval_text = f"{hours} часов"
        elif BACKUP_INTERVAL_HOURS == 24:
            interval_text = "24 часа"
        else:
            interval_text = "24 часа"
        return {
            "guild_id": int(primary.id) if primary is not None else 0,
            "guild_name": str(primary.name) if primary is not None else "—",
            "start_coins": int(start_coins or 8),
            "currency_name": str(currency_coins or "монеты"),
            "premium_name": str(currency_gems or "гемы"),
            "tax_rate": round(float(tax_rate or 0.02) * 100.0, 1),
            "admin_role": str(admin_role_id or "Администратор"),
            "welcome_channel": "#welcome",
            "public_stats": True,
            "weekly_report": True,
            "maintenance": False,
            "max_grid": 10,
            "backup_interval": interval_text,
        }

    async def _collect_economy(self, stats: dict, weekly: dict) -> dict:
        deposits_row = await self._fetchone(
            "SELECT COALESCE(SUM(amount), 0) FROM bank_deposits"
        )
        loans_row = await self._fetchone(
            "SELECT COALESCE(SUM(amount), 0) FROM bank_loans "
            "WHERE COALESCE(status, 'active') = 'active'"
        )
        taxes_row = await self._fetchone(
            "SELECT COALESCE(SUM(amount), 0) FROM tax_log"
        )

        generators = max(0, int(stats.get("lifetime_production", 0) or 0))
        market = max(0, int(stats.get("market_volume", 0) or 0))
        bank = max(0, int(deposits_row[0] or 0) if deposits_row else 0) + max(
            0, int(loans_row[0] or 0) if loans_row else 0
        )
        taxes = max(0, int(taxes_row[0] or 0) if taxes_row else 0)
        total = generators + market + bank + taxes
        if total <= 0:
            split = [
                {"label": "Генераторы", "value": 100, "color": "#f5c445"},
                {"label": "Биржа", "value": 0, "color": "#00e5ff"},
                {"label": "Банк", "value": 0, "color": "#a78bfa"},
                {"label": "Налоги", "value": 0, "color": "#35e08b"},
            ]
        else:
            raw = [generators, market, bank, taxes]
            values = [round(value / total * 100) for value in raw]
            values[-1] = max(0, 100 - sum(values[:-1]))
            split = [
                {"label": "Генераторы", "value": values[0], "color": "#f5c445"},
                {"label": "Биржа", "value": values[1], "color": "#00e5ff"},
                {"label": "Банк", "value": values[2], "color": "#a78bfa"},
                {"label": "Налоги", "value": values[3], "color": "#35e08b"},
            ]

        return {"split": split, "weekly": weekly}

    # ------------------------------------------------------------------
    # History / growth
    # ------------------------------------------------------------------

    def _history_entry(self, stats: dict) -> dict:
        today = dt.datetime.now(UTC).date().isoformat()
        return {
            "date": today,
            "players": int(stats.get("players", 0) or 0),
            "servers": int(stats.get("servers", 0) or 0),
            "online": int(stats.get("online", 0) or 0),
            "coins": int(stats.get("coins", 0) or 0),
            "gems": int(stats.get("gems", 0) or 0),
            "generators": int(stats.get("generators", 0) or 0),
            "production": int(stats.get("lifetime_production", 0) or 0),
            "market_volume": int(stats.get("market_volume", 0) or 0),
        }

    def _read_history(self) -> list[dict]:
        try:
            raw = self.history_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            days = data.get("days", []) if isinstance(data, dict) else []
            return [entry for entry in days if isinstance(entry, dict) and entry.get("date")]
        except (OSError, ValueError):
            return []

    def _record_history(self, stats: dict) -> list[dict]:
        days = self._read_history()
        today = self._history_entry(stats)
        days = [entry for entry in days if entry.get("date") != today["date"]]
        days.append(today)
        days.sort(key=lambda entry: str(entry.get("date", "")))
        days = days[-HISTORY_DAYS:]
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.history_path.with_suffix(".json.tmp")
            temp.write_text(
                json.dumps({"days": days}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temp, self.history_path)
        except OSError:
            log.debug("DASHBOARD_SYNC: не удалось записать историю", exc_info=True)
        return days

    def _history_series(self, days: list[dict]) -> tuple[dict, dict, dict]:
        by_date = {str(entry["date"]): entry for entry in days}
        today = dt.datetime.now(UTC).date()
        labels: list[str] = []
        earned: list[int] = []
        spent: list[int] = []
        online: list[int] = []
        previous: dict | None = None

        for offset in range(HISTORY_DAYS - 1, -1, -1):
            current_date = today - dt.timedelta(days=offset)
            key = current_date.isoformat()
            labels.append(current_date.strftime("%d.%m"))
            entry = by_date.get(key)
            if entry is None:
                entry = previous
            if entry is None:
                earned.append(0)
                spent.append(0)
                online.append(0)
                continue

            if previous is None:
                delta_production = 0
                delta_coins = 0
            else:
                delta_production = max(
                    0,
                    int(entry.get("production", 0)) - int(previous.get("production", 0)),
                )
                delta_coins = int(entry.get("coins", 0)) - int(previous.get("coins", 0))

            income = max(0, delta_production, delta_coins)
            outcome = max(0, income - delta_coins)
            earned.append(income)
            spent.append(outcome)
            online.append(int(entry.get("online", 0) or 0))
            previous = entry

        weekly = {
            "labels": labels[-7:],
            "values": earned[-7:],
        }
        return (
            {
                "labels": labels,
                "coins_earned": earned,
                "coins_spent": spent,
                "online": online,
            },
            weekly,
            self._growth(days),
        )

    def _growth(self, days: list[dict]) -> dict:
        if not days:
            return {
                "players": 0.0,
                "servers": 0.0,
                "coins": 0.0,
                "gems": 0.0,
                "generators": 0.0,
            }
        current = days[-1]
        target_date = dt.datetime.now(UTC).date() - dt.timedelta(days=7)
        old = days[0]
        for entry in days:
            if str(entry.get("date", "")) <= target_date.isoformat():
                old = entry
        return {
            "players": _percent(int(current.get("players", 0)), int(old.get("players", 0))),
            "servers": _percent(int(current.get("servers", 0)), int(old.get("servers", 0))),
            "coins": _percent(int(current.get("coins", 0)), int(old.get("coins", 0))),
            "gems": _percent(int(current.get("gems", 0)), int(old.get("gems", 0))),
            "generators": _percent(
                int(current.get("generators", 0)), int(old.get("generators", 0))
            ),
        }

    # ------------------------------------------------------------------
    # Health / files
    # ------------------------------------------------------------------

    def _db_size(self) -> int:
        db_path = getattr(self.bot, "db_path", None)
        if not db_path:
            return 0
        total = 0
        for suffix in ("", "-wal", "-shm"):
            path = Path(f"{db_path}{suffix}")
            try:
                if path.exists():
                    total += path.stat().st_size
            except OSError:
                pass
        return total

    def _latest_backup(self) -> str:
        backup_dir = getattr(self.bot, "backup_dir", None) or (
            self.data_dir / "backups"
        )
        try:
            files = sorted(
                Path(backup_dir).glob("castle_*.db"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return ""
        if not files:
            return ""
        return dt.datetime.fromtimestamp(files[0].stat().st_mtime, UTC).isoformat()

    def _health(self, stats: dict) -> list[dict]:
        latency = stats.get("latency", 0)
        db_size = int(stats.get("db_size_bytes", 0) or 0)
        tasks = getattr(self.bot, "background_tasks", []) or []
        alive = sum(1 for task in tasks if not task.done())
        sync_text = (
            self._last_success.strftime("%H:%M:%S UTC")
            if self._last_success
            else "ожидает"
        )
        return [
            {
                "name": "Discord Gateway",
                "status": "ok",
                "value": f"{latency} ms",
            },
            {
                "name": "База данных",
                "status": "ok",
                "value": f"WAL · {round(db_size / 1024 / 1024, 1)} МБ",
            },
            {
                "name": "Планировщик",
                "status": "ok",
                "value": f"{alive} задач",
            },
            {
                "name": "Синхронизация",
                "status": "ok",
                "value": sync_text,
            },
        ]

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def push(self, payload: dict) -> dict:
        headers = {
            "Accept": "application/json",
            "User-Agent": "GenManiaBot/1.0",
            "X-Ingest-Token": self.token,
        }
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
        connector = aiohttp.TCPConnector(family=socket.AF_INET)
        async with aiohttp.ClientSession(
            timeout=timeout, connector=connector
        ) as session:
            async with session.post(
                self.url, json=payload, headers=headers
            ) as response:
                body = await response.text()
                if response.status != 200:
                    raise RuntimeError(
                        f"ingest вернул {response.status}: {body[:200]}"
                    )
                if not body:
                    return {}
                try:
                    decoded = json.loads(body)
                except ValueError:
                    return {}
                return decoded if isinstance(decoded, dict) else {}

    async def _apply_pending_settings(self, response: dict) -> None:
        if not self.apply_settings or not isinstance(response, dict):
            return
        update = response.get("settings_update")
        if not isinstance(update, dict) or not update.get("settings"):
            return
        revision = str(update.get("revision", "")).strip()
        try:
            result = await self.apply_settings(update)
        except Exception:
            log.exception("DASHBOARD_SETTINGS: ошибка применения")
            return
        if not isinstance(result, dict) or not result.get("ok"):
            log.warning("DASHBOARD_SETTINGS: не применены: %s", result)
            return

        if revision:
            self._applied_settings_revision = revision
            try:
                temp = self.applied_revision_path.with_suffix(".txt.tmp")
                temp.write_text(revision, encoding="utf-8")
                os.replace(temp, self.applied_revision_path)
            except OSError:
                log.debug(
                    "DASHBOARD_SETTINGS: не удалось сохранить revision",
                    exc_info=True,
                )
        log.info(
            "DASHBOARD_SETTINGS: применены %s (guild=%s)",
            result.get("applied", []),
            update.get("guild_id"),
        )
