import os
from dotenv import load_dotenv

load_dotenv()


def _load_keys(env_prefix: str, fallback_var: str = "") -> list[str]:
    """
    Collect up to 5 numbered keys plus an optional legacy single key.
    Accepts both naming styles:
      GROQ_KEY_1 / GROQ_KEY_2   (preferred)
      GROQ_API_KEY1 / GROQ_API_KEY2  (also accepted)
    """
    seen: set[str] = set()
    keys: list[str] = []
    if fallback_var:
        v = os.getenv(fallback_var, "")
        if v:
            keys.append(v)
            seen.add(v)
    for i in range(1, 6):
        for var in (f"{env_prefix}_{i}", f"{fallback_var}{i}" if fallback_var else ""):
            if not var:
                continue
            v = os.getenv(var, "")
            if v and v not in seen:
                keys.append(v)
                seen.add(v)
    return keys


class Config:
    # Telegram
    API_ID: int = int(os.getenv("TELEGRAM_API_ID", "0"))
    API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")
    PHONE: str = os.getenv("TELEGRAM_PHONE", "")
    SESSION_NAME: str = os.getenv("TELEGRAM_SESSION_NAME", "tg_agent_session")

    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # Behavior
    AGENT_LANGUAGE: str = os.getenv("AGENT_LANGUAGE", "en")
    AGENT_PERSONA: str = os.getenv(
        "AGENT_PERSONA",
        "Professional, sharp, and concise. Sounds completely human — never robotic.",
    )
    MAX_DM_PER_HOUR: int = int(os.getenv("MAX_DM_PER_HOUR", "10"))
    MAX_GROUP_POSTS_PER_HOUR: int = int(os.getenv("MAX_GROUP_POSTS_PER_HOUR", "5"))
    RATE_LIMIT_SLEEP: float = float(os.getenv("RATE_LIMIT_SLEEP", "3"))
    AUTO_RESPOND: bool = os.getenv("AUTO_RESPOND", "true").lower() == "true"
    JOB_KEYWORDS: list[str] = [
        kw.strip()
        for kw in os.getenv(
            "JOB_KEYWORDS", "developer,engineer,remote,blockchain"
        ).split(",")
    ]

    # AI Providers — legacy single keys (still supported)
    OPENAI_API_KEY:    str = os.getenv("OPENAI_API_KEY", "")
    GROQ_API_KEY:      str = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY:    str = os.getenv("GEMINI_API_KEY", "")

    # Multi-key pools (up to 5 keys each — add KEY_1…KEY_5 in Railway env)
    # e.g. GROQ_KEY_1=gsk_... GROQ_KEY_2=gsk_... etc.
    GROQ_KEYS:     list[str] = _load_keys("GROQ_KEY",      "GROQ_API_KEY")
    OPENAI_KEYS:   list[str] = _load_keys("OPENAI_KEY",    "OPENAI_API_KEY")
    CLAUDE_KEYS:   list[str] = _load_keys("ANTHROPIC_KEY", "ANTHROPIC_API_KEY")
    DEEPSEEK_KEYS: list[str] = _load_keys("DEEPSEEK_KEY",  "DEEPSEEK_API_KEY")
    GEMINI_KEYS:   list[str] = _load_keys("GEMINI_KEY",    "GEMINI_API_KEY")

    # Bot
    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_ID:  int = int(os.getenv("TELEGRAM_OWNER_ID", "0"))

    # Optional
    SERPAPI_KEY:     str = os.getenv("SERPAPI_KEY", "")
    TAVILY_KEY:      str = os.getenv("TAVILY_API_KEY", "")
    FIRECRAWL_KEY:   str = os.getenv("FIRECRAWL_API_KEY", "")
    X_BEARER_TOKEN:  str = os.getenv("X_BEARER_TOKEN", "")
    DB_PATH: str = "telegram_agents.db"
