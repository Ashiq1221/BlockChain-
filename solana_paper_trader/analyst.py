"""
ANALYST AGENT
Two layers:
  1. Hard safety filters via RugCheck (mint authority, LP status, holder concentration).
     These are code-enforced — Claude can never override them.
  2. Claude verdict: given clean on-chain facts, score conviction 1-10 with reasoning.
"""
import json
import logging
import aiohttp
from config import settings

log = logging.getLogger("analyst")

SYSTEM = """You are the analyst agent in a paper-trading research system for new Solana tokens.
You receive verified on-chain facts about a token that already passed rug-safety filters.
Score how attractive an immediate momentum entry is.

Respond ONLY with JSON, no markdown fences:
{"conviction": <1-10 int>, "thesis": "<one sentence>", "biggest_risk": "<one sentence>"}

Scoring guide:
- 9-10: strong organic buy pressure, healthy liquidity ratio, early but not sniped
- 6-8: decent momentum, some concerns
- 1-5: weak volume, sell pressure, or suspicious metrics
Be skeptical by default. Most new tokens fail."""


async def rugcheck(session: aiohttp.ClientSession, mint: str) -> dict | None:
    url = f"{settings.RUGCHECK_BASE}/tokens/{mint}/report"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        log.warning("rugcheck failed for %s: %s", mint, e)
    return None


def hard_filters(report: dict) -> tuple[bool, str]:
    """Code-enforced safety gates. Returns (passed, reason_if_failed)."""
    if report is None:
        return False, "no rugcheck report"

    score = report.get("score", 999999)
    if score > settings.MAX_RUGCHECK_SCORE:
        return False, f"rugcheck score {score} too risky"

    token = report.get("token") or {}
    if settings.REQUIRE_MINT_REVOKED and token.get("mintAuthority"):
        return False, "mint authority not revoked"
    if token.get("freezeAuthority"):
        return False, "freeze authority active"

    # top holder concentration
    holders = report.get("topHolders") or []
    top10 = sum(h.get("pct", 0) for h in holders[:10])
    if top10 > settings.MAX_TOP10_HOLDER_PCT:
        return False, f"top10 holders own {top10:.0f}%"

    # LP locked or burned
    if settings.REQUIRE_LP_LOCKED_OR_BURNED:
        markets = report.get("markets") or []
        lp_ok = any(
            (m.get("lp") or {}).get("lpLockedPct", 0) >= 90
            for m in markets
        )
        if not lp_ok:
            return False, "LP not locked/burned"

    return True, ""


def heuristic_verdict(candidate: dict, report: dict) -> dict:
    """
    Free fallback scorer used when no ANTHROPIC_API_KEY is set.
    Scores 0-10 from the same momentum facts Claude would see:
    buy pressure, volume-to-liquidity, holder spread, rugcheck risk.
    """
    ratio = candidate["buys_5m"] / max(candidate["sells_5m"], 1)
    vol_liq = candidate["vol_5m"] / max(candidate["liquidity_usd"], 1)
    holders = report.get("totalHolders") or 0
    rc_score = report.get("score") or 999999

    score = 0
    if ratio >= 3:      score += 3
    elif ratio >= 2:    score += 2
    elif ratio >= 1.2:  score += 1

    if vol_liq >= 0.30:   score += 3
    elif vol_liq >= 0.15: score += 2
    elif vol_liq >= 0.05: score += 1

    if holders >= 500:  score += 2
    elif holders >= 200: score += 1

    if rc_score <= 100:  score += 2
    elif rc_score <= 250: score += 1

    return {
        "conviction": min(score, 10),
        "thesis": (f"heuristic: buy/sell {ratio:.1f}, vol/liq {vol_liq:.2f}, "
                   f"{holders} holders, rugcheck {rc_score}"),
        "biggest_risk": "no LLM analysis (heuristic mode)",
    }


async def claude_verdict(session: aiohttp.ClientSession, candidate: dict, report: dict) -> dict:
    """Ask Claude for a conviction score on a pre-vetted candidate.

    Calls the Messages API over raw HTTP (aiohttp) rather than the anthropic
    SDK, so the project installs on platforms without a Rust toolchain
    (e.g. Termux, where the SDK's jiter dependency cannot build).
    """
    facts = {
        "symbol": candidate["symbol"],
        "age_minutes": candidate["age_min"],
        "liquidity_usd": candidate["liquidity_usd"],
        "volume_5m_usd": candidate["vol_5m"],
        "buys_5m": candidate["buys_5m"],
        "sells_5m": candidate["sells_5m"],
        "buy_sell_ratio": round(candidate["buys_5m"] / max(candidate["sells_5m"], 1), 2),
        "vol_to_liq_ratio": round(candidate["vol_5m"] / max(candidate["liquidity_usd"], 1), 3),
        "rugcheck_score": report.get("score"),
        "holder_count": report.get("totalHolders"),
    }
    payload = {
        "model": settings.CLAUDE_MODEL,
        "max_tokens": settings.CLAUDE_MAX_TOKENS,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": json.dumps(facts)}],
    }
    headers = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        async with session.post(
            settings.ANTHROPIC_API_URL, json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as r:
            body = await r.json()
            if r.status != 200:
                err = (body.get("error") or {}).get("message", "")
                raise RuntimeError(f"API {r.status}: {err}")
        raw = "".join(b.get("text", "") for b in body.get("content", [])
                      if b.get("type") == "text")
        raw = raw.replace("```json", "").replace("```", "").strip()
        verdict = json.loads(raw)
        verdict["conviction"] = int(verdict.get("conviction", 0))
        return verdict
    except Exception as e:
        # covers no credits, rate limits, network errors — trade on heuristics
        log.warning("claude verdict failed (%s) — using heuristic score", e)
        return heuristic_verdict(candidate, report)


async def analyze(session: aiohttp.ClientSession, candidate: dict) -> dict | None:
    """Full pipeline for one candidate. Returns enriched dict or None if rejected."""
    report = await rugcheck(session, candidate["mint"])
    passed, reason = hard_filters(report or {})
    if not passed:
        log.info("REJECT %s: %s", candidate["symbol"], reason)
        return None

    if settings.ANTHROPIC_API_KEY:
        verdict = await claude_verdict(session, candidate, report)
    else:
        verdict = heuristic_verdict(candidate, report)
    if verdict["conviction"] < settings.MIN_CONVICTION:
        log.info("PASS %s: conviction %d (%s)",
                 candidate["symbol"], verdict["conviction"], verdict["thesis"])
        return None

    log.info("SIGNAL %s: conviction %d — %s",
             candidate["symbol"], verdict["conviction"], verdict["thesis"])
    return {**candidate, **verdict}
