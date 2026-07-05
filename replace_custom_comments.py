#!/usr/bin/env python3
"""
Cancel generic comments order #30232527 and replace with AI-generated custom comments
for post https://x.com/i/status/2073706172318916924 (LingoAI Jeju Island summit post).
"""
import sys, json, os
sys.path.insert(0, "/home/user/BlockChain-")

from automation import (
    load_state, save_state, log_agent,
    CloudflarePlatform, _generate_comments, _api_panel,
    _ai_order_agent, _master_controller_gate, PANELS
)

POST_URL  = "https://x.com/i/status/2073706172318916924"
OLD_ORDER = "30232527"
QUANTITY  = 20

POST_TEXT = (
    "LingoAI Ecosystem Update from Jeju Island, South Korea. "
    "Our CEO took the main stage at the 'Rise Beyond Intelligence' AI Industry Summit "
    "to deliver a powerful keynote: 'Decentralized Multilingual Data Infrastructure: "
    "Empowering the Global Majority to Own Data'. LingoAI is building decentralized "
    "AI infrastructure for multilingual data ownership."
)

state = load_state()

# ── Step 1: Cancel the existing generic comments order ─────────────────────────────────
print(f"Cancelling old comments order #{OLD_ORDER} on smmwiz...")
smmwiz = next((p for p in PANELS if p["name"] == "smmwiz" and p["key"]), None)
if smmwiz:
    try:
        cancel_res = _api_panel(smmwiz, {"action": "cancel", "order": OLD_ORDER})
        print(f"  Cancel response: {cancel_res}")
    except Exception as e:
        print(f"  Cancel failed: {e} — proceeding anyway")
else:
    print("  smmwiz not configured — skipping cancel")

# Update state to mark old order cancelled
if OLD_ORDER in state["orders"]:
    state["orders"][OLD_ORDER]["status"] = "Canceled"
    print(f"  Marked #{OLD_ORDER} as Canceled in local state")

# ── Step 2: Generate 20 custom AI comments ────────────────────────────────────────────────────
print(f"\nGenerating 20 custom AI comments for the post...")
cf = CloudflarePlatform()
cf.load_from_state(state)

comments_text = _generate_comments(POST_TEXT, QUANTITY, cf)
comments_list = [c.strip() for c in comments_text.split("\n") if c.strip()]

print(f"  Generated {len(comments_list)} comments:")
for i, c in enumerate(comments_list, 1):
    print(f"  {i:2d}. {c}")

if len(comments_list) < 5:
    print("ERROR: Too few comments generated. Aborting.")
    sys.exit(1)

# ── Step 3: Place new order with custom comments ──────────────────────────────────────────
print(f"\nPlacing new custom comments order (qty={QUANTITY})...")

# Lock check
allowed, reason = _master_controller_gate("comments", QUANTITY)
if not allowed:
    print(f"BLOCKED by Master Controller: {reason}")
    sys.exit(1)

extra = {"comments": comments_text}
res = _ai_order_agent("comments", QUANTITY, POST_URL, extra, cf)

if res.get("success"):
    new_oid = str(res["order"])
    print(f"\nSUCCESS — new order #{new_oid} on {res['panel']} svc#{res['service_id']}")
    state["orders"][new_oid] = {
        "id": new_oid, "kind": "comments", "link": POST_URL,
        "quantity": QUANTITY, "refillable": False, "status": "Pending",
        "panel": res["panel"], "start_count": None, "remains": None,
        "added_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "completed_at": None,
    }
    log_agent(state, f"[CustomComments] Replaced #{OLD_ORDER} with #{new_oid} — 20 AI-custom comments for {POST_URL}")
else:
    print(f"\nFAILED: {res.get('error')}")
    log_agent(state, f"[CustomComments] Failed to replace #{OLD_ORDER}: {res.get('error')}")

save_state(state)
print("\nState saved.")
