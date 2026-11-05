"""Raid party repository: parties, invites and cooldowns."""
from __future__ import annotations

import datetime
import logging
from typing import Any, Callable


class RaidRuntime:
    """Адаптер между bot.py и репозиторием рейдов."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._transaction_getter: Callable[[], Callable] = lambda: None
        self._commit_getter: Callable[[], Callable] = lambda: None
        self._parse_time_getter: Callable[[], Callable] = lambda: None
        self.party_ttl_minutes = 30
        self.invite_timeout = 120
        self.max_members = 3
        self.cooldown_seconds = 3600
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        transaction_getter: Callable[[], Callable],
        commit_getter: Callable[[], Callable],
        parse_time_getter: Callable[[], Callable],
        party_ttl_minutes: int,
        invite_timeout: int,
        max_members: int,
        cooldown_seconds: int,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._transaction_getter = transaction_getter
        self._commit_getter = commit_getter
        self._parse_time_getter = parse_time_getter
        self.party_ttl_minutes = party_ttl_minutes
        self.invite_timeout = invite_timeout
        self.max_members = max_members
        self.cooldown_seconds = cooldown_seconds
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    def transaction(self):
        factory = self._transaction_getter()
        return factory()

    async def commit(self) -> None:
        commit = self._commit_getter()
        if commit is not None:
            await commit()

    def parse_db_time(self, value):
        return self._parse_time_getter()(value)


def make_raid_layer(runtime: RaidRuntime):
    """Возвращает raid-функции, привязанные к runtime."""

    def party_member_ids(party) -> list[int]:
        """Достаёт участников отряда из строки raid_parties."""
        if not party:
            return []
        members = []
        for value in (party[1], party[2], party[3]):
            if value and value not in members:
                members.append(value)
        return members

    async def cleanup_expired_raid_invites():
        """Удаляет приглашения, чьи кнопки уже неактуальны."""
        cutoff = datetime.datetime.now() - datetime.timedelta(
            seconds=runtime.invite_timeout
        )
        async with runtime.db.execute(
            "SELECT id, created_at FROM raid_party_invites"
        ) as c:
            rows = await c.fetchall()

        expired = []
        for invite_id, created_at in rows:
            created = runtime.parse_db_time(created_at)
            if not created or created < cutoff:
                expired.append(invite_id)
        if not expired:
            return

        placeholders = ",".join("?" for _ in expired)
        await runtime.db.execute(
            f"DELETE FROM raid_party_invites WHERE id IN ({placeholders})",
            expired,
        )
        await runtime.commit()

    async def cleanup_expired_raid_parties():
        """Удаляет отряды без активности дольше TTL."""
        await cleanup_expired_raid_invites()
        ttl = datetime.timedelta(minutes=runtime.party_ttl_minutes)
        cutoff_local = datetime.datetime.now() - ttl
        cutoff_utc = datetime.datetime.now(datetime.timezone.utc) - ttl

        async with runtime.db.execute(
            "SELECT id, created_at, updated_at FROM raid_parties"
        ) as c:
            rows = await c.fetchall()

        expired = []
        for party_id, created_at, updated_at in rows:
            # updated_at пишем локальным временем. created_at у старых
            # строк заполняется SQLite как UTC — обрабатываем отдельно.
            last_seen = runtime.parse_db_time(updated_at)
            if last_seen is not None:
                is_expired = last_seen < cutoff_local
            else:
                created = runtime.parse_db_time(created_at)
                if created is None:
                    is_expired = True
                else:
                    is_expired = created.replace(
                        tzinfo=datetime.timezone.utc
                    ) < cutoff_utc
            if is_expired:
                expired.append(party_id)

        if not expired:
            return

        placeholders = ",".join("?" for _ in expired)
        await runtime.db.execute(
            f"DELETE FROM raid_party_invites "
            f"WHERE party_id IN ({placeholders})",
            expired,
        )
        await runtime.db.execute(
            f"DELETE FROM raid_parties WHERE id IN ({placeholders})",
            expired,
        )
        await runtime.commit()

    async def get_raid_party(user_id: int):
        """Возвращает активный отряд игрока или None."""
        await cleanup_expired_raid_parties()
        async with runtime.db.execute(
            "SELECT id, leader_id, member2_id, member3_id, "
            "created_at, updated_at "
            "FROM raid_parties "
            "WHERE leader_id = ? OR member2_id = ? OR member3_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (user_id, user_id, user_id),
        ) as c:
            return await c.fetchone()

    async def get_raid_party_by_id(party_id: int):
        async with runtime.db.execute(
            "SELECT id, leader_id, member2_id, member3_id, "
            "created_at, updated_at "
            "FROM raid_parties WHERE id = ?",
            (party_id,),
        ) as c:
            return await c.fetchone()

    async def touch_raid_party(party_id: int):
        await runtime.db.execute(
            "UPDATE raid_parties SET updated_at = ? WHERE id = ?",
            (datetime.datetime.now().isoformat(), party_id),
        )

    async def create_raid_party(user_id: int) -> int:
        """Создаёт отряд. Игрок может быть только в одном отряде."""
        async with runtime.transaction():
            async with runtime.db.execute(
                "SELECT id FROM raid_parties "
                "WHERE leader_id = ? OR member2_id = ? OR member3_id = ?",
                (user_id, user_id, user_id),
            ) as c:
                if await c.fetchone():
                    raise ValueError("Ты уже состоишь в отряде.")

            cur = await runtime.db.execute(
                "INSERT INTO raid_parties (leader_id, updated_at) "
                "VALUES (?, ?)",
                (user_id, datetime.datetime.now().isoformat()),
            )
            party_id = cur.lastrowid
            await runtime.db.execute(
                "DELETE FROM raid_party_invites WHERE target_id = ?",
                (user_id,),
            )
        return party_id

    async def join_raid_party(party_id: int, user_id: int):
        """Добавляет игрока в отряд после принятия приглашения."""
        async with runtime.transaction():
            async with runtime.db.execute(
                "SELECT id, leader_id, member2_id, member3_id "
                "FROM raid_parties WHERE id = ?",
                (party_id,),
            ) as c:
                party = await c.fetchone()

            if not party:
                raise ValueError("Отряд уже распался.")
            members = party_member_ids(party)
            if user_id in members:
                raise ValueError("Ты уже в этом отряде.")
            if len(members) >= runtime.max_members:
                raise ValueError("Отряд уже укомплектован.")

            async with runtime.db.execute(
                "SELECT id FROM raid_parties "
                "WHERE (leader_id = ? OR member2_id = ? OR member3_id = ?) "
                "AND id != ?",
                (user_id, user_id, user_id, party_id),
            ) as c:
                if await c.fetchone():
                    raise ValueError("Ты уже состоишь в другом отряде.")

            if party[2] is None:
                await runtime.db.execute(
                    "UPDATE raid_parties SET member2_id = ?, "
                    "updated_at = ? WHERE id = ?",
                    (
                        user_id,
                        datetime.datetime.now().isoformat(),
                        party_id,
                    ),
                )
            elif party[3] is None:
                await runtime.db.execute(
                    "UPDATE raid_parties SET member3_id = ?, "
                    "updated_at = ? WHERE id = ?",
                    (
                        user_id,
                        datetime.datetime.now().isoformat(),
                        party_id,
                    ),
                )
            else:
                raise ValueError("В отряде нет свободного места.")

            await runtime.db.execute(
                "DELETE FROM raid_party_invites WHERE target_id = ?",
                (user_id,),
            )
            await runtime.db.execute(
                "DELETE FROM raid_party_invites "
                "WHERE party_id = ? AND target_id = ?",
                (party_id, user_id),
            )

            async with runtime.db.execute(
                "SELECT id, leader_id, member2_id, member3_id "
                "FROM raid_parties WHERE id = ?",
                (party_id,),
            ) as c:
                updated = await c.fetchone()
            if (
                updated
                and len(party_member_ids(updated)) >= runtime.max_members
            ):
                await runtime.db.execute(
                    "DELETE FROM raid_party_invites WHERE party_id = ?",
                    (party_id,),
                )

    async def detach_user_from_raid_party(user_id: int) -> str:
        """Убирает игрока из отряда. Не коммитит."""
        async with runtime.db.execute(
            "SELECT id, leader_id, member2_id, member3_id "
            "FROM raid_parties "
            "WHERE leader_id = ? OR member2_id = ? OR member3_id = ?",
            (user_id, user_id, user_id),
        ) as c:
            party = await c.fetchone()

        await runtime.db.execute(
            "DELETE FROM raid_party_invites "
            "WHERE target_id = ? OR inviter_id = ?",
            (user_id, user_id),
        )
        if not party:
            return "none"

        party_id, leader_id, member2_id, member3_id = party
        now = datetime.datetime.now().isoformat()

        if leader_id == user_id:
            if member2_id:
                await runtime.db.execute(
                    "UPDATE raid_parties SET leader_id = ?, "
                    "member2_id = ?, member3_id = NULL, updated_at = ? "
                    "WHERE id = ?",
                    (member2_id, member3_id, now, party_id),
                )
                return "transferred"
            await runtime.db.execute(
                "DELETE FROM raid_party_invites WHERE party_id = ?",
                (party_id,),
            )
            await runtime.db.execute(
                "DELETE FROM raid_parties WHERE id = ?", (party_id,)
            )
            return "disbanded"

        if member2_id == user_id:
            await runtime.db.execute(
                "UPDATE raid_parties SET member2_id = ?, "
                "member3_id = NULL, updated_at = ? WHERE id = ?",
                (member3_id, now, party_id),
            )
            return "left"

        if member3_id == user_id:
            await runtime.db.execute(
                "UPDATE raid_parties SET member3_id = NULL, "
                "updated_at = ? WHERE id = ?",
                (now, party_id),
            )
            return "left"

        return "none"

    async def leave_raid_party(user_id: int) -> str:
        async with runtime.transaction():
            return await detach_user_from_raid_party(user_id)

    async def get_raid_cooldown_seconds(user_id: int) -> int:
        """Сколько секунд осталось до следующего рейда игрока."""
        async with runtime.db.execute(
            "SELECT last_raid_time FROM raid_cooldowns WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        last_raid = runtime.parse_db_time(row[0]) if row else None
        if not last_raid:
            return 0
        return max(
            0,
            int(
                runtime.cooldown_seconds
                - (datetime.datetime.now() - last_raid).total_seconds()
            ),
        )

    async def get_last_raid_target(user_id: int) -> int | None:
        async with runtime.db.execute(
            "SELECT target_id FROM raid_loot_log WHERE user_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        return row[0] if row else None

    return (
        party_member_ids,
        cleanup_expired_raid_parties,
        cleanup_expired_raid_invites,
        get_raid_party,
        get_raid_party_by_id,
        touch_raid_party,
        create_raid_party,
        join_raid_party,
        detach_user_from_raid_party,
        leave_raid_party,
        get_raid_cooldown_seconds,
        get_last_raid_target,
    )
