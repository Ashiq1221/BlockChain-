#!/usr/bin/env python3
"""
SMMFollows AI Manager — Cloudflare Intelligence Platform
---------------------------------------------------------
Full Cloudflare ecosystem:
  • Workers AI  — Multi-model ensemble (DeepSeek R1 + Llama 3.3 70B fast)
  • AI Gateway  — Unified routing, semantic caching, analytics
  • Vectorize   — Episodic memory: AI learns from every past cycle
  • D1 Database — Persistent SQL state, order history, analytics
  • KV Store    — Sub-millisecond SMM API response caching
  • Parallel tools — Batch multiple tool calls in one AI step
  • Confidence routing — Fast model scouts; deep model verifies critical decisions
  • Auto-provisioning — Creates all CF resources on first run

Usage:
  python automation.py                   # continuous monitoring loop
  python automation.py --once            # single cycle and exit
  python automation.py --status          # dashboard
  python automation.py --post URL        # queue a post URL for ordering
  python automation.py --refill          # refill-focused pass
  python automation.py --provision       # (re)create all Cloudflare resources
  python automation.py --analytics       # show D1 analytics report
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import anthropic as _anthropic_mod
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
import requests

# ── Env loader ────────────────────────────────────────────────────────────────

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

# ── Config ────────────────────────────────────────────────────────────────────

# SMM panels — tried in order, first success wins
PANELS = [
    {
        "name": "smmfollows",
        "url":  "https://smmfollows.com/api/v2",
        "web":  "https://smmfollows.com",
        "key":  os.environ.get("SMM_API_KEY", ""),
        "user": os.environ.get("SMM_USER", "hhrh197"),
        "pass": os.environ.get("SMM_PASS", "Yawer@123"),
        "services": {
            "likes":    {"id": 16465, "min": 10,  "max": 2_000_000, "rate_per_k": 2.10},
            "retweets": {"id": 9018,  "min": 100, "max": 3000,      "rate_per_k": 2.10},
            "comments": {"id": 7338,  "min": 5,   "max": 150,       "rate_per_k": 28.13},
            "views":    {"id": 17682, "min": 100, "max": 100_000_000, "rate_per_k": 1.5},
        },
    },
    {
        "name": "smmwiz",
        "url":  "https://smmwiz.com/api/v2",
        "web":  "https://smmwiz.com",
        "key":  os.environ.get("SMMWIZ_API_KEY", ""),
        "user": os.environ.get("SMMWIZ_USER", ""),
        "pass": os.environ.get("SMMWIZ_PASS", ""),
        "services": {
            "likes":    {"id": 17712, "min": 20,  "max": 5000,    "rate_per_k": 0.94},
            "retweets": {"id": 18535, "min": 100, "max": 100_000, "rate_per_k": 2.16},
            "comments": {"id": 0,     "min": 5,   "max": 0,       "rate_per_k": 0},
            "views":    {"id": 0,     "min": 100, "max": 0,       "rate_per_k": 0},
        },
    },
    {
        "name": "astrasmm",
        "url":  "https://astrasmm.com/api/v2",
        "web":  "https://astrasmm.com",
        "key":  os.environ.get("ASTRA_API_KEY", ""),
        "user": os.environ.get("ASTRA_USER", ""),
        "pass": os.environ.get("ASTRA_PASS", ""),
        "services": {
            "likes":    {"id": 18718, "min": 10,  "max": 50_000, "rate_per_k": 2.40},
            "retweets": {"id": 12109, "min": 100, "max": 10_000, "rate_per_k": 1.33},
            "comments": {"id": 0,     "min": 5,   "max": 0,      "rate_per_k": 0},
            "views":    {"id": 0,     "min": 100, "max": 0,      "rate_per_k": 0},
        },
    },
]
# Primary panel (backwards compat)
API_KEY = PANELS[0]["key"]
API_URL = PANELS[0]["url"]
PANEL   = "https://smmfollows.com"
USER    = os.environ.get("SMM_USER", "hhrh197")
PASSWD  = os.environ.get("SMM_PASS", "Yawer@123")

# Cloudflare identity
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "")
CF_GLOBAL_KEY = os.environ.get("CF_GLOBAL_API_KEY", "")
CF_EMAIL      = os.environ.get("CF_EMAIL", "")
CF_SCOPED_KEY = os.environ.get("DEEPSEEK_API_KEY", "")   # cfut_ token for inference

# Cloudflare AI models
CF_REASON_MODEL = os.environ.get("CF_AI_MODEL", "@cf/deepseek-ai/deepseek-r1-distill-llama-70b")
CF_FAST_MODEL   = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
CF_EMBED_MODEL  = "@cf/baai/bge-large-en-v1.5"
CF_EMBED_DIMS   = 1024

# Cloudflare service names (auto-provisioned)
CF_GATEWAY_ID    = os.environ.get("CF_GATEWAY_ID",       "smm-sentinel")
CF_VECTORIZE_IDX = os.environ.get("CF_VECTORIZE_INDEX",  "smm-episodic-memory")
CF_D1_DB_NAME    = os.environ.get("CF_D1_DB_NAME",       "smm-state")
CF_KV_TITLE      = os.environ.get("CF_KV_TITLE",         "smm-cache")
CF_R2_BUCKET     = os.environ.get("CF_R2_BUCKET",        "smm-logs")
X_ACCOUNT_HANDLE = os.environ.get("X_ACCOUNT_HANDLE",    "")

# Fallback AI keys
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
DEEPSEEK_DIRECT = os.environ.get("DEEPSEEK_API_KEY", "")

# Ensemble thresholds
CONFIDENCE_THRESHOLD = 0.75
CRITICAL_TOOLS = {"submit_ticket", "place_order"}

# Service catalogue (primary panel defaults, overridden per-panel at order time)
SERVICES = {
    "likes":    {"id": 16465, "name": "Twitter Likes+Impressions USA",    "refill": False, "min": 10,  "max": 2_000_000,   "rate_per_k": 2.10},
    "retweets": {"id": 9018,  "name": "Twitter Retweets Organic Global",  "refill": False, "min": 100, "max": 3000,        "rate_per_k": 2.10},
    "comments": {"id": 7338,  "name": "Twitter Comments USA",             "refill": False, "min": 5,   "max": 150,         "rate_per_k": 28.13},
    "views":    {"id": 17682, "name": "Twitter Views HQ",                 "refill": False, "min": 100, "max": 100_000_000, "rate_per_k": 1.5},
}

STATE_FILE   = Path("automation_state.json")
POLL_SECS    = 300
ORDER_QTY    = {
    "likes":    int(os.environ.get("SMM_LIKES_QTY",    "100")),
    "retweets": int(os.environ.get("SMM_RETWEETS_QTY", "100")),
    "comments": int(os.environ.get("SMM_COMMENTS_QTY", "5")),
}

ENGAGEMENT_INTERVAL_H = 8
NEW_POST_PACKAGE = [
    {"kind": "likes",    "quantity": 100},
    {"kind": "retweets", "quantity": 50},
    {"kind": "comments", "quantity": 20},
    {"kind": "views",    "quantity": 30000},
]

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("automation.log")],
)
log = logging.getLogger(__name__)

# ── Cloudflare Platform ─────────────────────────────────────────────────────────────

class CloudflarePlatform:
    """Unified Cloudflare ecosystem client: Workers AI, Gateway, Vectorize, D1, KV."""

    _CF_BASE = "https://api.cloudflare.com/client/v4"

    def __init__(self) -> None:
        self._s = requests.Session()
        if CF_GLOBAL_KEY:
            self._s.headers.update({"X-Auth-Key": CF_GLOBAL_KEY, "X-Auth-Email": CF_EMAIL})
        self.gateway_ok    = False
        self.vectorize_ok  = False
        self.d1_db_id: str | None = None
        self.kv_ns_id: str | None = None

    def _acct(self, path: str = "") -> str:
        return f"{self._CF_BASE}/accounts/{CF_ACCOUNT_ID}{path}"

    def _req(self, method: str, url: str, **kw) -> dict:
        kw.setdefault("timeout", 30)
        r = self._s.request(method, url, **kw)
        r.raise_for_status()
        return r.json()

    # ── Workers AI ──────────────────────────────────────────────────────────────

    def ai_run(self, model: str, payload: dict, use_gateway: bool = True) -> dict:
        """Invoke a Workers AI model, routing through AI Gateway when available."""
        if use_gateway and self.gateway_ok:
            url = (
                f"https://gateway.ai.cloudflare.com/v1"
                f"/{CF_ACCOUNT_ID}/{CF_GATEWAY_ID}/workers-ai/{model}"
            )
        else:
            url = self._acct(f"/ai/run/{model}")

        headers: dict = {"Content-Type": "application/json"}
        if CF_SCOPED_KEY and CF_SCOPED_KEY.startswith("cfut_"):
            headers["Authorization"] = f"Bearer {CF_SCOPED_KEY}"
        elif CF_GLOBAL_KEY:
            headers["X-Auth-Key"]    = CF_GLOBAL_KEY
            headers["X-Auth-Email"]  = CF_EMAIL

        r = requests.post(url, json=payload, headers=headers, timeout=90)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            raise RuntimeError(f"Workers AI error: {data.get('errors')}")
        return data["result"]

    def embed(self, text: str) -> list[float] | None:
        """Embed text using BGE-large-en-v1.5 (1024 dims)."""
        try:
            result = self.ai_run(CF_EMBED_MODEL, {"text": [text[:2000]]}, use_gateway=False)
            return result["data"][0]
        except Exception as exc:
            log.debug("Embed failed: %s", exc)
            return None

    # ── AI Gateway ──────────────────────────────────────────────────────────────

    def provision_gateway(self) -> bool:
        try:
            self._req("POST", self._acct("/ai-gateway/gateways"), json={
                "name": CF_GATEWAY_ID,
                "collect_logs": True,
                "cache_ttl": 300,
                "cache_invalidate_on_update": False,
                "rate_limiting_interval": 60,
                "rate_limiting_limit": 300,
                "rate_limiting_technique": "sliding",
            })
            log.info("[CF] AI Gateway '%s' created", CF_GATEWAY_ID)
            return True
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 409:
                log.info("[CF] AI Gateway '%s' already exists", CF_GATEWAY_ID)
                return True
            log.warning("[CF] Gateway provision failed: %s", exc)
            return False

    # ── Vectorize ───────────────────────────────────────────────────────────────

    def provision_vectorize(self) -> bool:
        try:
            self._req("POST", self._acct("/vectorize/v2/indexes"), json={
                "name": CF_VECTORIZE_IDX,
                "config": {"dimensions": CF_EMBED_DIMS, "metric": "cosine"},
            })
            log.info("[CF] Vectorize index '%s' created", CF_VECTORIZE_IDX)
            return True
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 409:
                log.info("[CF] Vectorize index '%s' already exists", CF_VECTORIZE_IDX)
                return True
            log.warning("[CF] Vectorize provision failed: %s", exc)
            return False

    def vectorize_upsert(self, vec_id: str, values: list[float], metadata: dict) -> bool:
        try:
            ndjson = json.dumps({"id": vec_id, "values": values, "metadata": metadata})
            url = self._acct(f"/vectorize/v2/indexes/{CF_VECTORIZE_IDX}/upsert")
            self._s.post(url, data=ndjson,
                         headers={"Content-Type": "application/x-ndjson"},
                         timeout=20).raise_for_status()
            return True
        except Exception as exc:
            log.debug("Vectorize upsert failed: %s", exc)
            return False

    def vectorize_query(self, values: list[float], top_k: int = 3) -> list[dict]:
        try:
            url = self._acct(f"/vectorize/v2/indexes/{CF_VECTORIZE_IDX}/query")
            r = self._s.post(url, json={
                "vector": values, "topK": top_k, "returnMetadata": "all",
            }, timeout=20)
            r.raise_for_status()
            return r.json().get("result", {}).get("matches", [])
        except Exception as exc:
            log.debug("Vectorize query failed: %s", exc)
            return []

    # ── D1 Database ───────────────────────────────────────────────────────────────

    def provision_d1(self) -> str | None:
        try:
            r = self._req("GET", self._acct("/d1/database"), params={"name": CF_D1_DB_NAME})
            for db in r.get("result", []):
                if db.get("name") == CF_D1_DB_NAME:
                    log.info("[CF] D1 '%s' found: %s", CF_D1_DB_NAME, db["uuid"])
                    return db["uuid"]
        except Exception:
            pass
        try:
            r = self._req("POST", self._acct("/d1/database"), json={"name": CF_D1_DB_NAME})
            db_id = r["result"]["uuid"]
            log.info("[CF] D1 '%s' created: %s", CF_D1_DB_NAME, db_id)
            return db_id
        except Exception as exc:
            log.warning("[CF] D1 provision failed: %s", exc)
            return None

    def d1_exec(self, sql: str, params: list | None = None) -> list[dict]:
        if not self.d1_db_id:
            return []
        try:
            r = self._req("POST", self._acct(f"/d1/database/{self.d1_db_id}/query"),
                          json={"sql": sql, "params": params or []})
            results = r.get("result", [])
            return results[0].get("results", []) if results else []
        except Exception as exc:
            log.debug("D1 query failed (%s): %s", exc, sql[:80])
            return []

    def d1_init_schema(self) -> None:
        for stmt in [
            """CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, kind TEXT, link TEXT, quantity INTEGER,
                refillable INTEGER DEFAULT 0, status TEXT, start_count TEXT,
                remains TEXT, added_at TEXT, completed_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS refills (
                order_id TEXT PRIMARY KEY, refill_id TEXT, requested_at TEXT,
                status TEXT, ticket_sent INTEGER DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS posts (url TEXT PRIMARY KEY, added_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS agent_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, message TEXT)""",
            """CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, balance REAL,
                orders_total INTEGER, orders_completed INTEGER,
                refills_completed INTEGER, refills_rejected INTEGER)""",
        ]:
            self.d1_exec(stmt)

    # ── KV Store ──────────────────────────────────────────────────────────────────

    def provision_kv(self) -> str | None:
        try:
            r = self._req("GET", self._acct("/storage/kv/namespaces"))
            for ns in r.get("result", []):
                if ns.get("title") == CF_KV_TITLE:
                    log.info("[CF] KV '%s' found: %s", CF_KV_TITLE, ns["id"])
                    return ns["id"]
        except Exception:
            pass
        try:
            r = self._req("POST", self._acct("/storage/kv/namespaces"), json={"title": CF_KV_TITLE})
            ns_id = r["result"]["id"]
            log.info("[CF] KV '%s' created: %s", CF_KV_TITLE, ns_id)
            return ns_id
        except Exception as exc:
            log.warning("[CF] KV provision failed: %s", exc)
            return None

    def kv_get(self, key: str) -> str | None:
        if not self.kv_ns_id:
            return None
        try:
            r = self._s.get(self._acct(f"/storage/kv/namespaces/{self.kv_ns_id}/values/{key}"),
                            timeout=10)
            return r.text if r.status_code == 200 else None
        except Exception:
            return None

    def kv_set(self, key: str, value: str, ttl: int = 60) -> None:
        if not self.kv_ns_id:
            return
        try:
            self._s.put(
                self._acct(f"/storage/kv/namespaces/{self.kv_ns_id}/values/{key}"),
                data=value,
                params={"expiration_ttl": ttl},
                headers={"Content-Type": "text/plain"},
                timeout=10,
            )
        except Exception:
            pass

    def r2_backup(self, state: dict) -> None:
        """Push a JSON snapshot of state to R2 for immutable audit log."""
        if not CF_ACCOUNT_ID or not CF_GLOBAL_KEY or not CF_R2_BUCKET:
            return
        try:
            today  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            ts     = datetime.now(timezone.utc).strftime("%H%M%S")
            key    = f"logs/{today}/state-{ts}.json"
            self._s.put(
                f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/r2/buckets/{CF_R2_BUCKET}/objects/{key}",
                data=json.dumps(state, default=str).encode(),
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            log.debug("[R2] Backup saved: %s", key)
        except Exception as exc:
            log.debug("[R2] Backup skipped: %s", exc)

    # ── Provision all ───────────────────────────────────────────────────────────────

    def provision_all(self, state: dict) -> None:
        if not CF_ACCOUNT_ID or not CF_GLOBAL_KEY:
            log.warning("[CF] Cannot provision — CF_ACCOUNT_ID or CF_GLOBAL_API_KEY missing")
            return
        log.info("[CF] Provisioning Cloudflare resources...")
        self.gateway_ok   = self.provision_gateway()
        self.vectorize_ok = self.provision_vectorize()
        db_id = self.provision_d1()
        if db_id:
            self.d1_db_id = db_id
            self.d1_init_schema()
            state.setdefault("cf_resources", {})["d1_db_id"] = db_id
        kv_id = self.provision_kv()
        if kv_id:
            self.kv_ns_id = kv_id
            state.setdefault("cf_resources", {})["kv_ns_id"] = kv_id
        log.info("[CF] Gateway=%s Vectorize=%s D1=%s KV=%s",
                 self.gateway_ok, self.vectorize_ok, bool(self.d1_db_id), bool(self.kv_ns_id))

    def load_from_state(self, state: dict) -> None:
        """Restore CF resource IDs from persisted state (avoids re-provisioning)."""
        res = state.get("cf_resources", {})
        self.d1_db_id     = res.get("d1_db_id")
        self.kv_ns_id     = res.get("kv_ns_id")
        self.gateway_ok   = bool(CF_GATEWAY_ID and CF_ACCOUNT_ID and CF_GLOBAL_KEY)
        self.vectorize_ok = bool(CF_ACCOUNT_ID and CF_GLOBAL_KEY)

# ── State ─────────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"orders": {}, "refills": {}, "pending_posts": [], "posts": [],
            "agent_log": [], "cf_resources": {}}

def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))

def log_agent(state: dict, msg: str) -> None:
    state["agent_log"] = (state.get("agent_log", []) + [
        {"at": datetime.now(timezone.utc).isoformat(), "msg": msg}
    ])[-50:]

def engagement_due(state: dict) -> bool:
    """Return True if 8 hours have passed since the last engagement run."""
    last = state.get("last_engagement_run")
    if not last:
        return True
    try:
        dt = datetime.fromisoformat(last)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() >= ENGAGEMENT_INTERVAL_H * 3600
    except Exception:
        return True

def mark_engagement_run(state: dict) -> None:
    state["last_engagement_run"] = datetime.now(timezone.utc).isoformat()

# ── SMM API ───────────────────────────────────────────────────────────────────────

def _api(payload: dict) -> dict:
    payload = dict(payload)
    payload["key"] = API_KEY
    r = requests.post(API_URL, data=payload, timeout=20)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:200]}

def _api_panel(panel: dict, payload: dict) -> dict:
    p = dict(payload)
    p["key"] = panel["key"]
    r = requests.post(panel["url"], data=p, timeout=20)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:200]}

_live_rate_cache: dict = {}  # (panel_name, kind) → (rate, expires_epoch)

def _get_live_rate(panel: dict, kind: str) -> float:
    """Fetch current rate for this service from panel API. Cached 5 min in memory."""
    import time
    key = (panel["name"], kind)
    cached = _live_rate_cache.get(key)
    if cached and time.time() < cached[1]:
        return cached[0]

    svc = panel["services"].get(kind, {})
    svc_id = svc.get("id")
    fallback = svc.get("rate_per_k", 999)
    if not svc_id or not panel["key"]:
        return fallback

    try:
        services = _api_panel(panel, {"action": "services"})
        if isinstance(services, list):
            for s in services:
                if str(s.get("service", "")) == str(svc_id):
                    rate = float(s.get("rate", fallback))
                    _live_rate_cache[key] = (rate, time.time() + 300)
                    return rate
    except Exception as exc:
        log.debug("[Rates] %s live fetch failed: %s", panel["name"], exc)

    return fallback

def _place_order_multi(kind: str, link: str, quantity: int, extra: dict | None = None) -> dict:
    """Fetch live rates from all panels in parallel, order from cheapest, fall back on failure."""
    eligible = [p for p in PANELS if p["key"] and p["services"].get(kind, {}).get("id")]
    if not eligible:
        return {"success": False, "error": "No panels available"}

    # Parallel live-rate fetch
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(eligible)) as pool:
        live_rates = list(pool.map(lambda p: _get_live_rate(p, kind), eligible))

    ranked = sorted(zip(eligible, live_rates), key=lambda x: x[1])
    comparison = " | ".join(f"{p['name']} ${r:.2f}/k" for p, r in ranked)
    log.info("[SMM] Live rates for %s: %s → placing with %s", kind, comparison, ranked[0][0]["name"])

    for panel, rate in ranked:
        svc = panel["services"][kind]
        svc_id = svc["id"]
        min_qty = svc.get("min", 1)
        max_qty = svc.get("max", 10_000_000)
        if quantity < min_qty:
            log.warning("[%s] skipped — quantity %d below minimum %d for %s",
                        panel["name"], quantity, min_qty, kind)
            continue
        if quantity > max_qty:
            log.warning("[%s] skipped — quantity %d above maximum %d for %s",
                        panel["name"], quantity, max_qty, kind)
            continue
        payload = {"action": "add", "service": svc_id, "link": link, "quantity": quantity}
        if extra:
            payload.update(extra)
        try:
            res = _api_panel(panel, payload)
            if res.get("order"):
                log.info("[%s] ✓ placed %s×%d → order #%s @ live $%.2f/k",
                         panel["name"], kind, quantity, res["order"], rate)
                return {"success": True, "order": str(res["order"]), "panel": panel["name"],
                        "service_id": svc_id, "quantity": quantity}
            log.warning("[%s] rejected (trying next cheapest): %s", panel["name"], res)
        except Exception as e:
            log.warning("[%s] error (trying next cheapest): %s", panel["name"], e)
    return {"success": False, "error": f"No panel can fulfill {quantity}× {kind} (check minimums)"}

def _api_cached(payload: dict, cf: CloudflarePlatform, ttl: int = 60) -> dict:
    """SMM API with KV caching for balance and services lookups."""
    action = payload.get("action", "")
    if action in ("balance", "services") and cf.kv_ns_id:
        key = f"smm-{action}"
        cached = cf.kv_get(key)
        if cached:
            log.debug("[KV] cache hit: %s", key)
            return json.loads(cached)
        result = _api(payload)
        cf.kv_set(key, json.dumps(result), ttl=ttl)
        return result
    return _api(payload)

def _panel_session(panel_cfg: dict | None = None) -> requests.Session | None:
    """Login to a panel's web UI. Defaults to smmfollows if no panel_cfg given."""
    web  = (panel_cfg or {}).get("web",  PANEL)
    user = (panel_cfg or {}).get("user", USER)
    pw   = (panel_cfg or {}).get("pass", PASSWD)
    sess = requests.Session()
    sess.headers["User-Agent"] = "Mozilla/5.0"
    try:
        r = sess.get(f"{web}/", timeout=20)
        m = re.search(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"', r.text)
        if not m:
            return None
        sess.post(f"{web}/", data={
            "_csrf": m.group(1), "LoginForm[username]": user,
            "LoginForm[password]": pw, "LoginForm[remember]": "1",
        }, headers={"Content-Type": "application/x-www-form-urlencoded",
                    "Referer": f"{web}/", "Origin": web},
            allow_redirects=True, timeout=20)
        return sess if "_identity_user" in sess.cookies else None
    except Exception:
        return None

# ── Episodic Memory ───────────────────────────────────────────────────────────────

def retrieve_memories(context: str, cf: CloudflarePlatform) -> str:
    """Query Vectorize for top-3 most relevant past cycles."""
    if not cf.vectorize_ok:
        return ""
    try:
        vec = cf.embed(context[:500])
        if not vec:
            return ""
        matches = cf.vectorize_query(vec, top_k=3)
        lines = []
        for m in matches:
            score = m.get("score", 0)
            if score < 0.55:
                continue
            meta = m.get("metadata", {})
            ts   = str(meta.get("timestamp", ""))[:16]
            summ = str(meta.get("summary", ""))[:200]
            lines.append(f"[{ts}] ({score:.0%} match): {summ}")
        return "\n".join(lines)
    except Exception as exc:
        log.debug("Memory retrieval failed: %s", exc)
        return ""

def store_memory(summary: str, state: dict, cf: CloudflarePlatform) -> None:
    """Embed and upsert a cycle summary into Vectorize."""
    if not cf.vectorize_ok or not summary:
        return
    try:
        text = (f"{summary} | orders:{len(state.get('orders',{}))} "
                f"refills:{len(state.get('refills',{}))} posts:{len(state.get('posts',[]))}")
        vec = cf.embed(text)
        if not vec:
            return
        vec_id = f"cycle-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        cf.vectorize_upsert(vec_id, vec, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary":   summary[:500],
            "orders":    len(state.get("orders", {})),
            "refills":   len(state.get("refills", {})),
        })
        log.debug("[MEMORY] stored %s", vec_id)
    except Exception as exc:
        log.debug("Memory store failed: %s", exc)

# ── D1 Analytics sync ──────────────────────────────────────────────────────────────

def sync_to_d1(state: dict, cf: CloudflarePlatform) -> None:
    """Mirror current state into D1 for SQL analytics."""
    if not cf.d1_db_id:
        return
    try:
        for oid, o in state.get("orders", {}).items():
            cf.d1_exec(
                "INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)",
                [oid, o.get("kind"), o.get("link"), o.get("quantity"),
                 int(bool(o.get("refillable"))), o.get("status"),
                 o.get("start_count"), o.get("remains"),
                 o.get("added_at"), o.get("completed_at")],
            )
        for oid, r in state.get("refills", {}).items():
            cf.d1_exec(
                "INSERT OR REPLACE INTO refills VALUES (?,?,?,?,?)",
                [oid, str(r.get("refill_id","")), r.get("requested_at"),
                 r.get("status"), int(bool(r.get("ticket_sent")))],
            )
        orders = state.get("orders", {})
        refills = state.get("refills", {})
        cf.d1_exec(
            "INSERT INTO metrics (timestamp,orders_total,orders_completed,refills_completed,refills_rejected) VALUES (?,?,?,?,?)",
            [datetime.now(timezone.utc).isoformat(), len(orders),
             sum(1 for o in orders.values() if o.get("status") == "Completed"),
             sum(1 for r in refills.values() if r.get("status") == "Completed"),
             sum(1 for r in refills.values() if r.get("status") == "Rejected")],
        )
    except Exception as exc:
        log.debug("D1 sync failed: %s", exc)

def print_analytics(cf: CloudflarePlatform) -> None:
    """Print D1-backed analytics report."""
    if not cf.d1_db_id:
        print("D1 not provisioned — run --provision first")
        return
    rows = cf.d1_exec("""
        SELECT kind,
               COUNT(*) as total,
               SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) as completed,
               SUM(CASE WHEN status='Partial'   THEN 1 ELSE 0 END) as partial,
               SUM(CASE WHEN status='Canceled'  THEN 1 ELSE 0 END) as canceled
        FROM orders GROUP BY kind ORDER BY total DESC
    """)
    refill_rows = cf.d1_exec("""
        SELECT status, COUNT(*) as n FROM refills GROUP BY status
    """)
    metrics = cf.d1_exec("""
        SELECT timestamp, orders_total, refills_completed, refills_rejected
        FROM metrics ORDER BY id DESC LIMIT 5
    """)
    print("\n── Order Analytics (all time) ────────────────────────────────────")
    for r in rows:
        print(f"  {r.get('kind','?'):<12} total={r['total']} completed={r['completed']} "
              f"partial={r['partial']} canceled={r['canceled']}")
    print("\n── Refill Outcomes ────────────────────────────────────────────")
    for r in refill_rows:
        print(f"  {r['status']:<12} {r['n']}")
    print("\n── Recent Metrics ─────────────────────────────────────────────")
    for r in metrics:
        print(f"  {str(r['timestamp'])[:16]}  orders={r['orders_total']} "
              f"refills_ok={r['refills_completed']} refills_rej={r['refills_rejected']}")
    print()

# ── Tool implementations ────────────────────────────────────────────────────────────

def tool_get_balance(cf: CloudflarePlatform | None = None) -> str:
    try:
        fn = (lambda: _api_cached({"action": "balance"}, cf, ttl=300)) if cf and cf.kv_ns_id else (lambda: _api({"action": "balance"}))
        data = fn()
        return json.dumps({"balance": data.get("balance"), "currency": data.get("currency","USD")})
    except Exception as exc:
        return json.dumps({"error": str(exc)})

def tool_check_orders(state: dict) -> str:
    ids = list(state["orders"].keys())
    if not ids:
        return json.dumps({"message": "No orders tracked yet."})
    try:
        if len(ids) == 1:
            statuses = {ids[0]: _api({"action": "status", "order": ids[0]})}
        else:
            statuses = _api({"action": "status", "orders": ",".join(ids)})
        now_utc = datetime.now(timezone.utc)
        results = []
        for oid, info in statuses.items():
            order = state["orders"].get(oid)
            if not order:
                continue
            new_status = info.get("status", order.get("status","?"))
            order["status"]      = new_status
            order["remains"]     = info.get("remains")
            order["start_count"] = info.get("start_count")
            if new_status in ("Completed","Partial") and not order.get("completed_at"):
                order["completed_at"] = now_utc.isoformat()
            cooldown_h = None
            if order.get("completed_at") and order.get("refillable"):
                try:
                    dt = datetime.fromisoformat(order["completed_at"])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    cooldown_h = round(max(0, 24 - (now_utc - dt).total_seconds()/3600), 1)
                except Exception:
                    pass
            results.append({
                "order_id": oid, "kind": order.get("kind"), "link": order.get("link"),
                "status": new_status, "start_count": info.get("start_count"),
                "remains": info.get("remains"), "quantity": order.get("quantity"),
                "refillable": order.get("refillable"), "refill_cooldown_h": cooldown_h,
                "refill_done": oid in state.get("refills", {}),
            })
        return json.dumps({"orders": results})
    except Exception as exc:
        return json.dumps({"error": str(exc)})

def tool_trigger_refill(state: dict, order_id: str) -> str:
    order = state["orders"].get(order_id)
    if not order:
        return json.dumps({"error": f"Order {order_id} not tracked."})
    if not order.get("refillable"):
        return json.dumps({"error": f"Order {order_id} is not refillable."})
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
            r = sess.get(f"{PANEL}/orders/{order_id}/refill", timeout=10,
                         headers={"X-Requested-With":"XMLHttpRequest","Accept":"application/json"})
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
    except Exception as exc:
        return json.dumps({"error": str(exc)})

def tool_check_refill_status(state: dict, order_id: str) -> str:
    refill = state.get("refills", {}).get(order_id)
    if not refill:
        return json.dumps({"message": f"No refill on record for {order_id}."})
    rid = refill.get("refill_id")
    if not rid or rid == "panel":
        return json.dumps(refill)
    try:
        res = _api({"action": "refill_status", "refill": int(rid)})
        refill["status"] = res.get("status", refill["status"])
        return json.dumps({**refill, "api_response": res})
    except Exception as exc:
        return json.dumps({"error": str(exc), "cached": refill})

def tool_submit_ticket(state: dict, order_ids: list, subject_type: str, message: str) -> str:
    sess = _panel_session()
    if not sess:
        return json.dumps({"error": "Panel login failed."})
    try:
        r = sess.get(f"{PANEL}/tickets", timeout=20)
        m = re.search(r'<input[^>]+name="_csrf"[^>]+value="([^"]+)"', r.text)
        if not m:
            return json.dumps({"error": "CSRF token not found."})
        r2 = sess.post(f"{PANEL}/ticket-create", data={
            "_csrf": m.group(1),
            "TicketForm[subject]": f"Junior - Orders [ {subject_type} ]",
            "TicketForm[message]": message,
            "subject": "Orders", "request": subject_type,
            "cancel-reason": "", "ordernumbers": ",".join(order_ids),
        }, headers={"Content-Type":"application/x-www-form-urlencoded",
                    "Referer":f"{PANEL}/tickets","Origin":PANEL,
                    "Accept":"application/json, */*","X-Requested-With":"XMLHttpRequest"},
            timeout=20)
        ok = r2.status_code == 200 and r2.json().get("status") == "success"
        return json.dumps({"success": ok, "status_code": r2.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})

def _generate_comments(post_text: str, count: int = 20, cf: "CloudflarePlatform | None" = None) -> str:
    """Use Workers AI (or Anthropic fallback) to generate custom comments for a post."""
    prompt = (
        f"Generate {count} unique, authentic Twitter comments for this post.\n"
        "Rules:\n"
        "- Each comment must be directly relevant to the post topic\n"
        "- Vary the style: some enthusiastic, some thoughtful, some short, some with emojis\n"
        "- Sound like real users — no bots, no generic praise\n"
        "- No hashtags, no @mentions\n"
        "- Return ONLY a JSON array of strings, nothing else\n\n"
        f'Post: "{post_text[:400]}"'
    )
    # Try Workers AI
    if cf and CF_ACCOUNT_ID and (CF_SCOPED_KEY or CF_GLOBAL_KEY):
        try:
            result = cf.ai_run(CF_FAST_MODEL, {"messages": [{"role": "user", "content": prompt}], "max_tokens": 1200})
            raw = result.get("response", "")
            text = re.sub(r"<think>.*?</think>", "", raw if isinstance(raw, str) else json.dumps(raw), flags=re.DOTALL).strip()
            m = re.search(r"\[[\s\S]*\]", text)
            if m:
                arr = json.loads(m.group())
                if isinstance(arr, list) and arr:
                    log.info("[Comments] Generated %d custom comments via Workers AI", len(arr))
                    return "\n".join(str(c) for c in arr[:count])
        except Exception as exc:
            log.debug("[Comments] Workers AI failed: %s", exc)
    # Try Anthropic
    if ANTHROPIC_AVAILABLE and ANTHROPIC_KEY:
        try:
            ai = _anthropic_mod.Anthropic(api_key=ANTHROPIC_KEY)
            resp = ai.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=1200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text if resp.content else ""
            m = re.search(r"\[[\s\S]*\]", text)
            if m:
                arr = json.loads(m.group())
                if isinstance(arr, list) and arr:
                    log.info("[Comments] Generated %d custom comments via Claude", len(arr))
                    return "\n".join(str(c) for c in arr[:count])
        except Exception as exc:
            log.debug("[Comments] Anthropic failed: %s", exc)
    # Fallback
    fallback = [
        "This is amazing! 🔥", "Love this content!", "Great post!", "So true 💯",
        "This resonates with me", "Absolutely spot on", "Keep it up! 👏",
        "Brilliant take", "Couldn't agree more", "This needs more attention",
        "Well said!", "Pure gold 🙌", "This is the content I needed today",
        "Facts 💪", "Sharing this immediately", "You always deliver 🎯",
        "This is exactly right", "Underrated post", "More people need to see this",
        "Excellent point!",
    ]
    return "\n".join(fallback[:count])

def tool_place_order(state: dict, link: str, kind: str, quantity: int,
                     post_text: str = "", cf: "CloudflarePlatform | None" = None) -> str:
    if kind not in SERVICES:
        return json.dumps({"error": f"Unknown kind: {kind}. Valid: {list(SERVICES)}"})
    try:
        extra: dict = {}
        if kind == "comments":
            extra["comments"] = _generate_comments(post_text, quantity, cf)
        res = _place_order_multi(kind, link, quantity, extra)
        if not res.get("success"):
            return json.dumps({"error": res.get("error", "All panels failed")})
        oid = str(res["order"])
        state["orders"][oid] = {
            "id": oid, "kind": kind, "link": link, "quantity": res["quantity"],
            "refillable": False, "status": "Pending", "panel": res.get("panel", "smmfollows"),
            "start_count": None, "remains": None,
            "added_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
        }
        if link not in state["posts"]:
            state["posts"].append(link)
        return json.dumps({"success": True, "order_id": oid, "panel": res.get("panel"),
                           "service_id": res.get("service_id"), "quantity": res["quantity"], "link": link})
    except Exception as exc:
        return json.dumps({"error": str(exc)})

def tool_get_services() -> str:
    return json.dumps(SERVICES)

def tool_get_pending_posts(state: dict) -> str:
    return json.dumps({"pending_posts": state.get("pending_posts", [])})

def tool_clear_pending_post(state: dict, link: str) -> str:
    pending = state.get("pending_posts", [])
    if link in pending:
        pending.remove(link)
        state["pending_posts"] = pending
        return json.dumps({"success": True, "removed": link})
    return json.dumps({"message": "Not in pending list."})

def tool_recall_memory(context: str, cf: CloudflarePlatform) -> str:
    memories = retrieve_memories(context, cf)
    if not memories:
        return json.dumps({"message": "No relevant past experience found yet."})
    return json.dumps({"past_experience": memories})

def tool_get_analytics(state: dict, cf: CloudflarePlatform) -> str:
    orders  = state.get("orders", {})
    refills = state.get("refills", {})
    base = {
        "orders_total":      len(orders),
        "orders_completed":  sum(1 for o in orders.values() if o.get("status")=="Completed"),
        "orders_partial":    sum(1 for o in orders.values() if o.get("status")=="Partial"),
        "orders_canceled":   sum(1 for o in orders.values() if o.get("status")=="Canceled"),
        "refills_total":     len(refills),
        "refills_completed": sum(1 for r in refills.values() if r.get("status")=="Completed"),
        "refills_rejected":  sum(1 for r in refills.values() if r.get("status")=="Rejected"),
        "posts_tracked":     len(state.get("posts",[])),
    }
    if cf.d1_db_id:
        rows = cf.d1_exec(
            "SELECT timestamp,refills_completed,refills_rejected FROM metrics ORDER BY id DESC LIMIT 3"
        )
        base["recent_metrics"] = rows
        base["source"] = "d1"
    else:
        base["source"] = "state"
    return json.dumps(base)

# ── Tool definitions ────────────────────────────────────────────────────────────

TOOL_DEFS = [
    {"name": "get_balance",
     "description": "Check current account balance (cached in KV for speed).",
     "input_schema": {"type":"object","properties":{},"required":[]}},
    {"name": "check_orders",
     "description": ("Fetch live status of all tracked orders. Returns order ID, kind, link, "
                     "status, remains, refillable flag, refill_cooldown_h, refill_done flag."),
     "input_schema": {"type":"object","properties":{},"required":[]}},
    {"name": "trigger_refill",
     "description": ("Request refill for an order. Only when: status=Completed/Partial, "
                     "refillable=true, cooldown_h=0, no successful refill exists."),
     "input_schema": {"type":"object","properties":{"order_id":{"type":"string"}},"required":["order_id"]}},
    {"name": "check_refill_status",
     "description": "Check status of a previously triggered refill.",
     "input_schema": {"type":"object","properties":{"order_id":{"type":"string"}},"required":["order_id"]}},
    {"name": "submit_ticket",
     "description": ("Submit support ticket. LAST RESORT only — after refill rejected 2+ times, "
                     "or clear non-delivery. Never on first rejection."),
     "input_schema": {"type":"object","properties":{
         "order_ids":    {"type":"array","items":{"type":"string"}},
         "subject_type": {"type":"string","description":"Refill | Cancellation | Other"},
         "message":      {"type":"string"},
     },"required":["order_ids","subject_type","message"]}},
    {"name": "place_order",
     "description": ("Place SMM order. ONLY when link is in pending_posts. Never spontaneously."),
     "input_schema": {"type":"object","properties":{
         "link":     {"type":"string"},
         "kind":     {"type":"string","description":"likes|retweets|comments|views"},
         "quantity": {"type":"integer"},
     },"required":["link","kind","quantity"]}},
    {"name": "get_services",
     "description": "Get service catalogue with IDs, rates, limits.",
     "input_schema": {"type":"object","properties":{},"required":[]}},
    {"name": "get_pending_posts",
     "description": "Get list of post URLs queued by the user for ordering.",
     "input_schema": {"type":"object","properties":{},"required":[]}},
    {"name": "clear_pending_post",
     "description": "Remove a URL from the pending queue after orders are placed.",
     "input_schema": {"type":"object","properties":{"link":{"type":"string"}},"required":["link"]}},
    {"name": "recall_memory",
     "description": ("Search episodic memory (Vectorize) for relevant past situations. "
                     "Use before making complex decisions to learn from history."),
     "input_schema": {"type":"object","properties":{
         "context": {"type":"string","description":"Describe current situation to find similar past cycles."},
     },"required":["context"]}},
    {"name": "get_analytics",
     "description": "Get performance analytics: order completion rates, refill success rates, history.",
     "input_schema": {"type":"object","properties":{},"required":[]}},
]

# ── Prompts ─────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior social media marketing strategist powering a Cloudflare-based AI automation system. You have deep expertise in:

PLATFORM KNOWLEDGE
- Twitter/X algorithm: engagement velocity, recency signals, credibility thresholds
- Natural growth: realistic ratios (likes:retweets ~3:1), staggered delivery to avoid spam detection
- Drop rates: SMM likes/RTs from low-quality sources get removed within 24-72h — this is normal
- Refill mechanics: 24h cooldown after completion is standard; rejection means engagement hasn't dropped enough yet

SMM STRATEGY
- New post package: 100-200 likes + 25-50 retweets + 5k-10k views = natural baseline
- Never >1000 likes/day on one post — looks synthetic
- Comments are expensive and risky — use only when explicitly requested
- Wait 10-15 min after posting before ordering (let Twitter index the post)

DECISION FRAMEWORK
1. Start each cycle: recall_memory to check for relevant past patterns
2. Always check_orders first for the full picture
3. trigger_refill only when: completed + cooldown=0 + no active refill
4. submit_ticket only as last resort (refill rejected 2+ times after cooldown)
5. place_order only when link appears in pending_posts
6. Use get_analytics to spot trends (high rejection rate → service issue)
7. Use parallel_tools to batch data collection (saves time)

CONFIDENCE GUIDANCE
Set confidence < 0.75 and/or escalate=true when:
- Decision involves placing orders or submitting tickets
- Signals are contradictory or patterns are unusual
- Refill behaviour doesn't match past experience"""

CF_TOOL_PROTOCOL = """

TOOL USE PROTOCOL
-----------------
Single tool:
{"tool": "tool_name", "args": {}}

Multiple tools in parallel (executed simultaneously — use this to save time):
{"parallel_tools": [{"tool": "name", "args": {}}, {"tool": "name2", "args": {}}]}

Done — include confidence (0.0-1.0) and escalate flag:
{"done": true, "summary": "...", "confidence": 0.9, "escalate": false}

Rules:
- Output ONLY bare JSON, no surrounding text or <think> blocks
- Set confidence < 0.75 OR escalate=true for order placement, ticket submission, or uncertainty
"""

# ── Tool dispatcher ──────────────────────────────────────────────────────────────

def dispatch_tool(name: str, args: dict, state: dict, cf: CloudflarePlatform) -> str:
    mapping = {
        "get_balance":         lambda: tool_get_balance(cf),
        "check_orders":        lambda: tool_check_orders(state),
        "trigger_refill":      lambda: tool_trigger_refill(state, args["order_id"]),
        "check_refill_status": lambda: tool_check_refill_status(state, args["order_id"]),
        "submit_ticket":       lambda: tool_submit_ticket(state, args["order_ids"], args["subject_type"], args["message"]),
        "place_order":         lambda: tool_place_order(state, args["link"], args["kind"], args["quantity"]),
        "get_services":        lambda: tool_get_services(),
        "get_pending_posts":   lambda: tool_get_pending_posts(state),
        "clear_pending_post":  lambda: tool_clear_pending_post(state, args["link"]),
        "recall_memory":       lambda: tool_recall_memory(args.get("context",""), cf),
        "get_analytics":       lambda: tool_get_analytics(state, cf),
    }
    fn = mapping.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return fn()
    except Exception as exc:
        log.exception("Tool %s raised: %s", name, exc)
        return json.dumps({"error": str(exc)})

def _run_parallel_tools(tool_calls: list, state: dict, cf: CloudflarePlatform) -> dict:
    """Execute multiple tool calls concurrently, return {tool_name: result} dict."""
    results: dict = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(tool_calls), 6)) as pool:
        futures = {
            pool.submit(dispatch_tool, tc["tool"], tc.get("args", {}), state, cf): tc["tool"]
            for tc in tool_calls
        }
        for future in concurrent.futures.as_completed(futures):
            tool_name = futures[future]
            try:
                results[tool_name] = future.result()
            except Exception as exc:
                results[tool_name] = json.dumps({"error": str(exc)})
    return results

# ── JSON helpers ──────────────────────────────────────────────────────────────────

def _strip_think(raw: str) -> str:
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

def _parse_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return None

# ── Ensemble AI Cycle ──────────────────────────────────────────────────────────────

def _build_system_with_tools() -> str:
    tools_desc = json.dumps(
        [{"name": t["name"], "description": t["description"],
          "parameters": t["input_schema"]} for t in TOOL_DEFS],
        indent=2,
    )
    return SYSTEM_PROMPT + CF_TOOL_PROTOCOL + f"\nAVAILABLE TOOLS:\n{tools_desc}"

def _cf_ai_turn(model: str, messages: list, cf: CloudflarePlatform) -> str:
    result = cf.ai_run(model, {"messages": messages, "max_tokens": 2048})
    return _strip_think(result.get("response", ""))

def _process_cmd(cmd: dict | None, text: str, messages: list,
                 state: dict, cf: CloudflarePlatform) -> str | None:
    """
    Process a parsed AI command.
    Returns final string if cycle should end, None if it should continue.
    """
    if cmd is None:
        return text or "Cycle complete."
    if cmd.get("done"):
        return None
    if "parallel_tools" in cmd:
        tool_calls = cmd["parallel_tools"]
        log.info("  -> parallel[%s]", ", ".join(tc["tool"] for tc in tool_calls))
        results = _run_parallel_tools(tool_calls, state, cf)
        for tn, res in results.items():
            log.info("     <- %s: %s", tn, res[:120])
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": f"Parallel tool results: {json.dumps(results)}"})
        return None
    if "tool" in cmd:
        tool_name = cmd["tool"]
        tool_args = cmd.get("args", {})
        log.info("  -> %s(%s)", tool_name, json.dumps(tool_args)[:100])
        result = dispatch_tool(tool_name, tool_args, state, cf)
        log.info("     <- %s", result[:150])
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": f"Tool result for {tool_name}: {result}"})
        return None
    return text or "Cycle complete."

def _run_cloudflare_ensemble(state: dict, task: str, cf: CloudflarePlatform,
                              max_iters: int = 25) -> str:
    """
    Two-stage ensemble:
    Stage 1 — Llama 3.3 70B fast: collects data, makes preliminary decision.
    Stage 2 — DeepSeek R1 (if confidence < threshold OR critical action):
               reviews full context, makes final decision.
    """
    memories = retrieve_memories(task[:300], cf)
    augmented_task = task
    if memories:
        augmented_task = f"{task}\n\n=== RELEVANT PAST EXPERIENCE ===\n{memories}"

    system_msg = _build_system_with_tools()
    messages: list = [
        {"role": "system", "content": system_msg},
        {"role": "user",   "content": augmented_task},
    ]

    # ── Stage 1: Fast model ────────────────────────────────────────────────────
    log.info("[ENSEMBLE] Stage 1 — Llama 3.3 70B (scout)")
    fast_summary = ""
    confidence   = 1.0
    escalate     = False
    last_text    = ""

    for _ in range(max_iters):
        text = _cf_ai_turn(CF_FAST_MODEL, messages, cf)
        last_text = text
        if text:
            log.info("[FAST] %s", text[:280])

        cmd = _parse_json(text)
        if cmd and cmd.get("done"):
            fast_summary = cmd.get("summary", text)
            confidence   = float(cmd.get("confidence", 1.0))
            escalate     = bool(cmd.get("escalate", False))
            needs_deep   = confidence < CONFIDENCE_THRESHOLD or escalate
            log.info("[ENSEMBLE] Fast done (conf=%.0f%% escalate=%s needs_deep=%s)",
                     confidence*100, escalate, needs_deep)
            if not needs_deep:
                store_memory(fast_summary, state, cf)
                return fast_summary
            break

        result = _process_cmd(cmd, text, messages, state, cf)
        if result is not None:
            store_memory(result, state, cf)
            return result

    # ── Stage 2: Deep model ───────────────────────────────────────────────────
    log.info("[ENSEMBLE] Stage 2 — DeepSeek R1 (strategist, conf was %.0f%%)", confidence*100)
    messages.append({
        "role": "user",
        "content": (
            f"Fast-model preliminary assessment (confidence {confidence:.0%}):\n{fast_summary}\n\n"
            "You are the deep reasoning model. Review all tool results above and make the "
            "final authoritative decision. Call additional tools if needed."
        ),
    })

    for _ in range(max(max_iters // 2, 10)):
        text = _cf_ai_turn(CF_REASON_MODEL, messages, cf)
        last_text = text
        if text:
            log.info("[DEEP] %s", text[:280])

        cmd = _parse_json(text)
        if cmd and cmd.get("done"):
            final = cmd.get("summary", text)
            store_memory(final, state, cf)
            return final

        result = _process_cmd(cmd, text, messages, state, cf)
        if result is not None:
            store_memory(result, state, cf)
            return result

    final = fast_summary or last_text or "Cycle complete."
    store_memory(final, state, cf)
    return final

# ── AI Priority Chain ──────────────────────────────────────────────────────────────

def run_agent_cycle(state: dict, task: str, cf: CloudflarePlatform,
                    max_iters: int = 25) -> str:
    """
    Priority: CF Ensemble (Llama+DeepSeek) → DeepSeek direct → Claude → rule-based.
    """
    if CF_ACCOUNT_ID and (CF_SCOPED_KEY or CF_GLOBAL_KEY):
        try:
            log.info("[AI] Cloudflare ensemble (Llama 3.3 70B + DeepSeek R1)")
            return _run_cloudflare_ensemble(state, task, cf, max_iters)
        except Exception as exc:
            log.warning("[AI] CF ensemble failed (%s) — trying DeepSeek direct", exc)

    if DEEPSEEK_DIRECT and not DEEPSEEK_DIRECT.startswith("cfut_"):
        try:
            log.info("[AI] DeepSeek direct API")
            return _run_deepseek_direct(state, task, max_iters)
        except Exception as exc:
            log.warning("[AI] DeepSeek failed (%s) — trying Claude", exc)

    if ANTHROPIC_KEY:
        try:
            log.info("[AI] Claude fallback")
            return _run_claude_cycle(state, task, cf, max_iters)
        except Exception as exc:
            log.warning("[AI] Claude failed (%s) — rule-based", exc)

    log.info("[AI] Rule-based fallback")
    return _rule_based_cycle(state)

# ── DeepSeek Direct ───────────────────────────────────────────────────────────────

def _run_deepseek_direct(state: dict, task: str, max_iters: int = 25) -> str:
    ds_tools = [{"type":"function","function":{
        "name": t["name"], "description": t["description"], "parameters": t["input_schema"],
    }} for t in TOOL_DEFS]
    messages = [{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":task}]
    cf_dummy = CloudflarePlatform()
    for _ in range(max_iters):
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            json={"model":"deepseek-chat","messages":messages,"tools":ds_tools,
                  "tool_choice":"auto","max_tokens":4096},
            headers={"Authorization":f"Bearer {DEEPSEEK_DIRECT}","Content-Type":"application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        choice  = resp.json()["choices"][0]
        message = choice["message"]
        if choice["finish_reason"] == "stop" or not message.get("tool_calls"):
            return message.get("content") or "Cycle complete."
        messages.append(message)
        for tc in message.get("tool_calls", []):
            fn = tc["function"]
            try:
                inp = json.loads(fn["arguments"])
            except Exception:
                inp = {}
            result = dispatch_tool(fn["name"], inp, state, cf_dummy)
            messages.append({"role":"tool","tool_call_id":tc["id"],"content":result})
    return "Agent reached max iterations."

# ── Claude Fallback ───────────────────────────────────────────────────────────────

def _run_claude_cycle(state: dict, task: str, cf: CloudflarePlatform, max_iters: int = 25) -> str:
    if not ANTHROPIC_AVAILABLE:
        return "Claude unavailable (anthropic not installed)."
    ai = _anthropic_mod.Anthropic(api_key=ANTHROPIC_KEY)
    messages = [{"role":"user","content":task}]
    for _ in range(max_iters):
        response = ai.messages.create(
            model="claude-sonnet-4-6", max_tokens=4096,
            system=SYSTEM_PROMPT, tools=TOOL_DEFS, messages=messages,
        )
        texts = [b.text for b in response.content if hasattr(b,"text") and b.text.strip()]
        for t in texts:
            log.info("[Claude] %s", t[:400])
        if response.stop_reason == "end_turn":
            return " ".join(texts) or "Cycle complete."
        if response.stop_reason != "tool_use":
            break
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = dispatch_tool(block.name, block.input, state, cf)
            tool_results.append({"type":"tool_result","tool_use_id":block.id,"content":result})
        messages.append({"role":"assistant","content":response.content})
        messages.append({"role":"user","content":tool_results})
    return "Cycle complete."

# ── Rule-based Fallback ─────────────────────────────────────────────────────────────

def _rule_based_cycle(state: dict) -> str:
    now = datetime.now(timezone.utc)
    cf  = CloudflarePlatform()
    try:
        bal = json.loads(tool_get_balance(None))
        log.info("[RULE] Balance: $%s", bal.get("balance"))
    except Exception:
        pass
    orders_json = json.loads(tool_check_orders(state))
    orders = orders_json.get("orders", [])
    triggered, waiting, done_list, issues, actions = [], [], [], [], []
    for o in orders:
        oid, status = o["order_id"], o["status"]
        if status not in ("Completed","Partial") or not o["refillable"]:
            continue
        refill_info   = state.get("refills",{}).get(oid,{})
        refill_status = refill_info.get("status")
        cooldown_h    = o.get("refill_cooldown_h")
        if refill_status == "Completed":
            done_list.append(oid); continue
        if refill_status == "Pending":
            tool_check_refill_status(state, oid)
            new_s = state.get("refills",{}).get(oid,{}).get("status","Pending")
            if new_s == "Completed":
                done_list.append(oid)
            elif new_s == "Rejected" and cooldown_h == 0:
                res = json.loads(tool_trigger_refill(state, oid))
                if res.get("success"):
                    triggered.append(oid); actions.append(f"Re-triggered refill #{oid}")
                else:
                    issues.append(f"#{oid}: rejected twice")
            else:
                waiting.append(oid)
            continue
        if cooldown_h and cooldown_h > 0:
            waiting.append(oid)
            log.info("[RULE] #%s cooldown %.1fh", oid, cooldown_h)
            continue
        res = json.loads(tool_trigger_refill(state, oid))
        if res.get("success"):
            triggered.append(oid); actions.append(f"Triggered refill #{oid}")
        else:
            issues.append(f"#{oid}: refill failed — {res.get('error','?')}")
    # Pending posts queued manually — always send engagement package
    for link in list(state.get("pending_posts", [])):
        for item in NEW_POST_PACKAGE:
            res = json.loads(tool_place_order(state, link, item["kind"], item["quantity"]))
            if res.get("success"):
                actions.append(f"Placed {item['kind']}×{item['quantity']} for {link[-40:]}")
        tool_clear_pending_post(state, link)

    # Every 8 hours — send engagement package to any newly discovered posts
    if engagement_due(state):
        new_posts = state.get("pending_engagement_posts", [])
        for link in new_posts:
            for item in NEW_POST_PACKAGE:
                res = json.loads(tool_place_order(state, link, item["kind"], item["quantity"]))
                if res.get("success"):
                    actions.append(f"[8h] {item['kind']}×{item['quantity']} → {link[-40:]}")
        if new_posts:
            mark_engagement_run(state)
            state["pending_engagement_posts"] = []
    parts = [f"[Rule-based — {now.strftime('%H:%M UTC')}]"]
    if triggered:  parts.append(f"Refills triggered: {triggered}")
    if waiting:    parts.append(f"In cooldown: {waiting}")
    if done_list:  parts.append(f"Refills done: {done_list}")
    if actions:    parts.append("Actions: " + "; ".join(actions))
    if issues:     parts.append("Issues: " + "; ".join(issues))
    if not triggered and not actions and not issues:
        parts.append("Nothing to do — all healthy.")
    return " | ".join(parts)

# ── Dashboard ───────────────────────────────────────────────────────────────────────

def print_dashboard(state: dict, cf: CloudflarePlatform) -> None:
    try:
        bal = _api({"action": "balance"})
        print(f"\nBalance: ${bal.get('balance')} {bal.get('currency','USD')}")
    except Exception as exc:
        print(f"\nBalance: error ({exc})")
    cf_status = (
        f"Gateway={'on' if cf.gateway_ok else 'off'} "
        f"Vectorize={'on' if cf.vectorize_ok else 'off'} "
        f"D1={'on' if cf.d1_db_id else 'off'} "
        f"KV={'on' if cf.kv_ns_id else 'off'}"
    )
    print(f"Cloudflare: {cf_status}")
    sep = "─" * 82
    print(f"\n{sep}")
    print(f"{'ID':<12} {'Kind':<11} {'Status':<20} {'Rem':<6} {'Refill':<16} Link")
    print(sep)
    now = datetime.now(timezone.utc)
    for oid, o in state["orders"].items():
        ri = state.get("refills",{}).get(oid)
        refill_str = "—"
        if ri:
            rs  = ri.get("status","?")
            rid = ri.get("refill_id","")
            refill_str = f"{rs}({rid})" if rid != "panel" else f"{rs}(panel)"
        cooldown_str = ""
        if o.get("refillable") and o.get("completed_at"):
            try:
                dt = datetime.fromisoformat(o["completed_at"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                h = max(0, 24-(now-dt).total_seconds()/3600)
                if h > 0:
                    cooldown_str = f" ⏳{h:.0f}h"
            except Exception:
                pass
        print(f"  {oid:<10} {o.get('kind','?'):<11} "
              f"{(o.get('status','?')+cooldown_str):<20} "
              f"{str(o.get('remains','?')):<6} {refill_str:<16} "
              f"{o.get('link','?')[-42:]}")
    print(sep)
    if state.get("pending_posts"):
        print(f"Pending: {state['pending_posts']}")
    print(f"Posts tracked: {len(state['posts'])}")
    if state.get("agent_log"):
        print("\nRecent AI decisions:")
        for e in state["agent_log"][-5:]:
            print(f"  [{e['at'][11:19]}] {e['msg'][:115]}")
    print()

# ── Task prompt ────────────────────────────────────────────────────────────────

MONITOR_TASK = """\
Run your standard monitoring cycle using the Cloudflare Intelligence Platform:

1. Use parallel_tools to fetch balance + check_orders + get_analytics simultaneously.
2. Call recall_memory with a description of any unusual patterns you find.
3. For completed/partial refillable orders: trigger refill if cooldown=0 and no active refill.
4. For pending refills: check their status.
5. For pending_posts: place the FULL engagement package for each post:
     100 likes | 50 retweets | 20 comments | 30,000 views
   (This runs every 8 hours automatically — do not skip any item in the package.)
6. Submit a ticket ONLY as last resort (refill rejected 2+ times, clear non-delivery).
7. Set confidence < 0.75 in your done message if placing orders or submitting tickets.
8. End with a strategic summary: what you found, what you did, what to watch.
"""

# ── CLI / Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SMMFollows AI — Cloudflare Intelligence Platform"
    )
    parser.add_argument("--once",      action="store_true", help="Single cycle and exit")
    parser.add_argument("--status",    action="store_true", help="Print dashboard and exit")
    parser.add_argument("--post",      metavar="URL",       help="Queue a post URL for ordering")
    parser.add_argument("--refill",    action="store_true", help="Refill-focused pass")
    parser.add_argument("--provision", action="store_true", help="(Re)provision Cloudflare resources")
    parser.add_argument("--analytics", action="store_true", help="Show D1 analytics report")
    parser.add_argument("--interval",  type=int, default=POLL_SECS,
                        help=f"Seconds between cycles (default {POLL_SECS})")
    args = parser.parse_args()

    state = load_state()
    cf = CloudflarePlatform()

    if args.provision:
        cf.provision_all(state)
        save_state(state)
        log.info("Provisioning complete.")
        return

    cf.load_from_state(state)

    if args.post:
        url = args.post.strip()
        if url not in state.get("pending_posts", []):
            state.setdefault("pending_posts", []).append(url)
            save_state(state)
            log.info("Post queued: %s — AI will order on next cycle.", url)
        else:
            log.info("Already queued: %s", url)

    if args.status:
        print_dashboard(state, cf)
        return

    if args.analytics:
        print_analytics(cf)
        return

    if args.refill:
        task = (
            "Refill-focused pass: check all orders, then for every completed "
            "refillable order where cooldown=0 and no successful refill exists, "
            "trigger refill. Check status of pending refills. Summarise outcomes."
        )
        summary = run_agent_cycle(state, task, cf)
        log_agent(state, f"[REFILL] {summary[:200]}")
        save_state(state)
        sync_to_d1(state, cf); cf.r2_backup(state)
        return

    if args.once or args.post:
        summary = run_agent_cycle(state, MONITOR_TASK, cf)
        log_agent(state, summary[:200])
        save_state(state)
        sync_to_d1(state, cf); cf.r2_backup(state)
        return

    log.info("=== SMMFollows AI — Cloudflare Intelligence Platform (interval=%ds) ===", args.interval)
    log.info("CF: Gateway=%s Vectorize=%s D1=%s KV=%s",
             cf.gateway_ok, cf.vectorize_ok, bool(cf.d1_db_id), bool(cf.kv_ns_id))
    log.info("Models: Llama 3.3 70B (fast scout) + DeepSeek R1 (deep strategist) | Ctrl+C to stop.")

    while True:
        try:
            summary = run_agent_cycle(state, MONITOR_TASK, cf)
            log_agent(state, summary[:200])
            save_state(state)
            sync_to_d1(state, cf); cf.r2_backup(state)
        except KeyboardInterrupt:
            log.info("Stopped.")
            break
        except Exception as exc:
            log.exception("Unexpected error: %s", exc)
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
