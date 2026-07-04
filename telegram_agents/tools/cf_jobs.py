"""Bridge: mirror the bot's found jobs to Cloudflare KV.

@AshiqAibot reads your private Telegram groups (via your session) and saves
finds to a local SQLite DB that nothing else can see. This pushes each find
to Cloudflare KV under `job:<hash>` so the Apply Pilot autopilot (which runs
in GitHub Actions and can read CF KV with the global key) can pull and apply.

Best-effort and non-blocking: if CF creds are missing it silently no-ops, so
it never breaks the bot.
"""
import hashlib
import json
import os
import time

import requests

CF_ACCOUNT = os.getenv("CF_ACCOUNT_ID", "")
CF_KV_ID = os.getenv("CF_KV_ID", "d5310b7ebcec4352b40f50e1b61cbce1")
CF_EMAIL = os.getenv("CF_EMAIL", "")
CF_KEY = os.getenv("CF_GLOBAL_API_KEY", "")
CF_TOKEN = os.getenv("CF_AI_TOKEN", "")


def _headers() -> dict:
    if CF_TOKEN.startswith("cfut_"):
        return {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "text/plain"}
    if CF_KEY:
        return {"X-Auth-Key": CF_KEY, "X-Auth-Email": CF_EMAIL, "Content-Type": "text/plain"}
    return {}


def _find_url(job: dict) -> str:
    for k in ("apply_url", "url", "link", "source"):
        v = str(job.get(k, ""))
        if v.startswith("http"):
            return v
    return ""


def push_job(job: dict) -> bool:
    """Mirror one found job to CF KV. Returns True on success."""
    if not CF_ACCOUNT or not _headers():
        return False
    key_src = (str(job.get("title", "")) + str(job.get("company", "")) + _find_url(job))
    key = "job:" + hashlib.sha1(key_src.encode()).hexdigest()[:16]
    payload = {
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "description": str(job.get("description", ""))[:1500],
        "apply_url": _find_url(job),
        "source": job.get("source", ""),
        "found_at": time.time(),
        "status": "new",
    }
    try:
        r = requests.put(
            f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}"
            f"/storage/kv/namespaces/{CF_KV_ID}/values/{key}",
            headers=_headers(), data=json.dumps(payload), timeout=15,
        )
        return r.status_code < 300
    except Exception:
        return False


def push_jobs(jobs: list[dict]) -> int:
    return sum(1 for j in jobs if push_job(j))
