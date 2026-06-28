"""AOS configuration — reads from existing .env"""
import os
from dotenv import load_dotenv
load_dotenv()

class AOSConfig:
    # ── Orchestrator ──────────────────────────────────────────────────────────
    CLAUDE_KEY:    str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL:  str = "claude-sonnet-4-6"

    # ── Reasoning / Vision ───────────────────────────────────────────────────
    GEMINI_KEY:    str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL:  str = "gemini-2.0-flash"

    # ── Fast inference ───────────────────────────────────────────────────────
    GROQ_KEY:      str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL:    str = "llama-3.3-70b-versatile"

    # ── Coding ───────────────────────────────────────────────────────────────
    DEEPSEEK_KEY:  str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ── Fallback (GPT-4o-mini for cheap tasks) ────────────────────────────────
    OPENAI_KEY:    str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL:  str = "gpt-4o-mini"

    # ── Telegram Bot ─────────────────────────────────────────────────────────
    BOT_TOKEN:  str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    OWNER_ID:   int = int(os.getenv("TELEGRAM_OWNER_ID", "0"))

    # ── xAI Grok (real-time X/Twitter + web search) ──────────────────────────
    XAI_KEY:       str = os.getenv("XAI_API_KEY", "")
    XAI_MODEL:     str = "grok-3-latest"

    # ── Search ───────────────────────────────────────────────────────────────
    TAVILY_KEY:       str = os.getenv("TAVILY_API_KEY", "")
    X_BEARER_TOKEN:   str = os.getenv("X_BEARER_TOKEN", "")

    # ── Memory ───────────────────────────────────────────────────────────────
    DB_PATH:       str = os.getenv("AOS_DB_PATH", "aos_memory.db")

    # ── Pipeline tuning ──────────────────────────────────────────────────────
    MAX_DEBATE_ROUNDS: int = 5
    MIN_CONFIDENCE:    int = 70   # below this → run full debate
    FAST_THRESHOLD:    int = 85   # above this → skip extra rounds

    @classmethod
    def available_providers(cls) -> list[str]:
        p = []
        if cls.CLAUDE_KEY:   p.append("claude")
        if cls.GEMINI_KEY:   p.append("gemini")
        if cls.GROQ_KEY:     p.append("groq")
        if cls.DEEPSEEK_KEY: p.append("deepseek")
        if cls.OPENAI_KEY:   p.append("openai")
        return p
