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

# ── Service IDs ─────────────────────────────────────────────────────────────
# Run:  python agent.py list-services   to discover your account's real IDs
LIKES_SERVICE_ID    = int(os.getenv("SMM_LIKES_SVC",    "1"))
COMMENTS_SERVICE_ID = int(os.getenv("SMM_COMMENTS_SVC", "2"))
RETWEETS_SERVICE_ID = int(os.getenv("SMM_RETWEETS_SVC", "3"))

# ── Default Quantities ──────────────────────────────────────────────────────
DEFAULT_LIKES_QTY    = int(os.getenv("SMM_LIKES_QTY",    "100"))
DEFAULT_COMMENTS_QTY = int(os.getenv("SMM_COMMENTS_QTY", "10"))
DEFAULT_RETWEETS_QTY = int(os.getenv("SMM_RETWEETS_QTY", "50"))

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
