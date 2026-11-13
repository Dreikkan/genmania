#!/usr/bin/env python3
"""Запускает dev-бота в отдельном (detached) процессе и выходит.

В отличие от run_dev.py, не держит родительский процесс: удобно для
фонового live-стенда. PID пишется в dev/data/dev_bot.pid.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from run_dev import (
    DATA_DIR,
    DB_PATH,
    ENV_FILE,
    PID_FILE,
    PLACEHOLDER,
    ROOT_DIR,
    load_env,
    process_alive,
)


def main() -> int:
    load_env(ENV_FILE)
    os.environ["DATA_DIR"] = str(DATA_DIR)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token or token == PLACEHOLDER:
        print("❌ DISCORD_BOT_TOKEN не задан в dev/.env")
        return 2

    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text(encoding="ascii").strip())
        except ValueError:
            old_pid = 0
        if old_pid and process_alive(old_pid):
            print(f"❌ Dev-бот уже запущен (PID {old_pid}).")
            return 1
        PID_FILE.unlink(missing_ok=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stdout_path = DATA_DIR / "dev_stdout.log"
    stderr_path = DATA_DIR / "dev_stderr.log"

    stdout = open(stdout_path, "ab")
    stderr = open(stderr_path, "ab")
    creationflags = 0
    popen_kwargs = {}
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
        popen_kwargs["creationflags"] = creationflags
    else:
        popen_kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(
            [sys.executable, "-u", str(ROOT_DIR / "bot.py")],
            cwd=str(ROOT_DIR),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            **popen_kwargs,
        )
    finally:
        stdout.close()
        stderr.close()

    PID_FILE.write_text(str(process.pid), encoding="ascii")
    time.sleep(1.5)
    if process.poll() is not None:
        PID_FILE.unlink(missing_ok=True)
        print(f"❌ Dev-бот завершился сразу (код {process.returncode}).")
        print(f"   Смотри {stderr_path} и {DATA_DIR / 'bot.log'}")
        return 1

    print(f"✅ Dev-бот запущен в фоне (PID {process.pid}).")
    print(f"   DB: {DB_PATH}")
    print(f"   stdout: {stdout_path}")
    print(f"   stderr: {stderr_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
