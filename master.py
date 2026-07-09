#!/usr/bin/env python3
"""Lateral Thinking Master CLI — the top-level controller loop.

Usage:
  python master.py                 run one 5-minute lateral loop (dry-run unless
                                   APPLY_AUTO_SUBMIT=true)
  python master.py --budget 120    run for N seconds
Env: MASTER_BUDGET_SECONDS, APPLY_AUTO_SUBMIT, APPLY_MIN_FIT, TELEGRAM_*.
"""
import asyncio
import sys

from apply_agent import master


def _budget() -> int | None:
    if "--budget" in sys.argv:
        try:
            return int(sys.argv[sys.argv.index("--budget") + 1])
        except Exception:
            return None
    return None


if __name__ == "__main__":
    print(asyncio.run(master.run(_budget())))
