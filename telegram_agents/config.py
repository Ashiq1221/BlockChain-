import os
from dotenv import load_dotenv

load_dotenv()


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

    # AI Providers — system uses whichever has credits, in order
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GROQ_API_KEY:   str = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # xAI Grok — real-time X/Twitter + web search (primary opportunity finder)
    XAI_API_KEY:    str = os.getenv("XAI_API_KEY", "")
    XAI_MODEL:      str = "grok-3-latest"

    # Bot
    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_ID:  int = int(os.getenv("TELEGRAM_OWNER_ID", "0"))

    # Optional
    SERPAPI_KEY:     str = os.getenv("SERPAPI_KEY", "")
    TAVILY_KEY:      str = os.getenv("TAVILY_API_KEY", "")
    X_BEARER_TOKEN:  str = os.getenv("X_BEARER_TOKEN", "")
    DB_PATH: str = "telegram_agents.db"
