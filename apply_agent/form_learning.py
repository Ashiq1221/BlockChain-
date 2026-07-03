"""Self-learning form memory — per-domain application recipes.

Each submission attempt records what worked for a domain: the sequence of
button labels that advanced the form, the label that submitted it, the total
steps, and whether a success/confirmation screen was detected. The next
attempt on the same domain gets those hints fed to the AI navigator, so the
agent hardens itself over time.

Backed by Cloudflare KV (survives ephemeral CI with no git writes); falls
back to a local JSON file when CF creds are absent.
"""
import json
import os
import time
from urllib.parse import urlparse

import aiohttp

from aos.config import AOSConfig as C

KV_NS = os.getenv("CF_KV_ID", "d5310b7ebcec4352b40f50e1b61cbce1")
LOCAL = "form_recipes.json"
_BASE = "https://api.cloudflare.com/client/v4"


def domain_of(url: str) -> str:
    return (urlparse(url).netloc or url).replace("www.", "").lower()


def _cf_headers() -> dict:
    if C.CF_AI_TOKEN.startswith("cfut_"):
        return {"Authorization": f"Bearer {C.CF_AI_TOKEN}"}
    if C.CF_GLOBAL_KEY:
        return {"X-Auth-Key": C.CF_GLOBAL_KEY, "X-Auth-Email": C.CF_EMAIL}
    return {}


def _kv_url(key: str) -> str:
    return (f"{_BASE}/accounts/{C.CF_ACCOUNT_ID}/storage/kv/namespaces/"
            f"{KV_NS}/values/{key}")


def _local_load() -> dict:
    try:
        return json.loads(open(LOCAL).read())
    except Exception:
        return {}


def _local_save(data: dict) -> None:
    try:
        open(LOCAL, "w").write(json.dumps(data, indent=1))
    except Exception:
        pass


async def recall(url: str) -> dict:
    """Return the learned recipe for this URL's domain (empty dict if none)."""
    dom = domain_of(url)
    key = f"recipe:{dom}"
    if C.CF_ACCOUNT_ID and _cf_headers():
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(_kv_url(key), headers=_cf_headers(),
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        return json.loads(await r.text())
        except Exception:
            pass
    return _local_load().get(dom, {})


async def record(url: str, recipe: dict) -> None:
    """Persist/merge a recipe for this URL's domain."""
    dom = domain_of(url)
    recipe = {**recipe, "domain": dom, "updated": time.time()}
    # local
    data = _local_load()
    data[dom] = recipe
    _local_save(data)
    # CF KV
    if C.CF_ACCOUNT_ID and _cf_headers():
        try:
            async with aiohttp.ClientSession() as s:
                await s.put(_kv_url(f"recipe:{dom}"),
                            headers={**_cf_headers(), "Content-Type": "text/plain"},
                            data=json.dumps(recipe),
                            timeout=aiohttp.ClientTimeout(total=15))
        except Exception:
            pass


def hint_text(recipe: dict) -> str:
    """Render a learned recipe as a hint for the navigator prompt."""
    if not recipe:
        return "(no prior attempts on this site)"
    parts = []
    if recipe.get("advance_labels"):
        parts.append("buttons that advanced steps: " + ", ".join(recipe["advance_labels"][:8]))
    if recipe.get("submit_label"):
        parts.append(f"the SUBMIT button was labeled: '{recipe['submit_label']}'")
    if recipe.get("steps"):
        parts.append(f"form had ~{recipe['steps']} steps")
    if recipe.get("success_signal"):
        parts.append(f"success confirmation text contained: '{recipe['success_signal'][:60]}'")
    if recipe.get("submitted") is False:
        parts.append("PRIOR ATTEMPT FAILED to submit — try a different final button")
    return "; ".join(parts) or "(recipe present but empty)"
