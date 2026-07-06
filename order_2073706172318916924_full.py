#!/usr/bin/env python3
"""
Full order for https://x.com/i/status/2073706172318916924
- 1,000 likes      svc#16465  $2.10/k
- 100 custom comments svc#16680 $48.60/k  (100-day refill, Custom type)
-   500 retweets   svc#13139  $0.54/k  (30-day refill, non-drop)
- 100,000 views    svc#17682  $0.0015/k
"""
import sys
sys.path.insert(0, "/home/user/BlockChain-")
from automation import (
    load_state, save_state, log_agent, PANELS,
    _api_panel, _generate_comments, CloudflarePlatform,
    datetime, timezone
)

POST_URL = "https://x.com/i/status/2073706172318916924"
POST_TEXT = (
    "LingoAI Ecosystem Update from Jeju Island, South Korea. "
    "Our CEO took the main stage at the 'Rise Beyond Intelligence' AI Industry Summit "
    "to deliver a keynote: 'Decentralized Multilingual Data Infrastructure: "
    "Empowering the Global Majority to Own Data'"
)

ORDERS = [
    # (kind, qty, svc_id, rate, refillable, label)
    ("likes",    1000,   16465, 2.10,   False, "Likes USA"),
    ("comments",  100,   16680, 48.60,  True,  "Custom Comments India 100d-refill"),
    ("retweets",  500,   13139, 0.54,   True,  "Retweets non-drop 30d-refill"),
    ("views",  100_000,  17682, 0.0015, False, "Views+Impressions Global"),
]

state = load_state()
sf = next(p for p in PANELS if p["name"] == "smmfollows")

# Cloudflare for comment generation
cf = None
try:
    cf = CloudflarePlatform()
    cf.load_from_state(state)
except Exception:
    pass

# Generate 100 custom comments once
print("Generating 100 custom comments via AI...")
comments_text = _generate_comments(POST_TEXT, 100, cf)
lines = [l.strip() for l in comments_text.strip().splitlines() if l.strip()]
print(f"Generated {len(lines)} comment lines.\n")

placed = 0
total_cost = 0.0

for kind, qty, svc_id, rate, refillable, label in ORDERS:
    cost = qty / 1000 * rate
    print(f"Ordering {qty:>7,}x {kind:<10} svc#{svc_id}  ${rate:.4f}/k  est. ${cost:.4f}  [{label}]")

    payload = {
        "action": "add",
        "service": svc_id,
        "link": POST_URL,
        "quantity": qty,
    }
    if kind == "comments":
        payload["comments"] = comments_text

    try:
        res = _api_panel(sf, payload)
        if res.get("order"):
            oid = str(res["order"])
            print(f"  SUCCESS → order #{oid}")
            state["orders"][oid] = {
                "id": oid, "kind": kind, "link": POST_URL,
                "quantity": qty, "refillable": refillable, "status": "Pending",
                "panel": "smmfollows", "service_id": str(svc_id),
                "start_count": None, "remains": None,
                "added_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
            }
            log_agent(state, f"[full-order] #{oid}: {qty}x {kind} svc#{svc_id} for {POST_URL}")
            placed += 1
            total_cost += cost
        else:
            print(f"  FAILED: {res}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()

save_state(state)
print(f"Done. Orders placed: {placed}/{len(ORDERS)}  |  Est. total: ${total_cost:.4f}")
