#!/usr/bin/env python3
"""
Auto-Refill Monitor
-------------------
Watches all active orders and requests refill as soon as
each completed order becomes eligible (24 h window).

Usage:
  python monitor_refill.py          # runs forever, checks every 10 min
  python monitor_refill.py --once   # single check then exit
"""

from __future__ import annotations
import argparse, json, logging, sys, time
from pathlib import Path
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("monitor.log")],
)
log = logging.getLogger(__name__)

API_KEY  = "882fa9a6e54b39ffa8c7e2bf4fcc1f46"
API_URL  = "https://smmfollows.com/api/v2"
STATE_F  = Path("orders_state.json")

# Orders placed for your 3 posts
TRACKED_ORDERS = [
    {"order_id": "61450840", "type": "likes",    "link": "https://x.com/i/status/2065705610163941467", "refillable": True},
    {"order_id": "61450841", "type": "retweets", "link": "https://x.com/i/status/2065705610163941467", "refillable": True},
    {"order_id": "61450842", "type": "comments", "link": "https://x.com/i/status/2065705610163941467", "refillable": False},
    {"order_id": "61450843", "type": "likes",    "link": "https://x.com/i/status/2064879295843983840", "refillable": True},
    {"order_id": "61450844", "type": "retweets", "link": "https://x.com/i/status/2064879295843983840", "refillable": True},
    {"order_id": "61450845", "type": "comments", "link": "https://x.com/i/status/2064879295843983840", "refillable": False},
    {"order_id": "61450846", "type": "likes",    "link": "https://x.com/i/status/2064283340849738045", "refillable": True},
    {"order_id": "61450847", "type": "retweets", "link": "https://x.com/i/status/2064283340849738045", "refillable": True},
    {"order_id": "61450848", "type": "comments", "link": "https://x.com/i/status/2064283340849738045", "refillable": False},
]


def api(payload: dict) -> dict:
    payload["key"] = API_KEY
    r = requests.post(API_URL, data=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def load_state() -> dict:
    if STATE_F.exists():
        return json.loads(STATE_F.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_F.write_text(json.dumps(state, indent=2))


def run_cycle(state: dict) -> dict:
    ids = [o["order_id"] for o in TRACKED_ORDERS]
    ids_str = ",".join(ids)

    # Batch status check
    try:
        if len(ids) == 1:
            raw = api({"action": "status", "order": ids[0]})
            statuses = {ids[0]: raw}
        else:
            statuses = api({"action": "status", "orders": ids_str})
    except Exception as exc:
        log.error("Status check failed: %s", exc)
        return state

    bal = api({"action": "balance"})
    log.info("Balance: $%s %s", bal.get("balance"), bal.get("currency", ""))

    print(f"\n{'─'*72}")
    print(f"{'Order':<13} {'Type':<11} {'Status':<18} {'Remains':<10} Refilled?")
    print(f"{'─'*72}")

    for o in TRACKED_ORDERS:
        oid  = o["order_id"]
        info = statuses.get(oid, {})
        status   = info.get("status", "unknown")
        remains  = info.get("remains", "?")
        refilled = state.get(oid, {}).get("refilled", False)

        print(f"  {oid:<11} {o['type']:<11} {status:<18} {str(remains):<10} {'✓' if refilled else '–'}")

        # Update state
        state.setdefault(oid, {})
        state[oid]["status"] = status
        state[oid]["type"]   = o["type"]

        # Request refill if eligible
        if (
            o["refillable"]
            and status == "Completed"
            and not refilled
        ):
            try:
                res = api({"action": "refill", "order": oid})
                if "error" in res:
                    log.warning("  Refill order %s: %s", oid, res["error"])
                else:
                    rid = res.get("refill")
                    log.info("  Refill SENT order=%s refill_id=%s", oid, rid)
                    state[oid]["refilled"]  = True
                    state[oid]["refill_id"] = rid
            except Exception as exc:
                log.error("  Refill request failed for %s: %s", oid, exc)

    print(f"{'─'*72}\n")
    save_state(state)
    return state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--interval", type=int, default=600, help="Seconds between checks (default 600)")
    args = parser.parse_args()

    state = load_state()

    if args.once:
        run_cycle(state)
        return

    log.info("=== Refill Monitor started — checking every %ds ===", args.interval)
    while True:
        state = run_cycle(state)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
