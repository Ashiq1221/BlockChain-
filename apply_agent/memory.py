"""Application memory — the self-learning layer.

Every evaluated job is logged to SQLite; the job summary is embedded via
Cloudflare Workers AI and upserted into the Vectorize index so future
evaluations retrieve lessons from the most similar past applications.
"""
import json
import sqlite3
import time
import aiohttp
from aos import providers as p
from aos.config import AOSConfig as C

DB_PATH = "applications.db"
VECTORIZE_INDEX = "smm-episodic-memory"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, url TEXT UNIQUE, company TEXT, title TEXT,
    decision TEXT, fit_score REAL, status TEXT DEFAULT 'evaluated',
    cover_letter TEXT, notes TEXT
)
"""


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def record(url: str, company: str, title: str, decision: str,
           fit_score: float, cover_letter: str = "", notes: str = "") -> int:
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO applications (ts,url,company,title,decision,fit_score,cover_letter,notes) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(url) DO UPDATE SET decision=excluded.decision, "
            "fit_score=excluded.fit_score, cover_letter=excluded.cover_letter, notes=excluded.notes",
            (time.time(), url, company, title, decision, fit_score, cover_letter, notes),
        )
        return cur.lastrowid


def set_status(url: str, status: str, notes: str = "") -> None:
    """Update outcome: submitted / interview / rejected / offer — feeds learning."""
    with _db() as conn:
        conn.execute("UPDATE applications SET status=?, notes=notes||' '||? WHERE url=?",
                     (status, notes, url))


def report(limit: int = 30) -> list[dict]:
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT ts,url,company,title,decision,fit_score,status FROM applications "
            "ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def lessons_text(limit: int = 8) -> str:
    """Recent decisions + outcomes, rendered for the debate prompt."""
    rows = report(limit)
    if not rows:
        return ""
    lines = ["PAST APPLICATION HISTORY (learn from these):"]
    for r in rows:
        lines.append(f"• {r['title']} @ {r['company']} — decided {r['decision']} "
                     f"(fit {r['fit_score']}/10), outcome: {r['status']}")
    return "\n".join(lines)


# ── Vectorize episodic memory (best-effort, never blocks the pipeline) ────────

def _cf_headers() -> dict:
    h = {}
    if C.CF_AI_TOKEN.startswith("cfut_"):
        h["Authorization"] = f"Bearer {C.CF_AI_TOKEN}"
    elif C.CF_GLOBAL_KEY:
        h["X-Auth-Key"], h["X-Auth-Email"] = C.CF_GLOBAL_KEY, C.CF_EMAIL
    return h


async def remember(url: str, summary: str, metadata: dict) -> bool:
    vec = await p.cf_embed(summary)
    if not vec or not C.CF_ACCOUNT_ID:
        return False
    try:
        ndjson = json.dumps({"id": url[:64], "values": vec,
                             "metadata": {k: str(v)[:200] for k, v in metadata.items()}})
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.cloudflare.com/client/v4/accounts/{C.CF_ACCOUNT_ID}"
                f"/vectorize/v2/indexes/{VECTORIZE_INDEX}/upsert",
                headers={**_cf_headers(), "Content-Type": "application/x-ndjson"},
                data=ndjson, timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                return r.status < 300
    except Exception:
        return False


async def similar(summary: str, top_k: int = 3) -> list[dict]:
    vec = await p.cf_embed(summary)
    if not vec or not C.CF_ACCOUNT_ID:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://api.cloudflare.com/client/v4/accounts/{C.CF_ACCOUNT_ID}"
                f"/vectorize/v2/indexes/{VECTORIZE_INDEX}/query",
                headers={**_cf_headers(), "Content-Type": "application/json"},
                json={"vector": vec, "topK": top_k, "returnMetadata": "all"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json()
                return (data.get("result") or {}).get("matches", [])
    except Exception:
        return []
