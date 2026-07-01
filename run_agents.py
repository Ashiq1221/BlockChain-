#!/usr/bin/env python3
"""
10-Agent Autonomous SMM Deep-Probe System
==========================================
Zero ticket interaction. Agents dig entirely through technical means:
API variants, undocumented actions, Yii2 route patterns, JS analysis,
panel endpoint brute-force, and header/param manipulation.

Usage:
  python run_agents.py          # run forever
  python run_agents.py --once   # single cycle
"""

from __future__ import annotations
import argparse, json, logging, os, re, sys, threading, time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
import anthropic

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    C = {"red": Fore.RED, "green": Fore.GREEN, "yellow": Fore.YELLOW,
         "cyan": Fore.CYAN, "magenta": Fore.MAGENTA, "blue": Fore.BLUE,
         "white": Fore.WHITE, "reset": Style.RESET_ALL, "bold": Style.BRIGHT}
except ImportError:
    C = {k: "" for k in ["red","green","yellow","cyan","magenta","blue","white","reset","bold"]}

# ── Config ─────────────────────────────────────────────────────────────────────
API_KEY      = "882fa9a6e54b39ffa8c7e2bf4fcc1f46"
API_URL      = "https://smmfollows.com/api/v2"
PANEL        = "https://smmfollows.com"
USER         = "hhrh197"
PASSWD       = "Yawer@123"
STATE_F      = Path("agent_state.json")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

POSTS = [
    "https://x.com/i/status/2065705610163941467",
    "https://x.com/i/status/2064879295843983840",
    "https://x.com/i/status/2064283340849738045",
]
OLD_ORDERS = ["61218148", "61218147", "61218151", "61218154"]
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("agents.log")],
)
log = logging.getLogger(__name__)


def tag(name: str, color: str) -> str:
    return f"{C['bold']}{C[color]}[{name}]{C['reset']}"


# ── Shared state ───────────────────────────────────────────────────────────────
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
        return {"orders": {}, "balance": "0", "refills": {}, "discovered": {}, "probed": []}

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
                **self.data["orders"].get(oid, {}), **info,
                "updated_at": datetime.now().isoformat(),
            }
        self.save()

    def mark_refilled(self, oid: str, refill_id):
        with self._lock:
            self.data.setdefault("refills", {})[oid] = {
                "refill_id": refill_id, "at": datetime.now().isoformat(),
            }
        self.save()

    def was_refilled(self, oid: str) -> bool:
        with self._lock:
            return oid in self.data.get("refills", {})

    def record_discovery(self, key: str, value):
        with self._lock:
            self.data.setdefault("discovered", {})[key] = value
        self.save()

    def already_probed(self, key: str) -> bool:
        with self._lock:
            return key in self.data.get("probed", [])

    def mark_probed(self, key: str):
        with self._lock:
            p = self.data.get("probed", [])
            if key not in p:
                p.append(key)
            self.data["probed"] = p
        self.save()


STATE = AgentState()


# ── Helpers ────────────────────────────────────────────────────────────────────
def api_call(payload: dict, url: str = API_URL, timeout: int = 15) -> dict:
    payload["key"] = API_KEY
    r = requests.post(url, data=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def web_session() -> requests.Session | None:
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"})
    try:
        r = sess.get(PANEL + "/", timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        csrf_inp = soup.find("input", {"name": "_csrf"})
        if not csrf_inp:
            return None
        r2 = sess.post(PANEL + "/", allow_redirects=False, timeout=20,
                       headers={"Content-Type": "application/x-www-form-urlencoded",
                                "Referer": PANEL + "/"},
                       data=urlencode([("LoginForm[username]", USER),
                                       ("LoginForm[password]", PASSWD),
                                       ("LoginForm[remember]", "1"),
                                       ("_csrf", csrf_inp["value"])]))
        if "_identity_user" not in sess.cookies:
            return None
        loc = r2.headers.get("Location", "/")
        sess.get(loc if loc.startswith("http") else PANEL + loc, timeout=20)
        return sess
    except Exception:
        return None


# ── Base agent ────────────────────────────────────────────────────────────────
class BaseAgent(threading.Thread):
    NAME  = "Agent"
    COLOR = "white"
    CYCLE = 60

    def __init__(self, halt: threading.Event, once: bool = False):
        super().__init__(daemon=True, name=self.NAME)
        self._halt = halt
        self._once = once

    def log(self, msg: str, level: str = "info"):
        getattr(log, level)(f"{tag(self.NAME, self.COLOR)} {msg}")

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
    CYCLE = 300

    def cycle(self):
        res = api_call({"action": "balance"})
        bal = res.get("balance", "0")
        STATE.set("balance", bal)
        fbal = float(bal)
        color = C["red"] if fbal < 0.50 else C["green"]
        self.log(f"{color}${fbal:.4f} {res.get('currency','USD')}{C['reset']}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 2: Order Tracker
# ══════════════════════════════════════════════════════════════════════════════
class OrderTracker(BaseAgent):
    NAME  = "TRACKER"
    COLOR = "cyan"
    CYCLE = 90

    def cycle(self):
        all_ids = OLD_ORDERS + [o["id"] for o in NEW_ORDERS]
        statuses = api_call({"action": "status", "orders": ",".join(all_ids)})
        counts = {}
        for oid, info in statuses.items():
            prev_status = STATE.get("orders", {}).get(oid, {}).get("status", "?")
            curr_status = info.get("status", "?")
            STATE.update_order(oid, info)
            if curr_status != prev_status and prev_status != "?":
                self.log(f"#{oid} {prev_status} → {C['yellow']}{curr_status}{C['reset']}")
            counts[curr_status] = counts.get(curr_status, 0) + 1
        self.log("  ".join(f"{s}={n}" for s, n in counts.items()))


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 3: Refill API Prober — exhaustive API-level + panel refill attempts
# NOTE: Old orders (service 8140) have refill PERMANENTLY DISABLED at panel
#       level — no refill button exists in the UI, API returns "disabled".
#       New orders (service 12452/13139) have a 24h cooldown after completion.
# ══════════════════════════════════════════════════════════════════════════════
class RefillAPIProber(BaseAgent):
    NAME  = "REFILL-API"
    COLOR = "magenta"
    CYCLE = 1800

    # Every documented + undocumented action to try
    ACTIONS = [
        "refill", "refill_order", "force_refill", "manual_refill",
        "refill_v2", "re_refill", "refill_now", "do_refill",
        "trigger_refill", "start_refill", "request_refill",
        "resend", "retry", "reprocess", "reorder",
        "order_refill", "refill_request", "add_refill",
        "refill_add", "submit_refill", "queue_refill",
    ]
    EXTRA_PARAMS = [
        {},
        {"force": "1"},
        {"override": "1"},
        {"admin": "1"},
        {"type": "manual"},
        {"priority": "high"},
        {"reason": "drop"},
    ]

    def _panel_refill(self, sess: requests.Session, oid: str) -> bool:
        """Try the real panel refill endpoint (GET /orders/{id}/refill).
        Returns True on success."""
        try:
            r = sess.get(f"{PANEL}/orders/{oid}/refill", timeout=10,
                         headers={"X-Requested-With": "XMLHttpRequest",
                                  "Accept": "application/json",
                                  "Referer": f"{PANEL}/orders"})
            if r.status_code == 200:
                try:
                    data = r.json()
                    if data.get("status") == "success":
                        self.log(f"  {C['green']}PANEL REFILL SUCCESS #{oid}: {data}")
                        STATE.mark_refilled(oid, f"panel:{data.get('btn_text','ok')}")
                        return True
                    else:
                        err = data.get("error", str(data))
                        self.log(f"  Panel #{oid}: {err}")
                        STATE.record_discovery(f"panel_refill_err:{oid}", err)
                except Exception:
                    self.log(f"  Panel #{oid} non-JSON: {r.text[:80]}")
        except Exception as exc:
            self.log(f"  Panel request failed: {exc}", "warning")
        return False

    def _read_refill_badges(self, sess: requests.Session):
        """Scrape the orders page for refill availability badges/links."""
        try:
            r = sess.get(f"{PANEL}/orders", timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            # Countdown badges (cooldown still active)
            for span in soup.find_all("span", {"data-status": "Refill"}):
                title = span.get("title", "")
                if title:
                    self.log(f"  Cooldown badge: {title}")
                    STATE.record_discovery("refill_cooldown", title)
            # Active refill links (cooldown expired → clickable)
            active = soup.find_all("a", href=re.compile(r"/orders/\d+/refill"))
            for a in active:
                oid = re.search(r"/orders/(\d+)/refill", a["href"]).group(1)
                self.log(f"  {C['green']}ACTIVE REFILL LINK for #{oid}!")
                STATE.record_discovery(f"active_refill_link:{oid}", a["href"])
        except Exception as exc:
            self.log(f"  Badge scrape failed: {exc}", "warning")

    def cycle(self):
        # Old orders (service 8140): refill permanently disabled — no button exists
        # Only target new refillable orders
        targets = [o["id"] for o in NEW_ORDERS if o["refillable"]]
        if not targets:
            self.log("No refillable targets")
            return

        # Get a web session for panel-based attempts
        sess = web_session()

        # Always scrape refill badges so we know the countdown
        if sess:
            self._read_refill_badges(sess)

        # Report old order status definitively
        old_status = STATE.get("orders", {})
        old_remaining = {oid: old_status.get(oid, {}).get("remains", "?") for oid in OLD_ORDERS}
        self.log(f"  Old svc-8140 (refill disabled): {old_remaining}")

        for oid in targets:
            if STATE.was_refilled(oid):
                continue
            info = STATE.get("orders", {}).get(oid, {})
            if info.get("status") not in ("Completed", "Partial"):
                continue

            self.log(f"Probing refill for #{oid} (status={info.get('status')})")

            # 1. Panel endpoint (real UI flow)
            if sess and self._panel_refill(sess, oid):
                continue

            # 2. Standard API on multiple base URLs
            for base_url in [API_URL,
                              "https://smmfollows.com/api/v1",
                              "https://smmfollows.com/api/v3",
                              "https://smmfollows.com/api"]:
                try:
                    res = api_call({"action": "refill", "order": oid}, url=base_url)
                    if "error" not in res:
                        STATE.mark_refilled(oid, res.get("refill"))
                        self.log(f"  {C['green']}API REFILL OK via {base_url}! {res}")
                        break
                    elif res.get("error") not in ("Invalid action", "Not found"):
                        self.log(f"  {base_url}: {res['error']}")
                except Exception:
                    pass

            if STATE.was_refilled(oid):
                continue

            # 3. All undocumented action names (one-shot per key)
            for action in self.ACTIONS[1:]:
                probe_key = f"{action}:{oid}"
                if STATE.already_probed(probe_key):
                    continue
                try:
                    res = api_call({"action": action, "order": oid})
                    STATE.mark_probed(probe_key)
                    if "error" not in res:
                        self.log(f"  {C['green']}ACTION '{action}' WORKED: {res}")
                        STATE.record_discovery(f"working_action_{action}", res)
                        STATE.mark_refilled(oid, res.get("refill", action))
                        break
                    elif res.get("error") not in ("Invalid action",):
                        self.log(f"  action={action}: {res['error']}")
                except Exception:
                    pass

            if STATE.was_refilled(oid):
                continue

            # 4. Standard refill + extra params
            for extra in self.EXTRA_PARAMS[1:]:
                try:
                    payload = {"action": "refill", "order": oid, **extra}
                    res = api_call(payload)
                    if "error" not in res:
                        self.log(f"  {C['green']}REFILL+{extra} WORKED: {res}")
                        STATE.mark_refilled(oid, res.get("refill"))
                        break
                except Exception:
                    pass


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 4: Ticket Watcher — READ ONLY, no posting
# ══════════════════════════════════════════════════════════════════════════════
class TicketWatcher(BaseAgent):
    NAME  = "TICKET-WATCH"
    COLOR = "yellow"
    CYCLE = 900

    def cycle(self):
        sess = web_session()
        if not sess:
            self.log("login failed", "warning")
            return
        r = sess.get(f"{PANEL}/viewticket/944469", timeout=20)
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
            msgs.append((txt, is_staff))
        prev = STATE.get("ticket_msg_count", 0)
        if len(msgs) > prev:
            for txt, is_staff in msgs[prev:]:
                who = f"{C['green']}SUPPORT" if is_staff else "You"
                self.log(f"New [{who}]: {txt[:150]}")
        STATE.set("ticket_msg_count", len(msgs))
        staff_count = sum(1 for _, s in msgs if s)
        self.log(f"Ticket #944469: {len(msgs)} msgs ({staff_count} from support) — READ ONLY")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 5: Likes Guard
# ══════════════════════════════════════════════════════════════════════════════
class LikesGuard(BaseAgent):
    NAME  = "LIKES"
    COLOR = "red"
    CYCLE = 600

    def cycle(self):
        for o in (x for x in NEW_ORDERS if x["type"] == "likes"):
            info = STATE.get("orders", {}).get(o["id"], {})
            self.log(f"#{o['id']} {info.get('status','?')} remains={info.get('remains','?')}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 6: Retweets Guard
# ══════════════════════════════════════════════════════════════════════════════
class RetweetsGuard(BaseAgent):
    NAME  = "RETWEETS"
    COLOR = "blue"
    CYCLE = 600

    def cycle(self):
        for o in (x for x in NEW_ORDERS if x["type"] == "retweets"):
            info = STATE.get("orders", {}).get(o["id"], {})
            self.log(f"#{o['id']} {info.get('status','?')} remains={info.get('remains','?')}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 7: Comments Guard
# ══════════════════════════════════════════════════════════════════════════════
class CommentsGuard(BaseAgent):
    NAME  = "COMMENTS"
    COLOR = "cyan"
    CYCLE = 600

    def cycle(self):
        for o in (x for x in NEW_ORDERS if x["type"] == "comments"):
            info = STATE.get("orders", {}).get(o["id"], {})
            self.log(f"#{o['id']} {info.get('status','?')} remains={info.get('remains','?')}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 8: Endpoint Explorer — Yii2 route patterns + panel pages
# ══════════════════════════════════════════════════════════════════════════════
class EndpointExplorer(BaseAgent):
    NAME  = "ENDPOINT"
    COLOR = "magenta"
    CYCLE = 3600

    # Yii2 controller/action route patterns
    YII2_ROUTES = [
        # order controller
        "/order/refill", "/order/do-refill", "/order/request-refill",
        "/order/force-refill", "/order/manual-refill", "/order/re-refill",
        "/order/resend", "/order/retry", "/order/reprocess",
        "/order/view", "/order/update", "/order/complete",
        # refill controller
        "/refill/create", "/refill/do", "/refill/request",
        "/refill/add", "/refill/submit", "/refill/process",
        "/refill/force", "/refill/manual", "/refill/index",
        # orders (plural) controller
        "/orders/do-refill", "/orders/request-refill",
        "/orders/manual-refill", "/orders/force-refill",
        # site controller
        "/site/refill", "/site/order-refill",
        # api controller
        "/api/order/refill", "/api/refill/create",
        "/api/v2/order/refill", "/api/v2/refill",
        # admin
        "/admin/refill/create", "/admin/order/refill",
        "/admin/refill/do", "/admin/order/do-refill",
    ]

    # Panel pages that might have useful forms/actions
    PANEL_PAGES = [
        "/refill", "/refills", "/order-refill",
        "/orders/refill", "/refill-status",
        "/account", "/profile", "/settings",
        "/api", "/api/docs", "/api/help",
    ]

    def cycle(self):
        sess = web_session()
        if not sess:
            self.log("login failed")
            return

        self.log("Probing Yii2 routes and panel pages...")
        found = []

        # 1. Probe all Yii2 routes
        for path in self.YII2_ROUTES:
            probe_key = f"ep:{path}"
            if STATE.already_probed(probe_key):
                continue
            try:
                r = sess.get(PANEL + path, timeout=8, allow_redirects=False)
                STATE.mark_probed(probe_key)
                if r.status_code not in (404, 302):
                    self.log(f"  {C['yellow']}GET {path} → {r.status_code} len={len(r.content)}")
                    found.append(path)
                    STATE.record_discovery(f"route:{path}", {"status": r.status_code, "len": len(r.content)})

                    # If it's an interesting page, try POST too
                    if r.status_code in (200, 405, 500):
                        self._try_post_refill(sess, path)
            except Exception:
                pass

        # 2. POST to Yii2 refill routes directly
        for path in ["/order/refill", "/refill/create", "/orders/do-refill"]:
            self._try_post_refill(sess, path)

        # 3. Probe panel pages for useful forms
        for path in self.PANEL_PAGES:
            try:
                r = sess.get(PANEL + path, timeout=10, allow_redirects=True)
                if r.status_code == 200 and len(r.content) > 10000:
                    soup = BeautifulSoup(r.text, "html.parser")
                    forms = soup.find_all("form")
                    for f in forms:
                        action = f.get("action", "")
                        if any(kw in action.lower() for kw in ["refill", "order", "resend"]):
                            self.log(f"  {C['green']}FORM at {path}: action={action}")
                            found.append(f"form:{path}:{action}")
            except Exception:
                pass

        if found:
            self.log(f"Discoveries: {found}")
        else:
            self.log("No new endpoints found this cycle")

    def _try_post_refill(self, sess: requests.Session, path: str):
        """Try POST-based refill submission for all old orders."""
        for oid in OLD_ORDERS:
            probe_key = f"post:{path}:{oid}"
            if STATE.already_probed(probe_key):
                continue
            STATE.mark_probed(probe_key)
            try:
                # Get CSRF from the page first
                r_page = sess.get(PANEL + "/orders", timeout=10)
                soup = BeautifulSoup(r_page.text, "html.parser")
                meta_csrf = soup.find("meta", {"name": "csrf-token"})
                csrf_inp = soup.find("input", {"name": "_csrf"})
                csrf_val = (meta_csrf.get("content") if meta_csrf
                            else csrf_inp["value"] if csrf_inp else "")

                for payload_data in [
                    [("order_id", oid), ("_csrf", csrf_val)],
                    [("id", oid), ("_csrf", csrf_val)],
                    [("orderId", oid), ("_csrf", csrf_val)],
                    [("order", oid), ("_csrf", csrf_val)],
                    [("OrderRefillForm[order_id]", oid), ("_csrf", csrf_val)],
                ]:
                    r = sess.post(PANEL + path, data=urlencode(payload_data),
                                  headers={"Content-Type": "application/x-www-form-urlencoded",
                                           "X-Requested-With": "XMLHttpRequest",
                                           "Referer": PANEL + "/orders"},
                                  allow_redirects=False, timeout=10)
                    if r.status_code not in (404, 400) and len(r.content) > 5:
                        self.log(f"  {C['green']}POST {path} [{oid}] → {r.status_code}: {r.text[:100]}")
                        STATE.record_discovery(f"post_refill:{path}:{oid}",
                                               {"status": r.status_code, "body": r.text[:200]})
                        break
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 9: JS Bundle Analyzer — deep extraction of AJAX endpoints
# ══════════════════════════════════════════════════════════════════════════════
class JSBundleAnalyzer(BaseAgent):
    NAME  = "JS-ANALYZE"
    COLOR = "magenta"
    CYCLE = 7200

    def cycle(self):
        sess = web_session()
        if not sess:
            return

        self.log("Downloading and analyzing JS bundles...")

        # Get all JS files
        r_main = sess.get(PANEL + "/", timeout=20)
        soup = BeautifulSoup(r_main.text, "html.parser")
        js_sources = [s.get("src", "") for s in soup.find_all("script", src=True) if s.get("src")]

        # Also scrape orders and refill pages for additional JS
        for page in ["/orders", "/refill"]:
            try:
                rp = sess.get(PANEL + page, timeout=15)
                sp = BeautifulSoup(rp.text, "html.parser")
                js_sources += [s.get("src", "") for s in sp.find_all("script", src=True) if s.get("src")]
            except Exception:
                pass

        js_sources = list(set(js_sources))
        all_endpoints: set[str] = set()
        refill_code_blocks: list[str] = []

        for js_url in js_sources:
            if not js_url:
                continue
            if not js_url.startswith("http"):
                js_url = PANEL + js_url
            try:
                jr = sess.get(js_url, timeout=15)
                txt = jr.text

                # Extract all string paths
                paths = re.findall(r'["\']/([\w\-/?.=&]+)["\']', txt)
                all_endpoints.update(p for p in paths if 2 < len(p) < 60)

                # Find refill-specific code blocks
                for m in re.finditer(r'.{0,200}refill.{0,200}', txt, re.IGNORECASE):
                    block = m.group().strip()
                    if any(kw in block.lower() for kw in ["url", "ajax", "post", "fetch", "action", "href"]):
                        refill_code_blocks.append(f"[{js_url.split('/')[-1]}] {block[:300]}")

                # Extract ajax/fetch call patterns
                ajax_calls = re.findall(
                    r'(?:url|href|action)\s*[:=]\s*["\']([^"\']+)["\']', txt
                )
                for call in ajax_calls:
                    if any(kw in call.lower() for kw in ["refill", "order", "api"]):
                        self.log(f"  AJAX endpoint: {call[:100]}")
                        STATE.record_discovery(f"ajax:{call}", js_url)

                # Look for window.modules config (found je348cke2pr1agxl.js previously)
                modules = re.findall(r'window\.modules\.(\w+)\s*=\s*(\{[^}]+\})', txt)
                for mod_name, mod_body in modules:
                    if any(kw in mod_body.lower() for kw in ["refill", "order"]):
                        self.log(f"  window.modules.{mod_name}: {mod_body[:200]}")
                        STATE.record_discovery(f"module:{mod_name}", mod_body)

            except Exception as exc:
                self.log(f"  JS {js_url.split('/')[-1]}: {exc}", "warning")

        # Test newly discovered endpoints
        interesting = [p for p in all_endpoints
                       if any(kw in p.lower() for kw in ["refill", "order", "api", "admin"])
                       and not STATE.already_probed(f"js_ep:{p}")]

        self.log(f"Found {len(all_endpoints)} paths, {len(interesting)} interesting, "
                 f"{len(refill_code_blocks)} refill code blocks")

        for ep in interesting[:30]:
            STATE.mark_probed(f"js_ep:{ep}")
            try:
                r = sess.get(PANEL + "/" + ep.lstrip("/"), timeout=8, allow_redirects=False)
                if r.status_code not in (404,):
                    self.log(f"  {C['yellow']}/{ep} → {r.status_code} len={len(r.content)}")
                    STATE.record_discovery(f"js_found:{ep}", r.status_code)
            except Exception:
                pass

        for block in refill_code_blocks[:5]:
            self.log(f"  Refill code: {block[:200]}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 10: Master Coordinator
# ══════════════════════════════════════════════════════════════════════════════
class MasterCoordinator(BaseAgent):
    NAME  = "COORD"
    COLOR = "yellow"
    CYCLE = 600

    def cycle(self):
        orders  = STATE.get("orders", {})
        refills = STATE.get("refills", {})
        bal     = float(STATE.get("balance", "0") or "0")
        disc    = STATE.get("discovered", {})

        counts: dict[str, int] = {}
        for info in orders.values():
            s = info.get("status", "?")
            counts[s] = counts.get(s, 0) + 1

        self.log(f"${bal:.4f} | Orders: {counts} | Refills done: {list(refills.keys())}")

        pending_refill = [
            o["id"] for o in NEW_ORDERS
            if o["refillable"]
            and orders.get(o["id"], {}).get("status") == "Completed"
            and not STATE.was_refilled(o["id"])
        ]

        # Cooldown info from last badge scrape
        cooldown = disc.get("refill_cooldown", "")
        if pending_refill:
            cd_note = f" — cooldown: {cooldown}" if cooldown else ""
            self.log(f"  {C['yellow']}New orders pending refill: {pending_refill}{cd_note}")

        # Old orders: refill permanently disabled (service 8140 no button)
        self.log(f"  {C['red']}Old svc-8140 orders: refill disabled at panel level (no button)")

        # Active refill links discovered
        active = [k for k in disc if k.startswith("active_refill_link:")]
        if active:
            self.log(f"  {C['green']}ACTIVE REFILL LINKS: {active}")

        if disc:
            non_cooldown = {k: v for k, v in disc.items()
                            if not k.startswith("panel_refill_err") and k != "refill_cooldown"}
            if non_cooldown:
                self.log(f"  Discoveries: {list(non_cooldown.keys())[:10]}")
        if bal < 0.05:
            self.log(f"  {C['red']}ADD FUNDS — balance critical")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 11: AI Researcher — Claude-powered hypothesis engine
# Reads all panel discoveries, asks Claude to reason about patterns,
# generate novel endpoint/param combinations, then executes them live.
# ══════════════════════════════════════════════════════════════════════════════
class AIResearcher(BaseAgent):
    NAME  = "AI-RESEARCH"
    COLOR = "cyan"
    CYCLE = 1800   # 30 min — waits for new data between runs

    # Accumulated experiment log persisted in STATE
    _EXP_KEY = "ai_experiments"

    def _ask_claude(self, prompt: str) -> str:
        """Call Claude API. Raises anthropic.BadRequestError if no credits."""
        if not ANTHROPIC_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()

    def _builtin_hypotheses(self) -> dict:
        """Rule-based hypothesis engine (runs when Claude API has no credits).
        Generates structured experiments based on Yii2 patterns and known behaviour."""
        orders = STATE.get("orders", {})
        disc   = STATE.get("discovered", {})

        exps = []
        eid  = [0]
        def nid():
            eid[0] += 1
            return f"EXP-{eid[0]:03d}"

        # — Yii2 order detail page (check if refill form is hidden there)
        for oid in OLD_ORDERS:
            exps.append({"id": nid(), "method": "GET",
                "url": f"/orders/{oid}/view",
                "headers": {}, "body": {},
                "success_signal": "refill form or button in HTML",
                "reasoning": "Yii2 /controller/id/action — view action may expose refill form"})

        # — POST the refill form directly with CSRF
        exps.append({"id": nid(), "method": "POST",
            "url": "/orders/{order_id}/refill",
            "headers": {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
            "body": {"_csrf": "__CSRF__"},
            "success_signal": '{"status":"success"}',
            "reasoning": "Panel JS uses GET but POST may bypass cooldown guard"})

        # — Try /orders/{id}/force-refill Yii2 dash action
        exps.append({"id": nid(), "method": "GET",
            "url": "/orders/{order_id}/force-refill",
            "headers": {"X-Requested-With": "XMLHttpRequest"},
            "body": {},
            "success_signal": "success in response",
            "reasoning": "Yii2 dash-action naming convention for admin shortcut"})

        # — Panel account settings — look for hidden admin flags
        exps.append({"id": nid(), "method": "GET",
            "url": "/account/settings",
            "headers": {}, "body": {},
            "success_signal": "settings page with extra fields",
            "reasoning": "Account settings may expose service-level toggles"})

        # — Service management page
        exps.append({"id": nid(), "method": "GET",
            "url": "/services/8140",
            "headers": {}, "body": {},
            "success_signal": "page with refill toggle",
            "reasoning": "Service detail page may allow per-user refill override"})

        # — Order detail page
        for oid in OLD_ORDERS[:2]:
            exps.append({"id": nid(), "method": "GET",
                "url": f"/order/{oid}",
                "headers": {}, "body": {},
                "success_signal": "page with refill button",
                "reasoning": "Alternative singular /order/ route in Yii2"})

        # — Try /refill/create with POST body
        exps.append({"id": nid(), "method": "POST",
            "url": "/refill/create",
            "headers": {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
            "body": {"order_id": "{order_id}", "_csrf": "__CSRF__"},
            "success_signal": "success or refill id",
            "reasoning": "Yii2 /refill/create is the standard create action"})

        # — Try /refill/do
        exps.append({"id": nid(), "method": "POST",
            "url": "/refill/do",
            "headers": {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
            "body": {"id": "{order_id}", "_csrf": "__CSRF__"},
            "success_signal": "success in body",
            "reasoning": "Yii2 /refill/do may be the AJAX handler for the #setRefill modal"})

        # — Try history page for setRefill modal form action
        exps.append({"id": nid(), "method": "GET",
            "url": "/history",
            "headers": {}, "body": {},
            "success_signal": "#setRefill modal with form action exposed",
            "reasoning": "siteHistory JS module uses #setRefill modal — it lives on /history page"})

        # — /user/orders or /user/order for alternative routing
        exps.append({"id": nid(), "method": "GET",
            "url": "/user/orders",
            "headers": {}, "body": {},
            "success_signal": "page loads with refill buttons",
            "reasoning": "Alternative Yii2 user-scoped order controller"})

        # — Direct API refill with 'orders' (plural) key
        exps.append({"id": nid(), "method": "POST",
            "url": "/api/v2",
            "headers": {}, "body": {"action": "refill", "orders": "61218148,61218147,61218151,61218154"},
            "success_signal": "refill key in response",
            "reasoning": "Bulk refill may use plural 'orders' instead of 'order'"})

        # — Check order-specific detail using numeric /orders?search=
        for oid in OLD_ORDERS[:2]:
            exps.append({"id": nid(), "method": "GET",
                "url": f"/orders?search={oid}",
                "headers": {}, "body": {},
                "success_signal": "refill button rendered for this order",
                "reasoning": "Search view may render different action buttons"})

        return {
            "analysis": (
                "Service 8140 has refill disabled at panel level (no UI button, API blocked). "
                "New orders (12452/13139) are in 24h cooldown. "
                "Built-in hypothesis engine active (Claude API credits not loaded yet)."
            ),
            "experiments": exps,
            "unexplored_pages": ["/history", "/account/settings", "/services/8140",
                                  "/order/refill", "/user/orders", "/user/profile",
                                  "/orders/history", "/refill/index"],
            "priority_action": "Check /history page for #setRefill modal form action"
        }

    def _build_context(self) -> str:
        orders   = STATE.get("orders", {})
        disc     = STATE.get("discovered", {})
        probed   = STATE.get("probed", [])
        refills  = STATE.get("refills", {})
        bal      = STATE.get("balance", "0")
        cooldown = disc.get("refill_cooldown", "unknown")
        prev_exp = STATE.get(self._EXP_KEY, [])[-10:]  # last 10 experiments

        order_summary = []
        for oid, info in orders.items():
            order_summary.append(
                f"  #{oid}: status={info.get('status')} remains={info.get('remains')} "
                f"service={'8140' if oid in OLD_ORDERS else '12452/13139'}"
            )

        disc_summary = []
        for k, v in disc.items():
            if not k.startswith("panel_refill_err") and k != "refill_cooldown":
                disc_summary.append(f"  {k}: {str(v)[:120]}")

        return f"""You are analyzing a Yii2 PHP panel at https://smmfollows.com (SMM panel).
Goal: trigger refill for orders that are either (a) past 24h cooldown or (b) on service 8140 which has refill "disabled".

CURRENT STATE
=============
Balance: ${bal}
Refill cooldown (new orders 12452/13139): {cooldown}
Orders already refilled: {list(refills.keys())}

ORDER STATUSES
==============
{chr(10).join(order_summary)}

OLD ORDERS (service 8140 — "Refill is disabled for this service"):
  #61218148 Completed remains=0
  #61218147 Partial   remains=4
  #61218151 Partial   remains=11
  #61218154 Partial   remains=11

NEW ORDERS (services 12452/13139 — 24h cooldown active):
  #61450840 likes     Completed
  #61450841 retweets  Completed
  #61450843 likes     Completed
  #61450844 retweets  Completed
  #61450846 likes     Completed
  #61450847 retweets  Completed

ALREADY DISCOVERED
==================
{chr(10).join(disc_summary) if disc_summary else "  (none yet)"}

ALREADY PROBED (action names / endpoint keys):
{json.dumps(probed[:40], indent=2)}

PREVIOUS AI EXPERIMENTS
=======================
{json.dumps(prev_exp, indent=2)}

KNOWN PANEL BEHAVIOUR
=====================
- POST https://smmfollows.com/api/v2 with key+action — standard v2 API
- GET  /orders/{{id}}/refill (AJAX) → {{"status":"error","error":"Error"}} during cooldown
- GET  /orders/{{id}}/refill → expect {{"status":"success","btn_text":"..."}} when ready
- Service 8140 API: returns "Refill is disabled for this service"
- Panel HTML: service 8140 order rows have NO refill button, only re-order
- Panel HTML: new orders show countdown badge <span data-status="Refill" title="...">
- Admin routes (/admin/refill/create etc.) return 500 (need admin session)
- Yii2 framework: routes are /controller/action-name
- JS bundle je348cke2pr1agxl.js: siteHistory module uses #setRefill modal
  that POSTs to form action= (unknown endpoint, need to find the modal in HTML)
- /refill page = refill history search (not a trigger)
- CSRF token available from <meta name="csrf-token"> or <input name="_csrf">

TASK
====
1. Identify the MOST PROMISING untried approach to trigger refill for the
   old service-8140 orders (impossible via standard API — need creative path).
2. Identify best approach for new orders once cooldown expires.
3. Suggest 5–10 concrete experiments: each must specify:
   - HTTP method, URL path, headers, body params
   - What response would indicate success vs failure
   - Why this might work (reasoning)
4. Also: what panel pages/routes have we NOT explored that might reveal
   the actual refill mechanism? (Yii2 admin controllers, user profile,
   order detail page, etc.)

Reply in this exact JSON format (no markdown, pure JSON):
{{
  "analysis": "2-3 sentence summary of the situation",
  "experiments": [
    {{
      "id": "EXP-001",
      "method": "GET|POST",
      "url": "/path/here",
      "headers": {{"Header-Name": "value"}},
      "body": {{"param": "value"}},
      "success_signal": "what response means success",
      "reasoning": "why this might work"
    }}
  ],
  "unexplored_pages": ["/path1", "/path2"],
  "priority_action": "single most important thing to try right now"
}}"""

    def _execute_experiment(self, exp: dict, sess: requests.Session | None,
                             csrf: str = "") -> dict:
        method  = exp.get("method", "GET").upper()
        path    = exp.get("url", "")
        headers = exp.get("headers", {})
        body    = {k: (v.replace("__CSRF__", csrf) if isinstance(v, str) else v)
                   for k, v in exp.get("body", {}).items()}

        if not path.startswith("http"):
            url = PANEL + path
        else:
            url = path

        result = {"id": exp.get("id"), "url": url, "method": method,
                  "status": None, "body": None, "success": False}
        try:
            base_headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                            "Referer": PANEL + "/orders"}
            base_headers.update(headers)

            req_sess = sess or requests.Session()
            if method == "GET":
                r = req_sess.get(url, headers=base_headers, timeout=12, allow_redirects=False)
            else:
                r = req_sess.post(url, data=body, headers={
                    **base_headers, "Content-Type": "application/x-www-form-urlencoded"
                }, timeout=12, allow_redirects=False)

            result["status"] = r.status_code
            result["body"] = r.text[:300]

            content_type = r.headers.get("Content-Type", "")
            is_json = "application/json" in content_type or r.text.lstrip().startswith("{")

            if r.status_code == 200 and is_json:
                try:
                    jdata = r.json()
                    if jdata.get("status") == "success":
                        result["success"] = True
                        self.log(f"  {C['green']}JSON SUCCESS {exp['id']}: {r.text[:150]}")
                        STATE.record_discovery(f"ai_success:{exp['id']}", result)
                    else:
                        self.log(f"  {exp['id']} JSON: {r.text[:120]}")
                except Exception:
                    pass
            elif r.status_code == 200 and not is_json:
                # HTML page — record it for manual review, but log summary
                snippet = r.text[:120].replace("\n", " ").strip()
                self.log(f"  {exp['id']} HTML-200 {path}: {snippet[:80]}")
                STATE.record_discovery(f"ai_page:{path}", r.url)
            elif r.status_code not in (404, 400, 403):
                snippet = r.text[:80].replace("\n", " ").strip()
                self.log(f"  {exp['id']} {method} {path} → {r.status_code}: {snippet}")

        except Exception as exc:
            result["error"] = str(exc)
            self.log(f"  {exp['id']} failed: {exc}", "warning")

        return result

    def _inject_order_ids(self, exp: dict) -> list[dict]:
        """Expand one experiment template into per-order experiments."""
        body = exp.get("body", {})
        # If body has a placeholder order field, expand per order
        has_order_placeholder = any(
            "{order_id}" in str(v) for v in body.values()
        ) or any(
            "{order_id}" in str(v) for v in [exp.get("url", "")]
        )
        if not has_order_placeholder:
            return [exp]

        expanded = []
        for oid in OLD_ORDERS + [o["id"] for o in NEW_ORDERS if o["refillable"]]:
            import copy
            e = copy.deepcopy(exp)
            e["id"] = f"{exp['id']}-{oid}"
            e["url"] = e.get("url", "").replace("{order_id}", oid)
            e["body"] = {k: v.replace("{order_id}", oid) if isinstance(v, str) else v
                         for k, v in e.get("body", {}).items()}
            expanded.append(e)
        return expanded

    def cycle(self):
        self.log("Querying Claude for research hypotheses...")
        data = None

        # Try Claude API first; fall back to built-in engine on credit/network errors
        try:
            context = self._build_context()
            reply   = self._ask_claude(context)
            try:
                clean = re.sub(r"```json|```", "", reply).strip()
                data  = json.loads(clean)
                self.log(f"  {C['green']}Claude API active — using AI hypotheses")
            except Exception:
                self.log(f"Claude non-JSON reply: {reply[:200]}", "warning")
                STATE.record_discovery("ai_raw_reply", reply[:500])
        except ValueError:
            self.log(f"  {C['yellow']}ANTHROPIC_API_KEY not set — using built-in engine")
            data = self._builtin_hypotheses()
        except anthropic.BadRequestError as exc:
            if "credit balance" in str(exc).lower():
                self.log(f"  {C['yellow']}Claude credits not loaded — using built-in engine")
                data = self._builtin_hypotheses()
            else:
                self.log(f"Claude BadRequest: {exc}", "error")
                data = self._builtin_hypotheses()
        except Exception as exc:
            self.log(f"Claude error: {exc} — using built-in engine", "warning")
            data = self._builtin_hypotheses()

        if not data:
            return

        analysis  = data.get("analysis", "")
        priority  = data.get("priority_action", "")
        exps      = data.get("experiments", [])
        unexplored = data.get("unexplored_pages", [])

        self.log(f"Analysis: {analysis}")
        self.log(f"Priority: {C['yellow']}{priority}")
        self.log(f"Experiments: {len(exps)} | Unexplored pages: {len(unexplored)}")

        # Log unexplored pages to STATE for EndpointExplorer
        for page in unexplored:
            STATE.record_discovery(f"ai_unexplored:{page}", "suggested by AI")

        # Get a web session + CSRF token for execution
        sess = web_session()
        csrf = ""
        if sess:
            try:
                r_csrf = sess.get(f"{PANEL}/orders", timeout=12)
                soup_c = BeautifulSoup(r_csrf.text, "html.parser")
                meta = soup_c.find("meta", {"name": "csrf-token"})
                inp  = soup_c.find("input", {"name": "_csrf"})
                csrf = meta["content"] if meta else (inp["value"] if inp else "")
            except Exception:
                pass

        # Execute each experiment
        experiment_log = STATE.get(self._EXP_KEY, [])
        for exp_template in exps:
            expanded = self._inject_order_ids(exp_template)
            for exp in expanded:
                exp_key = f"ai_exp:{exp['id']}:{exp.get('url','')}"
                if STATE.already_probed(exp_key):
                    continue
                STATE.mark_probed(exp_key)

                result = self._execute_experiment(exp, sess, csrf)
                experiment_log.append({
                    "at": datetime.now().isoformat(),
                    "exp": exp,
                    "result": result,
                })
                if result.get("success"):
                    self.log(f"  {C['green']}EXPERIMENT {exp['id']} SUCCEEDED!")
                    STATE.record_discovery("ai_breakthrough", exp)

        STATE.set(self._EXP_KEY, experiment_log[-50:])
        self.log(f"Cycle complete. Total AI experiments: {len(experiment_log)}")


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 12: Ethical Researcher
# Uses Claude with chain-of-thought to reason carefully about:
#   - what the panel legitimately allows for the user's account
#   - what evidence has been collected so far
#   - what the most honest interpretation of each finding is
#   - what the right next step is (technically and ethically)
# Writes a structured research report to ethical_research.log on each cycle.
# ══════════════════════════════════════════════════════════════════════════════
class EthicalResearcher(BaseAgent):
    NAME  = "ETHICAL"
    COLOR = "green"
    CYCLE = 3600           # 1 hour — deep reasoning takes time
    REPORT_F = Path("ethical_research.log")
    MODEL    = "claude-sonnet-4-6"   # full Sonnet for deeper CoT

    def _claude(self, system: str, user: str, max_tokens: int = 3000) -> str:
        if not ANTHROPIC_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        msg = client.messages.create(
            model=self.MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text.strip()

    # ── Evidence snapshot ────────────────────────────────────────────────────
    def _evidence(self) -> str:
        orders  = STATE.get("orders", {})
        disc    = STATE.get("discovered", {})
        refills = STATE.get("refills", {})
        bal     = STATE.get("balance", "0")
        exp_log = STATE.get("ai_experiments", [])[-20:]

        order_lines = []
        for oid, info in orders.items():
            svc = "8140" if oid in OLD_ORDERS else "12452/13139"
            order_lines.append(
                f"  #{oid} svc={svc} status={info.get('status')} "
                f"remains={info.get('remains')} refilled={'YES' if oid in refills else 'no'}"
            )

        disc_lines = [f"  {k}: {str(v)[:100]}"
                      for k, v in disc.items()
                      if k not in ("refill_cooldown",)]

        exp_summary = []
        for e in exp_log:
            res = e.get("result", {})
            exp_summary.append(
                f"  {e['exp'].get('id')} {e['exp'].get('method')} "
                f"{e['exp'].get('url')} → {res.get('status')} "
                f"{'SUCCESS' if res.get('success') else ''}"
            )

        cooldown = disc.get("refill_cooldown", "unknown")
        ticket_msgs = STATE.get("ticket_msg_count", 0)

        return f"""=== EVIDENCE COLLECTED BY ALL AGENTS ===

Panel: https://smmfollows.com  |  User: hhrh197  |  Balance: ${bal}
Support ticket #944469: {ticket_msgs} messages (read-only, no new posts)
New-order refill cooldown: {cooldown}

ORDER STATUS
{chr(10).join(order_lines) if order_lines else '  (none)'}

PANEL DISCOVERIES
{chr(10).join(disc_lines) if disc_lines else '  (none)'}

EXPERIMENTS RUN (last 20)
{chr(10).join(exp_summary) if exp_summary else '  (none)'}

KNOWN FACTS
- Service 8140 (old orders): panel shows ZERO refill button in order row HTML.
  API returns "Refill is disabled for this service". This is a panel-level block.
  The service description says "Refill: 30 Days ♻️" — a discrepancy.
- Services 12452 (likes) and 13139 (retweets): refill supported, 24h cooldown.
  Orders placed 2026-06-28 ~05:33 UTC. Cooldown expires ~2026-06-29 ~05:33 UTC.
- Panel JS: GET /orders/{{id}}/refill is the real UI refill endpoint.
  Returns {{"status":"error","error":"Error"}} during cooldown.
  Expected to return {{"status":"success"}} when ready.
- Admin routes (/admin/refill/create etc.) return HTTP 500 — need admin session.
- /refill page = refill history list (not a trigger).
- No #setRefill modal found on /orders or /history pages.
- Ticket #944469: staff has responded; reading only, no new posts sent."""

    # ── System prompt ────────────────────────────────────────────────────────
    SYSTEM = """You are an ethical technical researcher helping a user understand
the behavior of an SMM panel (SMMFollows.com) where they have a legitimate
paid account. Your job is to:

1. ANALYSE the evidence honestly — do not assume malice; consider bugs,
   misconfigurations, and legitimate business decisions.
2. REASON step-by-step (chain of thought) before reaching conclusions.
3. STAY within the scope of the user's own account and orders — do not
   suggest exploiting other users' data, privilege escalation beyond what
   a normal account should have, or bypassing authentication.
4. IDENTIFY what legitimate recourse exists when a promised service feature
   (e.g. "Refill: 30 Days") appears to be disabled.
5. PRODUCE a structured research report with: findings, confidence level,
   recommended next actions, and outstanding questions.

Be concise but thorough. Prioritise actionable findings."""

    # ── Per-cycle research prompt ────────────────────────────────────────────
    def _research_prompt(self, evidence: str, cycle: int) -> str:
        focus_rotation = [
            "service 8140 refill discrepancy (advertised vs blocked)",
            "what the panel JS refill flow tells us about the intended mechanism",
            "whether the 24h cooldown is a technical limit or a business policy",
            "what legitimate customer recourse options exist beyond tickets",
            "synthesise all findings into a complete picture and recommend the clearest path forward",
        ]
        focus = focus_rotation[cycle % len(focus_rotation)]

        return f"""RESEARCH CYCLE {cycle} — Focus: {focus}

{evidence}

Please provide:

1. CHAIN OF THOUGHT — reason step by step about the evidence above,
   especially as it relates to the focus topic.

2. FINDINGS — bullet list, each with a confidence level (HIGH/MED/LOW)
   and one sentence of supporting evidence.

3. NEXT EXPERIMENTS — 3-5 specific, targeted probes that have NOT been
   tried yet and are within the scope of a normal user account.
   Format each as: [METHOD] /path body={{...}} — reason

4. LEGITIMATE RECOURSE OPTIONS — non-ticket ways the user could escalate
   or resolve the service discrepancy for service 8140.

5. OUTSTANDING QUESTIONS — what would change your conclusions if answered.

Keep findings grounded in the evidence. Flag speculations clearly."""

    # ── Cycle ───────────────────────────────────────────────────────────────
    def cycle(self):
        self.log("Starting ethical research cycle...")
        evidence = self._evidence()
        cycle_n  = STATE.get("ethical_cycle", 0) + 1
        STATE.set("ethical_cycle", cycle_n)

        # Attempt Claude API; fall back to a structured local analysis
        try:
            prompt = self._research_prompt(evidence, cycle_n)
            report = self._claude(self.SYSTEM, prompt)
            source = "Claude"
        except ValueError:
            self.log(f"  {C['yellow']}API key not set — skipping this cycle")
            return
        except anthropic.BadRequestError as exc:
            if "credit balance" in str(exc).lower():
                self.log(f"  {C['yellow']}No credits — ethical researcher paused")
                return
            report = f"[Claude API error: {exc}]"
            source = "error"
        except Exception as exc:
            self.log(f"  Claude error: {exc}", "warning")
            return

        # Write report to file
        header = (f"\n{'═'*72}\n"
                  f"ETHICAL RESEARCH REPORT — Cycle {cycle_n} — "
                  f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} — via {source}\n"
                  f"{'═'*72}\n")
        with open(self.REPORT_F, "a") as f:
            f.write(header + report + "\n")

        # Log key findings to STATE
        STATE.record_discovery(f"ethical_report_{cycle_n}", report[:400])

        # Print summary lines
        lines = report.split("\n")
        for line in lines:
            line = line.strip()
            if line and (line.startswith(("FINDINGS", "NEXT EXP", "LEGITIMATE", "OUTSTANDING",
                                          "•", "-", "**", "HIGH", "MED", "LOW"))
                         or "confidence" in line.lower()):
                self.log(f"  {line[:140]}")

        self.log(f"Report written → {self.REPORT_F} (cycle {cycle_n}, source={source})")

        # Parse new experiments suggested by Claude and hand them to STATE
        # so EndpointExplorer or AIResearcher can pick them up
        new_eps = re.findall(
            r'\[(GET|POST)\]\s+(/[\w/\-{}]+)(?:\s+body=(\{[^}]*\}))?', report
        )
        if new_eps:
            self.log(f"  {C['cyan']}Claude suggested {len(new_eps)} new experiments:")
            for method, path, body in new_eps:
                self.log(f"    {method} {path}")
                STATE.record_discovery(f"ethical_exp:{method}:{path}", body or "")


# ══════════════════════════════════════════════════════════════════════════════
# LAUNCH
# ══════════════════════════════════════════════════════════════════════════════
def banner():
    print(f"""{C['bold']}{C['cyan']}
╔══════════════════════════════════════════════════════════════════════╗
║    12-AGENT DEEP PROBE + AI RESEARCH + ETHICAL RESEARCHER           ║
║  BALANCE · TRACKER · REFILL-API · TICKET-WATCH · LIKES · RETWEETS  ║
║  COMMENTS · ENDPOINT · JS-ANALYZE · COORD · AI-RESEARCH · ETHICAL  ║
╚══════════════════════════════════════════════════════════════════════╝
{C['reset']}""")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    banner()
    halt = threading.Event()

    agents: list[BaseAgent] = [
        BalanceMonitor(halt, args.once),    # 1
        OrderTracker(halt, args.once),      # 2
        RefillAPIProber(halt, args.once),   # 3
        TicketWatcher(halt, args.once),     # 4  read-only
        LikesGuard(halt, args.once),        # 5
        RetweetsGuard(halt, args.once),     # 6
        CommentsGuard(halt, args.once),     # 7
        EndpointExplorer(halt, args.once),  # 8
        JSBundleAnalyzer(halt, args.once),  # 9
        MasterCoordinator(halt, args.once), # 10
        AIResearcher(halt, args.once),      # 11 — Claude-powered hypothesis engine
        EthicalResearcher(halt, args.once), # 12 — CoT reasoning + structured reports
    ]

    log.info(f"Launching {len(agents)} agents (no ticket posting, AI research active)...")
    for a in agents:
        a.start()
        time.sleep(0.4)

    if args.once:
        for a in agents:
            a.join(timeout=180)
        log.info("One-shot complete.")
        return

    log.info("All agents running. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        log.info("Stopping...")
        halt.set()
        for a in agents:
            a.join(timeout=5)
        log.info("Done.")


if __name__ == "__main__":
    main()
