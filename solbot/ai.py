"""Claude-powered trade analyst.

After a candidate passes the rule-based safety filters, Claude reviews the
full market + on-chain picture and returns a structured verdict. The bot
only enters when the AI agrees, and scales position size by its conviction.

Enabled automatically when ANTHROPIC_API_KEY is set (override with
SOLBOT_AI_ENABLED=false). Fails safe: any API error skips the candidate —
it will be re-vetted on a later scan.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from . import config
from .discovery import PairInfo

log = logging.getLogger("solbot.ai")

AI_MODEL = os.getenv("SOLBOT_AI_MODEL", "claude-opus-4-8")
AI_ENABLED = os.getenv(
    "SOLBOT_AI_ENABLED", "true" if os.getenv("ANTHROPIC_API_KEY") else "false"
).strip().lower() in ("1", "true", "yes", "on")
MIN_CONVICTION = int(os.getenv("SOLBOT_AI_MIN_CONVICTION", "60"))

SYSTEM_PROMPT = (
    "You are a risk-focused analyst for a Solana meme-coin trading bot. "
    "You review tokens that already passed mechanical filters (liquidity, volume, "
    "mint/freeze authority renounced, holder concentration). Your job is to catch "
    "what the filters miss: pump-and-dump patterns, wash-traded volume, momentum "
    "that has already exhausted itself, suspicious buy/sell dynamics, and copycat "
    "or scam-adjacent names. Meme coins are lottery tickets — most go to zero — so "
    "only endorse entries where the short-term risk/reward is genuinely favorable. "
    "Skipping a mediocre setup costs nothing; a bad entry costs real money. "
    "Conviction scale: 0-40 clear skip, 41-59 weak, 60-79 reasonable setup, "
    "80-100 unusually strong. size_multiplier scales the standard position "
    "(0.5 = half size, 1.0 = standard, max 1.5 for exceptional setups)."
)

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["buy", "skip"]},
        "conviction": {"type": "integer", "description": "0-100 confidence in the verdict"},
        "size_multiplier": {"type": "number", "description": "0.5-1.5 position scaling"},
        "reasoning": {"type": "string", "description": "2-3 sentence rationale"},
        "risk_flags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short labels for each identified risk",
        },
    },
    "required": ["verdict", "conviction", "size_multiplier", "reasoning", "risk_flags"],
    "additionalProperties": False,
}


@dataclass
class AIDecision:
    verdict: str
    conviction: int
    size_multiplier: float
    reasoning: str
    risk_flags: list[str]

    @property
    def approved(self) -> bool:
        return self.verdict == "buy" and self.conviction >= MIN_CONVICTION


_client = None


def client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.AsyncAnthropic()
    return _client


def _candidate_brief(pair: PairInfo, top10_pct: float | None) -> str:
    holder_line = (
        f"{top10_pct:.1f}% (excl. pool)" if top10_pct is not None else "unavailable"
    )
    return f"""Evaluate this Solana meme coin for a short-term momentum entry (hold minutes to hours, TP +{config.TAKE_PROFIT_PCT:.0f}% / SL -{config.STOP_LOSS_PCT:.0f}%):

Token: {pair.name} ({pair.symbol})
Mint: {pair.mint}
DEX: {pair.dex_id} | discovered via DexScreener {pair.source or "listing"}
Pair age: {pair.age_minutes:.0f} minutes
Price: ${pair.price_usd:.10f} ({pair.price_native:.12f} SOL)
Liquidity: ${pair.liquidity_usd:,.0f}
Volume: ${pair.volume_h1:,.0f} (1h) / ${pair.volume_h24:,.0f} (24h)
Transactions 1h: {pair.txns_h1_buys} buys / {pair.txns_h1_sells} sells (ratio {pair.buy_sell_ratio:.2f})
Price change: {pair.price_change_h1:+.1f}% (1h) / {pair.price_change_h24:+.1f}% (24h)
Top-10 holder share: {holder_line}
Mint & freeze authority: renounced (verified on-chain)

All mechanical filters passed. Should the bot enter?"""


async def analyze(pair: PairInfo, top10_pct: float | None = None) -> AIDecision | None:
    """Ask Claude for a structured entry decision. None = unusable answer (skip)."""
    if not AI_ENABLED:
        return None
    try:
        response = await client().messages.create(
            model=AI_MODEL,
            max_tokens=16000,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            output_config={"format": {"type": "json_schema", "schema": DECISION_SCHEMA}},
            messages=[{"role": "user", "content": _candidate_brief(pair, top10_pct)}],
        )
        if response.stop_reason == "refusal":
            log.warning("AI declined to analyze %s", pair.symbol)
            return None
        text = next((b.text for b in response.content if b.type == "text"), "")
        data = json.loads(text)
        decision = AIDecision(
            verdict=data["verdict"],
            conviction=max(0, min(100, int(data["conviction"]))),
            size_multiplier=max(0.5, min(1.5, float(data["size_multiplier"]))),
            reasoning=data["reasoning"],
            risk_flags=list(data["risk_flags"]),
        )
        log.info(
            "AI on %s: %s (conviction %d, size x%.2f)%s — %s",
            pair.symbol, decision.verdict.upper(), decision.conviction,
            decision.size_multiplier,
            f" flags: {', '.join(decision.risk_flags)}" if decision.risk_flags else "",
            decision.reasoning,
        )
        return decision
    except Exception as exc:
        log.warning("AI analysis of %s failed (%s) — skipping candidate", pair.symbol, exc)
        return None
