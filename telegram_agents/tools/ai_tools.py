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

# ── Provider implementations ───────────────────────────────────────────────────

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


def _groq(system: str, prompt: str, max_tokens: int, model: str = "llama-3.1-8b-instant") -> str:
    if not Config.GROQ_API_KEY:
        raise ValueError("No Groq key")
    import time as _time
    for attempt in range(2):
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {Config.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
            },
            timeout=60,
        )
        if resp.status_code == 429 and attempt == 0:
            print(f"[AI] Groq {model} 429 — waiting 30s...")
            _time.sleep(30)
            continue
        if resp.status_code == 429:
            raise RuntimeError("Groq rate limit")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    raise RuntimeError("Groq rate limit after retry")


def _groq_70b(system: str, prompt: str, max_tokens: int) -> str:
    return _groq(system, prompt, max_tokens, model="llama-3.3-70b-versatile")


def _groq_gemma(system: str, prompt: str, max_tokens: int) -> str:
    return _groq(system, prompt, max_tokens, model="gemma2-9b-it")


def _gemini(system: str, prompt: str, max_tokens: int, model: str = "gemini-1.5-flash") -> str:
    if not Config.GEMINI_API_KEY:
        raise ValueError("No Gemini key")
    import time as _time
    for attempt in range(2):
        resp = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={Config.GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}],
                "generationConfig": {"maxOutputTokens": max_tokens},
            },
            timeout=60,
        )
        if resp.status_code == 429 and attempt == 0:
            print(f"[AI] Gemini {model} 429 — waiting 30s...")
            _time.sleep(30)
            continue
        if resp.status_code == 429:
            raise RuntimeError("Gemini rate limit")
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    raise RuntimeError("Gemini rate limit after retry")


def _gemini_flash2(system: str, prompt: str, max_tokens: int) -> str:
    return _gemini(system, prompt, max_tokens, model="gemini-2.0-flash")


# ── Auto-fallback core ──────────────────────────────────────────────────────────────

def _call(system_addon: str, user_prompt: str, max_tokens: int = 1024) -> str:
    """Route through Groq + OpenAI parallel race (ai_router)."""
    from telegram_agents.tools.ai_router import route as _router_route
    system = SYSTEM_BASE + "\n" + system_addon
    return _router_route(system, user_prompt, max_tokens)


def current_provider() -> str:
    from telegram_agents.tools.ai_router import router_status
    return router_status()


# ── Public API (same as before — nothing else needs to change) ──────────────────

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
