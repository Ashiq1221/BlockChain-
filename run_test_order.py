#!/usr/bin/env python3
"""
One-time test handoff — delegates entirely to the multi-agent council system.
Agents decide which panel, which service, best rate. Humans do not intervene.
"""
import sys
sys.path.insert(0, "/home/user/BlockChain-")

from automation import (
    load_state, save_state, log_agent,
    CloudflarePlatform, run_agent_cycle, sync_to_d1
)

POST_URL = "https://x.com/i/status/2069014496086217116"

TEST_TASK = f"""\
ONE-TIME TEST ORDER — hand this entirely to the multi-agent council system.

Post: {POST_URL}

Exact quantities requested by user:
  • 21  likes
  • 5   comments  (AI-generate custom comments relevant to the post content)
  • 10  retweets

Instructions for agents:
1. Call get_pending_posts — the post above is already queued.
2. For EACH of the 3 order types (likes, comments, retweets):
   - Fetch the full live service catalog from ALL panels via the AI agent system.
   - Convene the 10-agent Order Placement Council for a full 3-round debate.
   - Only place the order if the council approves (≥60% vote).
   - Never change the quantity — deliver exactly what was asked.
3. For comments: generate AI custom comments relevant to the actual post text.
4. Call clear_pending_post after all 3 orders are placed.
5. Report the outcome of each council vote and each order placed.

This is a one-time test — do NOT apply the standard 8-hour engagement package.
Agents have full authority to reject any order if the council finds a reason to.
"""

state = load_state()
if POST_URL not in state.get("pending_posts", []):
    state.setdefault("pending_posts", []).append(POST_URL)
    save_state(state)

print("=" * 60)
print("Handing off to 30-agent council system...")
print(f"Post  : {POST_URL}")
print("Orders: 21 likes | 5 comments | 10 retweets")
print("=" * 60)

cf = CloudflarePlatform()
cf.load_from_state(state)

summary = run_agent_cycle(state, TEST_TASK, cf)

log_agent(state, f"[TEST] {summary[:200]}")
save_state(state)
sync_to_d1(state, cf)

print("\n" + "=" * 60)
print("Agent council summary:")
print(summary)
print("=" * 60)
