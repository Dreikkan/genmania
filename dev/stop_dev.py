#!/usr/bin/env python3
"""Останавливает только dev-бота по PID из dev/data/dev_bot.pid."""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

PID_FILE = Path(__file__).resolve().parent / "data" / "dev_bot.pid"


def main() -> int:
    if not PID_FILE.exists():
        print("ℹ️  PID-файл не найден: dev-бот, вероятно, не запущен.")
        return 0
    try:
        pid = int(PID_FILE.read_text(encoding="ascii").strip())
    except ValueError:
        print("❌ Некорректный PID-файл, удаляю.")
        PID_FILE.unlink(missing_ok=True)
        return 1

    if os.name == "nt":
        check = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
        )
        alive = str(pid) in (check.stdout or "")
    else:
        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            alive = False

    if not alive:
        print(f"ℹ️  Процесс {pid} уже не работает.")
        PID_FILE.unlink(missing_ok=True)
        return 0

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
    else:
        os.kill(pid, signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True)
    print(f"🛑 Dev-бот остановлен (PID {pid}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
