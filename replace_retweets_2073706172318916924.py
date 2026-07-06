#!/usr/bin/env python3
"""
Place 40 replacement retweets for post 2073706172318916924.
Original order #61559100 used svc#13138 (no refill — dropped, ticketed).
Replacement uses svc#13139 ($0.54/k, Refill Button: 30 Days — non-drop).
"""
import sys
sys.path.insert(0, "/home/user/BlockChain-")
from automation import (
    load_state, save_state, log_agent, PANELS,
    _api_panel, datetime, timezone
)

POST_URL  = "https://x.com/i/status/2073706172318916924"
SVC_ID    = "13139"   # smmfollows — Refill Button: 30 Days — $0.54/k
QUANTITY  = 40

state = load_state()
smmfollows = next(p for p in PANELS if p["name"] == "smmfollows" and p["key"])

print(f"Placing {QUANTITY}x retweets (svc#{SVC_ID}, 30-day refill) for {POST_URL}")
try:
    res = _api_panel(smmfollows, {
        "action": "add",
        "service": SVC_ID,
        "link": POST_URL,
        "quantity": QUANTITY,
    })
    if res.get("order"):
        oid = str(res["order"])
        print(f"SUCCESS — order #{oid}: {QUANTITY}x retweets svc#{SVC_ID} @ $0.54/k (30-day refill)")
        state["orders"][oid] = {
            "id": oid, "kind": "retweets", "link": POST_URL,
            "quantity": QUANTITY, "refillable": True, "status": "Pending",
            "panel": "smmfollows", "service_id": SVC_ID,
            "start_count": None, "remains": None,
            "added_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
        }
        log_agent(state, f"[RT-Replacement-NonDrop] #{oid}: {QUANTITY}x retweets svc#{SVC_ID} 30d-refill for {POST_URL}")
        save_state(state)
        print("State saved.")
    else:
        print(f"FAILED: {res}")
except Exception as e:
    print(f"ERROR: {e}")
