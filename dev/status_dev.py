#!/usr/bin/env python3
"""Показывает состояние dev-бота, хвост лога и состояние базы."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEV_DIR = Path(__file__).resolve().parent
DATA_DIR = DEV_DIR / "data"
PID_FILE = DATA_DIR / "dev_bot.pid"
LOG_FILE = DATA_DIR / "bot.log"


def process_alive(pid: int) -> bool:
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
        )
        return str(pid) in (result.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main() -> int:
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="ascii").strip())
        except ValueError:
            pid = -1
        if pid > 0 and process_alive(pid):
            print(f"✅ Dev-бот запущен (PID {pid}).")
        else:
            print("⚠️  PID-файл есть, но процесс не найден.")
    else:
        print("ℹ️  Dev-бот не запущен (PID-файла нет).")

    if LOG_FILE.exists():
        print("\n--- последние строки bot.log ---")
        raw = LOG_FILE.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1251", errors="replace")
        for line in text.splitlines()[-20:]:
            print(line)
    else:
        print("\nℹ️  bot.log ещё не создан.")

    print("\n--- база ---")
    check = subprocess.run([sys.executable, str(DEV_DIR / "check_db.py")])
    return check.returncode


if __name__ == "__main__":
    raise SystemExit(main())
