#!/usr/bin/env python3
"""CI runner for the apply-now workflow.

Reads job URLs (one per line, # for comments) from job_links.txt and runs
the full Apply Pilot pipeline on each. Set APPLY_AUTO_SUBMIT=true in the
workflow env to actually submit; default is dry-run + screenshots.
"""
import asyncio
from pathlib import Path

from apply import run

LINKS = Path("job_links.txt")


async def main() -> None:
    if not LINKS.exists():
        print("job_links.txt not found — nothing to do.")
        return
    urls = [l.strip() for l in LINKS.read_text().splitlines()
            if l.strip() and not l.strip().startswith("#")]
    print(f"🎼 Apply Pilot CI — {len(urls)} link(s)")
    for url in urls:
        try:
            await run(url, fill=True, submit=None)  # None → APPLY_AUTO_SUBMIT env decides
        except Exception as e:
            print(f"❌ {url}: {e}")
        print("─" * 70)


if __name__ == "__main__":
    asyncio.run(main())
