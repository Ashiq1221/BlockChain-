#!/usr/bin/env python3
"""
smmwiz non-delivery handler:
1. Submit non-delivery tickets on smmfollows support for all smmwiz orders
2. Place replacement orders on smmfollows for every undelivered smmwiz order
"""
import sys, re, json
sys.path.insert(0, "/home/user/BlockChain-")
from automation import (
    load_state, save_state, log_agent, PANELS,
    _api_panel, _panel_session, _ai_order_agent,
    _master_controller_gate, datetime, timezone
)

PANEL_URL = "https://smmfollows.com"
state = load_state()

# All smmwiz orders and what they failed to deliver
SMMWIZ_ORDERS = [
    # (order_id, kind, qty, link, note)
    ("30182848", "likes",    20,  "https://x.com/i/status/2070034213085274431", "Completed but dropped"),
    ("30183453", "likes",    21,  "https://x.com/i/status/2069014496086217116", "Completed but dropped"),
    ("30183457", "comments",  5,  "https://x.com/i/status/2069014496086217116", "Completed but dropped"),
    ("30232523", "likes",   100,  "https://x.com/i/status/2073706172318916924", "Cancelled — never delivered"),
    ("30232527", "comments", 20,  "https://x.com/i/status/2073706172318916924", "Pending — not delivered (cancel unavailable)"),
]

# ── Step 1: Submit tickets on smmfollows support ───────────────────────────────
print("=== Submitting smmwiz non-delivery tickets ===\n")
smmfollows_cfg = next(p for p in PANELS if p["name"] == "smmfollows")
sess = _panel_session(smmfollows_cfg)
if not sess:
    print("ERROR: smmfollows login failed")
    sys.exit(1)

# Group by post link
groups: dict = {}
for oid, kind, qty, link, note in SMMWIZ_ORDERS:
    groups.setdefault(link, []).append((oid, kind, qty, note))

submitted = 0
for link, items in groups.items():
    order_ids = [i[0] for i in items]
    message = (
        "Hello,\n\n"
        "The following orders were placed on smmwiz panel but NONE were delivered "
        "(either dropped immediately after 'Completed' or still stuck as Pending).\n"
        "We are requesting credit/replacement for all these orders.\n\n"
        f"Post: {link}\n\n"
        "Orders:\n" +
        "\n".join(f"  - #{o}: {qty}x {kind} on smmwiz — {note}"
                  for o, kind, qty, note in items) +
        "\n\nPlease issue credit or re-deliver. Thank you."
    )
    try:
        r = sess.get(f"{PANEL_URL}/tickets", timeout=20)
        m = re.search(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"', r.text)
        if not m:
            print(f"  SKIP {link[-35:]}: CSRF not found"); continue
        r2 = sess.post(f"{PANEL_URL}/ticket-create", data={
            "_csrf": m.group(1),
            "TicketForm[subject]": "Junior - Orders [ Not Delivered - smmwiz ]",
            "TicketForm[message]": message,
            "subject": "Orders", "request": "Not delivered",
            "cancel-reason": "", "ordernumbers": ",".join(order_ids),
        }, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{PANEL_URL}/tickets", "Origin": PANEL_URL,
            "Accept": "application/json, */*", "X-Requested-With": "XMLHttpRequest",
        }, timeout=20)
        resp = r2.json() if r2.status_code == 200 else {}
        if resp.get("status") == "success":
            print(f"  TICKET OK  {link[-45:]}  orders: {', '.join('#'+o for o in order_ids)}")
            submitted += 1
        else:
            print(f"  WARN {link[-35:]}: {resp}")
    except Exception as e:
        print(f"  ERR: {e}")

print(f"\nTickets submitted: {submitted}/{len(groups)}\n")

# ── Step 2: Replacement orders on smmfollows ───────────────────────────────────
print("=== Placing replacement orders on smmfollows ===\n")

# What needs replacing (deduplicated by kind+link)
replacements = [
    # The 21 likes and 100 likes are for different posts
    ("likes",    20,  "https://x.com/i/status/2070034213085274431"),
    ("likes",    21,  "https://x.com/i/status/2069014496086217116"),
    ("comments",  5,  "https://x.com/i/status/2069014496086217116"),
    ("likes",   100,  "https://x.com/i/status/2073706172318916924"),
    ("comments", 20,  "https://x.com/i/status/2073706172318916924"),
]

cf = None
try:
    from automation import CloudflarePlatform
    cf = CloudflarePlatform()
    cf.load_from_state(state)
except Exception:
    pass

placed = 0
for kind, qty, link in replacements:
    allowed, reason = _master_controller_gate(kind, qty)
    if not allowed:
        print(f"  BLOCKED {qty}x {kind}: {reason}")
        continue
    print(f"Ordering {qty}x {kind} for {link[-40:]} on smmfollows...")
    res = _ai_order_agent(kind, qty, link, None, cf)
    if res.get("success"):
        oid = str(res["order"])
        print(f"  SUCCESS — order #{oid} svc#{res['service_id']} @ ${res.get('rate',0):.4f}/k")
        state["orders"][oid] = {
            "id": oid, "kind": kind, "link": link,
            "quantity": qty, "refillable": False, "status": "Pending",
            "panel": res["panel"], "service_id": res.get("service_id"),
            "start_count": None, "remains": None,
            "added_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
        }
        log_agent(state, f"[smmwiz-replacement] #{oid}: {qty}x {kind} smmfollows for {link}")
        placed += 1
    else:
        print(f"  FAILED: {res.get('error')}")
    print()

save_state(state)
print(f"Done. Replacement orders placed: {placed}/{len(replacements)}")
