"""Claude AI integration — provides intelligence to every agent."""
import anthropic
from telegram_agents.config import Config

_client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

# Model name compatibility across anthropic SDK versions
_MODEL = getattr(Config, "CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

SYSTEM_BASE = f"""You are an elite AI operating as part of a 10-agent autonomous Telegram management system.
Persona: {Config.AGENT_PERSONA}
Language: {Config.AGENT_LANGUAGE}

Core principles:
- Always respond with clear, actionable intelligence.
- Imitate natural human communication patterns — never sound automated.
- Prioritize the user's goals above everything else.
- Be strategic, efficient, and precise.
"""


def think(system_addon: str, user_prompt: str, max_tokens: int = 1024) -> str:
    """Single-turn Claude reasoning call."""
    response = _client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        system=SYSTEM_BASE + "\n" + system_addon,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


def compose_message(context: str, goal: str, tone: str = "professional") -> str:
    return think(
        system_addon=f"You compose Telegram messages. Tone: {tone}. Keep messages concise and human.",
        user_prompt=f"Context:\n{context}\n\nGoal: {goal}\n\nWrite the message (plain text, no markdown):",
        max_tokens=512,
    )


def analyze_text(text: str, question: str) -> str:
    return think(
        system_addon="You analyze text and extract insights.",
        user_prompt=f"Text:\n{text}\n\nQuestion: {question}",
        max_tokens=768,
    )


def plan_action(goal: str, available_tools: list[str], context: str = "") -> str:
    tools_str = "\n".join(f"- {t}" for t in available_tools)
    return think(
        system_addon="You are a strategic planner. Return a numbered step-by-step action plan.",
        user_prompt=f"Goal: {goal}\n\nAvailable tools:\n{tools_str}\n\nContext: {context}\n\nCreate a precise action plan:",
        max_tokens=1024,
    )


def classify(text: str, categories: list[str]) -> str:
    cats = ", ".join(categories)
    return think(
        system_addon="You classify text into categories. Reply with ONLY the category name.",
        user_prompt=f"Text: {text}\n\nCategories: {cats}\n\nCategory:",
        max_tokens=50,
    )


def score_relevance(item: str, goal: str) -> int:
    result = think(
        system_addon="You score relevance 1-10. Reply with ONLY the integer score.",
        user_prompt=f"Item: {item}\n\nGoal: {goal}\n\nScore (1-10):",
        max_tokens=10,
    )
    try:
        return int("".join(filter(str.isdigit, result)))
    except Exception:
        return 5


def extract_jobs(text: str) -> list[dict]:
    raw = think(
        system_addon="You extract job postings from text. Return JSON array with keys: title, company, description, url.",
        user_prompt=f"Text:\n{text}\n\nExtract all job postings as JSON array:",
        max_tokens=2048,
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
    return think(
        system_addon="You write compelling, personalized job application messages for Telegram. Sound genuinely interested, not templated.",
        user_prompt=f"Job:\nTitle: {job.get('title')}\nCompany: {job.get('company')}\nDescription: {job.get('description', '')[:500]}\n\nApplicant profile:\n{user_profile}\n\nWrite the application message:",
        max_tokens=600,
    )


def generate_post(topic: str, group_context: str, style: str = "informative") -> str:
    return think(
        system_addon=f"You write engaging Telegram group posts. Style: {style}. No hashtag spam. Sound human.",
        user_prompt=f"Topic: {topic}\nGroup context: {group_context}\n\nWrite the post:",
        max_tokens=512,
    )


def smart_reply(incoming: str, conversation_history: str, goal: str) -> str:
    return think(
        system_addon="You craft smart, natural Telegram replies that advance the user's goals.",
        user_prompt=f"Conversation history:\n{conversation_history}\n\nLatest message: {incoming}\n\nGoal: {goal}\n\nReply:",
        max_tokens=400,
    )
