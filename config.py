"""Central configuration — all values overridable via environment variables."""

from __future__ import annotations
import os


# ── SMMFollows API ──────────────────────────────────────────────────────────
SMM_API_KEY = os.getenv("SMM_API_KEY", "YOUR_SMM_API_KEY_HERE")
SMM_API_URL = "https://smmfollows.com/api/v2"

# ── Claude / Anthropic AI ───────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_API_KEY_HERE")
CLAUDE_MODEL      = "claude-sonnet-4-6"

# ── Bot Timing ──────────────────────────────────────────────────────────────
POLL_INTERVAL_SEC   = 60    # seconds between order status checks
REFILL_INTERVAL_SEC = 300   # seconds between refill sweeps
AGENT_THINK_SEC     = 30    # seconds between agent decision cycles

# ── Service IDs (verified live from your account) ───────────────────────────
# ID 12452 → Twitter Likes Turkey HQ | rate $0.88/1k | refill YES | min 10
# ID 7339  → Twitter Comments Custom USA | rate $33.75/1k | min 5
# ID 13139 → Twitter Retweets HQ | rate $0.54/1k | refill YES | min 10
LIKES_SERVICE_ID    = int(os.getenv("SMM_LIKES_SVC",    "12452"))
COMMENTS_SERVICE_ID = int(os.getenv("SMM_COMMENTS_SVC", "7339"))
RETWEETS_SERVICE_ID = int(os.getenv("SMM_RETWEETS_SVC", "13139"))

# ── Default Quantities ──────────────────────────────────────────────────────
DEFAULT_LIKES_QTY    = int(os.getenv("SMM_LIKES_QTY",    "50"))
DEFAULT_COMMENTS_QTY = int(os.getenv("SMM_COMMENTS_QTY", "5"))
DEFAULT_RETWEETS_QTY = int(os.getenv("SMM_RETWEETS_QTY", "10"))

# ── Targets ─────────────────────────────────────────────────────────────────
# Comma-separated post URLs the agent should boost
TARGET_LINKS: list[str] = [
    url.strip()
    for url in os.getenv(
        "SMM_TARGET_LINKS",
        "https://twitter.com/example/status/123456789",
    ).split(",")
    if url.strip()
]

# ── Agent Persona (passed to Claude as system context) ──────────────────────
AGENT_PERSONA = (
    "You are an expert social media growth agent. "
    "Your job is to boost engagement on Twitter/X posts by placing targeted "
    "likes, retweets, and context-aware comments via the SMMFollows API. "
    "Always keep orders healthy — refill any order that is completed or partial. "
    "Generate comments that are natural, positive, and relevant to the post topic."
)
