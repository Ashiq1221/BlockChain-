"""Claude AI via direct HTTP — no anthropic SDK needed, works on Android."""
import httpx
from telegram_agents.config import Config

_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL   = "claude-3-5-sonnet-20241022"
_HEADERS = {
    "x-api-key": Config.ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

SYSTEM_BASE = f"""You are an elite AI operating as part of a 10-agent autonomous Telegram management system.
Persona: {Config.AGENT_PERSONA}
Language: {Config.AGENT_LANGUAGE}

Core principles:
- Always respond with clear, actionable intelligence.
- Imitate natural human communication — never sound automated.
- Prioritize the user's goals above everything else.
- Be strategic, efficient, and precise.
"""


def _call(system_addon: str, user_prompt: str, max_tokens: int = 1024) -> str:
    body = {
        "model": _MODEL,
        "max_tokens": max_tokens,
        "system": SYSTEM_BASE + "\n" + system_addon,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    try:
        resp = httpx.post(_API_URL, headers=_HEADERS, json=body, timeout=60)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception as e:
        return f"[AI error: {e}]"


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
