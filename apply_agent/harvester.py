"""Telegram job-link harvester.

Scrapes the public web previews (t.me/s/<channel>) of Telegram job channels —
no login or bot membership needed — extracts every outbound job link, dedups
into SQLite, and flags the ones matching the candidate's target roles.
"""
import os
import re
import sqlite3
import time
import aiohttp
from bs4 import BeautifulSoup

from .profile import PROFILE

DB_PATH = "applications.db"
DEFAULT_CHANNELS = "cryptojobslist,cryptojobs,web3hiring,devjobs"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS job_leads (
    url TEXT PRIMARY KEY, channel TEXT, title TEXT,
    matched INTEGER DEFAULT 0, ts REAL, status TEXT DEFAULT 'new'
)
"""
_SKIP_HOSTS = re.compile(r"(^|\.)t\.me$|(^|\.)telegram\.(org|me)$|twitter\.com|x\.com|"
                         r"instagram\.com|youtube\.com|youtu\.be|linktr\.ee", re.I)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}


def _match_score(text: str) -> bool:
    """Does this posting look like one of the candidate's target roles?"""
    t = text.lower()
    keywords = ("community", "social media", "content", "ambassador", "moderator",
                "marketing", "growth", "kol", "prompt", "ai operations", "annotat",
                "copywrit", "creator", "smm")
    return any(k in t for k in keywords)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    return conn


async def _scrape_channel(session: aiohttp.ClientSession, channel: str) -> list[dict]:
    leads = []
    try:
        async with session.get(f"https://t.me/s/{channel}",
                               timeout=aiohttp.ClientTimeout(total=25)) as r:
            html = await r.text()
    except Exception:
        return leads
    soup = BeautifulSoup(html, "html.parser")
    for msg in soup.select(".tgme_widget_message_wrap"):
        text_el = msg.select_one(".tgme_widget_message_text")
        text = text_el.get_text(" ", strip=True) if text_el else ""
        title = text[:120]
        for a in msg.select("a[href]"):
            url = a["href"].split("?utm")[0].strip()
            if not url.startswith("http"):
                continue
            host = re.sub(r"^https?://([^/]+).*", r"\1", url)
            if _SKIP_HOSTS.search(host):
                continue
            leads.append({"url": url, "channel": channel, "title": title,
                          "matched": _match_score(text)})
    return leads


async def harvest(channels: str = "") -> dict:
    """Scrape all channels; store new leads. Returns {'new': [...], 'total': n}."""
    names = [c.strip().lstrip("@") for c in
             (channels or os.getenv("JOB_TG_CHANNELS", DEFAULT_CHANNELS)).split(",") if c.strip()]
    async with aiohttp.ClientSession(headers=_HEADERS) as session:
        all_leads: list[dict] = []
        for name in names:
            all_leads.extend(await _scrape_channel(session, name))

    new = []
    with _db() as conn:
        for lead in all_leads:
            cur = conn.execute(
                "INSERT OR IGNORE INTO job_leads (url,channel,title,matched,ts) "
                "VALUES (?,?,?,?,?)",
                (lead["url"], lead["channel"], lead["title"], int(lead["matched"]), time.time()))
            if cur.rowcount:
                new.append(lead)
    # matched roles first, then newest
    new.sort(key=lambda l: (not l["matched"],))
    return {"new": new, "total": len(all_leads), "channels": names}


def pending(limit: int = 25, matched_only: bool = False) -> list[dict]:
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        q = ("SELECT url,channel,title,matched FROM job_leads WHERE status='new' "
             + ("AND matched=1 " if matched_only else "")
             + "ORDER BY matched DESC, ts DESC LIMIT ?")
        return [dict(r) for r in conn.execute(q, (limit,)).fetchall()]


def mark(url: str, status: str) -> None:
    with _db() as conn:
        conn.execute("UPDATE job_leads SET status=? WHERE url=?", (status, url))


def render(leads: list[dict], header: str = "") -> str:
    lines = [header] if header else []
    for i, l in enumerate(leads, 1):
        star = "⭐ " if l.get("matched") else ""
        lines.append(f"{i}. {star}{(l.get('title') or 'untitled')[:80]}")
        lines.append(f"   {l['url']}   (via @{l['channel']})")
    if not leads:
        lines.append("No job links found.")
    return "\n".join(lines)
