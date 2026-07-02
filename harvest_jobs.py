#!/usr/bin/env python3
"""Harvest job links from public Telegram job channels.

Usage:
  python harvest_jobs.py                 scrape channels, show new links
  python harvest_jobs.py --queue         also append ⭐ matches to job_links.txt
  python harvest_jobs.py --pending       show unprocessed leads from past runs
Channels come from JOB_TG_CHANNELS env (comma-separated), default:
cryptojobslist,cryptojobs,web3hiring,devjobs
"""
import asyncio
import sys
from pathlib import Path

from apply_agent import harvester


async def main() -> None:
    if "--pending" in sys.argv:
        print(harvester.render(harvester.pending(), "📥 Pending job leads:"))
        return
    res = await harvester.harvest()
    print(f"Scanned {res['total']} links across @{', @'.join(res['channels'])}\n")
    print(harvester.render(res["new"], f"🆕 {len(res['new'])} new job links:"))
    if "--queue" in sys.argv:
        matches = [l["url"] for l in res["new"] if l["matched"]]
        if matches:
            with Path("job_links.txt").open("a") as f:
                f.write("\n".join(matches) + "\n")
            print(f"\n➕ queued {len(matches)} matched links into job_links.txt")


if __name__ == "__main__":
    asyncio.run(main())
