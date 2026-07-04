"""Pull job leads that @AshiqAibot mirrored into Cloudflare KV.

The bot writes finds to KV under `job:<hash>` (see telegram_agents/tools/
cf_jobs.py). This reads them so the autopilot can debate + apply to the ones
with a real web application URL. Leads are marked processed in KV so they are
not re-applied.
"""
import json
import os

import aiohttp

from aos.config import AOSConfig as C

KV_ID = os.getenv("CF_KV_ID", "d5310b7ebcec4352b40f50e1b61cbce1")
_BASE = "https://api.cloudflare.com/client/v4"


def _headers(ct: str = "application/json") -> dict:
    h = {"Content-Type": ct}
    if C.CF_AI_TOKEN.startswith("cfut_"):
        h["Authorization"] = f"Bearer {C.CF_AI_TOKEN}"
    elif C.CF_GLOBAL_KEY:
        h["X-Auth-Key"], h["X-Auth-Email"] = C.CF_GLOBAL_KEY, C.CF_EMAIL
    return h


def _kv(path: str) -> str:
    return f"{_BASE}/accounts/{C.CF_ACCOUNT_ID}/storage/kv/namespaces/{KV_ID}{path}"


async def pull_bot_jobs(limit: int = 20, only_new: bool = True) -> list[dict]:
    """Return job leads the bot stored in KV (with an apply_url), newest first."""
    if not C.CF_ACCOUNT_ID or not (C.CF_AI_TOKEN or C.CF_GLOBAL_KEY):
        return []
    leads: list[dict] = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(_kv("/keys?prefix=job:"), headers=_headers(),
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                keys = [k["name"] for k in (await r.json()).get("result", [])]
            for key in keys[:limit * 2]:
                async with s.get(_kv(f"/values/{key}"), headers=_headers(),
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status != 200:
                        continue
                    try:
                        job = json.loads(await r.text())
                    except Exception:
                        continue
                job["_key"] = key
                if only_new and job.get("status") != "new":
                    continue
                if not job.get("apply_url"):          # no web form → bot's DM flow handles it
                    continue
                leads.append(job)
                if len(leads) >= limit:
                    break
    except Exception:
        return leads
    leads.sort(key=lambda j: j.get("found_at", 0), reverse=True)
    return leads


async def mark_processed(key: str, status: str = "processed") -> None:
    if not C.CF_ACCOUNT_ID or not (C.CF_AI_TOKEN or C.CF_GLOBAL_KEY):
        return
    try:
        async with aiohttp.ClientSession() as s:
            # read-modify-write the status flag
            async with s.get(_kv(f"/values/{key}"), headers=_headers(),
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                job = json.loads(await r.text()) if r.status == 200 else {}
            job["status"] = status
            await s.put(_kv(f"/values/{key}"), headers=_headers("text/plain"),
                        data=json.dumps(job), timeout=aiohttp.ClientTimeout(total=15))
    except Exception:
        pass
