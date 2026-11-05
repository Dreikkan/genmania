import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def _run_script(name: str):
    result = subprocess.run(
        [sys.executable, str(HERE / name)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, (
        f"{name} failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_emoji_coverage():
    _run_script("emoji_coverage_script.py")


def test_buttons_emoji():
    _run_script("buttons_emoji_script.py")
