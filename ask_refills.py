#!/usr/bin/env python3
"""
Ask for refills on all completed smmfollows orders from the last 30 days.
Two-pronged approach:
  1. API refill endpoint (action=refill) — instant, no web login needed
  2. Also flags for ticket-based refill (submitted via GitHub Actions mode=tickets)
"""
import sys, json
sys.path.insert(0, "/home/user/BlockChain-")
from automation import (
    load_state, save_state, log_agent, PANELS,
    _api_panel, datetime, timezone, timedelta
)

state = load_state()
sf = next(p for p in PANELS if p["name"] == "smmfollows" and p["key"])

# ── 1. Gather all completed orders from last 30 days ─────────────────────────
cutoff = datetime.now(timezone.utc) - timedelta(days=30)
candidates = {}
for oid, o in state.get("orders", {}).items():
    if o.get("panel") != "smmfollows":
        continue
    try:
        dt = datetime.fromisoformat(o.get("added_at", "").replace("Z", "+00:00"))
        if dt < cutoff:
            continue
    except Exception:
        continue
    candidates[oid] = o

print(f"Found {len(candidates)} smmfollows orders in last 30 days")

# ── 2. Live-check status ──────────────────────────────────────────────────────
ids = list(candidates.keys())
live = {}
for i in range(0, len(ids), 20):
    batch = ids[i:i+20]
    res = _api_panel(sf, {"action": "status", "orders": ",".join(batch)})
    if isinstance(res, list):
        for r in res:
            live[str(r.get("order", ""))] = r

for oid in ids:
    if oid not in live:
        r = _api_panel(sf, {"action": "status", "order": oid})
        if r.get("status"):
            live[oid] = r

print(f"Got live status for {len(live)}/{len(candidates)} orders\n")

# ── 3. Classify orders ────────────────────────────────────────────────────────
# Refill-eligible: Completed + start_count >= 5 (real delivery happened)
# Skip non-delivery orders (start_count < 5) — those need tickets, not refills
refill_eligible = []
non_delivery    = []
skipped         = []

for oid, o in candidates.items():
    lv       = live.get(oid, {})
    status   = lv.get("status", o.get("status", ""))
    start    = int(lv.get("start_count") or 0)
    remains  = int(lv.get("remains") or 0)
    qty      = o.get("quantity", 0)
    kind     = o.get("kind", "?")
    svc      = o.get("service_id", "?")

    if status in ("Completed", "Partial") and start >= 5:
        refill_eligible.append((oid, o, start, remains))
    elif status in ("Completed", "Partial") and start < 5 and remains == 0:
        non_delivery.append((oid, o, start))
    else:
        skipped.append((oid, o, status))

print(f"Refill-eligible (real delivery, start≥5): {len(refill_eligible)}")
print(f"Non-delivery (start<5): {len(non_delivery)}")
print(f"Other/skipped: {len(skipped)}")
print()

# ── 4. Trigger API refills ────────────────────────────────────────────────────
already_refilled = set(state.get("refills", {}).keys())
state.setdefault("refills", {})

print("=" * 60)
print("TRIGGERING API REFILLS")
print("=" * 60)

refill_ok   = []
refill_fail = []

for oid, o, start, remains in refill_eligible:
    if oid in already_refilled and state["refills"][oid].get("status") == "Pending":
        print(f"  #{oid} {o['kind']:<10} — already pending refill, skipping")
        continue

    print(f"  #{oid} {o['kind']:<10} qty={o['quantity']:<7} svc#{o.get('service_id','?')} "
          f"start={start} — requesting refill...")
    try:
        res = _api_panel(sf, {"action": "refill", "order": oid})
        if res.get("refill") or res.get("status") == "success" or res.get("id"):
            rfid = str(res.get("refill") or res.get("id") or "ok")
            print(f"    SUCCESS → refill #{rfid}")
            state["refills"][oid] = {
                "order_id": oid, "refill_id": rfid, "status": "Pending",
                "requested_at": datetime.now(timezone.utc).isoformat(),
            }
            log_agent(state, f"[refill] #{oid}: {o['kind']} refill requested → refill#{rfid}")
            refill_ok.append(oid)
        else:
            print(f"    RESPONSE: {res}")
            refill_fail.append((oid, str(res)))
    except Exception as e:
        print(f"    ERROR: {e}")
        refill_fail.append((oid, str(e)))

print()
print("=" * 60)
print(f"API REFILL SUMMARY: {len(refill_ok)} triggered, {len(refill_fail)} failed")
print("=" * 60)
if refill_fail:
    print("Failed:")
    for oid, reason in refill_fail:
        print(f"  #{oid}: {reason[:120]}")

# ── 5. Log non-delivery orders for ticket action ──────────────────────────────
if non_delivery:
    print()
    print("=" * 60)
    print(f"NON-DELIVERY ORDERS ({len(non_delivery)}) — Need tickets, not refills")
    print("These will be handled by: python automation.py --tickets")
    print("=" * 60)
    for oid, o, start in non_delivery:
        print(f"  #{oid} {o['kind']:<10} qty={o['quantity']:<7} svc#{o.get('service_id','?')} start={start}")

save_state(state)
print()
print("State saved.")
print()
print("Next step: trigger GitHub Actions mode=tickets to submit web-based refill requests")
