"""Offline income helpers."""
from __future__ import annotations

OFFLINE_MAX_HOURS = 24
OFFLINE_PENALTY_START_HOURS = 2
OFFLINE_PENALTY_RATE = 0.7


def effective_offline_seconds(seconds: float) -> float:
    """Эффективные секунды накопления с потолком и офлайн-штрафом."""
    capped = max(0.0, min(float(seconds), OFFLINE_MAX_HOURS * 3600))
    start = OFFLINE_PENALTY_START_HOURS * 3600
    if capped <= start:
        return capped
    return start + (capped - start) * OFFLINE_PENALTY_RATE
