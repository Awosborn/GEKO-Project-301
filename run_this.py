#!/usr/bin/env python3
"""Interactive command launcher for GEKO MVP workflows."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

COMMANDS = {
    "1": [sys.executable, "-m", "pytest", "-q"],
    "2": [sys.executable, "-m", "MVP.ml.train_next_bid", "--help"],
    "3": [sys.executable, "-m", "MVP.ml.train_next_card", "--help"],
    "4": [
        sys.executable,
        "-m",
        "MVP.ml.play_vs_ai",
        "--model-dir",
        "artifacts/models/bid",
        "--boards",
        "1",
    ],
}


def main() -> int:
    print("Choose a command by number:")
    print("  1) Run tests (pytest -q)")
    print("  2) Show next-bid training CLI help")
    print("  3) Show next-card training CLI help")
    print("  4) Play random deals (AI players 1-3, you are player 4)")

    choice = input("Enter a number (1-4): ").strip()

    command = COMMANDS.get(choice)
    if command is None:
        print(f"Invalid choice: {choice!r}. Please run again and choose 1, 2, 3, or 4.")
        return 1

    print(f"Running: {shlex.join(command)}")
    completed = subprocess.run(command, cwd=REPO_ROOT)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
