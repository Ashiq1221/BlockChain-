#!/usr/bin/env python3
"""
SMMFollows AI Manager
---------------------
Claude acts as a senior SMM strategist who monitors all orders,
makes intelligent refill decisions, knows when to wait vs escalate,
and only places orders when you share a link.

Usage:
  python automation.py                        # run monitoring loop forever
  python automation.py --once                 # single AI cycle and exit
  python automation.py --status               # print dashboard and exit
  python automation.py --post URL             # queue a post URL for AI to order
  python automation.py --refill               # trigger AI refill pass now
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import requests

# ── Config (loaded from environment / .env file) ──────────────────────────────────────────────

def _load_env() -> None:
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                import os
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

import os

API_KEY          = os.environ.get("SMM_API_KEY", "")
API_URL          = "https://smmfollows.com/api/v2"
PANEL            = "https://smmfollows.com"
USER             = os.environ.get("SMM_USER", "hhrh197")
PASSWD           = os.environ.get("SMM_PASS", "Yawer@123")
ANTHROPIC_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
DEEPSEEK_KEY     = os.environ.get("DEEPSEEK_API_KEY", "")
HAPPY_HORSE_KEY  = os.environ.get("HAPPY_HORSE_API_KEY", "")
CF_ACCOUNT_ID    = os.environ.get("CF_ACCOUNT_ID", "")
CF_AI_MODEL      = os.environ.get("CF_AI_MODEL", "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b")
CF_GLOBAL_KEY    = os.environ.get("CF_GLOBAL_API_KEY", "")
CF_EMAIL         = os.environ.get("CF_EMAIL", "")
CLAUDE_MODEL     = "claude-sonnet-4-6"
DEEPSEEK_MODEL   = "deepseek-chat"

# AI priority: Cloudflare Workers AI (DeepSeek R1) → direct DeepSeek → Claude → rule-based
AI_PRIORITY = ["cloudflare", "deepseek", "claude", "rules"]

# Service catalogue (verified from your account)
SERVICES = {
    "likes":    {"id": 12452, "name": "Twitter Likes Turkey HQ", "refill": True,  "min": 10,  "max": 15000, "rate_per_k": 0.88},
    "retweets": {"id": 13139, "name": "Twitter Retweets HQ",     "refill": True,  "min": 10,  "max": 1000000,"rate_per_k": 0.54},
    "comments": {"id": 7338,  "name": "Twitter Comments USA",    "refill": False, "min": 5,   "max": 150,   "rate_per_k": 28.13},
    "views":    {"id": 17682, "name": "Twitter Views HQ",        "refill": False, "min": 100, "max": 100000000, "rate_per_k": 1.5},
}

STATE_FILE = Path("automation_state.json")
POLL_SECS  = 300   # check orders every 5 min

# ── Logging ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("automation.log"),
    ],
)
log = logging.getLogger(__name__)

# ── State ─────────────────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "orders": {},        # order_id -> order info
        "refills": {},       # order_id -> refill info
        "pending_posts": [], # URLs queued by user for ordering
        "posts": [],         # all tracked post URLs
        "agent_log": [],     # AI decision log (last 50 entries)
    }


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def log_agent(state: dict, msg: str) -> None:
    entry = {"at": datetime.now(timezone.utc).isoformat(), "msg": msg}
    state["agent_log"] = (state.get("agent_log", []) + [entry])[-50:]

# ── API helpers ───────────────────────────────────────────────────────────────────────────

def _api(payload: dict) -> dict:
    payload = dict(payload)
    payload["key"] = API_KEY
    r = requests.post(API_URL, data=payload, timeout=20)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:200]}


def _panel_session() -> requests.Session | None:
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    })
    try:
        r = sess.get(f"{PANEL}/", timeout=20)
        m = re.search(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"', r.text)
        if not m:
            return None
        sess.post(f"{PANEL}/", data={
            "_csrf": m.group(1),
            "LoginForm[username]": USER,
            "LoginForm[password]": PASSWD,
            "LoginForm[remember]": "1",
        }, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{PANEL}/",
            "Origin": PANEL,
        }, allow_redirects=True, timeout=20)
        return sess if "_identity_user" in sess.cookies else None
    except Exception:
        return None

# ── Tool implementations (what the AI can call) ────────────────────────────────────────────

def tool_get_balance() -> str:
    try:
        data = _api({"action": "balance"})
        return json.dumps({"balance": data.get("balance"), "currency": data.get("currency", "USD")})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_check_orders(state: dict) -> str:
    """Batch-check all tracked orders and update state."""
    ids = list(state["orders"].keys())
    if not ids:
        return json.dumps({"message": "No orders tracked yet."})
    try:
        if len(ids) == 1:
            raw = _api({"action": "status", "order": ids[0]})
            statuses = {ids[0]: raw}
        else:
            statuses = _api({"action": "status", "orders": ",".join(ids)})

        results = []
        now_utc = datetime.now(timezone.utc)

        for oid, info in statuses.items():
            order = state["orders"].get(oid)
            if not order:
                continue
            old_status = order.get("status", "?")
            new_status = info.get("status", old_status)
            order["status"]      = new_status
            order["remains"]     = info.get("remains")
            order["start_count"] = info.get("start_count")

            if new_status in ("Completed", "Partial") and not order.get("completed_at"):
                order["completed_at"] = now_utc.isoformat()

            cooldown_h = None
            if order.get("completed_at") and order.get("refillable"):
                try:
                    dt = datetime.fromisoformat(order["completed_at"])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    elapsed_h = (now_utc - dt).total_seconds() / 3600
                    cooldown_h = round(max(0, 24 - elapsed_h), 1)
                except Exception:
                    pass

            results.append({
                "order_id":    oid,
                "kind":        order.get("kind"),
                "link":        order.get("link"),
                "status":      new_status,
                "start_count": info.get("start_count"),
                "remains":     info.get("remains"),
                "quantity":    order.get("quantity"),
                "refillable":  order.get("refillable"),
                "refill_cooldown_h": cooldown_h,
                "refill_done": oid in state.get("refills", {}),
            })

        return json.dumps({"orders": results})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_trigger_refill(state: dict, order_id: str) -> str:
    """Attempt refill via API, fall back to panel."""
    order = state["orders"].get(order_id)
    if not order:
        return json.dumps({"error": f"Order {order_id} not tracked."})
    if not order.get("refillable"):
        return json.dumps({"error": f"Order {order_id} service does not support refill."})

    try:
        res = _api({"action": "refill", "order": order_id})
        if "refill" in res:
            state["refills"][order_id] = {
                "refill_id": res["refill"],
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "status": "Pending",
            }
            return json.dumps({"success": True, "refill_id": res["refill"], "method": "api"})
        err = res.get("error", str(res))
        sess = _panel_session()
        if sess:
            r = sess.get(f"{PANEL}/orders/{order_id}/refill", timeout=10, headers={
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
                "Referer": f"{PANEL}/orders",
            })
            if r.status_code == 200:
                j = r.json()
                if j.get("status") == "success":
                    state["refills"][order_id] = {
                        "refill_id": "panel",
                        "requested_at": datetime.now(timezone.utc).isoformat(),
                        "status": "Pending",
                    }
                    return json.dumps({"success": True, "method": "panel"})
                err = j.get("error", str(j))
        return json.dumps({"success": False, "error": err})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_check_refill_status(state: dict, order_id: str) -> str:
    refill = state.get("refills", {}).get(order_id)
    if not refill:
        return json.dumps({"message": f"No refill on record for order {order_id}."})
    rid = refill.get("refill_id")
    if not rid or rid == "panel":
        return json.dumps(refill)
    try:
        res = _api({"action": "refill_status", "refill": int(rid)})
        refill["status"] = res.get("status", refill["status"])
        return json.dumps({**refill, "api_response": res})
    except Exception as e:
        return json.dumps({"error": str(e), "cached": refill})


def tool_submit_ticket(state: dict, order_ids: list[str],
                       subject_type: str, message: str) -> str:
    """Submit a support ticket. Only called when AI decides it's necessary."""
    sess = _panel_session()
    if not sess:
        return json.dumps({"error": "Panel login failed."})
    try:
        r = sess.get(f"{PANEL}/tickets", timeout=20)
        m = re.search(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"', r.text)
        if not m:
            return json.dumps({"error": "Could not get CSRF token."})
        r2 = sess.post(f"{PANEL}/ticket-create", data={
            "_csrf": m.group(1),
            "TicketForm[subject]": f"Junior - Orders [ {subject_type} ]",
            "TicketForm[message]": message,
            "subject": "Orders",
            "request": subject_type,
            "cancel-reason": "",
            "ordernumbers": ",".join(order_ids),
        }, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{PANEL}/tickets",
            "Origin": PANEL,
            "Accept": "application/json, */*",
            "X-Requested-With": "XMLHttpRequest",
        }, timeout=20)
        ok = r2.status_code == 200 and r2.json().get("status") == "success"
        return json.dumps({"success": ok, "status_code": r2.status_code})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_place_order(state: dict, link: str, kind: str, quantity: int) -> str:
    """Place a single order. Only called when user has shared the link."""
    svc = SERVICES.get(kind)
    if not svc:
        return json.dumps({"error": f"Unknown kind: {kind}. Valid: {list(SERVICES.keys())}"})
    if quantity < svc["min"] or quantity > svc["max"]:
        return json.dumps({"error": f"Quantity {quantity} out of range [{svc['min']}, {svc['max']}] for {kind}"})
    try:
        res = _api({"action": "add", "service": svc["id"], "link": link, "quantity": quantity})
        oid = str(res.get("order", ""))
        if not oid:
            return json.dumps({"error": "No order ID returned", "response": res})
        state["orders"][oid] = {
            "id": oid, "kind": kind, "link": link, "quantity": quantity,
            "refillable": svc["refill"], "status": "Pending",
            "start_count": None, "remains": None,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        if link not in state["posts"]:
            state["posts"].append(link)
        return json.dumps({"success": True, "order_id": oid, "service": svc["name"],
                           "quantity": quantity, "link": link})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_get_services() -> str:
    """Return available service catalogue with rates and limits."""
    return json.dumps(SERVICES)


def tool_get_pending_posts(state: dict) -> str:
    """Return list of post URLs queued by the user for ordering."""
    return json.dumps({"pending_posts": state.get("pending_posts", [])})


def tool_clear_pending_post(state: dict, link: str) -> str:
    """Remove a post from the pending queue after orders are placed."""
    pending = state.get("pending_posts", [])
    if link in pending:
        pending.remove(link)
        state["pending_posts"] = pending
        return json.dumps({"success": True, "removed": link})
    return json.dumps({"message": "Not in pending list."})


# ── Tool definitions for Claude ───────────────────────────────────────────────────────────────────────────

TOOL_DEFS = [
    {
        "name": "get_balance",
        "description": "Check the current account balance.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "check_orders",
        "description": (
            "Fetch live status of all tracked orders. Returns order ID, kind, link, "
            "status, start_count, remains, quantity, refillable flag, hours until "
            "refill cooldown expires, and whether a refill has been attempted."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "trigger_refill",
        "description": (
            "Request a refill for a specific order. Only call when: "
            "(1) order is Completed or Partial, "
            "(2) service supports refill, "
            "(3) at least 24h have passed since completion, "
            "(4) a refill hasn't already been successfully triggered."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order ID to refill."},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "check_refill_status",
        "description": "Check the status of a previously triggered refill for an order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The order ID whose refill to check."},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "submit_ticket",
        "description": (
            "Submit a support ticket. Use sparingly — only when there is a clear "
            "service failure that cannot be resolved automatically. Do NOT ticket on "
            "first refill rejection (retry first). Do NOT ticket if a refill is in "
            "cooldown. Valid subject_type values: 'Refill', 'Cancellation', 'Other'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_ids":    {"type": "array", "items": {"type": "string"}, "description": "Affected order IDs."},
                "subject_type": {"type": "string", "description": "Ticket category: Refill | Cancellation | Other"},
                "message":      {"type": "string", "description": "Full ticket message to support."},
            },
            "required": ["order_ids", "subject_type", "message"],
        },
    },
    {
        "name": "place_order",
        "description": (
            "Place a new SMM order for a post URL. ONLY call this when the user has "
            "explicitly shared a link and it appears in pending_posts. "
            "Do NOT place orders spontaneously."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "link":     {"type": "string",  "description": "Full post URL."},
                "kind":     {"type": "string",  "description": "likes | retweets | comments | views"},
                "quantity": {"type": "integer", "description": "Number to order."},
            },
            "required": ["link", "kind", "quantity"],
        },
    },
    {
        "name": "get_services",
        "description": "Get the available service catalogue with IDs, rates, and limits.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_pending_posts",
        "description": "Get the list of post URLs queued by the user that need orders placed.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "clear_pending_post",
        "description": "Remove a post URL from the pending queue after all orders are placed for it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "link": {"type": "string", "description": "The post URL to remove from the queue."},
            },
            "required": ["link"],
        },
    },
]

# ── AI agent system prompt ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior social media marketing strategist and automation manager for a Twitter/X growth account. You have deep expertise in:

PLATFORM KNOWLEDGE
- Twitter/X algorithm: engagement velocity, recency signals, credibility thresholds
- Natural-looking growth patterns: staggered delivery, realistic ratios (likes:retweets ~3:1, comments take longer)
- Risk factors: sudden spikes trigger spam detection; accounts need organic-looking baselines
- Drop rates: SMM likes/retweets from bot accounts get removed by Twitter within 24-72h — this is normal
- Engagement quality: Turkish/emerging-market likes are cheaper but have higher drop rates

SMM PANEL EXPERTISE
- Refill mechanics: 24h cooldown after completion is a standard platform-wide policy, not a bug
- Refill rejection causes: (a) engagement hasn't dropped below threshold, (b) service provider out of stock, (c) too soon
- Non-delivery vs drop: start_count=0 at completion means either (a) genuine non-delivery or (b) all drops happened during fulfillment — check if post had ANY engagement before concluding
- Support ticket strategy: only ticket when (a) refill rejected 2+ times after cooldown OR (b) order completed with 0 start_count and 0 remains (clear non-delivery)
- Ticket etiquette: one ticket per issue, reference order IDs and refill IDs, be concise

ORDER STRATEGY
- For a new post: likes (100-200) + retweets (25-50) + views (5000-10000) is a good safe package
- Comments are risky (USA accounts, expensive, can look spammy) — use sparingly
- Wait 10-15 min after posting before ordering to let Twitter index the post
- Never order more than 1000 likes/day on a single post (looks unnatural)
- Space out orders: likes first, then retweets 30min later

YOUR ROLE
- Run periodic cycles: check order statuses, make smart refill decisions, handle pending posts
- Think like an expert: don't react to every rejection — diagnose the real situation
- Be conservative with support tickets — one ticket per real issue after retrying
- When a post URL is in pending_posts, place appropriate orders (ask yourself: what quantities make sense for this account's growth stage?)
- Log your reasoning clearly in each cycle summary

TOOL USAGE RULES
1. Always check_orders first to get the current picture
2. trigger_refill only after 24h cooldown AND not already pending/completed
3. submit_ticket only as last resort, never for first-time cooldown errors
4. place_order only when a link exists in pending_posts
5. One clear decision per cycle — don't do everything at once"""

# ── Agent cycle ─────────────────────────────────────────────────────────────────────────────────

def dispatch_tool(name: str, inp: dict, state: dict) -> str:
    mapping = {
        "get_balance":       lambda: tool_get_balance(),
        "check_orders":      lambda: tool_check_orders(state),
        "trigger_refill":    lambda: tool_trigger_refill(state, inp["order_id"]),
        "check_refill_status": lambda: tool_check_refill_status(state, inp["order_id"]),
        "submit_ticket":     lambda: tool_submit_ticket(state, inp["order_ids"], inp["subject_type"], inp["message"]),
        "place_order":       lambda: tool_place_order(state, inp["link"], inp["kind"], inp["quantity"]),
        "get_services":      lambda: tool_get_services(),
        "get_pending_posts": lambda: tool_get_pending_posts(state),
        "clear_pending_post": lambda: tool_clear_pending_post(state, inp["link"]),
    }
    fn = mapping.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return fn()
    except Exception as exc:
        log.exception("Tool %s raised: %s", name, exc)
        return json.dumps({"error": str(exc)})


CF_TOOL_PROTOCOL = """\

TOOL USE PROTOCOL
-----------------
When you need to call a tool, respond with ONLY this JSON (no other text):
{"tool": "tool_name", "args": {}}

When you are done, respond with ONLY this JSON:
{"done": true, "summary": "concise strategic summary of what you did and found"}

Never include <think> blocks or explanatory text alongside the JSON — output bare JSON only.
"""


def _run_cloudflare_ai_cycle(state: dict, task: str, max_iterations: int = 30) -> str:
    """Run agent cycle via Cloudflare Workers AI (DeepSeek R1 distill)."""
    if not CF_ACCOUNT_ID:
        raise ValueError("CF_ACCOUNT_ID not set")

    tools_desc = json.dumps(
        [{"name": t["name"], "description": t["description"],
          "parameters": t["input_schema"]} for t in TOOL_DEFS],
        indent=2,
    )
    system_content = (
        SYSTEM_PROMPT
        + CF_TOOL_PROTOCOL
        + f"\nAVAILABLE TOOLS:\n{tools_desc}"
    )

    messages: list[dict] = [
        {"role": "system", "content": system_content},
        {"role": "user",   "content": task},
    ]
    cf_url = (
        f"https://api.cloudflare.com/client/v4/accounts"
        f"/{CF_ACCOUNT_ID}/ai/run/{CF_AI_MODEL}"
    )
    # Prefer scoped AI token; fall back to Global API Key if not set
    if DEEPSEEK_KEY:
        cf_headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    else:
        cf_headers = {"X-Auth-Key": CF_GLOBAL_KEY, "X-Auth-Email": CF_EMAIL, "Content-Type": "application/json"}
    last_text = ""

    for iteration in range(max_iterations):
        resp = requests.post(
            cf_url,
            json={"messages": messages, "max_tokens": 2048},
            headers=cf_headers,
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise Exception(f"CF AI error: {data.get('errors')}")

        raw = data["result"]["response"]
        # Strip DeepSeek R1 reasoning blocks
        text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        last_text = text

        if text:
            log.info("[CF-AI] %s", text[:400])

        cmd = None
        try:
            cmd = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    cmd = json.loads(m.group())
                except Exception:
                    pass

        if cmd is None:
            return text or "Cycle complete."

        if cmd.get("done"):
            return cmd.get("summary", "Cycle complete.")

        if "tool" in cmd:
            tool_name = cmd["tool"]
            tool_args = cmd.get("args", {})
            log.info("  -> %s(%s)", tool_name, json.dumps(tool_args)[:120])
            result = dispatch_tool(tool_name, tool_args, state)
            log.info("     <- %s", result[:200])
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user",
                             "content": f"Tool result for {tool_name}: {result}"})
            continue

        return text or "Cycle complete."

    return last_text or "Agent reached max iterations."


def _run_deepseek_cycle(state: dict, task: str, max_iterations: int = 30) -> str:
    """Run agent cycle via DeepSeek (OpenAI-compatible API with tool use)."""
    ds_tools = []
    for t in TOOL_DEFS:
        ds_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            }
        })

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": task},
    ]
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            json={
                "model": DEEPSEEK_MODEL,
                "messages": messages,
                "tools": ds_tools,
                "tool_choice": "auto",
                "max_tokens": 4096,
            },
            headers={
                "Authorization": f"Bearer {DEEPSEEK_KEY}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        choice  = data["choices"][0]
        message = choice["message"]
        finish  = choice["finish_reason"]

        if message.get("content"):
            log.info("[DeepSeek] %s", str(message["content"])[:500])

        if finish == "stop" or not message.get("tool_calls"):
            return message.get("content") or "Cycle complete."

        messages.append(message)
        for tc in message.get("tool_calls", []):
            fn   = tc["function"]
            name = fn["name"]
            try:
                inp = json.loads(fn["arguments"])
            except Exception:
                inp = {}
            log.info("  -> %s(%s)", name, json.dumps(inp)[:120])
            result = dispatch_tool(name, inp, state)
            log.info("     <- %s", result[:200])
            messages.append({
                "role":         "tool",
                "tool_call_id": tc["id"],
                "content":      result,
            })

    return "Agent reached max iterations."


def _run_claude_cycle(state: dict, task: str, max_iterations: int = 30) -> str:
    """Run agent cycle via Claude (Anthropic SDK)."""
    ai = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    messages = [{"role": "user", "content": task}]
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        response = ai.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFS,
            messages=messages,
        )

        text_parts = [b.text for b in response.content if hasattr(b, "text")]
        for t in text_parts:
            if t.strip():
                log.info("[Claude] %s", t[:500])

        if response.stop_reason == "end_turn":
            return " ".join(text_parts) or "Cycle complete."

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            log.info("  -> %s(%s)", block.name, json.dumps(block.input)[:120])
            result = dispatch_tool(block.name, block.input, state)
            log.info("     <- %s", result[:200])
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": block.id,
                "content":     result,
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user",      "content": tool_results})

    return "Agent reached max iterations."


def run_agent_cycle(state: dict, task: str, max_iterations: int = 30) -> str:
    """
    Run one AI agent cycle.
    Priority: Cloudflare Workers AI (DeepSeek R1) → direct DeepSeek → Claude → rule-based.
    """
    # 1. Try Cloudflare Workers AI (DeepSeek R1 — fast, JSON tool-use via prompt)
    if CF_ACCOUNT_ID and (DEEPSEEK_KEY or CF_GLOBAL_KEY):
        try:
            log.info("[AI] Using Cloudflare Workers AI (%s)", CF_AI_MODEL)
            return _run_cloudflare_ai_cycle(state, task, max_iterations)
        except requests.HTTPError as exc:
            log.warning("[AI] Cloudflare AI error (%s) — trying DeepSeek direct", exc)
        except Exception as exc:
            log.warning("[AI] Cloudflare AI error (%s) — trying DeepSeek direct", exc)

    # 2. Try direct DeepSeek API (OpenAI-compatible tool use)
    if DEEPSEEK_KEY:
        try:
            log.info("[AI] Using DeepSeek direct API")
            return _run_deepseek_cycle(state, task, max_iterations)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (401, 402, 429):
                log.warning("[AI] DeepSeek unavailable (%s) — trying Claude", exc)
            else:
                log.warning("[AI] DeepSeek error (%s) — trying Claude", exc)
        except Exception as exc:
            log.warning("[AI] DeepSeek error (%s) — trying Claude", exc)

    # 3. Try Claude (fallback)
    if ANTHROPIC_KEY:
        try:
            log.info("[AI] Using Claude fallback")
            return _run_claude_cycle(state, task, max_iterations)
        except anthropic.BadRequestError as exc:
            if "credit balance" in str(exc).lower():
                log.warning("[AI] Claude no credits — using rule-based fallback")
            else:
                log.warning("[AI] Claude error (%s) — using rule-based fallback", exc)
        except anthropic.APIError as exc:
            log.warning("[AI] Claude API error (%s) — using rule-based fallback", exc)

    # 4. Rule-based fallback
    log.info("[AI] Using rule-based fallback")
    return _rule_based_cycle(state)


def _rule_based_cycle(state: dict) -> str:
    """
    Expert rule-based SMM manager — runs when all AI options are unavailable.
    """
    now = datetime.now(timezone.utc)
    actions = []

    try:
        bal = json.loads(tool_get_balance())
        log.info("[RULE] Balance: $%s %s", bal.get("balance"), bal.get("currency", "USD"))
    except Exception:
        pass

    orders_json = json.loads(tool_check_orders(state))
    orders = orders_json.get("orders", [])

    refill_triggered = []
    refill_waiting   = []
    refill_done      = []
    issues           = []

    for o in orders:
        oid        = o["order_id"]
        status     = o["status"]
        kind       = o["kind"]
        refillable = o["refillable"]
        cooldown_h = o.get("refill_cooldown_h")
        refill_info = state.get("refills", {}).get(oid, {})
        refill_status = refill_info.get("status")

        if status not in ("Completed", "Partial"):
            continue
        if not refillable:
            continue
        if refill_status == "Completed":
            refill_done.append(oid)
            continue
        if refill_status == "Pending":
            result = json.loads(tool_check_refill_status(state, oid))
            new_status = state.get("refills", {}).get(oid, {}).get("status", "Pending")
            if new_status == "Completed":
                refill_done.append(oid)
            elif new_status == "Rejected":
                if cooldown_h == 0:
                    res = json.loads(tool_trigger_refill(state, oid))
                    if res.get("success"):
                        refill_triggered.append(oid)
                        actions.append(f"Re-triggered refill for #{oid} ({kind}) after rejection")
                    else:
                        issues.append(f"#{oid} ({kind}): refill rejected twice — may need support ticket")
                else:
                    refill_waiting.append(oid)
            continue
        if cooldown_h is not None and cooldown_h > 0:
            refill_waiting.append(oid)
            log.info("[RULE] #%s (%s): refill in %.1fh", oid, kind, cooldown_h)
            continue
        res = json.loads(tool_trigger_refill(state, oid))
        if res.get("success"):
            refill_triggered.append(oid)
            actions.append(f"Triggered refill for #{oid} ({kind}) via {res.get('method','?')}")
            log.info("[RULE] Refill triggered for #%s (%s)", oid, kind)
        else:
            err = res.get("error", "unknown")
            log.warning("[RULE] Refill failed for #%s: %s", oid, err)
            if "disabled" not in err.lower():
                issues.append(f"#{oid} ({kind}): refill failed — {err}")

    pending = state.get("pending_posts", [])
    for link in list(pending):
        log.info("[RULE] Placing orders for queued post: %s", link)
        for kind, qty in [("likes", 100), ("retweets", 30)]:
            res = json.loads(tool_place_order(state, link, kind, qty))
            if res.get("success"):
                actions.append(f"Placed {kind} x{qty} order #{res['order_id']} for {link[-40:]}")
                log.info("[RULE] Order placed: %s x%d -> #%s", kind, qty, res.get("order_id"))
            else:
                log.warning("[RULE] Order failed (%s x%d): %s", kind, qty, res.get("error"))
        tool_clear_pending_post(state, link)

    summary_parts = [f"[Rule-based cycle — {now.strftime('%H:%M UTC')}]"]
    if refill_triggered:
        summary_parts.append(f"Refills triggered: {refill_triggered}")
    if refill_waiting:
        summary_parts.append(f"Waiting for cooldown: {refill_waiting}")
    if refill_done:
        summary_parts.append(f"Refills completed: {refill_done}")
    if actions:
        summary_parts.append("Actions: " + "; ".join(actions))
    if issues:
        summary_parts.append("Issues (no ticket yet): " + "; ".join(issues))
    if not refill_triggered and not actions and not issues:
        summary_parts.append("Nothing to do — all orders healthy or in cooldown.")

    return " | ".join(summary_parts)


MONITOR_TASK = """\
Run your standard monitoring cycle:

1. Check account balance.
2. Call check_orders to get the full status picture.
3. For any completed/partial orders with refillable=true:
   - If refill_cooldown_h == 0 and no refill pending/done: trigger it.
   - If refill_cooldown_h > 0: note the wait time, do nothing.
4. For any pending refills: call check_refill_status to update.
5. Check pending_posts — if any URLs need orders, place them intelligently
   (good quantities, right services, right order).
6. Only submit a support ticket if there is a genuine unresolvable issue
   (refill rejected 2+ times, or clear non-delivery that hasn't been ticketed).
7. End with a concise strategic summary: what's healthy, what needs attention,
   what you did and why.
"""

# ── Dashboard ─────────────────────────────────────────────────────────────────────────────────

def print_dashboard(state: dict) -> None:
    try:
        bal = _api({"action": "balance"})
        print(f"\nBalance: ${bal.get('balance')} {bal.get('currency','USD')}")
    except Exception as e:
        print(f"\nBalance: error ({e})")

    sep = "─" * 80
    print(f"\n{sep}")
    print(f"{'ID':<12} {'Kind':<11} {'Status':<18} {'Rem':<6} {'Refill':<15} Link")
    print(sep)

    now = datetime.now(timezone.utc)
    for oid, o in state["orders"].items():
        refill_info = state.get("refills", {}).get(oid)
        refill_str = "—"
        if refill_info:
            rs = refill_info.get("status", "?")
            rid = refill_info.get("refill_id", "")
            refill_str = f"{rs} ({rid})" if rid != "panel" else f"{rs} (panel)"

        cooldown_str = ""
        if o.get("refillable") and o.get("completed_at"):
            try:
                dt = datetime.fromisoformat(o["completed_at"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                h_left = max(0, 24 - (now - dt).total_seconds() / 3600)
                if h_left > 0:
                    cooldown_str = f" ⏳{h_left:.0f}h"
            except Exception:
                pass

        print(
            f"  {oid:<10} {o.get('kind','?'):<11} "
            f"{o.get('status','?') + cooldown_str:<18} "
            f"{str(o.get('remains','?')):<6} "
            f"{refill_str:<15} "
            f"{o.get('link','?')[-45:]}"
        )

    print(sep)
    if state.get("pending_posts"):
        print(f"Pending posts (to order): {state['pending_posts']}")
    print(f"Tracked posts: {len(state['posts'])}")
    print()

    if state.get("agent_log"):
        print("Recent AI decisions:")
        for entry in state["agent_log"][-5:]:
            print(f"  [{entry['at'][11:19]}] {entry['msg'][:120]}")
    print()

# ── CLI ────────────────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SMMFollows AI Manager — DeepSeek R1 (Cloudflare Workers AI) powered"
    )
    parser.add_argument("--once",     action="store_true", help="Single AI cycle then exit")
    parser.add_argument("--status",   action="store_true", help="Print dashboard and exit")
    parser.add_argument("--post",     metavar="URL",       help="Queue a post URL for ordering")
    parser.add_argument("--refill",   action="store_true", help="Run refill-focused AI pass now")
    parser.add_argument("--interval", type=int, default=POLL_SECS,
                        help=f"Seconds between cycles (default {POLL_SECS})")
    args = parser.parse_args()

    state = load_state()

    if args.post:
        url = args.post.strip()
        if url not in state.get("pending_posts", []):
            state.setdefault("pending_posts", []).append(url)
            save_state(state)
            log.info("Post queued: %s — AI will place orders on next cycle.", url)
        else:
            log.info("Already queued: %s", url)

    if args.status:
        print_dashboard(state)
        return

    if args.refill:
        log.info("Running refill-focused AI cycle...")
        task = (
            "Run a refill-focused pass: check all orders, then for every completed "
            "refillable order where the 24h cooldown has expired and no successful "
            "refill exists yet, trigger refill. Check status of any pending refills. "
            "Summarise what you did."
        )
        summary = run_agent_cycle(state, task)
        log_agent(state, f"[REFILL] {summary[:200]}")
        save_state(state)
        return

    if args.once or args.post:
        summary = run_agent_cycle(state, MONITOR_TASK)
        log_agent(state, summary[:200])
        save_state(state)
        return

    log.info("=== SMMFollows AI Manager started (interval=%ds) ===", args.interval)
    log.info("Tracking %d orders | AI: Cloudflare Workers AI (DeepSeek R1)", len(state["orders"]))
    log.info("Press Ctrl+C to stop.")

    while True:
        try:
            summary = run_agent_cycle(state, MONITOR_TASK)
            log_agent(state, summary[:200])
            save_state(state)
        except KeyboardInterrupt:
            log.info("Stopped.")
            break
        except anthropic.APIError as exc:
            log.error("Claude API error: %s", exc)
        except Exception as exc:
            log.exception("Unexpected error: %s", exc)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
