"""Optional Birdeye integration — richer discovery, security data, and candles.

Enabled when SOLBOT_BIRDEYE_API_KEY is set. Every endpoint degrades
gracefully: plans differ in which endpoints they include, so a 401/403/404
disables just that endpoint (warned once) and the bot continues without it.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

log = logging.getLogger("solbot.birdeye")

BASE = "https://public-api.birdeye.so"
API_KEY = os.getenv("SOLBOT_BIRDEYE_API_KEY", "")

_client: httpx.AsyncClient | None = None
_disabled_paths: set[str] = set()


def enabled() -> bool:
    return bool(API_KEY)


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=20,
            headers={"X-API-KEY": API_KEY, "x-chain": "solana", "accept": "application/json"},
        )
    return _client


async def _get(path: str, params: dict | None = None) -> dict | None:
    if not enabled() or path in _disabled_paths:
        return None
    try:
        resp = await client().get(f"{BASE}{path}", params=params)
        if resp.status_code in (401, 403, 404):
            _disabled_paths.add(path)
            log.warning(
                "birdeye %s not available on this API plan (%d) — continuing without it",
                path, resp.status_code,
            )
            return None
        resp.raise_for_status()
        data = resp.json()
        return data.get("data") if data.get("success", True) else None
    except httpx.HTTPError as exc:
        log.warning("birdeye %s failed: %s", path, exc)
        return None


# ── Discovery ────────────────────────────────────────────────────────────────

async def trending_mints(limit: int = 20) -> list[str]:
    data = await _get(
        "/defi/token_trending",
        {"sort_by": "rank", "sort_type": "asc", "offset": 0, "limit": limit},
    )
    tokens = (data or {}).get("tokens") or (data or {}).get("items") or []
    return [t["address"] for t in tokens if t.get("address")]


async def new_listing_mints(limit: int = 20) -> list[str]:
    data = await _get("/defi/v2/tokens/new_listing", {"limit": limit})
    items = (data or {}).get("items") or []
    return [t["address"] for t in items if t.get("address")]


# ── Token security ───────────────────────────────────────────────────────────

async def security(mint: str) -> dict | None:
    """Birdeye token-security record (holder concentration, freezeable, ...)."""
    return await _get("/defi/token_security", {"address": mint})


def security_summary(sec: dict) -> str:
    """Compact human-readable security digest for the AI brief."""
    parts = []
    top10 = sec.get("top10HolderPercent")
    if top10 is not None:
        parts.append(f"top-10 holders {float(top10) * 100:.1f}%")
    creator = sec.get("creatorPercentage")
    if creator is not None:
        parts.append(f"creator holds {float(creator) * 100:.2f}%")
    if sec.get("freezeable"):
        parts.append("FREEZEABLE (danger)")
    if sec.get("mutableMetadata"):
        parts.append("mutable metadata")
    if sec.get("isTrueToken") is False:
        parts.append("flagged non-standard token")
    return "; ".join(parts) if parts else "no security flags returned"


# ── Price history ────────────────────────────────────────────────────────────

async def recent_candles(mint: str, minutes: int = 120) -> str | None:
    """Summarize recent 15m candles so the AI can see the *shape* of the move,
    not just a 1h percentage snapshot."""
    now = int(time.time())
    data = await _get(
        "/defi/ohlcv",
        {
            "address": mint,
            "type": "15m",
            "time_from": now - minutes * 60,
            "time_to": now,
        },
    )
    items = (data or {}).get("items") or []
    if len(items) < 2:
        return None
    lines = []
    for c in items[-8:]:
        o, cl = float(c.get("o", 0)), float(c.get("c", 0))
        change = (cl / o - 1) * 100 if o else 0.0
        ts = time.strftime("%H:%M", time.gmtime(int(c.get("unixTime", 0))))
        lines.append(f"{ts}Z {change:+.1f}% vol ${float(c.get('v', 0)):,.0f}")
    return " | ".join(lines)
