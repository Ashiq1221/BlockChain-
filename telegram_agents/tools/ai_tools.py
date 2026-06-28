"""
Multi-provider AI with automatic fallback.
Order: Anthropic → OpenAI (ChatGPT) → Google Gemini (free)
If one runs out of credits or fails, instantly switches to the next.
"""
import httpx
from telegram_agents.config import Config

SYSTEM_BASE = f"""You are an elite AI operating as part of a 10-agent autonomous Telegram management system.
Persona: {Config.AGENT_PERSONA}
Language: {Config.AGENT_LANGUAGE}
Core principles:
- Always respond with clear, actionable intelligence.
- Imitate natural human communication — never sound automated.
- Prioritize the user's goals above everything else.
- Be strategic, efficient, and precise.
"""

# ── Provider implementations ──────────────────────────────────────────────────

def _anthropic(system: str, prompt: str, max_tokens: int) -> str:
    if not Config.ANTHROPIC_API_KEY:
        raise ValueError("No Anthropic key")
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": Config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    if resp.status_code in (429, 529):
        raise RuntimeError(f"Anthropic credits exhausted ({resp.status_code})")
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def _openai(system: str, prompt: str, max_tokens: int) -> str:
    if not Config.OPENAI_API_KEY:
        raise ValueError("No OpenAI key")
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
        },
        timeout=60,
    )
    if resp.status_code in (429, 402):
        raise RuntimeError(f"OpenAI credits exhausted ({resp.status_code})")
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _groq(system: str, prompt: str, max_tokens: int) -> str:
    if not Config.GROQ_API_KEY:
        raise ValueError("No Groq key")
    resp = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {Config.GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
        },
        timeout=60,
    )
    if resp.status_code == 429:
        raise RuntimeError("Groq rate limit")
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _gemini(system: str, prompt: str, max_tokens: int) -> str:
    if not Config.GEMINI_API_KEY:
        raise ValueError("No Gemini key")
    resp = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={Config.GEMINI_API_KEY}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        },
        timeout=60,
    )
    if resp.status_code == 429:
        raise RuntimeError("Gemini rate limit")
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


# ── Auto-fallback core ────────────────────────────────────────────────────────

_PROVIDERS = [
    ("Anthropic", _anthropic),
    ("ChatGPT",   _openai),
    ("Groq",      _groq),      # FREE — 14,400 req/day
    ("Gemini",    _gemini),
]

_active_provider = 0   # start with Anthropic


def _call(system_addon: str, user_prompt: str, max_tokens: int = 1024) -> str:
    global _active_provider
    system = SYSTEM_BASE + "\n" + system_addon
    errors = []

    # Try from current active provider, then fall through
    for i in range(_active_provider, len(_PROVIDERS)):
        name, fn = _PROVIDERS[i]
        try:
            result = fn(system, user_prompt, max_tokens)
            if i != _active_provider:
                print(f"[AI] Switched to {name}")
                _active_provider = i
            return result
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"[AI] {name} failed — trying next... ({e})")

    # All providers failed — reset to Anthropic for next call
    _active_provider = 0
    return f"[All AI providers failed: {' | '.join(errors)}]"


def current_provider() -> str:
    return _PROVIDERS[_active_provider][0]


# ── Public API (same as before — nothing else needs to change) ────────────────

def think(system_addon: str, user_prompt: str, max_tokens: int = 1024) -> str:
    return _call(system_addon, user_prompt, max_tokens)


def compose_message(context: str, goal: str, tone: str = "professional") -> str:
    return _call(
        f"You compose Telegram messages. Tone: {tone}. Keep messages concise and human.",
        f"Context:\n{context}\n\nGoal: {goal}\n\nWrite the message (plain text, no markdown):",
        512,
    )


def analyze_text(text: str, question: str) -> str:
    return _call("You analyze text and extract insights.",
                 f"Text:\n{text}\n\nQuestion: {question}", 768)


def plan_action(goal: str, available_tools: list[str], context: str = "") -> str:
    tools_str = "\n".join(f"- {t}" for t in available_tools)
    return _call(
        "You are a strategic planner. Return a numbered step-by-step action plan.",
        f"Goal: {goal}\n\nAvailable tools:\n{tools_str}\n\nContext: {context}\n\nCreate a precise action plan:",
        1024,
    )


def classify(text: str, categories: list[str]) -> str:
    return _call(
        "You classify text into categories. Reply with ONLY the category name.",
        f"Text: {text}\n\nCategories: {', '.join(categories)}\n\nCategory:", 50,
    )


def score_relevance(item: str, goal: str) -> int:
    result = _call(
        "You score relevance 1-10. Reply with ONLY the integer score.",
        f"Item: {item}\n\nGoal: {goal}\n\nScore (1-10):", 10,
    )
    try:
        return int("".join(filter(str.isdigit, result)) or "5")
    except Exception:
        return 5


def extract_jobs(text: str) -> list[dict]:
    raw = _call(
        "You extract job postings from text. Return JSON array with keys: title, company, description, url.",
        f"Text:\n{text}\n\nExtract all job postings as JSON array:", 2048,
    )
    import json, re
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return []


def craft_job_application(job: dict, user_profile: str) -> str:
    return _call(
        "You write compelling, personalized job application messages for Telegram. Sound genuinely interested, not templated.",
        f"Job:\nTitle: {job.get('title')}\nCompany: {job.get('company')}\nDescription: {job.get('description','')[:500]}\n\nApplicant:\n{user_profile}\n\nWrite the application message:",
        600,
    )


def generate_post(topic: str, group_context: str, style: str = "informative") -> str:
    return _call(
        f"You write engaging Telegram group posts. Style: {style}. No hashtag spam. Sound human.",
        f"Topic: {topic}\nGroup context: {group_context}\n\nWrite the post:", 512,
    )


def smart_reply(incoming: str, conversation_history: str, goal: str) -> str:
    return _call(
        "You craft smart, natural Telegram replies that advance the user's goals.",
        f"Conversation history:\n{conversation_history}\n\nLatest message: {incoming}\n\nGoal: {goal}\n\nReply:",
        400,
    )
