"""Rug-pull safety checks: market filters + on-chain mint inspection."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import config, rpc
from .discovery import PairInfo

log = logging.getLogger("solbot.safety")


@dataclass
class SafetyReport:
    ok: bool
    reasons: list[str]

    def __str__(self) -> str:
        return "PASS" if self.ok else "FAIL: " + "; ".join(self.reasons)


def check_market(pair: PairInfo) -> list[str]:
    """DexScreener-metric filters. Returns list of failure reasons."""
    reasons: list[str] = []
    if pair.liquidity_usd < config.MIN_LIQUIDITY_USD:
        reasons.append(f"liquidity ${pair.liquidity_usd:,.0f} < ${config.MIN_LIQUIDITY_USD:,.0f}")
    if pair.liquidity_usd > config.MAX_LIQUIDITY_USD:
        reasons.append(f"liquidity ${pair.liquidity_usd:,.0f} above meme range")
    if pair.volume_h1 < config.MIN_VOLUME_H1_USD:
        reasons.append(f"h1 volume ${pair.volume_h1:,.0f} < ${config.MIN_VOLUME_H1_USD:,.0f}")
    txns = pair.txns_h1_buys + pair.txns_h1_sells
    if txns < config.MIN_TXNS_H1:
        reasons.append(f"h1 txns {txns} < {config.MIN_TXNS_H1}")
    if pair.buy_sell_ratio < config.MIN_BUY_SELL_RATIO:
        reasons.append(f"buy/sell ratio {pair.buy_sell_ratio:.2f} < {config.MIN_BUY_SELL_RATIO}")
    age_min = pair.age_minutes
    if age_min < config.MIN_PAIR_AGE_MINUTES:
        reasons.append(f"pair only {age_min:.0f}m old (< {config.MIN_PAIR_AGE_MINUTES:.0f}m)")
    if age_min > config.MAX_PAIR_AGE_HOURS * 60:
        reasons.append(f"pair {age_min / 60:.0f}h old (> {config.MAX_PAIR_AGE_HOURS:.0f}h)")
    if pair.price_change_h1 < config.MIN_PRICE_CHANGE_H1_PCT:
        reasons.append(f"h1 change {pair.price_change_h1:+.1f}% lacks momentum")
    if pair.price_change_h1 > config.MAX_PRICE_CHANGE_H1_PCT:
        reasons.append(f"h1 change {pair.price_change_h1:+.1f}% — chasing a vertical pump")
    if pair.price_native <= 0:
        reasons.append("no SOL price")
    return reasons


async def check_onchain(mint: str) -> list[str]:
    """On-chain mint checks. Returns list of failure reasons."""
    reasons: list[str] = []
    try:
        info = await rpc.get_mint_info(mint)
    except RuntimeError as exc:
        return [f"mint lookup failed: {exc}"]
    if info is None:
        return ["mint account not found"]
    if config.REQUIRE_MINT_RENOUNCED and info.get("mintAuthority"):
        reasons.append("mint authority NOT renounced (owner can print supply)")
    if config.REQUIRE_FREEZE_RENOUNCED and info.get("freezeAuthority"):
        reasons.append("freeze authority NOT renounced (owner can freeze wallets)")
    try:
        top_pct = await rpc.get_top_holder_pct(mint)
    except RuntimeError as exc:
        reasons.append(f"holder check failed: {exc}")
        top_pct = None
    if top_pct is not None and top_pct > config.MAX_TOP10_HOLDER_PCT:
        reasons.append(
            f"top-10 holders own {top_pct:.1f}% (> {config.MAX_TOP10_HOLDER_PCT:.0f}%)"
        )
    return reasons


async def evaluate(pair: PairInfo) -> SafetyReport:
    """Run cheap market filters first, then on-chain checks."""
    reasons = check_market(pair)
    if reasons:  # skip RPC cost when the market filters already reject
        return SafetyReport(False, reasons)
    reasons = await check_onchain(pair.mint)
    return SafetyReport(not reasons, reasons)
