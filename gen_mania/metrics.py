"""In-process metrics for Gen Mania without external dependencies."""
from __future__ import annotations

from collections import deque
import datetime
import time

from .config import SLOW_DB_TX_MS, UTC


class MetricsRegistry:
    """Лёгкие in-process метрики команд, БД и фоновых задач."""

    def __init__(self):
        self.started_at = time.time()
        self.commands_total = 0
        self.command_errors = 0
        self.command_durations: deque[float] = deque(maxlen=500)
        self.commands_by_name: dict[str, int] = {}
        self.command_errors_by_type: dict[str, int] = {}
        self.db_tx_total = 0
        self.db_tx_errors = 0
        self.db_tx_durations: deque[float] = deque(maxlen=500)
        self.slow_db_tx = 0
        self.background_errors = 0
        self.background_errors_by_task: dict[str, int] = {}

    @staticmethod
    def _percentile(values, percentile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = round((percentile / 100.0) * (len(ordered) - 1))
        index = max(0, min(len(ordered) - 1, index))
        return round(ordered[index], 2)

    def record_command(self, name: str, duration_ms: float) -> None:
        self.commands_total += 1
        self.command_durations.append(max(0.0, float(duration_ms)))
        self.commands_by_name[name] = self.commands_by_name.get(name, 0) + 1

    def record_command_error(self, error_name: str) -> None:
        self.commands_total += 1
        self.command_errors += 1
        self.command_errors_by_type[error_name] = (
            self.command_errors_by_type.get(error_name, 0) + 1
        )

    def record_db_tx(self, duration_ms: float, ok: bool = True) -> None:
        duration = max(0.0, float(duration_ms))
        self.db_tx_total += 1
        self.db_tx_durations.append(duration)
        if not ok:
            self.db_tx_errors += 1
        if duration >= SLOW_DB_TX_MS:
            self.slow_db_tx += 1

    def record_background_error(self, task_name: str) -> None:
        self.background_errors += 1
        self.background_errors_by_task[task_name] = (
            self.background_errors_by_task.get(task_name, 0) + 1
        )

    def snapshot(self) -> dict:
        return {
            "started_at": datetime.datetime.fromtimestamp(
                self.started_at, UTC
            ).isoformat(),
            "uptime_seconds": int(time.time() - self.started_at),
            "commands_total": self.commands_total,
            "command_errors": self.command_errors,
            "command_avg_ms": round(
                sum(self.command_durations) / len(self.command_durations), 2
            ) if self.command_durations else 0.0,
            "command_p95_ms": self._percentile(self.command_durations, 95),
            "commands_by_name": dict(self.commands_by_name),
            "command_errors_by_type": dict(self.command_errors_by_type),
            "db_tx_total": self.db_tx_total,
            "db_tx_errors": self.db_tx_errors,
            "db_tx_avg_ms": round(
                sum(self.db_tx_durations) / len(self.db_tx_durations), 2
            ) if self.db_tx_durations else 0.0,
            "db_tx_p95_ms": self._percentile(self.db_tx_durations, 95),
            "slow_db_tx": self.slow_db_tx,
            "background_errors": self.background_errors,
            "background_errors_by_task": dict(self.background_errors_by_task),
        }


METRICS = MetricsRegistry()
