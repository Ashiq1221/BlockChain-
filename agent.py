#!/usr/bin/env python3
"""
SMMFollows AI Agent
-------------------
Powered by Claude — places Likes, Comments, and Retweets autonomously,
monitors every order, and auto-refills whenever a refill becomes eligible.

Usage:
  python agent.py run              # start the autonomous agent loop
  python agent.py list-services    # print your service catalogue and exit
  python agent.py balance          # print account balance and exit
  python agent.py once             # run one full cycle then exit (great for cron)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

import anthropic

import config
from agent_tools import AgentTools, OrderRegistry, TOOL_DEFINITIONS
from smm_client import SMMClient, SMMError

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log"),
    ],
)
log = logging.getLogger(__name__)


# ── tool dispatch ─────────────────────────────────────────────────────────────

def dispatch_tool(tools: AgentTools, name: str, inp: dict) -> str:
    """Route a tool call from Claude to the right AgentTools method."""
    mapping = {
        "get_balance":          lambda: tools.get_balance(),
        "list_services":        lambda: tools.list_services(),
        "place_likes":          lambda: tools.place_likes(**inp),
        "place_retweets":       lambda: tools.place_retweets(**inp),
        "place_comments":       lambda: tools.place_comments(**inp),
        "check_all_orders":     lambda: tools.check_all_orders(),
        "check_order":          lambda: tools.check_order(**inp),
        "refill_order":         lambda: tools.refill_order(**inp),
        "auto_refill_all":      lambda: tools.auto_refill_all(),
        "check_refill_statuses":lambda: tools.check_refill_statuses(),
        "get_summary":          lambda: tools.get_summary(),
    }
    fn = mapping.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        log.exception("Tool %s raised: %s", name, exc)
        return json.dumps({"error": str(exc)})


# ── single agent cycle ─────────────────────────────────────────────────────────

def run_agent_cycle(
    ai: anthropic.Anthropic,
    tools: AgentTools,
    task_prompt: str,
    *,
    max_iterations: int = 20,
) -> str:
    """
    Run one autonomous Claude agent cycle.
    Claude drives tool calls until it decides it's done (stop_reason='end_turn').
    Returns Claude's final text summary.
    """
    messages: list[dict] = [{"role": "user", "content": task_prompt}]
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        log.debug("Agent iteration %d", iteration)

        response = ai.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            system=config.AGENT_PERSONA,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        # Collect any text the agent produced this turn
        text_parts = [b.text for b in response.content if hasattr(b, "text")]
        if text_parts:
            log.info("[Agent] %s", " ".join(text_parts))

        # Done — no more tool calls
        if response.stop_reason == "end_turn":
            return " ".join(text_parts) or "Agent cycle complete."

        # Process all tool calls in this response
        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            log.info("  -> Calling tool: %s  args=%s", block.name, block.input)
            result = dispatch_tool(tools, block.name, block.input)
            log.info("     Result: %s", result[:300])
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": block.id,
                "content":     result,
            })

        # Feed results back to Claude
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user",      "content": tool_results})

    return "Agent reached max iterations."


# ── main bot loop ──────────────────────────────────────────────────────────────

INITIAL_TASK = """\
You are managing a social media growth campaign for the following post URLs:

{links}

Your tasks for this cycle:
1. Call get_balance to confirm the account has funds.
2. Call list_services to identify the correct service IDs for:
   - Twitter/X Likes
   - Twitter/X Retweets
   - Twitter/X Comments
3. For EACH URL above:
   a. Place a likes order ({likes_qty} likes).
   b. Place a retweets order ({retweets_qty} retweets).
   c. Generate {comments_qty} natural, engaging comments relevant to a social media post,
      then place a comments order with those comments.
4. Call check_all_orders and auto_refill_all.
5. Report the summary using get_summary.
"""

MONITOR_TASK = """\
You are monitoring an ongoing social media growth campaign.

Your tasks for this monitoring cycle:
1. Call check_all_orders to get the latest status of all orders.
2. Call auto_refill_all to refill any completed or partial orders.
3. Call check_refill_statuses to report on pending refills.
4. Call get_summary and report the current state of the campaign.
5. If any order has failed or been cancelled, note it.
"""


class SMMAgent:
    def __init__(self) -> None:
        self.smm_client  = SMMClient(config.SMM_API_KEY, config.SMM_API_URL)
        self.registry    = OrderRegistry()
        self.tools       = AgentTools(self.smm_client, self.registry)
        self.ai          = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def run_once(self) -> None:
        """Run one initial placement cycle — useful for cron / one-shot."""
        log.info("=== SMMFollows AI Agent — one-shot cycle ===")
        task = INITIAL_TASK.format(
            links        = "\n".join(f"  - {u}" for u in config.TARGET_LINKS),
            likes_qty    = config.DEFAULT_LIKES_QTY,
            retweets_qty = config.DEFAULT_RETWEETS_QTY,
            comments_qty = config.DEFAULT_COMMENTS_QTY,
        )
        summary = run_agent_cycle(self.ai, self.tools, task)
        log.info("Cycle complete: %s", summary)

    def run(self) -> None:
        """Continuous loop: initial orders, then periodic monitoring + refill."""
        log.info("=== SMMFollows AI Agent starting ===")
        log.info("Targets: %s", config.TARGET_LINKS)

        # Initial placement
        self.run_once()

        log.info(
            "Entering monitor loop (every %ds) — Ctrl-C to stop",
            config.AGENT_THINK_SEC,
        )
        while True:
            time.sleep(config.AGENT_THINK_SEC)
            log.info("--- Monitor cycle ---")
            try:
                summary = run_agent_cycle(self.ai, self.tools, MONITOR_TASK)
                log.info("Monitor cycle: %s", summary)
            except anthropic.APIError as exc:
                log.error("Claude API error: %s", exc)
            except SMMError as exc:
                log.error("SMM API error: %s", exc)
            except Exception as exc:  # noqa: BLE001
                log.exception("Unexpected error in monitor cycle: %s", exc)


# ── CLI ───────────────────────────────────────────────────────────────────────

def cmd_run(_args: argparse.Namespace) -> None:
    SMMAgent().run()


def cmd_once(_args: argparse.Namespace) -> None:
    SMMAgent().run_once()


def cmd_balance(_args: argparse.Namespace) -> None:
    client = SMMClient(config.SMM_API_KEY, config.SMM_API_URL)
    try:
        data = client.balance()
        print(f"Balance: {data.get('balance')} {data.get('currency','')}")
    except SMMError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_list_services(_args: argparse.Namespace) -> None:
    client = SMMClient(config.SMM_API_KEY, config.SMM_API_URL)
    try:
        svcs = client.services()
    except SMMError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'ID':<8} {'Category':<20} {'Name':<45} {'Rate':<10} {'Min':<8} {'Max':<10} {'Refill'}")
    print("-" * 110)
    for s in svcs:
        print(
            f"{str(s.get('service','')):<8} "
            f"{str(s.get('category',''))[:20]:<20} "
            f"{str(s.get('name',''))[:45]:<45} "
            f"{str(s.get('rate','')):<10} "
            f"{str(s.get('min','')):<8} "
            f"{str(s.get('max','')):<10} "
            f"{s.get('refill', False)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SMMFollows AI Agent — Claude-powered likes, comments, retweets & auto-refill"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run",           help="Start continuous agent loop (default)")
    sub.add_parser("once",          help="Run one placement cycle then exit")
    sub.add_parser("balance",       help="Print account balance and exit")
    sub.add_parser("list-services", help="Print full service catalogue and exit")

    args = parser.parse_args()

    dispatch = {
        "run":           cmd_run,
        "once":          cmd_once,
        "balance":       cmd_balance,
        "list-services": cmd_list_services,
    }
    dispatch.get(args.command or "run", cmd_run)(args)


if __name__ == "__main__":
    main()
