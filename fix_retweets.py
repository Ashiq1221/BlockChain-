#!/usr/bin/env python3
"""
1. Submit tickets for all retweet orders where refill is disabled (not delivered).
2. Reorder 40 retweets for post 2073706172318916924 using svc#13139 (30-day refill).
"""
import sys, json, re, requests
sys.path.insert(0, "/home/user/BlockChain-")

from automation import (
    load_state, save_state, log_agent, PANELS,
    _api_panel, _panel_session, CloudflarePlatform,
    datetime, timezone
)

PANEL_URL = "https://smmfollows.com"
STATE_FILE = "/home/user/BlockChain-/automation_state.json"

# Retweet orders with "Refill is disabled" — panel charged but drops are unrecoverable
REFILL_DISABLED_ORDERS = {
    "61500416": "https://x.com/i/status/2064283937091035590",
    "61505279": "https://x.com/i/status/2070034213085274431",
    "61505926": "https://x.com/i/status/2069014496086217116",
    "61506092": "https://x.com/i/status/2069014496086217116",
    "61559100": "https://x.com/i/status/2073706172318916924",
}

# Group by post
groups = {}
for oid, link in REFILL_DISABLED_ORDERS.items():
    groups.setdefault(link, []).append(oid)

state = load_state()
smmfollows = next(p for p in PANELS if p["name"] == "smmfollows" and p["key"])

# ── Step 1: Submit tickets via web UI ──────────────────────────────────────────
print("=== Submitting retweet non-delivery tickets ===\n")
sess = _panel_session()
if not sess:
    print("ERROR: Panel login failed")
    sys.exit(1)

submitted = 0
for link, order_ids in groups.items():
    qty_total = sum(
        state["orders"].get(oid, {}).get("quantity", 0)
        for oid in order_ids
    )
    message = (
        f"Hello,\n\n"
        f"The following retweet orders show as 'Completed' in the panel but "
        f"the retweets were NEVER delivered (or dropped to 0 immediately).\n"
        f"The service has 'Refill is disabled' so we cannot request a refill.\n"
        f"Please replace or compensate these orders.\n\n"
        f"Post: {link}\n\n"
        f"Orders:\n" +
        "\n".join(
            f"  - #{oid}: {state['orders'].get(oid,{}).get('quantity',0)}x retweets — Completed, not delivered"
            for oid in order_ids
        ) +
        f"\n\nTotal retweets not delivered: {qty_total}\n"
        f"Kindly re-deliver or issue credit. Thank you."
    )
    try:
        r = sess.get(f"{PANEL_URL}/tickets", timeout=20)
        m = re.search(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"', r.text)
        if not m:
            print(f"  SKIP {link[:40]}: CSRF not found")
            continue
        r2 = sess.post(f"{PANEL_URL}/ticket-create", data={
            "_csrf": m.group(1),
            "TicketForm[subject]": "Junior - Orders [ Retweets Not Delivered ]",
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
            print(f"  TICKET SUBMITTED for {link[-30:]} — orders: {', '.join('#'+o for o in order_ids)}")
            submitted += 1
        else:
            print(f"  WARN {link[-30:]}: {resp}")
    except Exception as e:
        print(f"  ERROR {link[-30:]}: {e}")

print(f"\nTickets submitted: {submitted}/{len(groups)}\n")

# ── Step 2: Reorder 40 retweets with NON-DROP + 30-day refill service ──────────
POST_URL   = "https://x.com/i/status/2073706172318916924"
SVC_ID     = "13139"   # smmfollows — Refill Button: 30 Days — $0.54/k
QUANTITY   = 40

print(f"=== Placing new NON-DROP retweet order (svc#{SVC_ID}, 30-day refill) ===")
try:
    res = _api_panel(smmfollows, {
        "action": "add",
        "service": SVC_ID,
        "link": POST_URL,
        "quantity": QUANTITY,
    })
    if res.get("order"):
        new_oid = str(res["order"])
        print(f"SUCCESS — order #{new_oid} placed: {QUANTITY}x retweets svc#{SVC_ID} @ $0.54/k (30-day refill)")
        state["orders"][new_oid] = {
            "id": new_oid, "kind": "retweets", "link": POST_URL,
            "quantity": QUANTITY, "refillable": True, "status": "Pending",
            "panel": "smmfollows", "service_id": SVC_ID,
            "start_count": None, "remains": None,
            "added_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
        }
        log_agent(state, f"[RT-Replacement] #{new_oid}: {QUANTITY}x retweets svc#{SVC_ID} non-drop+refill for {POST_URL}")
    else:
        print(f"FAILED: {res}")
except Exception as e:
    print(f"ERROR: {e}")

save_state(state)
print("\nState saved.")
