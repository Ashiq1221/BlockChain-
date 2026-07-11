"""Token discovery via the free DexScreener API.

Candidate sources:
  * latest token profiles  — newly listed/promoted tokens
  * latest token boosts    — tokens paying for visibility (high attention)

Each candidate mint is resolved to its most liquid SOL pair, and the pair's
market metrics (liquidity, volume, txns, price change, age) are returned for
the strategy filters.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

log = logging.getLogger("solbot.discovery")

DEX_BASE = "https://api.dexscreener.com"


@dataclass
class PairInfo:
    mint: str
    symbol: str
    name: str
    pair_address: str
    dex_id: str
    price_usd: float
    price_native: float          # price in SOL
    liquidity_usd: float
    volume_h1: float
    volume_h24: float
    txns_h1_buys: int
    txns_h1_sells: int
    price_change_h1: float
    price_change_h24: float
    pair_created_at: float       # unix seconds
    url: str = ""
    source: str = ""

    @property
    def age_minutes(self) -> float:
        return (time.time() - self.pair_created_at) / 60 if self.pair_created_at else 0.0

    @property
    def buy_sell_ratio(self) -> float:
        return self.txns_h1_buys / max(self.txns_h1_sells, 1)


@dataclass
class Discovery:
    _client: httpx.AsyncClient = field(
        default_factory=lambda: httpx.AsyncClient(timeout=20)
    )

    async def _get(self, path: str) -> list | dict:
        resp = await self._client.get(f"{DEX_BASE}{path}")
        resp.raise_for_status()
        return resp.json()

    async def candidate_mints(self) -> dict[str, str]:
        """Return {mint: source} for fresh Solana token candidates."""
        mints: dict[str, str] = {}
        for path, source in (
            ("/token-profiles/latest/v1", "profile"),
            ("/token-boosts/latest/v1", "boost"),
        ):
            try:
                items = await self._get(path)
            except httpx.HTTPError as exc:
                log.warning("dexscreener %s failed: %s", path, exc)
                continue
            for item in items or []:
                if item.get("chainId") == "solana" and item.get("tokenAddress"):
                    mints.setdefault(item["tokenAddress"], source)
        return mints

    async def best_sol_pair(self, mint: str, source: str = "") -> PairInfo | None:
        """Most liquid SOL-quoted pair for a mint, or None."""
        try:
            data = await self._get(f"/latest/dex/tokens/{mint}")
        except httpx.HTTPError as exc:
            log.warning("pair lookup for %s failed: %s", mint, exc)
            return None
        pairs = [
            p
            for p in (data.get("pairs") or [])
            if p.get("chainId") == "solana"
            and (p.get("quoteToken") or {}).get("symbol") in ("SOL", "WSOL")
        ]
        if not pairs:
            return None
        best = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
        return self._to_pair_info(best, source)

    async def refresh_pair(self, pair_address: str) -> PairInfo | None:
        """Re-fetch a known pair for position monitoring."""
        try:
            data = await self._get(f"/latest/dex/pairs/solana/{pair_address}")
        except httpx.HTTPError as exc:
            log.warning("pair refresh %s failed: %s", pair_address, exc)
            return None
        pairs = data.get("pairs") or ([data["pair"]] if data.get("pair") else [])
        return self._to_pair_info(pairs[0]) if pairs else None

    @staticmethod
    def _to_pair_info(p: dict, source: str = "") -> PairInfo:
        txns_h1 = (p.get("txns") or {}).get("h1") or {}
        volume = p.get("volume") or {}
        change = p.get("priceChange") or {}
        base = p.get("baseToken") or {}
        return PairInfo(
            mint=base.get("address", ""),
            symbol=base.get("symbol", "?"),
            name=base.get("name", "?"),
            pair_address=p.get("pairAddress", ""),
            dex_id=p.get("dexId", ""),
            price_usd=float(p.get("priceUsd") or 0),
            price_native=float(p.get("priceNative") or 0),
            liquidity_usd=float((p.get("liquidity") or {}).get("usd") or 0),
            volume_h1=float(volume.get("h1") or 0),
            volume_h24=float(volume.get("h24") or 0),
            txns_h1_buys=int(txns_h1.get("buys") or 0),
            txns_h1_sells=int(txns_h1.get("sells") or 0),
            price_change_h1=float(change.get("h1") or 0),
            price_change_h24=float(change.get("h24") or 0),
            pair_created_at=float(p.get("pairCreatedAt") or 0) / 1000,
            url=p.get("url", ""),
            source=source,
        )

    async def close(self) -> None:
        await self._client.aclose()
