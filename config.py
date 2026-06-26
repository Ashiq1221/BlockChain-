import os

# ── SMMFollows API ──────────────────────────────────────────────────────────
API_KEY  = os.getenv("SMM_API_KEY", "YOUR_API_KEY_HERE")
API_URL  = "https://smmfollows.com/api/v2"

# ── Bot behaviour ───────────────────────────────────────────────────────────
POLL_INTERVAL   = 60   # seconds between status checks
REFILL_INTERVAL = 300  # seconds between refill sweeps

# ── Default quantities ──────────────────────────────────────────────────────
DEFAULT_LIKES_QTY    = 100
DEFAULT_COMMENTS_QTY = 10
DEFAULT_RETWEETS_QTY = 50

# ── Service IDs (update after calling /services) ───────────────────────────
# Run `python smm_bot.py --list-services` to discover real IDs for your account
LIKES_SERVICE_ID     = int(os.getenv("SMM_LIKES_SVC",    "1"))
COMMENTS_SERVICE_ID  = int(os.getenv("SMM_COMMENTS_SVC", "2"))
RETWEETS_SERVICE_ID  = int(os.getenv("SMM_RETWEETS_SVC", "3"))

# ── Targets (edit or supply via env) ────────────────────────────────────────
# Comma-separated Twitter/X post URLs that the bot should boost
TARGET_LINKS: list[str] = [
    url.strip()
    for url in os.getenv(
        "SMM_TARGET_LINKS",
        "https://twitter.com/example/status/123456789"
    ).split(",")
    if url.strip()
]

# Comment texts rotated for each comment order
COMMENT_TEXTS: list[str] = [
    "Great post!",
    "Amazing content!",
    "Love this!",
    "Keep it up!",
    "Fantastic work!",
]
