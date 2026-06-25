#!/usr/bin/env python3
"""Run the SkillPulse static-analysis metric suite on backend Python code."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
TARGET = "app"


def run(label: str, cmd: list[str]) -> int:
    print(f"\n=== {label} ===")
    result = subprocess.run(cmd, cwd=BACKEND)
    if result.returncode != 0:
        print(f"[FAIL] {label}")
    else:
        print(f"[OK] {label}")
    return result.returncode


def main() -> int:
    checks = [
        ("Ruff (style + bugbear subset)", [sys.executable, "-m", "ruff", "check", TARGET]),
        ("Radon cyclomatic complexity", [sys.executable, "-m", "radon", "cc", TARGET, "-a", "-nc"]),
        ("Radon maintainability index", [sys.executable, "-m", "radon", "mi", TARGET, "-nc"]),
        ("Radon Halstead volume", [sys.executable, "-m", "radon", "hal", TARGET]),
        ("Vulture dead code", [sys.executable, "-m", "vulture", TARGET, "--min-confidence", "80"]),
        ("Mypy type coverage", [sys.executable, "-m", "mypy", TARGET]),
        ("Interrogate docstrings", [sys.executable, "-m", "interrogate", TARGET, "-v"]),
        ("Pydeps import graph", [sys.executable, "-m", "pydeps", TARGET, "--show-deps", "--noshow"]),
        ("Pylint architecture signals", [sys.executable, "-m", "pylint", TARGET, "--disable=all", "--enable=import-error,cyclic-import,R0902,W0603,C0103,R0801"]),
        ("Pytest", [sys.executable, "-m", "pytest", "-q"]),
    ]

    failures = 0
    for label, cmd in checks:
        failures += run(label, cmd) != 0

    print(f"\nQuality checks finished with {failures} failing step(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
