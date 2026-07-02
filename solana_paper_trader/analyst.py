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
from anthropic import AsyncAnthropic
from config import settings

log = logging.getLogger("analyst")
client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

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


async def claude_verdict(candidate: dict, report: dict) -> dict:
    """Ask Claude for a conviction score on a pre-vetted candidate."""
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
    try:
        msg = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.CLAUDE_MAX_TOKENS,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(facts)}],
        )
        raw = "".join(b.text for b in msg.content if b.type == "text")
        raw = raw.replace("```json", "").replace("```", "").strip()
        verdict = json.loads(raw)
        verdict["conviction"] = int(verdict.get("conviction", 0))
        return verdict
    except Exception as e:
        log.warning("claude verdict failed: %s", e)
        return {"conviction": 0, "thesis": "analysis failed", "biggest_risk": str(e)}


async def analyze(session: aiohttp.ClientSession, candidate: dict) -> dict | None:
    """Full pipeline for one candidate. Returns enriched dict or None if rejected."""
    report = await rugcheck(session, candidate["mint"])
    passed, reason = hard_filters(report or {})
    if not passed:
        log.info("REJECT %s: %s", candidate["symbol"], reason)
        return None

    verdict = await claude_verdict(candidate, report)
    if verdict["conviction"] < settings.MIN_CONVICTION:
        log.info("PASS %s: conviction %d (%s)",
                 candidate["symbol"], verdict["conviction"], verdict["thesis"])
        return None

    log.info("SIGNAL %s: conviction %d — %s",
             candidate["symbol"], verdict["conviction"], verdict["thesis"])
    return {**candidate, **verdict}
