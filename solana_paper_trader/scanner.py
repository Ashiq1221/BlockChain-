"""
SCANNER AGENT
Polls DexScreener for newly created Solana pairs and applies cheap
pre-filters (liquidity, age) so downstream agents only see plausible candidates.
"""
import time
import logging
import aiohttp
from config import settings

log = logging.getLogger("scanner")


async def fetch_json(session: aiohttp.ClientSession, url: str) -> dict | list | None:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                return await r.json()
            log.warning("GET %s -> %s", url, r.status)
    except Exception as e:
        log.warning("fetch failed %s: %s", url, e)
    return None


async def get_new_candidates(session: aiohttp.ClientSession, seen: set[str]) -> list[dict]:
    """
    Returns a list of candidate dicts:
    {mint, symbol, pair_address, price_usd, liquidity_usd, age_min, vol_5m, buys_5m, sells_5m}
    """
    candidates = []

    # 1. Latest boosted/profiled tokens are noisy; the token-pairs search on
    #    recent Solana pairs gives better raw material.
    data = await fetch_json(
        session,
        f"{settings.DEXSCREENER_BASE}/token-profiles/latest/v1",
    )
    mints = []
    if isinstance(data, list):
        mints = [d.get("tokenAddress") for d in data
                 if d.get("chainId") == settings.CHAIN and d.get("tokenAddress")]

    # 2. Hydrate each mint with pair data (price, liquidity, age, txns)
    for mint in mints[:30]:
        if mint in seen:
            continue
        pairs = await fetch_json(
            session, f"{settings.DEXSCREENER_BASE}/latest/dex/tokens/{mint}"
        )
        if not pairs or not pairs.get("pairs"):
            continue
        # take the deepest-liquidity pair
        best = max(pairs["pairs"], key=lambda p: (p.get("liquidity") or {}).get("usd", 0))
        liq = (best.get("liquidity") or {}).get("usd", 0) or 0
        created = best.get("pairCreatedAt", 0) / 1000  # ms -> s
        age_min = (time.time() - created) / 60 if created else 1e9
        txns5 = (best.get("txns") or {}).get("m5", {})

        if liq < settings.MIN_LIQUIDITY_USD:
            continue
        if age_min > settings.MAX_PAIR_AGE_MIN:
            continue

        candidates.append({
            "mint": mint,
            "symbol": (best.get("baseToken") or {}).get("symbol", "?"),
            "pair_address": best.get("pairAddress"),
            "price_usd": float(best.get("priceUsd") or 0),
            "liquidity_usd": liq,
            "age_min": round(age_min, 1),
            "vol_5m": (best.get("volume") or {}).get("m5", 0),
            "buys_5m": txns5.get("buys", 0),
            "sells_5m": txns5.get("sells", 0),
        })
        seen.add(mint)

    log.info("scanner: %d new candidates", len(candidates))
    return candidates


async def get_price(session: aiohttp.ClientSession, mint: str) -> float | None:
    """Current USD price for an open position (used by the risk manager)."""
    data = await fetch_json(
        session, f"{settings.DEXSCREENER_BASE}/latest/dex/tokens/{mint}"
    )
    if data and data.get("pairs"):
        best = max(data["pairs"], key=lambda p: (p.get("liquidity") or {}).get("usd", 0))
        try:
            return float(best.get("priceUsd") or 0) or None
        except (TypeError, ValueError):
            return None
    return None
