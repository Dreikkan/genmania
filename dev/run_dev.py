#!/usr/bin/env python3
"""Запуск локальной dev-копии Gen Mania с изолированной папкой data.

Токен читается из dev/.env и никогда не печатается.
Production-база и production-бот не затрагиваются.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEV_DIR = Path(__file__).resolve().parent
ROOT_DIR = DEV_DIR.parent
ENV_FILE = DEV_DIR / ".env"
DATA_DIR = DEV_DIR / "data"
DB_PATH = DATA_DIR / "castle.db"
PID_FILE = DATA_DIR / "dev_bot.pid"
PLACEHOLDER = "your_dev_bot_token"


def load_env(path: Path) -> None:
    if not path.exists():
        raise SystemExit(
            f"Не найден {path}. Скопируй dev/.env.example в dev/.env "
            "и вставь токен тестового приложения."
        )
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            # Dev-стенд всегда использует значения из dev/.env,
            # чтобы случайный production-токен в shell не перетёк сюда.
            os.environ[key] = value


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
    parser = argparse.ArgumentParser(description="Gen Mania dev launcher")
    parser.add_argument(
        "--check", action="store_true", help="только проверить окружение"
    )
    parser.add_argument(
        "--probe", action="store_true", help="проверить токен через Discord API"
    )
    args = parser.parse_args()

    load_env(ENV_FILE)
    # Жёстко изолируем данные: никаких /app/data и production-базы.
    os.environ["DATA_DIR"] = str(DATA_DIR)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token or token == PLACEHOLDER:
        print("❌ DISCORD_BOT_TOKEN не задан в dev/.env")
        print()
        print("Что сделать:")
        print("  1. Создай отдельное ТЕСТОВОЕ приложение:")
        print("     https://discord.com/developers/applications")
        print("  2. Bot -> Reset Token -> скопируй токен.")
        print("  3. Включи Privileged Gateway Intents -> Server Members Intent.")
        print("  4. Пригласи тестового бота на тестовый сервер.")
        print("  5. Вставь токен в dev/.env (не в чат и не в git).")
        print()
        print("Прод-токен использовать не рекомендуется: два процесса")
        print("с одним токеном конфликтуют за gateway-соединение.")
        return 2

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✅ DATA_DIR: {DATA_DIR}")
    print(f"✅ DB: {DB_PATH} ({'есть' if DB_PATH.exists() else 'будет создана'})")
    print(f"✅ Токен загружен (длина {len(token)}), значение не выводится.")

    if args.probe:
        probe = DEV_DIR / "check_bot.py"
        result = subprocess.run([sys.executable, str(probe)])
        if result.returncode != 0:
            return result.returncode

    if args.check:
        return 0

    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text(encoding="ascii").strip())
        except ValueError:
            old_pid = 0
        if old_pid and process_alive(old_pid):
            print(f"❌ Dev-бот уже запущен (PID {old_pid}).")
            print("   Останови его: python dev\\stop_dev.py")
            return 1
        PID_FILE.unlink(missing_ok=True)

    print("🚀 Запуск dev-бота... (Ctrl+C для остановки)")
    process = subprocess.Popen(
        [sys.executable, "-u", str(ROOT_DIR / "bot.py")],
        cwd=str(ROOT_DIR),
    )
    PID_FILE.write_text(str(process.pid), encoding="ascii")
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        return 130
    finally:
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
