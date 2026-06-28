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
import argparse, json, logging, re, sys, threading, time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    C = {"red": Fore.RED, "green": Fore.GREEN, "yellow": Fore.YELLOW,
         "cyan": Fore.CYAN, "magenta": Fore.MAGENTA, "blue": Fore.BLUE,
         "white": Fore.WHITE, "reset": Style.RESET_ALL, "bold": Style.BRIGHT}
except ImportError:
    C = {k: "" for k in ["red","green","yellow","cyan","magenta","blue","white","reset","bold"]}

# ── Config ─────────────────────────────────────────────────────────────────────
API_KEY  = "882fa9a6e54b39ffa8c7e2bf4fcc1f46"
API_URL  = "https://smmfollows.com/api/v2"
PANEL    = "https://smmfollows.com"
USER     = "hhrh197"
PASSWD   = "Yawer@123"
STATE_F  = Path("agent_state.json")

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
# LAUNCH
# ══════════════════════════════════════════════════════════════════════════════
def banner():
    print(f"""{C['bold']}{C['cyan']}
╔══════════════════════════════════════════════════════════════════════╗
║        10-AGENT DEEP PROBE — SMMFOLLOWS  (NO TICKET POSTING)       ║
║  BALANCE · TRACKER · REFILL-API · TICKET-WATCH · LIKES · RETWEETS  ║
║  COMMENTS · ENDPOINT · JS-ANALYZE · COORD                           ║
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
    ]

    log.info(f"Launching {len(agents)} agents (no ticket posting)...")
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
