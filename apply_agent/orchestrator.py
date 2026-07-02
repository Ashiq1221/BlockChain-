"""Structured-debate orchestrator for job applications.

Round 1 — three specialists evaluate the posting in parallel:
    RECRUITER        does the resume clear the screen?
    HIRING MANAGER   skeptic — gaps, red flags, dealbreakers
    STRATEGIST       positioning — the angle that wins the interview
Round 2 — a MODERATOR weighs the debate against past-application lessons
           and issues a structured decision (APPLY/SKIP + fit score).
Round 3 — on APPLY, the WRITER produces a tailored cover letter and
           screener answers, grounded strictly in the real profile.
"""
import asyncio
import json
import re
from dataclasses import dataclass, field

from aos import providers as p
from . import memory
from .profile import PROFILE, profile_text

_PREFER = "claude"          # falls back through CF Workers AI automatically
_JSON_RE = re.compile(r"\{.*\}", re.S)


@dataclass
class ApplyPlan:
    url: str
    company: str = ""
    title: str = ""
    decision: str = "SKIP"          # APPLY | SKIP
    fit_score: float = 0.0          # 0–10
    reasons: list[str] = field(default_factory=list)
    positioning: str = ""
    keywords: list[str] = field(default_factory=list)
    cover_letter: str = ""
    screener_answers: dict = field(default_factory=dict)
    debate: dict = field(default_factory=dict)
    job_text: str = ""


def _parse_json(text: str) -> dict:
    m = _JSON_RE.search(text or "")
    if not m:
        return {}
    raw = m.group(0)
    for candidate in (raw, raw.replace("'", '"')):
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return {}


async def _fetch_job(url: str) -> str:
    """Full-page fetch (longer cap than aos.providers.fetch_page)."""
    import aiohttp
    from bs4 import BeautifulSoup
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/124.0.0.0 Safari/537.36"}
    try:
        async with aiohttp.ClientSession(headers=headers) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
                html = await r.text()
    except Exception:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "svg"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)[:9000]


async def _debate_round(job_text: str, lessons: str) -> dict:
    profile = profile_text()
    base = (f"JOB POSTING:\n{job_text[:6000]}\n\n"
            f"CANDIDATE PROFILE:\n{profile}\n\n"
            f"{lessons}\n\n"
            'Reply ONLY with JSON: {"fit_score": 0-10, "verdict": "APPLY|SKIP", '
            '"strengths": ["..."], "gaps": ["..."], "angle": "one-sentence positioning"}')

    recruiter, manager, strategist = await asyncio.gather(
        p.think(base, system=(
            "You are a veteran technical RECRUITER with 40 years of experience. "
            "Judge whether this candidate clears the initial screen for this job. "
            "Be realistic about ATS keyword match."), max_tokens=500, prefer=_PREFER),
        p.think(base, system=(
            "You are the skeptical HIRING MANAGER for this role. Find every gap, "
            "red flag, and dealbreaker. You reject 90% of applicants — is this one of the 10%?"),
            max_tokens=500, prefer=_PREFER),
        p.think(base, system=(
            "You are a 200-IQ CAREER STRATEGIST. Find the single sharpest positioning "
            "angle that makes this candidate memorable for this exact role."),
            max_tokens=500, prefer=_PREFER),
    )
    return {"recruiter": _parse_json(recruiter) or {"raw": recruiter[:300]},
            "manager":   _parse_json(manager)   or {"raw": manager[:300]},
            "strategist": _parse_json(strategist) or {"raw": strategist[:300]}}


async def _moderate(job_text: str, debate: dict, lessons: str) -> dict:
    prompt = (
        f"JOB POSTING (excerpt):\n{job_text[:3000]}\n\n"
        f"DEBATE POSITIONS:\n{json.dumps(debate, indent=1)[:3000]}\n\n"
        f"{lessons}\n\n"
        "Weigh the three positions. Where they disagree, decide who has the stronger "
        "argument and why. Then issue the final structured decision.\n"
        'Reply ONLY with JSON: {"company": "...", "title": "...", '
        '"decision": "APPLY|SKIP", "fit_score": 0-10, "reasons": ["..."], '
        '"positioning": "...", "keywords": ["ats", "keywords", "to", "use"]}'
    )
    out = await p.think(prompt, system=(
        "You are the MODERATOR of a hiring-strategy debate. You make the final call. "
        "APPLY only when fit_score >= 5 or the strategist found a genuinely strong angle."),
        max_tokens=600, prefer=_PREFER)
    return _parse_json(out)


async def _write_materials(job_text: str, decision: dict) -> tuple[str, dict]:
    profile = profile_text()
    prompt = (
        f"JOB POSTING (excerpt):\n{job_text[:3000]}\n\n"
        f"CANDIDATE PROFILE:\n{profile}\n\n"
        f"WINNING POSITIONING: {decision.get('positioning','')}\n"
        f"ATS KEYWORDS TO WEAVE IN: {', '.join(decision.get('keywords', [])[:10])}\n\n"
        "Write:\n"
        "1. A cover letter (150-220 words, confident, specific, zero clichés, "
        "grounded ONLY in real facts from the profile — never invent experience).\n"
        "2. Short answers to: why_this_company, why_you, biggest_achievement.\n"
        'Reply ONLY with JSON: {"cover_letter": "...", '
        '"answers": {"why_this_company": "...", "why_you": "...", "biggest_achievement": "..."}}'
    )
    out = await p.think(prompt, system=(
        "You are an elite application WRITER. Human voice, no fluff, no fabrication. "
        "Every claim must trace back to the profile."), max_tokens=900, prefer=_PREFER)
    data = _parse_json(out)
    return data.get("cover_letter", ""), data.get("answers", {})


async def evaluate_job(url: str, job_text: str = "") -> ApplyPlan:
    """Full pipeline: fetch → debate → decide → write → remember."""
    plan = ApplyPlan(url=url)
    plan.job_text = job_text or await _fetch_job(url)
    if len(plan.job_text) < 100:
        plan.reasons = ["Could not fetch the job posting (page blocked or empty). "
                        "Open the link in a browser and paste the description."]
        return plan

    lessons = memory.lessons_text()
    past = await memory.similar(plan.job_text[:1500])
    if past:
        lessons += "\nSIMILAR PAST JOBS: " + "; ".join(
            f"{m.get('metadata', {}).get('title','?')} → {m.get('metadata', {}).get('status','?')}"
            for m in past)

    plan.debate = await _debate_round(plan.job_text, lessons)
    decision = await _moderate(plan.job_text, plan.debate, lessons)

    plan.company    = decision.get("company", "")
    plan.title      = decision.get("title", "")
    plan.decision   = "APPLY" if str(decision.get("decision", "")).upper().startswith("APPLY") else "SKIP"
    try:
        plan.fit_score = float(decision.get("fit_score", 0))
    except (TypeError, ValueError):
        plan.fit_score = 0.0
    plan.reasons     = decision.get("reasons", [])
    plan.positioning = decision.get("positioning", "")
    plan.keywords    = decision.get("keywords", [])

    if plan.decision == "APPLY":
        plan.cover_letter, plan.screener_answers = await _write_materials(plan.job_text, decision)

    memory.record(url, plan.company, plan.title, plan.decision,
                  plan.fit_score, plan.cover_letter,
                  notes=plan.positioning)
    await memory.remember(plan.job_text[:1500], plan.job_text[:1000], {
        "url": url, "title": plan.title, "company": plan.company,
        "decision": plan.decision, "fit": plan.fit_score, "status": "evaluated",
    })
    return plan


def render_plan(plan: ApplyPlan) -> str:
    """Human-readable summary for CLI / Telegram."""
    icon = "✅ APPLY" if plan.decision == "APPLY" else "⏭️ SKIP"
    lines = [
        f"{icon} — {plan.title or 'Unknown role'} @ {plan.company or 'Unknown company'}",
        f"Fit score: {plan.fit_score}/10",
        f"Positioning: {plan.positioning}" if plan.positioning else "",
        "",
        "Reasons:",
        *[f"• {r}" for r in plan.reasons[:5]],
    ]
    if plan.keywords:
        lines += ["", "ATS keywords: " + ", ".join(plan.keywords[:10])]
    if plan.cover_letter:
        lines += ["", "── Cover letter ──", plan.cover_letter]
    return "\n".join(filter(None, lines))
