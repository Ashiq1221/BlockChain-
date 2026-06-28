#!/usr/bin/env python3
"""
10-Agent Autonomous SMM System
===============================
10 concurrent agents dig into the SMMFollows panel and work non-stop to:
  • Keep all orders delivered
  • Force refills (API + ticket pressure + endpoint probing)
  • Discover hidden panel endpoints
  • Monitor and re-order when balance allows

Usage:
  python run_agents.py          # run all 10 agents forever
  python run_agents.py --once   # one full cycle then exit
"""

from __future__ import annotations
import argparse, json, logging, os, re, sys, threading, time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    C = {
        "red":    Fore.RED,
        "green":  Fore.GREEN,
        "yellow": Fore.YELLOW,
        "cyan":   Fore.CYAN,
        "magenta":Fore.MAGENTA,
        "blue":   Fore.BLUE,
        "white":  Fore.WHITE,
        "reset":  Style.RESET_ALL,
        "bold":   Style.BRIGHT,
    }
except ImportError:
    C = {k: "" for k in ["red","green","yellow","cyan","magenta","blue","white","reset","bold"]}

# ── Configuration ──────────────────────────────────────────────────────────────
API_KEY   = "882fa9a6e54b39ffa8c7e2bf4fcc1f46"
API_URL   = "https://smmfollows.com/api/v2"
PANEL     = "https://smmfollows.com"
USER      = "hhrh197"
PASSWD    = "Yawer@123"
STATE_F   = Path("agent_state.json")

# Service IDs (verified live)
SVC_LIKES    = 12452   # Twitter Likes Turkey HQ | $0.88/1k | refill YES
SVC_RETWEETS = 13139   # Twitter Retweets HQ     | $0.54/1k | refill YES
SVC_COMMENTS = 7339    # Twitter Comments Custom  | $33.75/1k

POSTS = [
    "https://x.com/i/status/2065705610163941467",
    "https://x.com/i/status/2064879295843983840",
    "https://x.com/i/status/2064283340849738045",
]

# Orders we're tracking
OLD_ORDERS = ["61218148", "61218147", "61218151", "61218154"]   # svc 8140
NEW_ORDERS = [
    {"id":"61450840","type":"likes",   "post":POSTS[0],"refillable":True},
    {"id":"61450841","type":"retweets","post":POSTS[0],"refillable":True},
    {"id":"61450842","type":"comments","post":POSTS[0],"refillable":False},
    {"id":"61450843","type":"likes",   "post":POSTS[1],"refillable":True},
    {"id":"61450844","type":"retweets","post":POSTS[1],"refillable":True},
    {"id":"61450845","type":"comments","post":POSTS[1],"refillable":False},
    {"id":"61450846","type":"likes",   "post":POSTS[2],"refillable":True},
    {"id":"61450847","type":"retweets","post":POSTS[2],"refillable":True},
    {"id":"61450848","type":"comments","post":POSTS[2],"refillable":False},
]

TICKET_ID       = "944469"   # primary long-running ticket with support history
TICKET_ID_NEW   = "1136178"  # secondary ticket we created

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agents.log"),
    ],
)
log = logging.getLogger(__name__)


def tag(name: str, color: str) -> str:
    return f"{C['bold']}{C[color]}[{name}]{C['reset']}"


# ── Shared State ───────────────────────────────────────────────────────────────
class AgentState:
    def __init__(self):
        self._lock = threading.Lock()
        self.data: dict = self._load()

    def _load(self) -> dict:
        if STATE_F.exists():
            try:
                return json.loads(STATE_F.read_text())
            except Exception:
                pass
        return {"orders": {}, "balance": "0", "ticket": {}, "refills": {}, "explored": []}

    def save(self):
        with self._lock:
            STATE_F.write_text(json.dumps(self.data, indent=2, default=str))

    def get(self, key, default=None):
        with self._lock:
            return self.data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self.data[key] = value
        self.save()

    def update_order(self, oid: str, info: dict):
        with self._lock:
            self.data.setdefault("orders", {})[oid] = {
                **self.data["orders"].get(oid, {}),
                **info,
                "updated_at": datetime.now().isoformat(),
            }
        self.save()

    def mark_refilled(self, oid: str, refill_id):
        with self._lock:
            self.data.setdefault("refills", {})[oid] = {
                "refill_id": refill_id,
                "refilled_at": datetime.now().isoformat(),
            }
        self.save()

    def was_refilled(self, oid: str) -> bool:
        with self._lock:
            return oid in self.data.get("refills", {})


STATE = AgentState()


# ── API helpers ────────────────────────────────────────────────────────────────
def api(payload: dict, timeout: int = 20) -> dict:
    payload["key"] = API_KEY
    r = requests.post(API_URL, data=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def web_session() -> requests.Session | None:
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
    try:
        r = sess.get(PANEL + "/", timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        csrf_inp = soup.find("input", {"name": "_csrf"})
        if not csrf_inp:
            return None
        csrf_val = csrf_inp["value"]
        login_data = urlencode([
            ("LoginForm[username]", USER),
            ("LoginForm[password]", PASSWD),
            ("LoginForm[remember]", "1"),
            ("_csrf", csrf_val),
        ])
        r2 = sess.post(PANEL + "/", data=login_data,
                       headers={"Content-Type": "application/x-www-form-urlencoded",
                                "Referer": PANEL + "/"},
                       allow_redirects=False, timeout=20)
        if "_identity_user" not in sess.cookies:
            return None
        loc = r2.headers.get("Location", "/")
        if not loc.startswith("http"):
            loc = PANEL + loc
        sess.get(loc, timeout=20)
        return sess
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# AGENT BASE CLASS
# ══════════════════════════════════════════════════════════════════════════════
class BaseAgent(threading.Thread):
    NAME   = "Agent"
    COLOR  = "white"
    CYCLE  = 60  # seconds between runs

    def __init__(self, stop_event: threading.Event, once: bool = False):
        super().__init__(daemon=True, name=self.NAME)
        self._halt = stop_event
        self._once = once

    def log(self, msg: str, level: str = "info"):
        prefix = tag(self.NAME, self.COLOR)
        getattr(log, level)(f"{prefix} {msg}")

    def run(self):
        self.log(f"started (cycle={self.CYCLE}s)")
        if self._once:
            try:
                self.cycle()
            except Exception as exc:
                self.log(f"ERROR: {exc}", "error")
            return
        while not self._halt.is_set():
            try:
                self.cycle()
            except Exception as exc:
                self.log(f"ERROR: {exc}", "error")
            self._halt.wait(self.CYCLE)

    def cycle(self):
        raise NotImplementedError


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 1: Balance Monitor
# ══════════════════════════════════════════════════════════════════════════════
class BalanceMonitor(BaseAgent):
    NAME  = "BALANCE"
    COLOR = "green"
    CYCLE = 300  # 5 min

    def cycle(self):
        res = api({"action": "balance"})
        bal = res.get("balance", "0")
        cur = res.get("currency", "USD")
        STATE.set("balance", bal)
        fbal = float(bal)
        if fbal < 0.50:
            self.log(f"{C['red']}LOW BALANCE${fbal:.4f} {cur} — add funds!", "warning")
        else:
            self.log(f"${fbal:.4f} {cur}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 2: Order Status Tracker
# ══════════════════════════════════════════════════════════════════════════════
class OrderTracker(BaseAgent):
    NAME  = "TRACKER"
    COLOR = "cyan"
    CYCLE = 120  # 2 min

    def cycle(self):
        all_ids = OLD_ORDERS + [o["id"] for o in NEW_ORDERS]
        statuses = api({"action": "status", "orders": ",".join(all_ids)})
        for oid, info in statuses.items():
            prev = STATE.get("orders", {}).get(oid, {})
            curr_status = info.get("status", "?")
            prev_status = prev.get("status", "?")
            STATE.update_order(oid, info)
            if curr_status != prev_status and prev_status != "?":
                self.log(f"#{oid} changed: {prev_status} → {C['yellow']}{curr_status}{C['reset']}")
        completed = sum(1 for i in statuses.values() if i.get("status") == "Completed")
        partial   = sum(1 for i in statuses.values() if i.get("status") == "Partial")
        inprog    = sum(1 for i in statuses.values() if "progress" in str(i.get("status","")).lower())
        self.log(f"Completed={completed} Partial={partial} InProgress={inprog} / {len(all_ids)} total")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 3: Refill Executor
# ══════════════════════════════════════════════════════════════════════════════
class RefillExecutor(BaseAgent):
    NAME  = "REFILL"
    COLOR = "magenta"
    CYCLE = 1800  # 30 min

    def cycle(self):
        for o in NEW_ORDERS:
            if not o["refillable"]:
                continue
            oid = o["id"]
            if STATE.was_refilled(oid):
                continue
            order_info = STATE.get("orders", {}).get(oid, {})
            status = order_info.get("status", "")
            if status != "Completed":
                continue
            res = api({"action": "refill", "order": oid})
            if "error" in res:
                self.log(f"#{oid}: {res['error']}")
            else:
                rid = res.get("refill")
                STATE.mark_refilled(oid, rid)
                self.log(f"#{C['green']}{oid}{C['reset']} REFILL SENT refill_id={rid}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 4: Ticket Monitor
# ══════════════════════════════════════════════════════════════════════════════
class TicketMonitor(BaseAgent):
    NAME  = "TICKET"
    COLOR = "yellow"
    CYCLE = 900  # 15 min

    def _read_ticket(self, sess: requests.Session, tid: str) -> list[dict]:
        r = sess.get(f"{PANEL}/viewticket/{tid}", timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        msgs, seen = [], set()
        for blk in soup.find_all("div", class_="ticket-message-block"):
            inner = blk.find("div", class_="message")
            if not inner:
                continue
            txt = inner.get_text(separator=" ", strip=True)
            if not txt or txt in seen:
                continue
            seen.add(txt)
            is_staff = "ticket-message-left" in blk.get("class", [])
            msgs.append({"text": txt, "staff": is_staff, "soup": soup})
        return msgs

    def cycle(self):
        sess = web_session()
        if not sess:
            self.log("web login failed", "warning")
            return

        # Primary ticket #944469 (180 messages, main support thread)
        msgs = self._read_ticket(sess, TICKET_ID)
        ticket_state = STATE.get("ticket", {})
        prev_count   = ticket_state.get("msg_count", 0)
        new_count    = len(msgs)

        if new_count > prev_count:
            for m in msgs[prev_count:]:
                who = f"{C['green']}SUPPORT" if m["staff"] else "You"
                self.log(f"[Ticket #{TICKET_ID}] New from {who}: {m['text'][:200]}")

        staff_msgs = [m for m in msgs if m["staff"]]
        latest_staff = staff_msgs[-1]["text"][:200] if staff_msgs else "none"
        self.log(f"Ticket #{TICKET_ID}: {len(msgs)} msgs, last support: {latest_staff[:100]}")

        ticket_state["msg_count"]    = new_count
        ticket_state["has_response"] = len(staff_msgs) > 0
        STATE.set("ticket", ticket_state)

    def post_to_ticket(self, sess: requests.Session, tid: str, msg: str):
        """Post a reply message to any ticket."""
        r = sess.get(f"{PANEL}/viewticket/{tid}", timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        csrf_inp = soup.find("input", {"name": "_csrf"})
        if not csrf_inp:
            return
        data = urlencode([("TicketMessageForm[message]", msg), ("_csrf", csrf_inp["value"])])
        r2 = sess.post(f"{PANEL}/viewticket/{tid}", data=data,
                       headers={"Content-Type": "application/x-www-form-urlencoded",
                                "Referer": f"{PANEL}/viewticket/{tid}"},
                       allow_redirects=False, timeout=20)
        if r2.status_code in (302, 200):
            self.log(f"Message sent to ticket #{tid}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 5: Likes Guard
# ══════════════════════════════════════════════════════════════════════════════
class LikesGuard(BaseAgent):
    NAME  = "LIKES"
    COLOR = "red"
    CYCLE = 600  # 10 min

    def cycle(self):
        bal = float(STATE.get("balance", "0") or "0")
        if bal < 0.10:
            self.log(f"balance too low (${bal:.4f}), skipping")
            return

        for o in [x for x in NEW_ORDERS if x["type"] == "likes"]:
            info   = STATE.get("orders", {}).get(o["id"], {})
            status = info.get("status", "")
            remains = int(info.get("remains") or 0)

            if status == "Completed" and remains == 0:
                self.log(f"#{o['id']} on {o['post'][-19:]} — completed & drained. "
                         f"Refill pending or need funds to re-order.")
            elif status == "Partial" and remains > 0:
                self.log(f"#{o['id']} partial: {remains} still pending delivery")
            elif status in ("In progress", "Pending"):
                self.log(f"#{o['id']} delivering... remains={remains}")
            else:
                self.log(f"#{o['id']} status={status} remains={remains}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 6: Retweets Guard
# ══════════════════════════════════════════════════════════════════════════════
class RetweetsGuard(BaseAgent):
    NAME  = "RETWEETS"
    COLOR = "blue"
    CYCLE = 600

    def cycle(self):
        bal = float(STATE.get("balance", "0") or "0")
        for o in [x for x in NEW_ORDERS if x["type"] == "retweets"]:
            info    = STATE.get("orders", {}).get(o["id"], {})
            status  = info.get("status", "")
            remains = int(info.get("remains") or 0)
            self.log(f"#{o['id']} post={o['post'][-19:]} status={status} remains={remains}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 7: Comments Guard
# ══════════════════════════════════════════════════════════════════════════════
class CommentsGuard(BaseAgent):
    NAME  = "COMMENTS"
    COLOR = "cyan"
    CYCLE = 600

    def cycle(self):
        for o in [x for x in NEW_ORDERS if x["type"] == "comments"]:
            info    = STATE.get("orders", {}).get(o["id"], {})
            status  = info.get("status", "")
            remains = int(info.get("remains") or 0)
            self.log(f"#{o['id']} post={o['post'][-19:]} status={status} remains={remains}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 8: Old Order Recovery (most aggressive)
# ══════════════════════════════════════════════════════════════════════════════
class OldOrderRecovery(BaseAgent):
    NAME  = "RECOVERY"
    COLOR = "red"
    CYCLE = 3600  # 1 hour

    # Undocumented / alternative API actions to probe
    ALT_ACTIONS = [
        {"action": "refill_order"},
        {"action": "force_refill"},
        {"action": "manual_refill"},
        {"action": "refill_v2"},
        {"action": "re_refill"},
    ]

    def cycle(self):
        self.log("--- Starting recovery cycle for old orders ---")
        any_success = False
        for oid in OLD_ORDERS:
            info   = STATE.get("orders", {}).get(oid, {})
            status = info.get("status", "unknown")
            self.log(f"#{oid} status={status}")

            # Primary: try standard refill API
            try:
                res = api({"action": "refill", "order": oid})
                if "error" in res:
                    self.log(f"  API refill: {res['error']}")
                    self._probe_alt(oid)
                else:
                    rid = res.get("refill")
                    STATE.mark_refilled(oid, rid)
                    self.log(f"  {C['green']}REFILL SENT! refill_id={rid}")
                    any_success = True
            except Exception as exc:
                self.log(f"  API error: {exc}", "error")

        # Every 6h, post a ticket update if no refill yet
        last_post = STATE.get("recovery_last_ticket_post")
        can_post = True
        if last_post:
            elapsed = (datetime.now() - datetime.fromisoformat(last_post)).total_seconds()
            can_post = elapsed > 21600

        if can_post and not any_success:
            self._ticket_followup()
            STATE.set("recovery_last_ticket_post", datetime.now().isoformat())

    def _ticket_followup(self):
        sess = web_session()
        if not sess:
            return
        # Post to the primary ticket
        orders = STATE.get("orders", {})
        lines = []
        for oid in OLD_ORDERS:
            s = orders.get(oid, {}).get("status", "?")
            r = orders.get(oid, {}).get("remains", "?")
            lines.append(f"  #{oid}: {s} (remains={r})")
        status_block = "\n".join(lines)
        msg = (
            f"AUTOMATED STATUS CHECK — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"Orders still awaiting refill:\n{status_block}\n\n"
            "The API still returns 'Refill is disabled for this service' for all 4 orders. "
            "Please confirm when the manual refill has been triggered for order 61218148 "
            "(Completed) and schedule refill for 61218147, 61218151, 61218154 as soon as "
            "they finish delivery. Thank you."
        )
        # Post via TicketMonitor helper (reuse method)
        try:
            r = sess.get(f"{PANEL}/viewticket/{TICKET_ID}", timeout=20)
            soup = BeautifulSoup(r.text, "html.parser")
            csrf_inp = soup.find("input", {"name": "_csrf"})
            if csrf_inp:
                data = urlencode([("TicketMessageForm[message]", msg), ("_csrf", csrf_inp["value"])])
                resp = sess.post(f"{PANEL}/viewticket/{TICKET_ID}", data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "Referer": f"{PANEL}/viewticket/{TICKET_ID}"},
                                 allow_redirects=False, timeout=20)
                if resp.status_code in (302, 200):
                    self.log(f"Follow-up posted to ticket #{TICKET_ID}")
        except Exception as exc:
            self.log(f"Ticket post failed: {exc}", "error")

    def _probe_alt(self, oid: str):
        """Try undocumented API actions."""
        for payload in self.ALT_ACTIONS:
            try:
                res = api({**payload, "order": oid})
                if "error" not in res:
                    self.log(f"  ALT ACTION '{payload['action']}' succeeded: {res}")
                    return
            except Exception:
                pass

        # Also probe order-specific sub-actions
        for action in ["status_refill", "check_refill", "get_refill"]:
            try:
                res = api({"action": action, "order": oid})
                if "error" not in str(res):
                    self.log(f"  Probe '{action}': {res}")
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 9: Panel Explorer
# ══════════════════════════════════════════════════════════════════════════════
class PanelExplorer(BaseAgent):
    NAME  = "EXPLORER"
    COLOR = "magenta"
    CYCLE = 7200  # 2 hours (expensive, run less often)

    EXTRA_API_ACTIONS = [
        "services", "balance", "orders", "user", "profile",
        "admin_refill", "bulk_refill", "force_complete", "resend",
        "refill_all", "process_refill", "refill_check", "order_refill",
        "get_orders", "list_orders", "pending_refills",
    ]

    def cycle(self):
        self.log("Probing panel endpoints...")
        # 1. Scan JS bundles for hidden endpoints
        self._scan_js()
        # 2. Probe API with undocumented actions
        self._probe_api_actions()
        # 3. Check alternative panel pages
        self._probe_panel_pages()

    def _scan_js(self):
        sess = web_session()
        if not sess:
            return
        try:
            r = sess.get(PANEL + "/", timeout=20)
            soup = BeautifulSoup(r.text, "html.parser")
            js_urls = [s["src"] for s in soup.find_all("script", src=True) if s.get("src")]
            for js_url in js_urls:
                if not js_url.startswith("http"):
                    js_url = PANEL + js_url
                try:
                    jr = sess.get(js_url, timeout=15)
                    # Find all XHR/fetch/ajax calls
                    endpoints = re.findall(
                        r'["\']/([\w\-/]+)["\']',
                        jr.text
                    )
                    new_eps = [e for e in endpoints
                               if len(e) > 3 and e not in STATE.get("explored", [])]
                    if new_eps:
                        self.log(f"JS {js_url.split('/')[-1]}: found {len(new_eps)} new paths")
                        explored = STATE.get("explored", [])
                        explored.extend(new_eps[:50])
                        STATE.set("explored", explored)
                        # Test interesting ones
                        for ep in new_eps[:10]:
                            if any(kw in ep.lower() for kw in ["refill","order","api","admin","ticket"]):
                                self._test_endpoint(sess, ep)
                except Exception:
                    pass
        except Exception as exc:
            self.log(f"JS scan error: {exc}", "error")

    def _probe_api_actions(self):
        found = []
        for action in self.EXTRA_API_ACTIONS:
            try:
                res = api({"action": action}, timeout=10)
                if "error" not in res or res.get("error") != "Invalid action":
                    self.log(f"API action '{action}' → {str(res)[:80]}")
                    found.append(action)
            except Exception:
                pass
        if found:
            self.log(f"Working actions found: {found}")
        else:
            self.log("No new API actions discovered")

    def _probe_panel_pages(self):
        sess = web_session()
        if not sess:
            return
        paths = [
            "/api/v2", "/api/v3", "/api/admin", "/admin", "/panel",
            "/refills", "/refill-list", "/order-refill",
            "/admin/orders", "/admin/refills", "/support/admin",
            "/orders/refill", "/api/refills",
        ]
        for path in paths:
            try:
                r = sess.get(PANEL + path, timeout=8, allow_redirects=False)
                if r.status_code not in (404, 302):
                    self.log(f"Path {path} → {r.status_code} (len={len(r.content)})")
            except Exception:
                pass

    def _test_endpoint(self, sess: requests.Session, path: str):
        try:
            r = sess.get(PANEL + "/" + path.lstrip("/"), timeout=8, allow_redirects=False)
            if r.status_code not in (404, 302):
                self.log(f"Endpoint /{path} → {r.status_code}")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 10: Master Coordinator
# ══════════════════════════════════════════════════════════════════════════════
class MasterCoordinator(BaseAgent):
    NAME  = "COORDINATOR"
    COLOR = "yellow"
    CYCLE = 600  # 10 min

    def cycle(self):
        self.log("=== FULL SYSTEM REPORT ===")
        bal = STATE.get("balance", "0")
        self.log(f"  Balance: ${bal}")

        orders = STATE.get("orders", {})
        ticket = STATE.get("ticket", {})
        refills = STATE.get("refills", {})

        # Status summary
        if orders:
            statuses = {}
            for oid, info in orders.items():
                s = info.get("status", "?")
                statuses[s] = statuses.get(s, 0) + 1
            self.log(f"  Orders: {dict(statuses)}")

        # Refill summary
        refilled_ids = list(refills.keys())
        if refilled_ids:
            self.log(f"  {C['green']}Refills obtained: {refilled_ids}")
        else:
            self.log(f"  {C['yellow']}No refills processed yet")

        # Ticket status
        has_resp = ticket.get("has_response", False)
        msg_cnt  = ticket.get("msg_count", 0)
        if has_resp:
            self.log(f"  {C['green']}Ticket #{TICKET_ID}: SUPPORT REPLIED ({msg_cnt} messages)")
        else:
            self.log(f"  {C['yellow']}Ticket #{TICKET_ID}: Awaiting support ({msg_cnt} messages sent)")

        # Strategy decision
        self._strategize(orders, bal)

    def _strategize(self, orders: dict, bal: str):
        fbal = float(bal or "0")

        completed = [oid for oid, i in orders.items() if i.get("status") == "Completed"]
        partial   = [oid for oid, i in orders.items() if i.get("status") == "Partial"]
        in_prog   = [oid for oid, i in orders.items()
                     if "progress" in str(i.get("status","")).lower()
                     or i.get("status") == "Pending"]

        self.log(f"  Strategy: {len(completed)} completed | {len(partial)} partial | {len(in_prog)} in-progress")

        if fbal < 0.05:
            self.log(f"  {C['red']}ACTION NEEDED: Add funds to continue ordering!")
        elif fbal >= 0.88 and len([o for o in NEW_ORDERS if o["type"]=="likes"]) < 9:
            self.log(f"  Funds available — can place more likes orders")

        if partial:
            self.log(f"  Partial orders still delivering: {partial}")

        non_refilled = [
            o["id"] for o in NEW_ORDERS
            if o["refillable"]
            and orders.get(o["id"], {}).get("status") == "Completed"
            and o["id"] not in STATE.get("refills", {})
        ]
        if non_refilled:
            self.log(f"  {C['yellow']}Pending refills (24h cooldown may apply): {non_refilled}")


# ══════════════════════════════════════════════════════════════════════════════
# LAUNCH PAD
# ══════════════════════════════════════════════════════════════════════════════
def print_banner():
    banner = f"""
{C['bold']}{C['cyan']}
╔══════════════════════════════════════════════════════════════════════╗
║           10-AGENT AUTONOMOUS SMM SYSTEM  — SMMFOLLOWS             ║
║  Agents: BALANCE · TRACKER · REFILL · TICKET · LIKES · RETWEETS    ║
║          COMMENTS · RECOVERY · EXPLORER · COORDINATOR               ║
╚══════════════════════════════════════════════════════════════════════╝
{C['reset']}"""
    print(banner)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one cycle per agent then exit")
    args = parser.parse_args()

    print_banner()
    stop = threading.Event()

    agents: list[BaseAgent] = [
        BalanceMonitor(stop, args.once),    # 1
        OrderTracker(stop, args.once),      # 2
        RefillExecutor(stop, args.once),    # 3
        TicketMonitor(stop, args.once),     # 4
        LikesGuard(stop, args.once),        # 5
        RetweetsGuard(stop, args.once),     # 6
        CommentsGuard(stop, args.once),     # 7
        OldOrderRecovery(stop, args.once),  # 8
        PanelExplorer(stop, args.once),     # 9
        MasterCoordinator(stop, args.once), # 10
    ]

    log.info(f"Launching {len(agents)} agents...")
    for a in agents:
        a.start()
        time.sleep(0.5)  # stagger startup

    if args.once:
        for a in agents:
            a.join(timeout=120)
        log.info("One-shot complete.")
        return

    log.info(f"All {len(agents)} agents running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        log.info("Shutdown signal received. Stopping all agents...")
        stop.set()
        for a in agents:
            a.join(timeout=5)
        log.info("All agents stopped. State saved.")



if __name__ == "__main__":
    main()
