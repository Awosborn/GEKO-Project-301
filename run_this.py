#!/usr/bin/env python3
"""Interactive command launcher for GEKO MVP workflows."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CLI_PATH = REPO_ROOT / "MVP" / "cli.py"

COMMANDS = {
    "1": [sys.executable, str(CLI_PATH), "train-all"],
    "2": [sys.executable, str(CLI_PATH), "train-cycle"],
    "3": [sys.executable, str(CLI_PATH), "play"],
    "4": [sys.executable, str(CLI_PATH), "--help"],
}


def main() -> int:
    print("Choose a command by number:")
    print("  1) Generate self-play data + train both models (train-all)")
    print("  2) Generate self-play data + run self-play cycle (train-cycle)")
    print("  3) Play against stable models (play)")
    print("  4) Show CLI help")

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
