#!/usr/bin/env python3
"""
Order: https://x.com/i/status/2073706172318916924
Non-drop + 30-day refill services only.
"""
import sys
sys.path.insert(0, "/home/user/BlockChain-")

from automation import (
    load_state, save_state, log_agent,
    CloudflarePlatform, run_agent_cycle, sync_to_d1
)

POST_URL = "https://x.com/i/status/2073706172318916924"

TASK = f"""\
ORDER FOR POST — hand entirely to the multi-agent council system.

Post: {POST_URL}

Exact quantities (DO NOT change these under any circumstances):
  • 100  likes      — NON-DROP, 30-day refill guarantee
  •  40  retweets   — NON-DROP, 30-day refill guarantee
  •  20  comments   — NON-DROP, 30-day refill guarantee, AI-generated CUSTOM comments
  •  40000 views    — NON-DROP, 30-day refill guarantee

CRITICAL SERVICE REQUIREMENTS (must satisfy ALL):
1. NON-DROP only — reject any service that does not explicitly offer non-drop/HQ/stable delivery.
2. 30-day refill — reject any service with no refill or refill < 30 days.
3. For retweets: quantity is 40 — find a panel/service whose minimum is ≤ 40.
   smmfollows retweet min is 100 so try smmwiz or astrasmm for retweets.
4. For comments: generate 20 AI-custom comments relevant to the actual post content.
5. Never substitute a standard package. Deliver exactly the quantities listed above.

Agent instructions:
1. Call get_pending_posts — the post above is already queued.
2. For EACH of the 4 order types (likes, retweets, comments, views):
   - Fetch the FULL LIVE service catalog from ALL panels.
   - Filter to NON-DROP services with 30-day refill that support the required quantity.
   - Convene the 10-agent Order Placement Council (3-round debate, ≥60% threshold).
   - Only place the order if council approves.
3. For comments: call generate_comments first to produce 20 custom comments.
4. Call clear_pending_post after all 4 orders are placed.
5. Report council vote outcome and order ID for each.

Do NOT apply the standard engagement package. Exact quantities above are locked.
"""

state = load_state()
if POST_URL not in state.get("pending_posts", []):
    state.setdefault("pending_posts", []).append(POST_URL)
    save_state(state)

print("=" * 65)
print("Handing off to 30-agent council system...")
print(f"Post   : {POST_URL}")
print("Orders : 100 likes | 40 retweets | 20 custom comments | 40k views")
print("Service: NON-DROP + 30-day refill only")
print("=" * 65)

cf = CloudflarePlatform()
cf.load_from_state(state)

summary = run_agent_cycle(state, TASK, cf)

log_agent(state, f"[ORDER-2073706172318916924] {summary[:200]}")
save_state(state)
sync_to_d1(state, cf)

print("\n" + "=" * 65)
print("Agent council summary:")
print(summary)
print("=" * 65)
