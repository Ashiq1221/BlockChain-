"""
Autonomous Job Application Agent — 10-Agent Orchestrated System

ARCHITECTURE — 5 X-Specialist Pairs × 2 Agents = 10 AI Agents
  X is the PRIMARY job source. All 10 agents are tuned for X/Twitter.

  Pair 1  HUNTERS       Hunter_Alpha (Groq)    ↔ Hunter_Beta (CF Workers AI)
  Pair 2  PROFILERS     Profiler_Alpha (OpenAI) ↔ Profiler_Beta (Groq)
  Pair 3  CONTACTS      Contact_Alpha (CF AI)   ↔ Contact_Beta (Groq)
  Pair 4  STRATEGISTS   Strategy_Alpha (Groq)   ↔ Strategy_Beta (OpenAI)
  Pair 5  EXECUTORS     Exec_Alpha (OpenAI)     ↔ Exec_Beta (CF AI)

Each pair deliberates in 2 rounds: independent analysis → synthesis.
Orchestrator: x_pipeline() hunts X → applies via TG group + founder DM + form + email.

CF SERVICES USED
  AI Gateway  — proxy + 60-min cache for Groq / OpenAI (cuts 429s)
  Workers AI  — free llama-3.3-70b for Hunter_Beta, Contact_Alpha, Exec_Beta
  KV          — cloud state: applied_jobs + posted_groups (survives reboots)

Run: python3 job_agent.py
"""
import asyncio
import collections
import json
import os
import re
import smtplib
import time
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

load_dotenv()
console = Console()

# ── Config ─────────────────────────────────────────────────────────────────────

GROQ_KEY        = os.getenv("GROQ_API_KEY", "")
OPENAI_KEY      = os.getenv("OPENAI_API_KEY", "")
FIRECRAWL_KEY   = os.getenv("FIRECRAWL_API_KEY", "")
TAVILY_KEY      = os.getenv("TAVILY_API_KEY", "")
TG_API_ID       = int(os.getenv("TELEGRAM_API_ID", "0"))
TG_API_HASH     = os.getenv("TELEGRAM_API_HASH", "")
TG_PHONE        = os.getenv("TELEGRAM_PHONE", "")
SESSION_NAME    = os.getenv("TELEGRAM_SESSION_NAME", "tg_agent_session")
SMTP_HOST       = os.getenv("SMTP_HOST", "")
SMTP_PORT       = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER       = os.getenv("SMTP_USER", "")
SMTP_PASS       = os.getenv("SMTP_PASS", "")
SEARCH_EVERY_HOURS = float(os.getenv("JOB_SEARCH_HOURS", "6"))

APPLIED_FILE        = Path("applied_jobs.json")
POSTED_GROUPS_FILE  = Path("posted_groups.json")
TARGET_GROUPS_FILE  = Path("target_groups.json")

MY_EMAIL = "naveeddurfi@gmail.com"

MY_PROFILE = """
NAME        : Ashiq
TITLE       : AI Operations Specialist | Community Builder | Content Creator
EMAIL       : naveeddurfi@gmail.com
TELEGRAM    : @ashiq80
TWITTER/X   : @Ganaie__suhail  (https://twitter.com/Ganaie__suhail)
LINKEDIN    : https://linkedin.com/in/ashiq-ah-705334395
DISCORD     : ashiq1581
LOCATION    : Kashmir, India — open to fully remote

SUMMARY:
AI Operations Specialist, Community Builder, and Content Creator with hands-on
experience in AI data annotation, chatbot testing, prompt engineering, AI content
creation, and community growth. Grown a Web3 Twitter/X account to 16,000+ followers
organically and built a 6,000+ member community across Telegram, Discord, OpenChat,
and DSCVR. Multilingual: English, Hindi, Urdu, Kashmiri.

KEY STATS:
- 16,000+ Web3 Twitter/X followers (@Ganaie__suhail) — 100% organic, zero paid ads
- 6,000+ member community (Telegram, OpenChat, DSCVR) — daily active, built from scratch
- 6+ Web3/AI protocols served end-to-end: EMC Protocol, ICPepeworld, Network3,
  LingoAI, RIDO, JarvisBot_AI, ICPCollectible

EXPERIENCE:
• AI Data Annotator & QA Contributor (Freelance, 2024–Present)
  – Data labeling, chatbot evaluation, prompt engineering, AI content creation
• Community Manager & Moderator — AI & Web3 (2023–Present)
  – Daily moderation on Telegram, Discord, X; conflict resolution; retention programs
• Social & Content Operator — EMC Protocol (2024–Present)
  – Owned Twitter/X + Telegram strategy, brand voice, product announcements, AI visuals
• Social Media Manager — ICPepeworld, Network3, LingoAI, RIDO, JarvisBot_AI (2023–Present)
  – Multi-project content output: threads, copy, banners, analytics-driven optimization
• Founder & Content Lead — ICPCollectible (2023–Present)
  – Built 16,000+ follower account; ICP ecosystem commentary; ambassador programs

SKILLS:
Community: Moderation, Growth, Engagement, Conflict Resolution, Onboarding, UGC
AI/Data: Annotation & Labeling, QA, Chatbot Testing, Prompt Engineering, Automation
Content: Twitter/X Threads, Copywriting, Brand Voice, Short-Form Video, Graphic Design
Social: SMM, Analytics, Creator & Ambassador Programs, Localization & Translation Data
Tools: ChatGPT, Telegram, Discord, Twitter/X, OpenChat, DSCVR, design & video tools

TARGET ROLES:
Community Manager, Social Media Manager (Web3), Content Writer/Creator, Ecosystem Lead,
Growth Manager, Content Moderator/Reviewer, UGC Creator, AI Data Annotator,
AI Model Evaluator, Ambassador Program Manager

EDUCATION: B.Tech — Kashmir University (2019–2023)
CERT: AI Tools and ChatGPT Workshop Certification
LANGUAGES: English, Hindi, Urdu, Kashmiri
""".strip()

# Job board category search queries
JOB_QUERIES = [
    "site:cryptojobs.com community manager ambassador moderator remote",
    "site:web3.career community manager ambassador moderator content creator remote",
    "site:remote3.co web3 blockchain AI community manager ambassador",
    "site:wellfound.com web3 blockchain community manager ambassador remote",
    "site:crypto.jobs community manager ambassador content creator remote",
    "web3 crypto project hiring community manager ambassador 2026 apply",
    "blockchain startup community lead moderator content creator hiring 2026",
]

# Known job board domains — used to recognise individual job post URLs
JOB_BOARD_DOMAINS = {
    "web3.career", "cryptojobs.com", "remote3.co", "wellfound.com",
    "crypto.jobs", "blockew.com", "cryptocurrencyjobs.co",
}

_SKIP_TG = {
    "joinchat", "share", "s", "iv", "addstickers",
    "telegram", "tme", "durov", "BotFather", "SpamBot",
}

# ── AI ─────────────────────────────────────────────────────────────────────────

# ── AI rate limiter ────────────────────────────────────────────────────────────
# Groq free tier: ~30 RPM.  We self-limit to 20 RPM to stay comfortable.
_AI_CALL_TIMES: collections.deque = collections.deque(maxlen=20)
_AI_RPM = 20  # max calls per 60-second window


def _ai_throttle():
    """Sleep proactively if we are approaching the RPM ceiling."""
    now = time.monotonic()
    # Drop timestamps older than 60 s
    while _AI_CALL_TIMES and now - _AI_CALL_TIMES[0] > 60:
        _AI_CALL_TIMES.popleft()
    if len(_AI_CALL_TIMES) >= _AI_RPM:
        wait = 61 - (now - _AI_CALL_TIMES[0])
        if wait > 0:
            console.print(f"[dim yellow]AI rate-limit window full — pausing {wait:.0f}s[/dim yellow]")
            time.sleep(wait)
    _AI_CALL_TIMES.append(time.monotonic())


_CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID",   "92d3158363256e88393822c9ece2fb48")
_CF_EMAIL      = os.getenv("CF_EMAIL",        "ashiqah18008@gmail.com")
_CF_GLOBAL_KEY = os.getenv("CF_GLOBAL_KEY",   "")   # set in .env
_CF_KV_NS      = os.getenv("CF_KV_NAMESPACE", "cda8b9f468204833a58d79d9409133c7")
_CF_GW         = f"https://gateway.ai.cloudflare.com/v1/{_CF_ACCOUNT_ID}/job-agent"

_PROVIDERS = [
    ("Groq",   GROQ_KEY,   f"{_CF_GW}/groq/openai/v1/chat/completions",   "llama-3.3-70b-versatile"),
    ("OpenAI", OPENAI_KEY, f"{_CF_GW}/openai/v1/chat/completions",         "gpt-4o-mini"),
]


# ── CF Workers AI (free — llama-3.3-70b at the edge) ─────────────────────────

def cf_workers_ai(system: str, prompt: str, max_tokens: int = 600) -> str:
    """Free inference via CF Workers AI REST API — no Groq/OpenAI quota used."""
    _ai_throttle()
    model = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    try:
        r = httpx.post(
            f"https://api.cloudflare.com/client/v4/accounts/{_CF_ACCOUNT_ID}/ai/run/{model}",
            headers={
                "X-Auth-Email": _CF_EMAIL,
                "X-Auth-Key":   _CF_GLOBAL_KEY,
                "Content-Type": "application/json",
            },
            json={
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                "max_tokens": max_tokens,
            },
            timeout=45,
        )
        if r.status_code == 200:
            data = r.json()
            # OpenAI-compatible wrapper OR raw response field
            choices = data.get("result", {}).get("choices")
            if choices:
                return (choices[0].get("message", {}).get("content") or "").strip()
            return (data.get("result", {}).get("response") or "").strip()
        console.print(f"[dim yellow]CF Workers AI: HTTP {r.status_code}[/dim yellow]")
    except Exception as e:
        console.print(f"[dim yellow]CF Workers AI error: {str(e)[:60]}[/dim yellow]")
    return ""


def _call_provider(name: str, key: str, url: str, model: str,
                   system: str, prompt: str, max_tokens: int) -> str:
    """Single provider call — used by agent_call() for direct routing."""
    if not key:
        return ""
    _ai_throttle()
    try:
        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model":      model,
                "max_tokens": max_tokens,
                "messages":   [{"role": "system", "content": system},
                               {"role": "user",   "content": prompt}],
            },
            timeout=40,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        if r.status_code == 429:
            console.print(f"[yellow]{name}: 429 — falling back to cf_workers_ai[/yellow]")
            return cf_workers_ai(system, prompt, max_tokens)
        console.print(f"[yellow]{name}: HTTP {r.status_code}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]{name} error: {str(e)[:60]}[/yellow]")
    return ""


# ── 10-Agent Registry — 5 X-Specialist Pairs ──────────────────────────────────
# All 10 agents are trained specifically to hunt and apply for jobs via X/Twitter.
# Each pair deliberates in 2 rounds before any decision is final.
#
#  Pair 1  HUNTERS      Find hiring posts on X (cast wide + filter hard)
#  Pair 2  PROFILERS    Research company from their X presence + scrape profile
#  Pair 3  CONTACT MAPPERS  Find CEO/founder Twitter handle + TG group
#  Pair 4  STRATEGISTS  Craft X-native outreach message (draft + sharpen)
#  Pair 5  EXECUTORS    Apply via TG group / founder DM / form / email + QA

_GROQ_URL   = f"{_CF_GW}/groq/openai/v1/chat/completions"
_OPENAI_URL = f"{_CF_GW}/openai/v1/chat/completions"

AGENTS: dict[str, dict] = {

    # ── Pair 1: HUNTERS — search X for real hiring posts ──────────────────
    "Hunter_Alpha": {
        "pair": "hunters",
        "backend": "groq",
        "persona": (
            "You are Hunter Alpha — an X/Twitter job radar built for Web3 and AI. "
            "Your job: extract EVERY tweet that signals a hiring opportunity for "
            "community manager, ambassador, moderator, content creator, or AI roles. "
            "Cast wide. Err toward inclusion. Your partner filters."
        ),
    },
    "Hunter_Beta": {
        "pair": "hunters",
        "backend": "cf",
        "persona": (
            "You are Hunter Beta — a precision noise-canceller. "
            "Review Hunter Alpha's leads and kill false positives: retweets without jobs, "
            "expired listings, non-Web3 roles, bot spam, and vague 'join us' posts. "
            "Keep only tweets with clear hiring intent from real Web3/AI projects."
        ),
    },

    # ── Pair 2: PROFILERS — deep X profile research ────────────────────────
    "Profiler_Alpha": {
        "pair": "profilers",
        "backend": "openai",
        "persona": (
            "You are Profiler Alpha — a Web3 company intelligence analyst. "
            "From a Twitter/X profile bio, pinned tweet, and recent posts, extract: "
            "company name, product description, stage (seed/growth/established), "
            "team size hint, Telegram handle, website, email, hiring manager hints. "
            "Build the richest possible company brief."
        ),
    },
    "Profiler_Beta": {
        "pair": "profilers",
        "backend": "groq",
        "persona": (
            "You are Profiler Beta — a legitimacy validator and opportunity scorer. "
            "Score the opportunity 0–100 for Ashiq's profile. "
            "Red flags: no website, 0 engagement, copy-paste job post, dead project. "
            "Green flags: active community, named founder, real product, token/VC backing. "
            "Return score + proceed true/false."
        ),
    },

    # ── Pair 3: CONTACT MAPPERS — find the right person on X + TG ────────
    "Contact_Alpha": {
        "pair": "contacts",
        "backend": "cf",
        "persona": (
            "You are Contact Alpha — a social graph mapper. "
            "From a company's X profile, bio, mentions, and replies, identify: "
            "the founder or CEO's Twitter handle, any team members mentioned, "
            "Telegram handles, and the official TG community link. "
            "Extract every contact signal from the available data."
        ),
    },
    "Contact_Beta": {
        "pair": "contacts",
        "backend": "groq",
        "persona": (
            "You are Contact Beta — a contact authority validator. "
            "Review Contact Alpha's findings. Confirm: does this person have hiring authority? "
            "Is this the founder/CEO or just a mod? Rank contacts by decision-making power. "
            "Output the single best contact to DM and why."
        ),
    },

    # ── Pair 4: STRATEGISTS — write X-native outreach ─────────────────────
    "Strategy_Alpha": {
        "pair": "strategists",
        "backend": "groq",
        "persona": (
            "You are Strategy Alpha — an X-native copywriter who writes DMs that get replies. "
            "You know Web3 culture, speak founder-to-founder, and never sound like a bot. "
            "Draft a 3-sentence application DM that opens with something specific about "
            "the project, delivers one hard stat, and ends with a precise question."
        ),
    },
    "Strategy_Beta": {
        "pair": "strategists",
        "backend": "openai",
        "persona": (
            "You are Strategy Beta — a brutal DM editor. "
            "Read Strategy Alpha's draft and make it hit harder. "
            "Cut filler. Replace generic phrases with specifics. "
            "Make sentence 1 impossible to ignore. Output only the final message."
        ),
    },

    # ── Pair 5: EXECUTORS — apply across all channels ─────────────────────
    "Exec_Alpha": {
        "pair": "executors",
        "backend": "openai",
        "persona": (
            "You are Exec Alpha — a multi-channel application executor. "
            "Given a job lead and crafted message, choose and execute the optimal apply path: "
            "TG group reply > TG founder DM > Google Form > email. "
            "Adapt message format to each channel."
        ),
    },
    "Exec_Beta": {
        "pair": "executors",
        "backend": "cf",
        "persona": (
            "You are Exec Beta — a QA and success verifier. "
            "Review the application before it sends. Check: is it professional? "
            "Does it accurately represent Ashiq? Is the channel right for this project? "
            "Approve or flag for revision."
        ),
    },
}


def agent_call(agent_name: str, task: str, context: str = "", max_tokens: int = 500) -> str:
    """Route a task to the correct agent's AI backend."""
    cfg     = AGENTS[agent_name]
    system  = cfg["persona"]
    prompt  = f"TASK:\n{task}\n\nCONTEXT:\n{context}" if context else f"TASK:\n{task}"

    if cfg["backend"] == "cf":
        return cf_workers_ai(system, prompt, max_tokens)
    if cfg["backend"] == "groq":
        return _call_provider(
            agent_name, GROQ_KEY, _GROQ_URL, "llama-3.3-70b-versatile",
            system, prompt, max_tokens,
        )
    if cfg["backend"] == "openai":
        return _call_provider(
            agent_name, OPENAI_KEY, _OPENAI_URL, "gpt-4o-mini",
            system, prompt, max_tokens,
        )
    return ai(system, prompt, max_tokens)


def deliberate(
    agent_a: str,
    agent_b: str,
    task: str,
    context: str = "",
    max_tokens: int = 450,
) -> str:
    """
    Two-agent deliberation protocol:
      Round 1 — each agent analyses independently
      Round 2 — agent_a reviews agent_b's output, synthesises final answer

    Returns the best synthesised output.
    On provider failures, gracefully degrades to single-agent output.
    """
    pair = AGENTS[agent_a]["pair"]
    console.print(
        f"    [dim magenta]⚡ [{pair.upper()}] "
        f"{agent_a} ↔ {agent_b} deliberating...[/dim magenta]"
    )

    # Round 1: independent analysis
    out_a = agent_call(agent_a, task, context, max_tokens)
    out_b = agent_call(agent_b, task, context, max_tokens)

    if not out_a and not out_b:
        return ai("Expert analyst.", f"{task}\n\nContext:\n{context}", max_tokens)
    if not out_a:
        return out_b
    if not out_b:
        return out_a

    # Round 2: synthesis — agent_a incorporates agent_b's perspective
    synth = agent_call(
        agent_a,
        f"Synthesise the two analyses below into the single best answer.\n\n"
        f"YOUR PREVIOUS ANALYSIS:\n{out_a}\n\n"
        f"PARTNER'S ANALYSIS ({agent_b}):\n{out_b}\n\n"
        f"Merge the valid insights. Return only the final answer, nothing else.",
        context,
        max_tokens,
    )
    return synth or out_a


def _429_wait(response, attempt: int) -> float:
    """Exponential backoff for scraping services (Firecrawl, Tavily)."""
    try:
        ra = response.headers.get("Retry-After")
        if ra:
            return min(float(ra), 60.0)
    except Exception:
        pass
    return min(5 * (2 ** attempt), 60)


def _429_svc_wait(response) -> float:
    """Cap Retry-After at 30s — we'll try the next provider immediately instead."""
    try:
        ra = (response.headers.get("Retry-After")
              or response.headers.get("x-ratelimit-reset-requests"))
        if ra:
            return min(float(ra), 30.0)
    except Exception:
        pass
    return 0.0  # no header — skip to next provider immediately


def ai(system: str, prompt: str, max_tokens: int = 800) -> str:
    """
    Try providers in order. On 429, skip to the next provider immediately.
    If all providers are 429 in a round, wait 30s then retry (up to 3 rounds).
    """
    available = [(n, k, u, m) for n, k, u, m in _PROVIDERS if k]
    if not available:
        return ""

    for round_num in range(3):
        if round_num > 0:
            wait = 30 * round_num
            console.print(f"[yellow]All providers rate-limited — waiting {wait}s[/yellow]")
            time.sleep(wait)

        all_429 = True
        for name, key, url, model in available:
            _ai_throttle()
            try:
                r = httpx.post(
                    url,
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json={
                        "model":      model,
                        "max_tokens": max_tokens,
                        "messages":   [{"role": "system", "content": system},
                                       {"role": "user",   "content": prompt}],
                    },
                    timeout=40,
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
                if r.status_code == 429:
                    w = _429_svc_wait(r)
                    console.print(
                        f"[yellow]{name}: 429 — skipping to next provider"
                        + (f" (Retry-After capped at {w:.0f}s)" if w else "") + "[/yellow]"
                    )
                    if w:
                        time.sleep(w)
                    continue  # immediately try next provider
                all_429 = False
                console.print(f"[yellow]{name}: HTTP {r.status_code}[/yellow]")
            except Exception as e:
                all_429 = False
                console.print(f"[yellow]{name} error: {str(e)[:80]}[/yellow]")

        if not all_429:
            break  # a provider gave a non-429 error — no point retrying

    return ""


def _json_array(text: str) -> list:
    s, e = text.find("["), text.rfind("]") + 1
    if s < 0 or e <= s:
        return []
    try:
        return json.loads(text[s:e])
    except Exception:
        return []


def _json_obj(text: str) -> dict | None:
    s, e = text.find("{"), text.rfind("}") + 1
    if s < 0 or e <= s:
        return None
    try:
        return json.loads(text[s:e])
    except Exception:
        return None

# ── Web Search + Scrape ────────────────────────────────────────────────────────

async def firecrawl_search(query: str, limit: int = 5) -> list[dict]:
    if not FIRECRAWL_KEY:
        return []
    async with httpx.AsyncClient() as c:
        for attempt in range(3):
            try:
                r = await c.post(
                    "https://api.firecrawl.dev/v1/search",
                    headers={"Authorization": f"Bearer {FIRECRAWL_KEY}",
                             "Content-Type": "application/json"},
                    json={"query": query, "limit": limit},
                    timeout=25,
                )
                if r.status_code == 200:
                    return [{"title": x.get("title", ""), "url": x.get("url", ""),
                             "snippet": (x.get("description") or x.get("markdown", ""))[:300]}
                            for x in r.json().get("data", [])[:limit]]
                if r.status_code == 429:
                    wait = _429_wait(r, attempt)
                    console.print(f"[yellow]Firecrawl search 429 — waiting {wait:.0f}s[/yellow]")
                    await asyncio.sleep(wait)
                    continue
                break
            except Exception:
                break
    return []


async def firecrawl_scrape(url: str) -> str:
    if not FIRECRAWL_KEY or not url.startswith("http"):
        return ""
    async with httpx.AsyncClient() as c:
        for attempt in range(3):
            try:
                r = await c.post(
                    "https://api.firecrawl.dev/v1/scrape",
                    headers={"Authorization": f"Bearer {FIRECRAWL_KEY}",
                             "Content-Type": "application/json"},
                    json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
                    timeout=35,
                )
                if r.status_code == 200:
                    return (r.json().get("data", {}).get("markdown") or "")[:8000]
                if r.status_code == 429:
                    wait = _429_wait(r, attempt)
                    console.print(f"[yellow]Firecrawl scrape 429 — waiting {wait:.0f}s[/yellow]")
                    await asyncio.sleep(wait)
                    continue
                break
            except Exception:
                break
    return ""


async def firecrawl_scrape_html(url: str) -> str:
    """Scrape returning raw HTML — needed to extract Google Form entry IDs."""
    if not FIRECRAWL_KEY or not url.startswith("http"):
        return ""
    async with httpx.AsyncClient() as c:
        for attempt in range(3):
            try:
                r = await c.post(
                    "https://api.firecrawl.dev/v1/scrape",
                    headers={"Authorization": f"Bearer {FIRECRAWL_KEY}",
                             "Content-Type": "application/json"},
                    json={"url": url, "formats": ["html"], "onlyMainContent": False},
                    timeout=35,
                )
                if r.status_code == 200:
                    return (r.json().get("data", {}).get("html") or "")[:30000]
                if r.status_code == 429:
                    await asyncio.sleep(_429_wait(r, attempt))
                    continue
                break
            except Exception:
                break
    return ""


async def tavily_search(query: str, limit: int = 5) -> list[dict]:
    if not TAVILY_KEY:
        return []
    async with httpx.AsyncClient() as c:
        for attempt in range(3):
            try:
                r = await c.post(
                    "https://api.tavily.com/search",
                    json={"api_key": TAVILY_KEY, "query": query,
                          "search_depth": "advanced", "max_results": limit},
                    timeout=20,
                )
                if r.status_code == 200:
                    return [{"title": x.get("title", ""), "url": x.get("url", ""),
                             "snippet": x.get("content", "")[:300]}
                            for x in r.json().get("results", [])[:limit]]
                if r.status_code == 429:
                    wait = _429_wait(r, attempt)
                    console.print(f"[yellow]Tavily 429 — waiting {wait:.0f}s[/yellow]")
                    await asyncio.sleep(wait)
                    continue
                break
            except Exception:
                break
    return []


async def web_search(query: str, limit: int = 5) -> list[dict]:
    r = await firecrawl_search(query, limit)
    return r if r else await tavily_search(query, limit)


def _tg_handles(text: str) -> list[str]:
    return [h for h in re.findall(r"t\.me/(\w{3,32})", text)
            if h.lower() not in _SKIP_TG]


def _emails(text: str) -> list[str]:
    skip = {"example.com", "youremail.com", "email.com", "domain.com", "sentry.io"}
    return [e for e in re.findall(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", text)
            if not any(s in e for s in skip)]


def _is_job_board(url: str) -> bool:
    host = urlparse(url).netloc.lstrip("www.")
    return any(d in host for d in JOB_BOARD_DOMAINS)

# ═══════════════════════════════════════════════════════════════════════════════
# X / TWITTER — PRIMARY JOB SOURCE — 10-AGENT PIPELINE
# No API token needed — pure web scraping via Firecrawl + Tavily
# ═══════════════════════════════════════════════════════════════════════════════

# All search terms used by Pair 1 (HUNTERS)
X_SEARCH_TERMS = [
    "web3 crypto hiring community manager ambassador apply DM",
    "blockchain startup hiring community lead moderator remote",
    "AI web3 project hiring community manager content creator",
    "crypto project open role community apply now 2026",
    '"we are hiring" web3 community manager ambassador',
    '"now hiring" web3 blockchain community lead moderator',
    "web3 ambassador program open applications DM apply",
    "crypto startup hiring ecosystem lead growth manager remote",
    "blockchain AI hiring content creator social media manager",
    "web3 dao hiring community moderator contributor apply",
    "#web3jobs community manager ambassador moderator",
    "#cryptojobs hiring community lead content creator",
    "#web3hiring ambassador program apply DM",
    "defi protocol hiring community manager 2026",
    "layer2 blockchain hiring community ambassador open role",
]

X_SITE_QUERIES = [
    'site:twitter.com "web3" "hiring" "community manager" OR "ambassador" 2026',
    'site:twitter.com "blockchain" "we are hiring" community lead moderator',
    'site:twitter.com "AI" "crypto" hiring community manager DM apply',
    'site:twitter.com "ambassador program" web3 crypto open applications',
    'site:twitter.com "open role" web3 community moderator content creator',
    'site:x.com "web3" "hiring" community manager ambassador 2026',
    'site:x.com blockchain startup hiring DM community role remote',
    'site:x.com crypto AI hiring content creator ecosystem lead',
    'site:x.com "now hiring" web3 community moderator ambassador',
    'site:x.com "join our team" web3 blockchain community manager',
]

_NAV_SKIP = {"sign in", "log in", "create account", "trending", "who to follow",
             "privacy policy", "terms of service", "cookie policy", "explore"}
_HIRING_KW = {"hiring", "job", "role", "position", "apply", "dm us", "dm to apply",
              "looking for", "join us", "we need", "open role", "we're hiring",
              "we are hiring", "now hiring", "open position", "join our team"}
_WEB3_KW   = {"web3", "crypto", "blockchain", "defi", "nft", "dao", "token",
              "protocol", "dapp", "layer", "chain", "ai", "ecosystem"}


def _parse_x_blocks(markdown: str, source_url: str) -> list[dict]:
    """Extract tweet-like text blocks from Firecrawl markdown of an X page."""
    chunks = []
    author_m = re.search(r'(?:twitter\.com|x\.com)/(\w{3,30})/', source_url)
    author = author_m.group(1) if author_m else ""
    for block in re.split(r'\n{2,}', markdown):
        block = block.strip()
        if not (30 <= len(block) <= 800):
            continue
        if any(s in block.lower() for s in _NAV_SKIP):
            continue
        ext_urls = [u for u in re.findall(r'https?://[^\s\)\]\"\']+', block)
                    if not any(d in u for d in ("twitter.com", "x.com", "t.co"))]
        chunks.append({
            "text":      block,
            "author":    author,
            "urls":      ext_urls,
            "tweet_url": source_url,
        })
    return chunks


async def x_scrape_search(term: str) -> list[dict]:
    """Scrape x.com/search directly (JS-rendered via Firecrawl)."""
    encoded = re.sub(r'\s+', '%20', term.strip())
    url = f"https://x.com/search?q={encoded}&f=live&src=typed_query"
    page = await firecrawl_scrape(url)
    return _parse_x_blocks(page, url) if page and len(page) > 200 else []


async def x_scrape_profile(handle: str) -> dict:
    """
    Pair 2 (PROFILERS): Scrape an X/Twitter profile for bio, links, team hints.
    Returns structured profile dict.
    """
    handle = handle.lstrip("@").strip()
    url    = f"https://x.com/{handle}"
    page   = await firecrawl_scrape(url)
    if not page:
        return {"handle": handle, "raw": "", "telegram": "", "email": "", "website": ""}

    tg       = _tg_handles(page)
    emails   = _emails(page)
    website  = ""
    for u in re.findall(r'https?://[^\s\)\"\']+', page):
        host = urlparse(u).netloc.lstrip("www.")
        if not any(d in host for d in {"twitter.com", "x.com", "t.co", "bit.ly",
                                        "buff.ly", "ow.ly", "linktr.ee"}):
            website = u
            break

    return {
        "handle":   handle,
        "raw":      page[:3000],
        "telegram": tg[0]     if tg     else "",
        "email":    emails[0] if emails else "",
        "website":  website,
    }


async def x_find_founder_handle(company: str, poster_handle: str) -> str:
    """
    Pair 3 (CONTACT MAPPERS): Find the founder/CEO Twitter handle for a company.
    Searches X + web for the decision maker.
    """
    searches = [
        f'"{company}" founder CEO twitter x.com site:x.com OR site:twitter.com',
        f'{company} web3 founder co-founder twitter handle',
        f'"{company}" "CEO" OR "founder" site:linkedin.com OR site:crunchbase.com twitter',
    ]
    for q in searches:
        results = await web_search(q, limit=5)
        for r in results:
            blob = r.get("url", "") + " " + r.get("snippet", "") + " " + r.get("title", "")
            handles = re.findall(r'(?:twitter\.com|x\.com)/(\w{3,30})(?:/|$|\s)', blob)
            for h in handles:
                _skip = {"search", "hashtag", "intent", "share",
                         "home", "explore", "notifications", poster_handle.lower()}
                if h.lower() not in _skip:
                    return h
    return ""


async def x_collect_raw_leads() -> list[dict]:
    """
    Pair 1 step A (Hunter_Alpha): collect raw tweet data from all X sources.
    Returns deduplicated raw tweet chunks.
    """
    console.print("  [dim cyan][HUNTERS] Scanning X/Twitter across 25 search strategies...[/dim cyan]")
    all_chunks: list[dict] = []
    seen_keys:  set[str]   = set()

    def _add(batch: list[dict]):
        for c in batch:
            key = (c.get("text") or "")[:50]
            if key and key not in seen_keys:
                seen_keys.add(key)
                all_chunks.append(c)

    # Strategy A: direct x.com/search scrape (best quality)
    for term in X_SEARCH_TERMS[:8]:
        batch = await x_scrape_search(term)
        _add(batch)
        await asyncio.sleep(2)

    # Strategy B: site:twitter.com + site:x.com web searches
    for q in X_SITE_QUERIES:
        results = await web_search(q, limit=6)
        for r in results:
            url      = r.get("url", "")
            auth_m   = re.search(r'(?:twitter\.com|x\.com)/(\w+)/', url)
            snippet  = (r.get("snippet") or "") + " " + (r.get("title") or "")
            ext_urls = [u for u in re.findall(r'https?://[^\s\)\"\']+', snippet)
                        if not any(d in u for d in ("twitter.com", "x.com", "t.co"))]
            _add([{
                "text":      snippet.strip(),
                "author":    auth_m.group(1) if auth_m else "",
                "urls":      ext_urls,
                "tweet_url": url,
            }])
        await asyncio.sleep(1.5)

    console.print(f"  [dim]{len(all_chunks)} raw X posts collected[/dim]")
    return all_chunks


async def x_hunter_filter(raw: list[dict]) -> list[dict]:
    """
    Pair 1 deliberation (Hunter_Alpha ↔ Hunter_Beta):
    Both agents review raw leads; Beta filters Alpha's inclusions.
    Returns only high-signal hiring posts.
    """
    # Fast pre-filter: must have both a hiring keyword AND a web3 keyword
    candidates = [
        c for c in raw
        if (c.get("text") and len(c["text"]) >= 30
            and any(kw in c["text"].lower() for kw in _HIRING_KW)
            and any(kw in c["text"].lower() for kw in _WEB3_KW))
    ]
    console.print(f"  [dim]{len(candidates)} posts pass keyword pre-filter[/dim]")

    if not candidates:
        return []

    # Deliberate in batches of 10 to stay within token limits
    approved: list[dict] = []
    batch_size = 10
    for i in range(0, min(len(candidates), 40), batch_size):
        batch = candidates[i:i + batch_size]
        batch_text = "\n---\n".join(
            f"[{j}] @{c.get('author','?')}: {c.get('text','')[:200]}"
            for j, c in enumerate(batch)
        )
        verdict = deliberate(
            "Hunter_Alpha", "Hunter_Beta",
            "Review these X/Twitter posts. Return a JSON array of indices (0-based) "
            "that represent REAL hiring opportunities for Web3/AI community roles. "
            "Keep only posts where a real project is hiring with clear intent. "
            "Return [] if none qualify. Example: [0, 3, 7]",
            batch_text,
            max_tokens=200,
        )
        keep_indices = _json_array(verdict or "")
        for idx in keep_indices:
            if isinstance(idx, int) and 0 <= idx < len(batch):
                approved.append(batch[idx])
        await asyncio.sleep(1)

    console.print(
        f"  [bold cyan][HUNTERS] ✅ {len(approved)} high-signal leads approved[/bold cyan]"
    )
    return approved


async def x_profiler_research(chunk: dict) -> dict | None:
    """
    Pair 2 deliberation (Profiler_Alpha ↔ Profiler_Beta):
    Research the company, score it, extract all contact signals.
    Returns enriched job dict or None if score too low.
    """
    author  = chunk.get("author", "")
    text    = chunk.get("text", "")
    urls    = chunk.get("urls", [])
    src_url = chunk.get("tweet_url", "")

    # Scrape the poster's X profile for bio, links, TG
    profile = {}
    if author:
        profile = await x_scrape_profile(author)

    profile_ctx = (
        f"Poster X handle: @{author}\n"
        f"Tweet text: {text[:400]}\n"
        f"Profile bio/page: {profile.get('raw','')[:600]}\n"
        f"TG found in profile: {profile.get('telegram','')}\n"
        f"Website found: {profile.get('website','')}\n"
        f"Email found: {profile.get('email','')}\n"
        f"External URLs in tweet: {urls[:3]}"
    )

    # Profiler_Alpha: extract structured company intel
    intel_raw = deliberate(
        "Profiler_Alpha", "Profiler_Beta",
        "Extract structured job lead data from this X/Twitter profile. "
        "Return ONLY valid JSON:\n"
        '{"title":"","company":"","description":"","website":"","email":"",'
        '"telegram":"","apply_url":"","score":0,"proceed":true}\n'
        "- title: job role being offered\n"
        "- company: project/startup name\n"
        "- description: what they need (1–2 sentences)\n"
        "- website: project website (not twitter/x)\n"
        "- email: hiring email if visible\n"
        "- telegram: t.me handle if visible\n"
        "- apply_url: Google Form or other apply link if visible\n"
        "- score: relevance 0–100 for Ashiq's profile\n"
        "- proceed: false if score < 45 or dead project\n"
        "Return null if not a real job.",
        f"{profile_ctx}\n\nAshiq's profile:\n{MY_PROFILE[:600]}",
        max_tokens=350,
    )
    if not intel_raw or intel_raw.strip().lower() == "null":
        return None

    result = _json_obj(intel_raw)
    if not result or not result.get("company"):
        return None
    if not result.get("proceed", True):
        score = result.get("score", 0)
        console.print(
            f"  [dim][PROFILERS] ❌ Skipped (score {score}): {result.get('company','?')}[/dim]"
        )
        return None

    # Merge profile data into result
    if not result.get("telegram"):
        result["telegram"] = profile.get("telegram", "")
    if not result.get("website"):
        result["website"]  = profile.get("website", "")
    if not result.get("email"):
        result["email"]    = profile.get("email", "")

    result["poster_handle"] = author
    result["job_url"]       = src_url
    result["source"]        = "x_twitter"
    result.setdefault("title", "Web3 Role")

    console.print(
        f"  [green][PROFILERS] ✅ {result['title']} @ {result['company']} "
        f"(score {result.get('score',0)})[/green]"
    )
    return result


async def x_contact_mapper(job: dict) -> dict:
    """
    Pair 3 deliberation (Contact_Alpha ↔ Contact_Beta):
    Find the founder's Twitter handle, TG group, best outreach channel.
    Returns enriched contact dict merged into job.
    """
    company        = job.get("company", "")
    poster_handle  = job.get("poster_handle", "")
    known_tg       = job.get("telegram", "")
    known_website  = job.get("website", "")

    # Scrape company website for TG link if not already found
    if not known_tg and known_website and known_website.startswith("http"):
        site_page = await firecrawl_scrape(known_website)
        tg_hits   = _tg_handles(site_page)
        if tg_hits:
            known_tg = tg_hits[0]

    # Web search for founder handle if not the poster themselves
    founder_handle = ""
    if company:
        # First try web search for founder
        founder_handle = await x_find_founder_handle(company, poster_handle)

    # Contact pair deliberation: who is the best contact?
    contact_ctx = (
        f"Company: {company}\n"
        f"Job poster's X handle: @{poster_handle}\n"
        f"Found founder handle: @{founder_handle or 'unknown'}\n"
        f"Known TG group: {known_tg or 'none'}\n"
        f"Website: {known_website or 'none'}\n"
        f"Job description: {job.get('description','')[:200]}"
    )
    contact_verdict = deliberate(
        "Contact_Alpha", "Contact_Beta",
        "Determine the best contact strategy for this Web3 job. "
        "Return ONLY valid JSON:\n"
        '{"founder_x":"","tg_group":"","tg_dm_handle":"","best_channel":"tg|email|form","reason":""}\n'
        "- founder_x: best Twitter handle to DM (founder > poster if they differ)\n"
        "- tg_group: Telegram group handle to post in\n"
        "- tg_dm_handle: Telegram handle to DM directly\n"
        "- best_channel: primary apply channel\n"
        "- reason: one sentence",
        contact_ctx,
        max_tokens=200,
    )
    contacts = _json_obj(contact_verdict or "") or {}

    # Merge into job dict
    job["founder_x"]   = contacts.get("founder_x") or founder_handle or poster_handle
    job["telegram"]    = contacts.get("tg_group")   or known_tg
    job["tg_dm"]       = contacts.get("tg_dm_handle", "")
    job["best_channel"]= contacts.get("best_channel", "telegram")

    console.print(
        f"  [dim][CONTACTS] Founder: @{job['founder_x'] or '?'}  "
        f"TG: {job['telegram'] or '—'}  "
        f"Channel: {job['best_channel']}[/dim]"
    )
    return job


async def x_pipeline(tg_client=None) -> list[dict]:
    """
    Full X/Twitter 10-agent job pipeline:
      Pair 1 HUNTERS   → collect + filter raw X posts
      Pair 2 PROFILERS → research each lead, score, extract contacts
      Pair 3 CONTACTS  → find founder + TG group for each lead
    Returns list of enriched, ready-to-apply job dicts.
    """
    console.print(Rule("[bold cyan]X / TWITTER — 10-AGENT PIPELINE[/bold cyan]"))

    # ── Pair 1: HUNTERS — search + filter ────────────────────────────────
    raw    = await x_collect_raw_leads()
    leads  = await x_hunter_filter(raw)

    if not leads:
        console.print("  [yellow][HUNTERS] No qualifying leads found this cycle[/yellow]")
        return []

    # ── Pairs 2 + 3: PROFILERS + CONTACT MAPPERS — per-lead research ─────
    jobs: list[dict] = []
    seen_companies:  set[str] = set()

    for chunk in leads[:25]:
        company_hint = (chunk.get("author") or "")[:30]
        console.print(f"\n  [dim magenta]Processing X lead: @{company_hint}...[/dim magenta]")

        job = await x_profiler_research(chunk)
        if not job:
            continue

        company = job.get("company", "").strip().lower()
        if not company or company in seen_companies:
            continue
        seen_companies.add(company)

        job = await x_contact_mapper(job)
        jobs.append(job)
        await asyncio.sleep(2)

    console.print(
        f"\n  [bold green][X PIPELINE] ✅ {len(jobs)} enriched leads ready for apply[/bold green]"
    )
    return jobs


# ── Phase 1: Extract individual job links from a category/listing page ─────────

def extract_job_links(page_markdown: str, page_url: str) -> list[str]:
    """Pull individual job post URLs from a scraped listing page."""
    base = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"

    # Regex: markdown links [text](url) and bare URLs
    raw_links = re.findall(r'\[(?:[^\]]+)\]\(([^)]+)\)', page_markdown)
    raw_links += re.findall(r'https?://[^\s\)\"\']+', page_markdown)

    seen: set[str] = set()
    job_links: list[str] = []
    for link in raw_links:
        link = link.strip().rstrip(")")
        if not link.startswith("http"):
            link = urljoin(base, link)
        if link in seen:
            continue
        seen.add(link)
        host = urlparse(link).netloc.lstrip("www.")
        path = urlparse(link).path

        # Must be on a job board AND look like an individual posting (has ID or slug in path)
        if not _is_job_board(link):
            continue
        if len(path.strip("/").split("/")) < 2:
            continue  # skip top-level category pages
        # Skip pagination, filters, search pages
        if any(x in link for x in ["?", "#", "/search", "/filter", "/remote-jobs",
                                     "/category", "/tag", "+remote"]):
            continue
        job_links.append(link)

    return job_links[:15]

# ── Phase 2: Scrape individual job page → extract company + website ────────────

async def scrape_job_details(job_url: str) -> dict | None:
    """Visit an individual job posting and extract structured details."""
    console.print(f"    [dim]🔎 Scraping job: {job_url[:70]}[/dim]")
    page = await firecrawl_scrape(job_url)
    if not page or len(page) < 100:
        return None

    raw = ai(
        "Extract job details from this job posting page.\n"
        "Return ONLY valid JSON (no markdown):\n"
        '{"title":"","company":"","description":"","website":"","email":"","telegram":"","apply_url":""}\n'
        "- title: exact job title\n"
        "- company: the hiring company/project name\n"
        "- description: 2-3 sentences about the role requirements\n"
        "- website: the company's own website URL (not the job board URL)\n"
        "- email: hiring email if shown, else empty\n"
        "- telegram: t.me handle or @username if shown, else empty\n"
        "- apply_url: direct application link (Google Form, Typeform, JotForm, "
        "Airtable form, or company careers apply page); empty if none found\n"
        "Return null if this is not a real job posting.",
        f"Job URL: {job_url}\n\nPage content:\n{page[:4000]}",
        max_tokens=450,
    )
    if not raw or raw.strip().lower() == "null":
        return None
    result = _json_obj(raw)
    if not result or not result.get("company"):
        return None
    result["job_url"] = job_url
    return result

# ── Phase 3: Find project's Telegram group ─────────────────────────────────────

async def find_project_tg_group(company: str, website: str) -> str:
    """
    Find the project's Telegram group handle.
    Order: company website → web search for t.me link.
    """
    # 1. Scrape company website
    if website and website.startswith("http"):
        console.print(f"    [dim]🌐 Scraping {website[:60]}...[/dim]")
        page = await firecrawl_scrape(website)
        hits = _tg_handles(page)
        if hits:
            console.print(f"    [green]TG found on website: t.me/{hits[0]}[/green]")
            return hits[0]

    # 2. Web-search for their official TG group
    for query in [
        f'"{company}" telegram group t.me site:t.me OR site:telegram.me',
        f'"{company}" official telegram community t.me',
        f'{company} web3 crypto telegram join 2026',
    ]:
        results = await web_search(query, limit=4)
        for r in results:
            blob = r.get("url", "") + " " + r.get("snippet", "") + " " + r.get("title", "")
            hits = _tg_handles(blob)
            if hits:
                console.print(f"    [green]TG found via search: t.me/{hits[0]}[/green]")
                return hits[0]

    return ""

# ── Phase 4: Join TG group → identify CEO → DM ────────────────────────────────

async def tg_join_group(client, handle: str) -> bool:
    try:
        from pyrogram.errors import UserAlreadyParticipant, FloodWait, InviteHashExpired
        try:
            await client.join_chat(handle)
            return True
        except UserAlreadyParticipant:
            return True
        except FloodWait as fw:
            console.print(f"    [yellow]FloodWait {fw.value}s — waiting...[/yellow]")
            await asyncio.sleep(fw.value + 5)
            return False
        except InviteHashExpired:
            return False
    except Exception as e:
        console.print(f"    [dim red]Join failed: {str(e)[:60]}[/dim red]")
        return False


async def tg_get_admins(client, chat_id: str) -> list[dict]:
    try:
        admins = []
        async for m in client.get_chat_members(chat_id, filter="administrators"):
            u = m.user
            if u and not u.is_bot:
                admins.append({
                    "tg_id":      u.id,
                    "username":   u.username or "",
                    "first_name": u.first_name or "",
                    "is_owner":   m.status.name == "OWNER",
                })
        return admins
    except Exception:
        return []


async def tg_recent_messages(client, chat_id: str, limit: int = 25) -> str:
    try:
        lines = []
        async for msg in client.get_chat_history(chat_id, limit=limit):
            if msg.text:
                who = (getattr(msg.from_user, "username", None) or
                       getattr(msg.from_user, "first_name", "?"))
                lines.append(f"[{who}]: {msg.text[:100]}")
        return "\n".join(lines[:15])
    except Exception:
        return ""


def ai_pick_ceo(project: str, admins: list[dict], room: str) -> dict | None:
    """
    Contact pair deliberation:
    Contact_Alpha identifies the CEO/founder → Contact_Beta validates the pick.
    """
    task = (
        "Identify the CEO, founder, or hiring decision maker from this admin list.\n"
        "Priority: is_owner=true > username/name contains founder/ceo/lead/dev > name matches project.\n"
        "Return ONLY valid JSON (no markdown):\n"
        '{"tg_id":0,"username":"","first_name":"","reason":"","confidence":0}\n'
        "If confidence < 40, return the string: null"
    )
    ctx = (
        f"Project: {project}\n"
        f"Admins:\n{json.dumps(admins, indent=2)}\n\n"
        f"Recent group messages:\n{room[:500]}"
    )

    raw = deliberate("Contact_Alpha", "Contact_Beta", task, ctx, max_tokens=280)
    raw = (raw or "").strip()
    if not raw or raw.lower() in ("null", "none"):
        return None
    result = _json_obj(raw)
    if result and int(result.get("confidence", 0)) >= 40:
        return result
    return None


_JOB_POST_KW = [
    "hiring", "we are hiring", "now hiring", "looking for", "open position",
    "community manager", "ambassador", "moderator", "content creator",
    "social media manager", "apply", "join our team", "open role",
    "community lead", "growth manager", "ecosystem lead",
]


async def find_job_post_in_group(client, chat_id) -> dict | None:
    """Scan recent group messages for the job posting to reply to."""
    try:
        async for msg in client.get_chat_history(chat_id, limit=50):
            if not msg.text:
                continue
            low = msg.text.lower()
            if any(kw in low for kw in _JOB_POST_KW):
                return {
                    "msg_id": msg.id,
                    "text":   msg.text[:200],
                    "sender": (getattr(msg.from_user, "username", None)
                               or getattr(msg.from_user, "first_name", "?")),
                }
    except Exception:
        pass
    return None


async def apply_in_tg_group(client, chat_id, message: str, job_msg_id: int = 0) -> bool:
    """
    Post the application directly in the group.
    Replies to the job posting message if found; otherwise sends as new message.
    """
    try:
        if job_msg_id:
            await client.send_message(chat_id, message, reply_to_message_id=job_msg_id)
            console.print(f"    [bold green]✅ Applied in group (replied to job post)[/bold green]")
        else:
            await client.send_message(chat_id, message)
            console.print(f"    [bold green]✅ Applied in group (new message)[/bold green]")
        return True
    except Exception as e:
        console.print(f"    [dim red]Group post failed: {str(e)[:60]}[/dim red]")
        return False


async def join_and_apply(
    client, company: str, tg_group: str, message: str
) -> tuple[bool, str]:
    """
    Join group → post application in group → DM founder.
    Skips groups we have already posted in (tracked in posted_groups.json).
    Returns (any_success, founder_username_or_empty).
    """
    # Guard: never post in a group we've already applied in
    posted = load_posted_groups()
    group_key = tg_group.lower().lstrip("@")
    if group_key in posted:
        console.print(f"    [dim]Already posted in @{tg_group} — DM only[/dim]")
        group_ok = False
    else:
        console.print(f"    [dim]📡 Joining @{tg_group}...[/dim]")
        if not await tg_join_group(client, tg_group):
            return False, ""

        await asyncio.sleep(3)

        # ── 1. Find and reply to the job post in the group ──────────────────
        job_post = await find_job_post_in_group(client, tg_group)
        group_ok  = await apply_in_tg_group(client, tg_group, message,
                                            job_post["msg_id"] if job_post else 0)
        if group_ok:
            posted.add(group_key)
            save_posted_groups(posted)

    # ── 2. Also DM the founder / owner ──────────────────────────────────────
    founder = ""
    admins  = await tg_get_admins(client, tg_group)
    if admins:
        console.print(f"    [dim]👑 {len(admins)} admins — finding decision maker...[/dim]")
        room   = await tg_recent_messages(client, tg_group)
        target = ai_pick_ceo(company, admins, room)

        if not target:
            owner = next((a for a in admins if a.get("is_owner") and a.get("username")), None)
            if owner:
                target = {**owner, "reason": "group owner", "confidence": 65}

        if target and target.get("username"):
            uname = target["username"]
            fname = target.get("first_name", uname)
            conf  = target.get("confidence", 0)
            console.print(
                f"    [green]Founder: {fname} (@{uname}) — {conf}% "
                f"[dim]{target.get('reason','')[:50]}[/dim][/green]"
            )
            try:
                await client.send_message(f"@{uname}", message)
                console.print(f"    [bold green]✅ DM sent → @{uname}[/bold green]")
                founder = uname
            except Exception as e:
                console.print(f"    [dim]DM failed: {str(e)[:50]}[/dim]")
        else:
            console.print("    [dim]No identifiable founder — group post only[/dim]")
    else:
        console.print("    [dim]No admins accessible — group post only[/dim]")

    return group_ok or bool(founder), founder


# ── Scan already-joined groups for job posts ──────────────────────────────────

async def scan_joined_groups_for_jobs(client) -> list[dict]:
    """
    Scan Telegram groups the user is already a member of for hiring posts.
    Returns pre-structured job dicts ready for the apply pipeline.
    """
    console.print("[dim]Scanning joined TG groups for job posts...[/dim]")
    jobs: list[dict] = []
    seen: set[str]   = set()

    try:
        async for dialog in client.get_dialogs():
            chat = dialog.chat
            if not chat or chat.type.name not in ("GROUP", "SUPERGROUP"):
                continue
            chat_id  = chat.id
            chat_tag = chat.username or str(chat_id)
            try:
                async for msg in client.get_chat_history(chat_id, limit=40):
                    if not msg.text:
                        continue
                    low = msg.text.lower()
                    if not any(kw in low for kw in _JOB_POST_KW):
                        continue
                    key = f"{chat_id}:{msg.id}"
                    if key in seen:
                        continue
                    seen.add(key)
                    jobs.append({
                        "company":     chat.title or chat_tag,
                        "title":       "Web3 Role",
                        "description": msg.text[:400],
                        "tg_group":    chat_tag,
                        "chat_id":     chat_id,
                        "msg_id":      msg.id,
                        "website":     "",
                        "email":       "",
                        "apply_url":   "",
                        "job_url":     f"https://t.me/{chat_tag}/{msg.id}" if chat.username else "",
                        "source":      "tg_group_scan",
                    })
                    break  # one job post per group is enough
            except Exception:
                pass
            await asyncio.sleep(0.2)
    except Exception as e:
        console.print(f"[dim red]Group scan error: {str(e)[:60]}[/dim red]")

    console.print(f"  [cyan]→ {len(jobs)} job posts found in joined groups[/cyan]")
    return jobs

# ── Web Form Application ──────────────────────────────────────────────────────

_FORM_HOSTS = {
    "docs.google.com", "forms.gle",            # Google Forms
    "typeform.com",                             # Typeform
    "jotform.com",                              # JotForm
    "airtable.com",                             # Airtable forms
    "tally.so",                                 # Tally
    "forms.office.com", "microsoft.com",        # Microsoft Forms
}


def _is_form_url(url: str) -> bool:
    host = urlparse(url).netloc.lstrip("www.")
    return any(d in host for d in _FORM_HOSTS) or "form" in urlparse(url).path.lower()


async def apply_via_google_form(form_url: str, job: dict, msg: str) -> bool:
    """
    Fill and submit a Google Form application.
    Scrapes the form HTML to extract entry IDs, uses AI to generate answers,
    then POSTs to the formResponse endpoint.
    """
    if not any(d in form_url for d in ("docs.google.com/forms", "forms.gle")):
        return False

    console.print(f"    [dim]📋 Google Form detected — scraping fields...[/dim]")
    markdown = await firecrawl_scrape(form_url)
    html     = await firecrawl_scrape_html(form_url)
    if not markdown and not html:
        return False

    # Extract entry IDs from the raw HTML (Google Forms stores them as entry.XXXXXXXXX)
    entry_ids = list(dict.fromkeys(re.findall(r'entry\.(\d{7,})', html or "")))
    if not entry_ids:
        console.print("    [dim yellow]Google Form: no entry IDs found — skipping[/dim yellow]")
        return False

    console.print(f"    [dim]{len(entry_ids)} form fields found[/dim]")

    raw = ai(
        "Fill a Google Form job application. Return ONLY valid JSON — no markdown.\n"
        f"APPLICANT PROFILE:\n{MY_PROFILE}\n\n"
        "JSON format — keys are the numeric entry IDs, values are the answers:\n"
        '{"ENTRY_ID": "answer", ...}\n\n'
        "Field mapping rules:\n"
        "- Full name / your name      → 'Ashiq'\n"
        f"- Email                      → '{MY_EMAIL}'\n"
        "- Telegram handle            → '@ashiq80'\n"
        "- Twitter / X handle         → '@Ganaie__suhail'\n"
        "- Discord                    → 'ashiq1581'\n"
        "- LinkedIn                   → 'https://linkedin.com/in/ashiq-ah-705334395'\n"
        "- Portfolio / social links   → 'https://twitter.com/Ganaie__suhail'\n"
        "- Location / country         → 'Kashmir, India'\n"
        "- Remote / in-person         → 'Remote'\n"
        "- Availability / start date  → 'Immediately'\n"
        "- Salary / rate              → 'Negotiable / open to token-based'\n"
        "- Languages                  → 'English, Hindi, Urdu, Kashmiri'\n"
        "- Education                  → 'B.Tech, Kashmir University (2019–2023)'\n"
        "- Years of experience        → '3+ years'\n"
        "- Cover letter / why us / motivation → use the provided message verbatim\n"
        "- Skills / experience fields → draw from PROFILE above\n"
        "Use only the entry IDs listed. Return null if you cannot map the fields.",
        f"Job: {job.get('title')} at {job.get('company')}\n"
        f"Entry IDs (in order they appear in the form): {entry_ids}\n\n"
        f"Form questions (readable content):\n{markdown[:2500]}\n\n"
        f"Cover letter / application message:\n{msg}",
        max_tokens=700,
    )
    if not raw or raw.strip().lower() == "null":
        return False

    answers = _json_obj(raw)
    if not answers:
        return False

    # Resolve short form URL (forms.gle redirect) before extracting form ID
    resolved_url = form_url
    if "forms.gle" in form_url:
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(form_url, follow_redirects=True, timeout=10)
                resolved_url = str(r.url)
        except Exception:
            pass

    form_id_m = re.search(r'/forms/d/e?/([a-zA-Z0-9_-]{20,})', resolved_url)
    if not form_id_m:
        # fallback: try original URL
        form_id_m = re.search(r'/forms/d/e?/([a-zA-Z0-9_-]{20,})', form_url)
    if not form_id_m:
        console.print("    [dim yellow]Could not extract Google Form ID[/dim yellow]")
        return False

    form_id    = form_id_m.group(1)
    submit_url = f"https://docs.google.com/forms/d/{form_id}/formResponse"
    payload    = {f"entry.{eid}": str(ans) for eid, ans in answers.items() if ans}

    if not payload:
        return False

    async with httpx.AsyncClient() as c:
        try:
            r = await c.post(
                submit_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                follow_redirects=True,
                timeout=30,
            )
            body = r.text.lower()
            if r.status_code in (200, 302) and any(
                kw in body for kw in ("thank", "submitted", "response recorded", "recorded")
            ):
                console.print(
                    f"    [bold green]✅ Google Form submitted — {len(payload)} fields[/bold green]"
                )
                return True
            # A redirect back to viewform also usually means success
            if "formresponse" in str(r.url).lower() or r.status_code == 302:
                console.print(
                    f"    [bold green]✅ Google Form submitted (redirect)[/bold green]"
                )
                return True
            console.print(f"    [dim]Form response: {r.status_code}[/dim]")
        except Exception as e:
            console.print(f"    [dim red]Form submit error: {str(e)[:60]}[/dim red]")

    return False


async def apply_via_web_form(apply_url: str, job: dict, msg: str) -> bool:
    """
    Generic web-form application: detect type, route to the right handler.
    Supports Google Forms; logs others for manual follow-up.
    """
    if not apply_url or not apply_url.startswith("http"):
        return False

    host = urlparse(apply_url).netloc.lstrip("www.")

    if "docs.google.com" in host or "forms.gle" in host:
        return await apply_via_google_form(apply_url, job, msg)

    # Typeform / JotForm / Tally / Airtable — log URL, apply manually
    for known in ("typeform.com", "jotform.com", "tally.so", "airtable.com",
                  "forms.office.com"):
        if known in host:
            console.print(
                f"    [yellow]📋 {known} form — manual apply needed: {apply_url[:80]}[/yellow]"
            )
            return False

    # Generic: try to detect a form in the page and extract apply email/link
    console.print(f"    [dim]Checking {apply_url[:60]} for apply form...[/dim]")
    page = await firecrawl_scrape(apply_url)
    if page:
        emails = _emails(page)
        if emails:
            console.print(f"    [dim]Found email on apply page: {emails[0]}[/dim]")
            # Let the email fallback in job_cycle handle it
        forms = re.findall(r'docs\.google\.com/forms/[^\s\)\"\']+', page)
        if forms:
            return await apply_via_google_form("https://" + forms[0].lstrip("/"), job, msg)

    return False


# ── Application Crafting ───────────────────────────────────────────────────────

def craft_application(job: dict) -> str:
    """
    Strategy pair deliberation:
    Strategy_Alpha (CF Workers AI) drafts → Strategy_Beta (OpenAI) sharpens.
    Falls back to single ai() call if both providers fail.
    """
    source = job.get("source", "")
    style  = "Telegram DM" if source != "email" else "email"

    task = (
        f"Write a short {style} from Ashiq applying for this Web3/AI job.\n\n"
        f"PROFILE:\n{MY_PROFILE}\n\n"
        "RULES:\n"
        "- MAX 3 sentences\n"
        "- Sentence 1: something SPECIFIC about the project (never 'I saw your listing')\n"
        "- Sentence 2: ONE concrete matching stat (16k followers for SM, "
        "6k community for CM, annotation/AI skills for AI roles)\n"
        "- Sentence 3: ONE sharp specific question (not 'are you hiring?')\n"
        "- NO emojis, NO 'Dear', NO 'Hi there!', NO generic openers\n"
        "- Sign off exactly: Ashiq | @ashiq80 | naveeddurfi@gmail.com\n"
        "- Return ONLY the final message text, nothing else"
    )
    ctx = (
        f"Job title  : {job.get('title', 'role')}\n"
        f"Company    : {job.get('company', 'project')}\n"
        f"Description: {job.get('description', '')[:400]}"
    )

    # Strategy_Alpha drafts, Strategy_Beta sharpens via deliberation
    result = deliberate("Strategy_Alpha", "Strategy_Beta", task, ctx, max_tokens=250)
    if result and len(result) > 20 and not result.startswith("["):
        return result

    # Fallback to single ai() call
    return ai(
        f"Write a short {style} from Ashiq applying for a Web3/AI job.\n\n"
        f"ASHIQ'S FULL PROFILE:\n{MY_PROFILE}\n\n"
        "MAX 3 sentences. Be specific, not generic. "
        "Sign off: Ashiq | @ashiq80 | naveeddurri@gmail.com\n"
        "Return ONLY the message.",
        f"Job: {job.get('title','role')} at {job.get('company','project')}\n"
        f"Description: {job.get('description','')[:300]}",
        max_tokens=220,
    )

# ── Email Fallback ─────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, body: str) -> bool:
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, to]):
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"]    = SMTP_USER
        msg["To"]      = to
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as srv:
            srv.starttls()
            srv.login(SMTP_USER, SMTP_PASS)
            srv.sendmail(SMTP_USER, to, msg.as_string())
        return True
    except Exception as e:
        console.print(f"    [red]Email error: {e}[/red]")
        return False

# ── CF KV — cloud state persistence ───────────────────────────────────────────

def _cf_kv_headers() -> dict:
    return {"X-Auth-Email": _CF_EMAIL, "X-Auth-Key": _CF_GLOBAL_KEY}


def cf_kv_get(key: str) -> str | None:
    """Read from CF KV (returns None on miss or error)."""
    if not _CF_KV_NS:
        return None
    try:
        r = httpx.get(
            f"https://api.cloudflare.com/client/v4/accounts/{_CF_ACCOUNT_ID}"
            f"/storage/kv/namespaces/{_CF_KV_NS}/values/{key}",
            headers=_cf_kv_headers(),
            timeout=10,
        )
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None


def cf_kv_put(key: str, value: str) -> bool:
    """Write to CF KV (best-effort, does not block on failure)."""
    if not _CF_KV_NS:
        return False
    try:
        r = httpx.put(
            f"https://api.cloudflare.com/client/v4/accounts/{_CF_ACCOUNT_ID}"
            f"/storage/kv/namespaces/{_CF_KV_NS}/values/{key}",
            headers={**_cf_kv_headers(), "Content-Type": "text/plain"},
            content=value.encode(),
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False


# ── State ──────────────────────────────────────────────────────────────────────

def load_applied() -> dict:
    # Primary: CF KV (survives device restarts, syncs across devices)
    kv = cf_kv_get("applied_jobs")
    if kv:
        try:
            return json.loads(kv)
        except Exception:
            pass
    # Fallback: local JSON file
    if APPLIED_FILE.exists():
        try:
            return json.loads(APPLIED_FILE.read_text())
        except Exception:
            pass
    return {}


def save_applied(data: dict):
    serialized = json.dumps(data, indent=2, ensure_ascii=False)
    cf_kv_put("applied_jobs", serialized)   # cloud (best-effort)
    APPLIED_FILE.write_text(serialized)      # local backup


def load_posted_groups() -> set:
    kv = cf_kv_get("posted_groups")
    if kv:
        try:
            return set(json.loads(kv))
        except Exception:
            pass
    if POSTED_GROUPS_FILE.exists():
        try:
            return set(json.loads(POSTED_GROUPS_FILE.read_text()))
        except Exception:
            pass
    return set()


def save_posted_groups(groups: set):
    serialized = json.dumps(sorted(groups), indent=2)
    cf_kv_put("posted_groups", serialized)
    POSTED_GROUPS_FILE.write_text(serialized)


def load_target_groups() -> list[str]:
    """Load user-specified groups to always check for jobs. Edit target_groups.json to add more."""
    if TARGET_GROUPS_FILE.exists():
        try:
            return json.loads(TARGET_GROUPS_FILE.read_text())
        except Exception:
            pass
    # Default — write the file on first run so user can edit it
    defaults = ["Alturax"]
    TARGET_GROUPS_FILE.write_text(json.dumps(defaults, indent=2))
    return defaults

# ── Core Cycle ─────────────────────────────────────────────────────────────────

async def job_cycle(tg_client=None) -> int:
    applied_db = load_applied()
    total_sent = 0

    # ── Step 1: Search job boards → get category/listing pages ───────────────
    console.print("[dim]Step 1: Searching job boards...[/dim]")
    listing_urls: list[str] = []
    for q in JOB_QUERIES:
        results = await web_search(q, limit=4)
        for r in results:
            url = r.get("url", "")
            if url and _is_job_board(url):
                listing_urls.append(url)
        await asyncio.sleep(0.5)

    listing_urls = list(dict.fromkeys(listing_urls))  # dedupe
    console.print(f"  [dim]{len(listing_urls)} listing pages found[/dim]")

    # ── Step 2: Extract individual job post URLs from listing pages ───────────
    console.print("[dim]Step 2: Extracting individual job links...[/dim]")
    job_post_urls: list[str] = []
    for listing_url in listing_urls[:10]:
        page = await firecrawl_scrape(listing_url)
        if not page:
            continue
        links = extract_job_links(page, listing_url)
        job_post_urls.extend(links)
        await asyncio.sleep(0.3)

    job_post_urls = list(dict.fromkeys(job_post_urls))
    console.print(f"  [cyan]→ {len(job_post_urls)} individual job posts found[/cyan]")

    if not job_post_urls:
        console.print("[yellow]No individual job posts found — check search results[/yellow]")
        return 0

    # ── Step 2b: X/Twitter — PRIMARY source — full 10-agent pipeline ────────────
    x_jobs = await x_pipeline(tg_client)
    console.print(f"  [cyan]→ {len(x_jobs)} X leads fully enriched and ready[/cyan]")

    # ── Step 2c: Scout pair filters job list ─────────────────────────────────
    if job_post_urls:
        console.print("[dim]Step 2c: Hunter pair filtering job list...[/dim]")
        scout_verdict = deliberate(
            "Hunter_Alpha", "Hunter_Beta",
            "Review this list of job URLs. Return only URLs that are INDIVIDUAL job postings "
            "for community manager, ambassador, moderator, content creator, or AI roles. "
            "Remove job board homepages, category pages, and non-Web3 roles. "
            "Return a JSON array of URLs to keep, nothing else.",
            "\n".join(job_post_urls[:20]),
            max_tokens=600,
        )
        filtered = _json_array(scout_verdict)
        if filtered:
            job_post_urls = filtered
            console.print(f"  [cyan]→ Scouts approved {len(job_post_urls)} URLs[/cyan]")

    # ── Step 3-6: Process job-board posts (scrape then apply) ────────────────
    console.print("[dim]Step 3-6: Processing job-board posts...[/dim]")
    for job_url in job_post_urls[:20]:
        # Step 3: Scrape job page → get company + website
        job = await scrape_job_details(job_url)
        if not job:
            continue

        company   = job.get("company", "").strip()
        title     = job.get("title", "").strip()
        website   = job.get("website", "").strip()
        email     = job.get("email", "").strip()
        tg_raw    = job.get("telegram", "").strip()
        apply_url = job.get("apply_url", "").strip()

        if not company or not title:
            continue

        job_key = f"{company.lower()}::{title.lower()}"
        if job_key in applied_db:
            console.print(f"  [dim]Skip (done): {title} @ {company}[/dim]")
            continue

        console.print(f"\n  [bold magenta]◆ {title}[/bold magenta]  [cyan]{company}[/cyan]")
        console.print(
            f"    [dim]Website: {website or '—'}  "
            f"Form: {apply_url[:50] if apply_url else '—'}[/dim]"
        )

        # Profiler pair: score relevance before investing more resources
        research = deliberate(
            "Profiler_Alpha", "Profiler_Beta",
            "Score this job opportunity 0–100 for Ashiq's profile. "
            "Return ONLY valid JSON: "
            '{"score":0,"reason":"","proceed":true}. '
            "Set proceed=false if score < 45.",
            f"Title: {title}\nCompany: {company}\n"
            f"Description: {job.get('description','')[:600]}\n"
            f"Website: {website}\nApply URL: {apply_url}\n\n"
            f"Ashiq's profile:\n{MY_PROFILE}",
            max_tokens=200,
        )
        score_obj = _json_obj(research or "")
        if score_obj:
            score = score_obj.get("score", 50)
            proceed = score_obj.get("proceed", True)
            reason  = score_obj.get("reason", "")
            console.print(
                f"    [dim][RESEARCHERS] Score: {score}/100  "
                f"{'✅ proceed' if proceed else '❌ skip'}  — {reason[:60]}[/dim]"
            )
            if not proceed:
                continue

        # Step 4: Find TG group (website → web search)
        tg_group = tg_raw.lstrip("@").replace("t.me/", "").strip()
        if not tg_group:
            tg_group = await find_project_tg_group(company, website)

        # Scrape website for email / form links if missing
        if (not email or not apply_url) and website:
            page = await firecrawl_scrape(website)
            if not email:
                found_emails = _emails(page)
                if found_emails:
                    email = found_emails[0]
            if not apply_url:
                gforms = re.findall(r'https?://(?:docs\.google\.com/forms|forms\.gle)/[^\s\)\"\']+', page)
                if gforms:
                    apply_url = gforms[0]

        console.print(
            f"    [dim]TG: {'@'+tg_group if tg_group else '—'}  "
            f"Email: {email or '—'}  "
            f"Form: {'yes' if apply_url else '—'}[/dim]"
        )

        # Craft application
        msg = craft_application(job)
        if not msg or len(msg) < 20 or msg.startswith("["):
            console.print("    [yellow]AI failed to write application — skipping[/yellow]")
            continue

        console.print(f'    [dim italic]"{msg[:120]}..."[/dim italic]')

        # Exec pair QA — approve before sending
        exec_qa = deliberate(
            "Exec_Alpha", "Exec_Beta",
            "Review this job application message for quality and accuracy. "
            "Return ONLY JSON: "
            '{"approved":true,"channel":"form|telegram|email","note":""}. '
            "Approve if professional, specific, and represents Ashiq accurately. "
            f"Available channels: "
            f"{'form ' if apply_url else ''}"
            f"{'telegram ' if tg_group else ''}"
            f"{'email' if email else ''}",
            f"Message:\n{msg}\n\nJob: {title} @ {company}",
            max_tokens=150,
        )
        qa_obj = _json_obj(exec_qa or "")
        if qa_obj and not qa_obj.get("approved", True):
            console.print(
                f"    [yellow][EXECUTORS] QA rejected: {qa_obj.get('note','')[:60]}[/yellow]"
            )
            # Attempt one revision via craft_application
            msg = craft_application(job)
            if not msg or len(msg) < 20:
                continue

        sent_via = ""
        founder  = ""

        # Priority 1: Web form (Google Form etc.)
        if apply_url and _is_form_url(apply_url):
            ok = await apply_via_web_form(apply_url, job, msg)
            if ok:
                sent_via = f"web_form:{apply_url[:60]}"
                total_sent += 1

        # Priority 2: Telegram DM to founder
        if not sent_via and tg_group and tg_client:
            ok, founder = await join_and_apply(tg_client, company, tg_group, msg)
            if ok:
                sent_via = f"telegram_dm:@{founder} (via @{tg_group})"
                total_sent += 1
                await asyncio.sleep(15)

        # Priority 3: Email
        if not sent_via and email:
            ok = send_email(
                email,
                f"Application — {title} | Ashiq (@ashiq80)",
                msg,
            )
            if ok:
                sent_via = f"email:{email}"
                console.print(f"    [bold green]✅ Email → {email}[/bold green]")
                total_sent += 1

        if not sent_via:
            contact = (f"@{tg_group}" if tg_group else email) or "not found"
            console.print(f"    [yellow]📋 Logged — apply manually: {contact}[/yellow]")

        applied_db[job_key] = {
            "title":    title,
            "company":  company,
            "job_url":  job_url,
            "website":  website,
            "tg_group": tg_group,
            "founder":  founder,
            "message":  msg,
            "sent_via": sent_via or "manual",
            "ts":       datetime.now().isoformat(),
        }
        save_applied(applied_db)

    # ── Step 6b: Apply to X/Twitter leads (Pairs 4 + 5: STRATEGISTS + EXECUTORS) ─
    if x_jobs:
        console.print(Rule("[bold cyan]X / TWITTER LEADS — APPLYING[/bold cyan]"))
    for job in x_jobs:
        company   = job.get("company", "").strip()
        title     = job.get("title", "Web3 Role").strip()
        website   = job.get("website", "").strip()
        email     = job.get("email", "").strip()
        apply_url = job.get("apply_url", "").strip()
        job_url   = job.get("job_url", "")
        tg_group  = (job.get("telegram") or "").lstrip("@").replace("t.me/", "").strip()
        founder_x = job.get("founder_x", "")

        if not company:
            continue

        job_key = f"x::{company.lower()}::{title.lower()}"
        if job_key in applied_db:
            console.print(f"  [dim]Skip (done): {title} @ {company}[/dim]")
            continue

        console.print(
            f"\n  [bold magenta]◆ {title}[/bold magenta]  [cyan]{company}[/cyan]"
            f"  [dim yellow][@{job.get('poster_handle','?')} on X][/dim yellow]"
        )
        console.print(
            f"    [dim]TG: {'@'+tg_group if tg_group else '—'}  "
            f"Founder X: {'@'+founder_x if founder_x else '—'}  "
            f"Form: {'yes' if apply_url else '—'}[/dim]"
        )

        # Scrape website for email / form links if still missing
        if (not email or not apply_url) and website:
            page = await firecrawl_scrape(website)
            if not email:
                found_emails = _emails(page)
                if found_emails:
                    email = found_emails[0]
            if not apply_url:
                gforms = re.findall(
                    r'https?://(?:docs\.google\.com/forms|forms\.gle)/[^\s\)\"\']+', page
                )
                if gforms:
                    apply_url = gforms[0]

        # If still no TG group, try web search
        if not tg_group:
            tg_group = await find_project_tg_group(company, website)

        # Pair 4 STRATEGISTS: craft the application message
        msg = craft_application(job)
        if not msg or len(msg) < 20 or msg.startswith("["):
            console.print("    [yellow][STRATEGISTS] Could not craft message — skipping[/yellow]")
            continue

        console.print(f'    [dim italic]"{msg[:120]}..."[/dim italic]')

        # Pair 5 EXECUTORS: QA then execute
        exec_qa = deliberate(
            "Exec_Alpha", "Exec_Beta",
            "Review this application message. Return ONLY JSON: "
            '{"approved":true,"note":""}. '
            "Approve if it is professional, specific, and represents Ashiq accurately.",
            f"Message:\n{msg}\n\nJob: {title} @ {company}",
            max_tokens=120,
        )
        qa_obj = _json_obj(exec_qa or "")
        if qa_obj and not qa_obj.get("approved", True):
            console.print(
                f"    [yellow][EXECUTORS] QA revision: {qa_obj.get('note','')[:60]}[/yellow]"
            )
            msg = craft_application(job)
            if not msg or len(msg) < 20:
                continue

        sent_via = ""
        founder  = ""

        # Priority 1: Web form (Google Form etc.)
        if apply_url and _is_form_url(apply_url):
            ok = await apply_via_web_form(apply_url, job, msg)
            if ok:
                sent_via = f"web_form:{apply_url[:60]}"
                total_sent += 1

        # Priority 2: TG group post + founder DM
        if not sent_via and tg_group and tg_client:
            ok, founder = await join_and_apply(tg_client, company, tg_group, msg)
            if ok:
                sent_via = f"telegram:@{founder or tg_group}"
                total_sent += 1
                await asyncio.sleep(15)

        # Priority 3: Email fallback
        if not sent_via and email:
            ok = send_email(
                email,
                f"Application — {title} | Ashiq (@ashiq80)",
                msg,
            )
            if ok:
                sent_via = f"email:{email}"
                console.print(f"    [bold green]✅ Email → {email}[/bold green]")
                total_sent += 1

        if not sent_via:
            contact = (f"@{tg_group}" if tg_group else email) or job_url or "not found"
            console.print(f"    [yellow]📋 Manual apply: {contact}[/yellow]")

        applied_db[job_key] = {
            "title":      title,
            "company":    company,
            "job_url":    job_url,
            "website":    website,
            "tg_group":   tg_group,
            "founder_x":  founder_x,
            "founder_tg": founder,
            "message":    msg,
            "sent_via":   sent_via or "manual",
            "source":     "x_twitter",
            "ts":         datetime.now().isoformat(),
        }
        save_applied(applied_db)

    # ── Target groups: user-specified groups to always check for job posts ────
    if tg_client:
        target_groups = load_target_groups()
        if target_groups:
            console.print(Rule("[bold]TARGET GROUPS[/bold]"))
        for handle in target_groups:
            handle = handle.lstrip("@").strip()
            if not handle:
                continue

            posted = load_posted_groups()
            group_key = handle.lower()

            console.print(f"\n  [bold cyan]◆ Target group: @{handle}[/bold cyan]")

            # Join if not already a member
            joined = await tg_join_group(tg_client, handle)
            if not joined:
                console.print(f"    [yellow]Could not join @{handle}[/yellow]")
                continue

            await asyncio.sleep(2)

            # Find the job post to reply to
            job_post = await find_job_post_in_group(tg_client, handle)

            if not job_post:
                console.print(f"    [dim]No hiring post found in @{handle} — skipping[/dim]")
                continue

            console.print(
                f"    [dim]Job post found: \"{job_post['text'][:80]}...\"[/dim]"
            )

            # Build a minimal job dict from the post text
            job = {
                "title":       "Web3 Role",
                "company":     handle,
                "description": job_post["text"],
                "source":      "target_group",
            }

            job_key = f"target::{handle.lower()}::{job_post['msg_id']}"
            if job_key in applied_db:
                console.print(f"    [dim]Already applied to this post — skipping[/dim]")
                continue

            msg = craft_application(job)
            if not msg or len(msg) < 20:
                console.print("    [yellow]AI failed to write message — skipping[/yellow]")
                continue

            console.print(f'    [dim italic]"{msg[:120]}..."[/dim italic]')

            if group_key in posted:
                console.print(f"    [dim]Already posted in @{handle} before — DM only[/dim]")
                group_ok = False
            else:
                group_ok = await apply_in_tg_group(
                    tg_client, handle, msg, job_post["msg_id"]
                )
                if group_ok:
                    posted.add(group_key)
                    save_posted_groups(posted)
                    total_sent += 1
                    await asyncio.sleep(10)

            # Also DM the founder/owner
            admins = await tg_get_admins(tg_client, handle)
            if admins:
                room   = await tg_recent_messages(tg_client, handle)
                target = ai_pick_ceo(handle, admins, room)
                if not target:
                    owner = next((a for a in admins if a.get("is_owner") and a.get("username")), None)
                    if owner:
                        target = {**owner, "reason": "group owner", "confidence": 65}
                if target and target.get("username"):
                    uname = target["username"]
                    try:
                        await tg_client.send_message(f"@{uname}", msg)
                        console.print(f"    [bold green]✅ DM → @{uname}[/bold green]")
                        if not group_ok:
                            total_sent += 1
                    except Exception as e:
                        console.print(f"    [dim]DM failed: {str(e)[:50]}[/dim]")

            applied_db[job_key] = {
                "title":    "Web3 Role",
                "company":  handle,
                "tg_group": handle,
                "msg_id":   job_post["msg_id"],
                "message":  msg,
                "sent_via": f"target_group:@{handle}",
                "source":   "target_group",
                "ts":       datetime.now().isoformat(),
            }
            save_applied(applied_db)

    return total_sent

# ── Main Loop ──────────────────────────────────────────────────────────────────

async def main():
    cf_ai_ok = "✅ llama-3.3-70b free" if _CF_GLOBAL_KEY else "❌ set CF_GLOBAL_KEY"
    cf_kv_ok = "✅ cloud" if _CF_KV_NS else "❌ local only"
    console.print(Panel(
        "[bold cyan]🤖  X-FOCUSED 10-AGENT JOB SYSTEM — ONLINE[/bold cyan]\n\n"
        "[bold]X / Twitter Pipeline (PRIMARY SOURCE):[/bold]\n"
        "  Pair 1  HUNTERS    Hunt_α (Groq)      ↔ Hunt_β (CF AI)    — search + filter\n"
        "  Pair 2  PROFILERS  Profile_α (OpenAI)  ↔ Profile_β (Groq)  — company research\n"
        "  Pair 3  CONTACTS   Contact_α (CF AI)   ↔ Contact_β (Groq)  — find founder + TG\n"
        "  Pair 4  STRATEGY   Strategy_α (Groq)   ↔ Strategy_β (OpenAI)— craft message\n"
        "  Pair 5  EXECUTORS  Exec_α (OpenAI)     ↔ Exec_β (CF AI)    — QA + apply\n\n"
        "[bold]AI Backends:[/bold]\n"
        f"  Groq        : {'✅ llama-3.3-70b via CF Gateway' if GROQ_KEY else '❌'}\n"
        f"  OpenAI      : {'✅ gpt-4o-mini via CF Gateway' if OPENAI_KEY else '❌'}\n"
        f"  CF Workers  : {cf_ai_ok}\n\n"
        "[bold]CF Services:[/bold]\n"
        f"  AI Gateway  : ✅ proxy + 60-min response cache\n"
        f"  KV State    : {cf_kv_ok} (applied_jobs + posted_groups)\n\n"
        "[bold]Apply Channels:[/bold]\n"
        f"  Scraping    : Firecrawl {'✅' if FIRECRAWL_KEY else '❌'} | Tavily {'✅' if TAVILY_KEY else '❌'}\n"
        f"  Telegram    : {'✅ DMs + group posts' if TG_API_ID and TG_API_HASH else '❌ set TG credentials'}\n"
        f"  Email       : {'✅ ' + SMTP_USER if SMTP_USER else '❌ not configured'}\n\n"
        "Flow: X scrape (25 terms) → Hunter pair filter → Profiler pair score\n"
        "    → Contact pair maps founder+TG → Strategy pair crafts DM\n"
        "    → Exec pair QA → apply: Google Form → TG group+DM → email\n\n"
        f"Interval : every {SEARCH_EVERY_HOURS}h  |  Tracked : {len(load_applied())} jobs",
        border_style="cyan",
    ))

    tg_client = None
    if TG_API_ID and TG_API_HASH:
        session_path = Path(f"{SESSION_NAME}.session")
        if session_path.exists():
            try:
                from pyrogram import Client
                tg_client = Client(
                    SESSION_NAME,
                    api_id=TG_API_ID,
                    api_hash=TG_API_HASH,
                    phone_number=TG_PHONE,
                )
                await tg_client.start()
                me = await tg_client.get_me()
                console.print(
                    f"[green]✅ Telegram: {me.first_name} (@{me.username}) — DMs enabled[/green]"
                )
            except Exception as e:
                console.print(f"[yellow]TG client failed ({e}) — logging only[/yellow]")
                tg_client = None
        else:
            console.print(f"[yellow]No {SESSION_NAME}.session — TG DMs disabled[/yellow]")

    cycle = 0
    try:
        while True:
            cycle += 1
            console.print(Rule(
                f"[bold]CYCLE {cycle} — {datetime.now().strftime('%H:%M  %d %b %Y')}[/bold]"
            ))
            try:
                sent    = await job_cycle(tg_client)
                tracked = len(load_applied())
                console.print(
                    f"\n[bold green]✅ Cycle {cycle} done — "
                    f"{sent} applications sent | {tracked} total tracked[/bold green]"
                )
            except Exception as e:
                console.print(f"[red]Cycle {cycle} error: {e}[/red]")
                import traceback; traceback.print_exc()

            console.print(f"[dim]💤 Next cycle in {SEARCH_EVERY_HOURS}h[/dim]")
            await asyncio.sleep(SEARCH_EVERY_HOURS * 3600)
    finally:
        if tg_client:
            try:
                await tg_client.stop()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent stopped.[/yellow]")
