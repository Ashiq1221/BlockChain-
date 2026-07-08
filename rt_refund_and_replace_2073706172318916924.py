#!/usr/bin/env python3
"""
Step 1: Submit refund/re-delivery ticket for all failed retweet orders on post 2073706172318916924.
Step 2: Place 500 replacement retweets using svc#9260 (Real SuperInstant, 30-day refill, $2.30/k).

Failed RT orders (all show Completed, 0 delivered):
  #61559100 — 40 RT (original service)
  #61564364 — 40 RT (svc#13139, 1st replacement attempt)
  #61564515 — 500 RT (svc#13139, 2nd replacement attempt)
"""
import sys
sys.path.insert(0, "/home/user/BlockChain-")
from automation import (
    load_state, save_state, log_agent, PANELS,
    _api_panel, _panel_session,
    datetime, timezone
)
import re

POST_URL = "https://x.com/i/status/2073706172318916924"

FAILED_RT_ORDERS = [
    ("61559100", 40,  "unknown",  "Completed, start=1, remains=0 — 0 delivered"),
    ("61564364", 40,  "13139",    "Completed, start=0, remains=0 — 0 delivered"),
    ("61564515", 500, "13139",    "Completed, start=1, remains=0 — 0 delivered"),
]
TOTAL_FAILED_QTY = sum(qty for _, qty, _, _ in FAILED_RT_ORDERS)

REPLACEMENT_SVC  = 9260    # Real SuperInstant Retweets — 30-day refill, $2.30/k
REPLACEMENT_QTY  = 500
REPLACEMENT_RATE = 2.30    # per 1000
REPLACEMENT_COST = REPLACEMENT_QTY / 1000 * REPLACEMENT_RATE   # $1.15

state = load_state()
sf = next(p for p in PANELS if p["name"] == "smmfollows" and p["key"])

# ── Step 1: Check balance ────────────────────────────────────────────────────
bal_res = _api_panel(sf, {"action": "balance"})
balance = float(bal_res.get("balance", 0))
print(f"Current balance: ${balance:.4f}")
print(f"Replacement cost: ${REPLACEMENT_COST:.4f}  ({'OK' if balance >= REPLACEMENT_COST else 'INSUFFICIENT'})\n")

# ── Step 2: Submit ticket via web session ────────────────────────────────────
print("Submitting refund/re-delivery ticket for failed RT orders...")
sess = None
try:
    sess = _panel_session(sf)
except Exception as e:
    print(f"  [!] Panel session failed: {e}")
    print("  [!] Ticket must be submitted via GitHub Actions (mode=tickets).")
    print("  [!] Trigger: python automation.py --tickets")

if sess:
    PANEL_URL = sf["web"]
    order_ids = [oid for oid, _, _, _ in FAILED_RT_ORDERS]
    lines = "\n".join(
        f"  - #{oid}: {qty}x retweets svc#{svc_id} — {note}"
        for oid, qty, svc_id, note in FAILED_RT_ORDERS
    )
    message = (
        "Hello,\n\n"
        f"The following retweet orders for post {POST_URL} all show as \"Completed\" "
        "but ZERO retweets were actually delivered. The post engagement count did not change "
        "after any of these orders. start_count was ≤1 on all orders.\n\n"
        f"Total quantity paid for: {TOTAL_FAILED_QTY} retweets — 0 delivered.\n\n"
        f"Failed orders:\n{lines}\n\n"
        "Please issue a FULL REFUND or account credit for all 3 orders. "
        "We are placing a replacement order with a different service (svc#9260) as these services "
        "appear to not be functioning.\n\n"
        "Thank you."
    )
    subject = "Junior - Orders [ Retweets Not Delivered — Full Refund Request ]"

    try:
        r = sess.get(f"{PANEL_URL}/tickets", timeout=20)
        m = re.search(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"', r.text)
        if not m:
            print("  [!] CSRF token not found — session may not be valid")
        else:
            csrf = m.group(1)
            r2 = sess.post(f"{PANEL_URL}/ticket-create", data={
                "_csrf": csrf,
                "TicketForm[subject]": subject,
                "TicketForm[message]": message,
                "subject": "Orders",
                "request": "Not delivered",
                "cancel-reason": "",
                "ordernumbers": ",".join(order_ids),
            }, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{PANEL_URL}/tickets",
                "Origin": PANEL_URL,
                "Accept": "application/json, */*",
                "X-Requested-With": "XMLHttpRequest",
            }, timeout=20)
            resp = r2.json() if r2.status_code == 200 else {}
            if resp.get("status") == "success":
                print(f"  TICKET SUBMITTED — orders {order_ids}")
                state.setdefault("tickets_submitted", {})
                for oid in order_ids:
                    state["tickets_submitted"][oid] = datetime.now(timezone.utc).isoformat()
                log_agent(state, f"[ticket] Refund ticket submitted for failed RT orders {order_ids} on {POST_URL}")
            else:
                print(f"  [!] Ticket response: {resp}")
    except Exception as e:
        print(f"  [!] Ticket submission error: {e}")
        print("  [!] Will be submitted next time GitHub Actions runs with mode=tickets")

# ── Step 3: Place replacement RT order (svc#9260) ────────────────────────────
print(f"\nPlacing {REPLACEMENT_QTY}x replacement retweets (svc#{REPLACEMENT_SVC}, 30-day refill)...")
print(f"  Cost: ${REPLACEMENT_COST:.4f}  |  Balance: ${balance:.4f}")

if balance < REPLACEMENT_COST:
    print("  [!] Insufficient balance — please top up and re-run.")
    save_state(state)
    sys.exit(1)

try:
    res = _api_panel(sf, {
        "action":   "add",
        "service":  REPLACEMENT_SVC,
        "link":     POST_URL,
        "quantity": REPLACEMENT_QTY,
    })
    if res.get("order"):
        oid = str(res["order"])
        print(f"  SUCCESS → order #{oid}  ({REPLACEMENT_QTY}x RT svc#{REPLACEMENT_SVC} @ ${REPLACEMENT_RATE}/k)")
        state["orders"][oid] = {
            "id": oid, "kind": "retweets", "link": POST_URL,
            "quantity": REPLACEMENT_QTY, "refillable": True, "status": "Pending",
            "panel": "smmfollows", "service_id": str(REPLACEMENT_SVC),
            "start_count": None, "remains": None,
            "added_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
        }
        log_agent(state, f"[RT-replacement-svc9260] #{oid}: {REPLACEMENT_QTY}x retweets svc#{REPLACEMENT_SVC} 30d-refill for {POST_URL}")
        save_state(state)
        print("  State saved.")
    else:
        print(f"  FAILED: {res}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\nDone.")
print(f"  Ticket: {'submitted' if sess else 'pending GitHub Actions (mode=tickets)'}")
print(f"  Replacement RT order: see above")
