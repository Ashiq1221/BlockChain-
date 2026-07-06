#!/usr/bin/env python3
"""Submit non-delivery tickets for all retweet orders where refill is disabled."""
import sys, re
sys.path.insert(0, "/home/user/BlockChain-")
from automation import load_state, PANELS, _panel_session

PANEL_URL = "https://smmfollows.com"

# Orders confirmed "Refill is disabled" — panel charged but retweets dropped
REFILL_DISABLED = {
    "61500416": "https://x.com/i/status/2064283937091035590",
    "61505279": "https://x.com/i/status/2070034213085274431",
    "61505926": "https://x.com/i/status/2069014496086217116",
    "61506092": "https://x.com/i/status/2069014496086217116",
    "61559100": "https://x.com/i/status/2073706172318916924",
}

state = load_state()
orders = state["orders"]

# Group by post link
groups: dict = {}
for oid, link in REFILL_DISABLED.items():
    groups.setdefault(link, []).append(oid)

sess = _panel_session()
if not sess:
    print("ERROR: Panel login failed"); sys.exit(1)
print(f"Logged in. Submitting {len(groups)} ticket(s)...\n")

submitted = failed = 0
for link, ids in groups.items():
    qty_total = sum(orders.get(o, {}).get("quantity", 0) for o in ids)
    message = (
        "Hello,\n\n"
        "The following retweet orders show as 'Completed' in the panel but "
        "the retweets were never delivered (or dropped to 0 immediately). "
        "The service has 'Refill is disabled' so a refill cannot be requested.\n"
        "Please re-deliver or issue credit for these orders.\n\n"
        f"Post: {link}\n\n"
        "Orders:\n" +
        "\n".join(
            f"  - #{o}: {orders.get(o,{}).get('quantity',0)}x retweets — Completed, not delivered"
            for o in ids
        ) +
        f"\n\nTotal undelivered retweets: {qty_total}\n\nThank you."
    )
    try:
        r = sess.get(f"{PANEL_URL}/tickets", timeout=20)
        m = re.search(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"', r.text)
        if not m:
            print(f"  SKIP {link[-35:]}: CSRF not found"); failed += 1; continue
        r2 = sess.post(f"{PANEL_URL}/ticket-create", data={
            "_csrf": m.group(1),
            "TicketForm[subject]": "Junior - Orders [ Retweets Not Delivered ]",
            "TicketForm[message]": message,
            "subject": "Orders", "request": "Not delivered",
            "cancel-reason": "", "ordernumbers": ",".join(ids),
        }, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{PANEL_URL}/tickets", "Origin": PANEL_URL,
            "Accept": "application/json, */*", "X-Requested-With": "XMLHttpRequest",
        }, timeout=20)
        resp = r2.json() if r2.status_code == 200 else {}
        if resp.get("status") == "success":
            print(f"  OK  {link[-40:]}  orders: {', '.join('#'+o for o in ids)}")
            submitted += 1
        else:
            print(f"  WARN {link[-40:]}: {resp}"); failed += 1
    except Exception as e:
        print(f"  ERR {link[-40:]}: {e}"); failed += 1

print(f"\nDone. Submitted: {submitted}  Failed: {failed}")
