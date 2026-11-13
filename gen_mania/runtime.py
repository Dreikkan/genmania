"""Startup/runtime helpers: single-instance lock and WAL checkpoint."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger("gen_mania")


async def checkpoint_wal_best_effort(db) -> bool:
    """PASSIVE-checkpoint не блокирует БД и не мешает backup API.

    FULL/TRUNCATE могут вернуть "database table is locked", если в этот
    момент открыт курсор или идёт чтение. Для консистентного бэкапа
    checkpoint не обязателен: SQLite backup API сам читает WAL.
    """
    try:
        await db.execute("PRAGMA wal_checkpoint(PASSIVE)")
        return True
    except aiosqlite.Error as exc:
        logger.warning("WAL checkpoint пропущен: %s", exc)
        return False


class InstanceLock:
    """Не даёт запустить два бота на одной папке data."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._handle: Any = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = None
        try:
            handle = open(self.path, "a+", encoding="utf-8")
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(" ")
                    handle.flush()
                handle.seek(0)
                try:
                    locking = getattr(msvcrt, "locking")
                    locking(
                        handle.fileno(),
                        getattr(msvcrt, "LK_NBLCK", 0),
                        1,
                    )
                except OSError:
                    handle.close()
                    return False
            else:
                import fcntl

                try:
                    flock = getattr(fcntl, "flock")
                    flock(
                        handle.fileno(),
                        getattr(fcntl, "LOCK_EX", 0)
                        | getattr(fcntl, "LOCK_NB", 0),
                    )
                except OSError:
                    handle.close()
                    return False

            handle.seek(0)
            handle.write(f"{os.getpid()}".ljust(32))
            handle.flush()
            self._handle = handle
            return True
        except OSError:
            if handle is not None:
                handle.close()
            return False

    def release(self) -> None:
        if self._handle is None:
            return
        handle = self._handle
        self._handle = None
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                try:
                    locking = getattr(msvcrt, "locking")
                    locking(
                        handle.fileno(),
                        getattr(msvcrt, "LK_UNLCK", 0),
                        1,
                    )
                except OSError:
                    pass
            else:
                import fcntl

                try:
                    flock = getattr(fcntl, "flock")
                    flock(
                        handle.fileno(),
                        getattr(fcntl, "LOCK_UN", 0),
                    )
                except OSError:
                    pass
        finally:
            handle.close()
