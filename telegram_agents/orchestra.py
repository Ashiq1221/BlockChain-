"""
100-Agent AI Orchestra — autonomous Telegram management system.

Architecture:
  Orchestrator AI  →  selects which of 100 agents to activate per task
  Agent Pool       →  100 specialists across 9 departments
  Tool Layer       →  ToolRegistry (Telegram / Web / DB)
  Report Layer     →  real-time progress back to the bot

Departments (9):
  1. Discovery       (15 agents) — find projects, roles, groups, people
  2. Research        (10 agents) — deep-dive any target
  3. Content         (15 agents) — write DMs, posts, pitches
  4. Outreach        (15 agents) — send, join, engage
  5. Analytics       (10 agents) — measure, track, report
  6. Strategy        (10 agents) — plan, prioritise, optimise
  7. Quality Control (10 agents) — tone, spam-check, brand
  8. Community       (10 agents) — moderate, celebrate, grow
  9. Support          (5 agents) — retry, rate-limit, health
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from telegram_agents.tools import ai_tools, web_tools, telegram_tools
from telegram_agents.tools.ai_router import think as ai_think, think_sync, router_status
from telegram_agents.config import Config

# ─────────────────────────────────────────────────────────────────────────────
# Core data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    agent_id: int
    name: str
    dept: str
    ok: bool
    data: Any = None
    error: str = ""
    duration_ms: int = 0


@dataclass
class Agent:
    id: int
    name: str
    dept: str
    goal: str
    fn: Callable          # async (tools, db, ctx) → Any
    weight: float = 1.0   # relevance weight 0–1
    enabled: bool = True

    async def run(self, tools, db, ctx: dict) -> AgentResult:
        if not self.enabled:
            return AgentResult(self.id, self.name, self.dept, ok=False, error="disabled")
        t0 = time.monotonic()
        try:
            data = await self.fn(tools, db, ctx)
            ms = int((time.monotonic() - t0) * 1000)
            return AgentResult(self.id, self.name, self.dept, ok=True, data=data, duration_ms=ms)
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            return AgentResult(self.id, self.name, self.dept, ok=False, error=str(e), duration_ms=ms)


# ─────────────────────────────────────────────────────────────────────────────
# Shared AI helper (thin wrapper so agents don't import router directly)
# ─────────────────────────────────────────────────────────────────────────────

async def _ai(system: str, prompt: str, max_tokens: int = 500) -> str:
    return await ai_think(system, prompt, max_tokens)


_PERSONA = (
    "You are an elite AI agent specialising in Web3/AI community management for "
    "Ashiq (@ashiq80): 16K+ followers, 6K+ community members, top ambassador/CM/moderator. "
    "Be sharp, human, and strategic. Never sound robotic."
)

# ─────────────────────────────────────────────────────────────────────────────
# ── DEPARTMENT 1: DISCOVERY (agents 1–15) ────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

async def _web3_project_scout(tools, db, ctx):
    q = ctx.get("topic", "web3 AI project hiring ambassador CM 2026")
    results = await web_tools.web_search(f"{q} telegram community", num=6)
    projects = []
    for r in results[:5]:
        projects.append({"title": r.get("title",""), "url": r.get("url",""),
                         "snippet": r.get("snippet","")[:150]})
    return projects

async def _ai_project_scout(tools, db, ctx):
    q = ctx.get("topic", "AI startup hiring community manager 2026")
    results = await web_tools.web_search(f"{q} site:twitter.com OR site:linkedin.com", num=5)
    return [{"title": r.get("title",""), "snippet": r.get("snippet","")[:150]} for r in results[:4]]

async def _job_opportunity_finder(tools, db, ctx):
    keywords = Config.JOB_KEYWORDS or "blockchain developer remote"
    results = await web_tools.web_search(f"{keywords} job 2026 remote", num=8)
    jobs = []
    for r in results[:6]:
        jobs.append({"title": r.get("title",""), "url": r.get("url",""),
                     "company": r.get("snippet","")[:80]})
    return jobs

async def _telegram_group_finder(tools, db, ctx):
    topic = ctx.get("topic", "web3 AI crypto")
    groups = await web_tools.find_telegram_groups_online(topic)
    return groups[:10]

async def _twitter_trend_scanner(tools, db, ctx):
    topics = ["web3", "AI agent", "DeFi", "crypto airdrop", "blockchain job"]
    results = []
    for t in topics[:3]:
        r = await web_tools.web_search(f"site:twitter.com {t} 2026", num=3)
        if r:
            results.append({"topic": t, "tweet": r[0].get("snippet","")[:200]})
    return results

async def _hackathon_finder(tools, db, ctx):
    r = await web_tools.web_search("web3 AI hackathon bounty 2026 join", num=6)
    return [{"name": x.get("title",""), "url": x.get("url",""), "info": x.get("snippet","")[:120]} for x in r[:5]]

async def _airdrop_detector(tools, db, ctx):
    r = await web_tools.web_search("crypto airdrop ambassador 2026 apply telegram", num=6)
    return [{"project": x.get("title",""), "url": x.get("url",""), "info": x.get("snippet","")[:120]} for x in r[:5]]

async def _dao_opportunity_finder(tools, db, ctx):
    r = await web_tools.web_search("DAO contributor role web3 2026 remote discord telegram", num=5)
    return [{"dao": x.get("title",""), "url": x.get("url",""), "role": x.get("snippet","")[:100]} for x in r[:4]]

async def _defi_protocol_scanner(tools, db, ctx):
    r = await web_tools.web_search("DeFi protocol ambassador program 2026 apply", num=5)
    return [{"protocol": x.get("title",""), "url": x.get("url","")} for x in r[:4]]

async def _nft_project_scout(tools, db, ctx):
    r = await web_tools.web_search("NFT project community manager 2026 telegram hiring", num=5)
    return [{"project": x.get("title",""), "snippet": x.get("snippet","")[:100]} for x in r[:4]]

async def _ambassador_program_finder(tools, db, ctx):
    r = await web_tools.web_search("crypto AI ambassador program apply 2026", num=8)
    programs = []
    for x in r[:6]:
        programs.append({"program": x.get("title",""), "url": x.get("url",""),
                         "info": x.get("snippet","")[:120]})
    return programs

async def _moderator_role_finder(tools, db, ctx):
    r = await web_tools.web_search("telegram discord moderator web3 AI hiring 2026 remote", num=8)
    return [{"role": x.get("title",""), "url": x.get("url",""), "details": x.get("snippet","")[:120]} for x in r[:6]]

async def _content_creator_role_finder(tools, db, ctx):
    r = await web_tools.web_search("crypto web3 content creator writer role 2026 remote paid", num=6)
    return [{"role": x.get("title",""), "url": x.get("url",""), "pay": x.get("snippet","")[:100]} for x in r[:5]]

async def _remote_dev_job_finder(tools, db, ctx):
    r = await web_tools.web_search("blockchain python backend developer remote job 2026", num=8)
    jobs = [{"title": x.get("title",""), "url": x.get("url",""), "company": x.get("snippet","")[:80]} for x in r[:6]]
    # Save to DB
    for j in jobs[:3]:
        try:
            await db.save_job(title=j["title"], company=j["company"],
                              description="", source=j["url"], url=j["url"])
        except Exception:
            pass
    return jobs

async def _partnership_opportunity_finder(tools, db, ctx):
    r = await web_tools.web_search("web3 AI partnership collab community telegram 2026", num=5)
    return [{"partner": x.get("title",""), "url": x.get("url",""), "info": x.get("snippet","")[:120]} for x in r[:4]]


# ─────────────────────────────────────────────────────────────────────────────
# ── DEPARTMENT 2: RESEARCH (agents 16–25) ────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

async def _project_deep_analyzer(tools, db, ctx):
    project = ctx.get("project_name") or ctx.get("topic", "web3 AI project")
    r = await web_tools.web_search(f"{project} review team tokenomics roadmap 2026", num=5)
    snippets = " | ".join(x.get("snippet","")[:200] for x in r[:3])
    analysis = await _ai(
        _PERSONA + "\nYou are a Web3 research analyst.",
        f"Analyze this project for opportunity (ambassador/CM role): {project}\nContext: {snippets}\n"
        "Rate: opportunity (1-10), legitimacy (1-10), growth potential (1-10). 3 bullet insights. Be concise.",
        400
    )
    return {"project": project, "analysis": analysis}

async def _founder_researcher(tools, db, ctx):
    name = ctx.get("founder_name") or ctx.get("topic", "web3 CEO founder")
    r = await web_tools.web_search(f"{name} CEO founder web3 AI twitter linkedin 2026", num=4)
    snippets = " | ".join(x.get("snippet","")[:150] for x in r[:3])
    profile = await _ai(
        _PERSONA,
        f"Research this founder for a personalized DM: {name}\nContext: {snippets}\n"
        "Return: background (1 line), current focus (1 line), best angle for outreach (1 line).",
        300
    )
    return {"founder": name, "profile": profile}

async def _team_validator(tools, db, ctx):
    project = ctx.get("project_name", ctx.get("topic", "project"))
    r = await web_tools.web_search(f"{project} team linkedin github doxxed 2026", num=4)
    snippets = " ".join(x.get("snippet","")[:100] for x in r[:3])
    verdict = await _ai(
        _PERSONA,
        f"Is this team credible? Project: {project}. Context: {snippets}\n"
        "Answer: credible/suspicious, and one reason. Max 2 sentences.",
        150
    )
    return {"project": project, "verdict": verdict}

async def _market_position_analyzer(tools, db, ctx):
    project = ctx.get("project_name", ctx.get("topic", "web3 project"))
    r = await web_tools.web_search(f"{project} market cap ranking 2026 CoinGecko", num=3)
    snippets = " ".join(x.get("snippet","")[:100] for x in r[:2])
    return {"project": project, "market_info": snippets or "No data found"}

async def _community_size_analyzer(tools, db, ctx):
    project = ctx.get("project_name", ctx.get("topic", "web3 project"))
    r = await web_tools.web_search(f"{project} telegram members discord followers 2026", num=4)
    snippets = " ".join(x.get("snippet","")[:100] for x in r[:3])
    estimate = await _ai(
        _PERSONA,
        f"Estimate community size for {project}. Context: {snippets}\nOne sentence answer.",
        100
    )
    return {"project": project, "size_estimate": estimate}

async def _social_proof_checker(tools, db, ctx):
    project = ctx.get("project_name", ctx.get("topic", "project"))
    r = await web_tools.web_search(f"{project} twitter followers real fake community 2026", num=4)
    snippets = " ".join(x.get("snippet","")[:100] for x in r[:3])
    check = await _ai(
        _PERSONA,
        f"Is the social proof for {project} real or fake? Context: {snippets}\nOne verdict sentence.",
        100
    )
    return {"project": project, "social_check": check}

async def _tokenomics_analyzer(tools, db, ctx):
    project = ctx.get("project_name", ctx.get("topic", "web3 token project"))
    r = await web_tools.web_search(f"{project} tokenomics vesting allocation 2026", num=4)
    snippets = " ".join(x.get("snippet","")[:150] for x in r[:3])
    analysis = await _ai(
        _PERSONA + "\nYou are a DeFi analyst.",
        f"Analyze tokenomics for {project}: {snippets}\n"
        "Red flags or green flags? Max 3 bullet points.",
        200
    )
    return {"project": project, "tokenomics": analysis}

async def _roadmap_reviewer(tools, db, ctx):
    project = ctx.get("project_name", ctx.get("topic", "web3 project"))
    r = await web_tools.web_search(f"{project} roadmap 2026 milestones mainnet launch", num=4)
    snippets = " ".join(x.get("snippet","")[:150] for x in r[:3])
    review = await _ai(
        _PERSONA,
        f"Review roadmap for {project}: {snippets}\nIs it ambitious/realistic? 2 sentences.",
        150
    )
    return {"project": project, "roadmap_review": review}

async def _competitor_mapper(tools, db, ctx):
    project = ctx.get("project_name", ctx.get("topic", "web3 project"))
    r = await web_tools.web_search(f"{project} competitors alternatives 2026", num=5)
    snippets = " ".join(x.get("snippet","")[:100] for x in r[:4])
    competitors = await _ai(
        _PERSONA,
        f"Who are the top 3 competitors of {project}? Context: {snippets}\n"
        "List them with one differentiator each.",
        200
    )
    return {"project": project, "competitors": competitors}

async def _opportunity_risk_assessor(tools, db, ctx):
    project = ctx.get("project_name", ctx.get("topic", "opportunity"))
    r = await web_tools.web_search(f"{project} scam rug pull risk 2026", num=4)
    snippets = " ".join(x.get("snippet","")[:100] for x in r[:3])
    risk = await _ai(
        _PERSONA,
        f"Risk assessment for opportunity: {project}. Red flags found: {snippets}\n"
        "Risk level: low/medium/high. One reason. Max 2 sentences.",
        150
    )
    return {"opportunity": project, "risk": risk}


# ─────────────────────────────────────────────────────────────────────────────
# ── DEPARTMENT 3: CONTENT CREATION (agents 26–40) ────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

async def _dm_composer(tools, db, ctx):
    target = ctx.get("target_name", "founder")
    project = ctx.get("project_name", ctx.get("topic", "your project"))
    background = ctx.get("target_background", "")
    dm = await _ai(
        _PERSONA + "\nWrite a personalized, human Telegram DM. 2-3 short sentences. No emojis overload. Sound like a real person.",
        f"Write DM to {target} about {project}. "
        f"Background: {background}. "
        "I'm Ashiq (@ashiq80), 16K+ followers, 6K+ community, top Web3 community builder. "
        "Goal: introduce myself and explore collaboration/ambassador role. Natural, not salesy.",
        250
    )
    return dm

async def _group_post_writer(tools, db, ctx):
    topic = ctx.get("topic", "Web3 AI trends")
    style = ctx.get("style", "informative")
    post = await _ai(
        _PERSONA + "\nWrite a short, engaging Telegram group post. Max 3 short paragraphs. No spam. Human tone.",
        f"Write a Telegram post about: {topic}. Style: {style}. "
        "End with a question to drive engagement.",
        350
    )
    return post

async def _announcement_writer(tools, db, ctx):
    topic = ctx.get("topic", "exciting update")
    announcement = await _ai(
        _PERSONA + "\nWrite a Telegram announcement. Bold headline, 2-3 lines of info, strong CTA.",
        f"Write announcement about: {topic}",
        300
    )
    return announcement

async def _pitch_writer(tools, db, ctx):
    project = ctx.get("project_name", ctx.get("topic", "your project"))
    pitch = await _ai(
        _PERSONA + "\nWrite a short collaboration pitch. 3-4 sentences. Value-first approach.",
        f"Pitch for collaboration with {project}. I am Ashiq: Web3 community builder, 16K+ followers, "
        "ambassador/CM for top projects. What value do I bring? Make it compelling.",
        300
    )
    return pitch

async def _twitter_thread_writer(tools, db, ctx):
    topic = ctx.get("topic", "Web3 trends 2026")
    thread = await _ai(
        _PERSONA + "\nWrite a Twitter/X thread. 5 tweets, numbered 1/ to 5/. Each tweet < 280 chars.",
        f"Write a Twitter thread about: {topic}. Educational, shareable, ends with CTA.",
        500
    )
    return thread

async def _bio_optimizer(tools, db, ctx):
    current_bio = ctx.get("bio", "Web3 community builder | Ambassador | CM")
    optimized = await _ai(
        _PERSONA + "\nOptimize a Telegram/Twitter bio. Max 160 chars. Credibility + personality.",
        f"Optimize this bio for Ashiq (@ashiq80): '{current_bio}'. "
        "Keep: 16K followers, 6K community, Web3/AI expertise. Make it sharp and memorable.",
        150
    )
    return optimized

async def _cover_letter_writer(tools, db, ctx):
    job_title = ctx.get("job_title", ctx.get("topic", "Community Manager"))
    company = ctx.get("company", "Web3 company")
    letter = await _ai(
        _PERSONA + "\nWrite a short job application cover letter. 3 paragraphs max. Confident, direct.",
        f"Cover letter for {job_title} at {company}. "
        "Ashiq: 16K+ followers, 6K+ community members, 3+ years Web3/AI community management, "
        "ambassador/CM for multiple top projects. Focus on results, not just experience.",
        400
    )
    return letter

async def _newsletter_writer(tools, db, ctx):
    topic = ctx.get("topic", "Web3 AI weekly digest")
    newsletter = await _ai(
        _PERSONA + "\nWrite a short community newsletter. Header, 3 sections, closing. Human tone.",
        f"Newsletter topic: {topic}. For Ashiq's 6K+ community members.",
        500
    )
    return newsletter

async def _content_repurposer(tools, db, ctx):
    original = ctx.get("content", ctx.get("topic", ""))
    if not original:
        return "No content provided to repurpose"
    formats = await _ai(
        _PERSONA,
        f"Repurpose this content into 3 formats (Telegram post, Twitter, LinkedIn):\n{original[:500]}",
        500
    )
    return formats

async def _hashtag_researcher(tools, db, ctx):
    topic = ctx.get("topic", "web3 AI crypto")
    r = await web_tools.web_search(f"best hashtags {topic} 2026 engagement twitter telegram", num=3)
    snippets = " ".join(x.get("snippet","")[:100] for x in r[:2])
    tags = await _ai(
        _PERSONA,
        f"Best 10 hashtags for: {topic}. Context: {snippets}. Return as comma-separated list.",
        100
    )
    return tags

async def _emoji_optimizer(tools, db, ctx):
    text = ctx.get("content", ctx.get("topic", ""))
    if not text:
        return "No content to optimize"
    optimized = await _ai(
        _PERSONA + "\nAdd exactly 2-3 relevant emojis to this message. Don't change the words.",
        f"Add emojis to: {text[:300]}",
        300
    )
    return optimized

async def _cta_writer(tools, db, ctx):
    goal = ctx.get("goal", ctx.get("topic", "join the community"))
    cta = await _ai(
        _PERSONA + "\nWrite 3 short calls-to-action. Each max 15 words. Action-oriented.",
        f"Write CTAs for goal: {goal}",
        150
    )
    return cta

async def _story_writer(tools, db, ctx):
    topic = ctx.get("topic", "my Web3 journey")
    story = await _ai(
        _PERSONA + "\nWrite a short personal story. 3-4 sentences. Authentic, relatable, inspiring.",
        f"Write a story about: {topic}. From Ashiq's perspective as a Web3 community builder.",
        300
    )
    return story

async def _educational_post_writer(tools, db, ctx):
    topic = ctx.get("topic", "DeFi basics")
    post = await _ai(
        _PERSONA + "\nWrite an educational Telegram post. Clear, simple, actionable. Use numbered list.",
        f"Explain: {topic}. For a non-technical crypto audience. End with 'What would you add?'",
        400
    )
    return post

async def _meme_caption_writer(tools, db, ctx):
    topic = ctx.get("topic", "crypto market")
    caption = await _ai(
        _PERSONA + "\nWrite 3 short meme captions. Max 10 words each. Funny and relatable to crypto/Web3 audience.",
        f"Meme captions about: {topic}",
        150
    )
    return caption


# ─────────────────────────────────────────────────────────────────────────────
# ── DEPARTMENT 4: OUTREACH & ENGAGEMENT (agents 41–55) ───────────────────────
# ─────────────────────────────────────────────────────────────────────────────

async def _strategic_dm_sender(tools, db, ctx):
    sent = 0
    targets = ctx.get("dm_targets", [])
    message = ctx.get("dm_message", "")
    if not targets or not message:
        return {"sent": 0, "msg": "No targets or message provided"}
    stats = await db.get_stats()
    hourly = stats.get("messages_sent_today", 0)
    if hourly >= Config.MAX_DM_PER_HOUR * 8:
        return {"sent": 0, "msg": "Daily DM limit reached"}
    for t in targets[:3]:
        try:
            ok = await tools.send_dm(user_id=t, text=message)
            if ok:
                sent += 1
            await asyncio.sleep(Config.RATE_LIMIT_SLEEP)
        except Exception:
            pass
    return {"sent": sent, "of": len(targets[:3])}

async def _group_joiner(tools, db, ctx):
    topic = ctx.get("topic", "web3 AI crypto")
    count = ctx.get("count", 3)
    groups = await web_tools.find_telegram_groups_online(topic)
    joined = 0
    errors = []
    for g in groups[:count]:
        username = g.get("username", "")
        if not username:
            continue
        try:
            ok = await tools.join_group(username=username)
            if ok:
                joined += 1
            await asyncio.sleep(2)
        except Exception as e:
            errors.append(f"@{username}: {str(e)[:50]}")
    result = f"Joined {joined}/{min(count, len(groups))} groups about '{topic}'"
    if errors:
        result += f" | Errors: {'; '.join(errors[:2])}"
    return {"joined": joined, "msg": result}

async def _channel_poster(tools, db, ctx):
    channel = ctx.get("channel", "")
    text = ctx.get("content") or ctx.get("message", "")
    if not channel or not text:
        return {"ok": False, "msg": "Need channel and content"}
    ok = await tools.post_to_channel(channel=channel, text=text)
    return {"ok": ok, "channel": channel}

async def _community_engager(tools, db, ctx):
    dialogs = await tools.get_dialogs()
    groups = [d for d in dialogs if d.get("type") in ("group","supergroup") and d.get("unread",0) > 0]
    engaged = 0
    for g in groups[:2]:
        topic = ctx.get("topic", "Web3 AI trends")
        history = await tools.get_chat_history(group_id=g["id"])
        if history:
            last = history[0].get("text","")[:200]
            reply = await _ai(
                _PERSONA + "\nWrite a short, natural group engagement reply. Max 2 sentences.",
                f"Reply to this in a {topic} group: '{last}'"
            )
            await tools.post_in_group(group_id=g["id"], text=reply)
            engaged += 1
            await asyncio.sleep(3)
    return {"groups_engaged": engaged}

async def _follow_up_manager(tools, db, ctx):
    # Find contacts we haven't followed up with
    contacts = await db.get_contacts()
    followed_up = 0
    for c in contacts[:2]:
        if not c.get("username"):
            continue
        msg = await _ai(
            _PERSONA + "\nWrite a natural follow-up message. 1-2 sentences. Friendly check-in.",
            f"Follow up with {c.get('first_name','them')} after initial outreach about Web3 collaboration."
        )
        ok = await tools.send_dm(user_id=f"@{c['username']}", text=msg)
        if ok:
            followed_up += 1
        await asyncio.sleep(Config.RATE_LIMIT_SLEEP)
    return {"followed_up": followed_up}

async def _relationship_builder(tools, db, ctx):
    dialogs = await tools.get_dialogs()
    key_people = [d for d in dialogs if d.get("type") == "user"][:3]
    notes = []
    for p in key_people:
        notes.append({"name": p.get("title",""), "id": p.get("id"), "last": p.get("last_message","")[:50]})
    summary = await _ai(
        _PERSONA,
        f"Based on these recent conversations, who should I prioritize for relationship building? {json.dumps(notes)}\n"
        "Pick top 1-2 and suggest a next action for each.",
        200
    )
    return {"relationships": summary}

async def _collaboration_initiator(tools, db, ctx):
    project = ctx.get("project_name", ctx.get("topic", "a Web3 project"))
    contact = ctx.get("target_username", "")
    pitch = await _ai(
        _PERSONA + "\nWrite a short collaboration initiation message. Value-first. 2-3 sentences.",
        f"Reach out to {project} for collaboration. Ashiq brings: 16K followers, 6K community, "
        "Web3/AI expertise, ambassador track record.",
        200
    )
    if contact:
        ok = await tools.send_dm(user_id=f"@{contact}", text=pitch)
        return {"sent": ok, "pitch": pitch, "to": contact}
    return {"pitch": pitch, "note": "No contact specified, pitch drafted only"}

async def _network_expander(tools, db, ctx):
    groups = await tools.get_dialogs()
    total = len([g for g in groups if g.get("type") in ("group","supergroup","channel")])
    contacts_count = len(await db.get_contacts())
    suggestion = await _ai(
        _PERSONA,
        f"I'm in {total} groups and have {contacts_count} contacts. "
        "Suggest 3 specific ways to expand my Web3/AI network this week. Bullet points.",
        250
    )
    return {"groups": total, "contacts": contacts_count, "strategy": suggestion}

async def _event_announcer(tools, db, ctx):
    event = ctx.get("event_name", ctx.get("topic", "Community AMA"))
    date = ctx.get("date", "this week")
    announcement = await _ai(
        _PERSONA + "\nWrite a Telegram event announcement. Exciting but concise. Include: what, when, why join.",
        f"Announce: {event} on {date}. For Ashiq's Web3 community.",
        250
    )
    return announcement

async def _welcome_sender(tools, db, ctx):
    new_members = ctx.get("new_members", [])
    if not new_members:
        return {"sent": 0, "msg": "No new members to welcome"}
    welcome = await _ai(
        _PERSONA + "\nWrite a warm, brief welcome message for a new community member. 2 sentences.",
        "Welcome a new member to Ashiq's Web3/AI community. Make them feel valued."
    )
    sent = 0
    for member in new_members[:5]:
        ok = await tools.send_dm(user_id=member, text=welcome)
        if ok:
            sent += 1
        await asyncio.sleep(1)
    return {"sent": sent, "message": welcome}

async def _feedback_requester(tools, db, ctx):
    topic = ctx.get("topic", "our community")
    msg = await _ai(
        _PERSONA + "\nWrite a short, genuine feedback request. 2-3 sentences. Easy to answer.",
        f"Ask community for feedback on: {topic}"
    )
    return msg

async def _testimonial_collector(tools, db, ctx):
    msg = await _ai(
        _PERSONA + "\nWrite a casual message asking for a testimonial. Non-pushy. 2 sentences.",
        "Ask a satisfied community member for a quick testimonial about Ashiq's community management."
    )
    return msg

async def _referral_activator(tools, db, ctx):
    incentive = ctx.get("incentive", "early access or exclusive role")
    msg = await _ai(
        _PERSONA + "\nWrite a referral invite message. Short, exciting, clear benefit.",
        f"Ask community to refer friends with incentive: {incentive}"
    )
    return msg

async def _group_poll_creator(tools, db, ctx):
    topic = ctx.get("topic", "Web3 trends")
    poll = await _ai(
        _PERSONA + "\nCreate a simple Telegram poll. Question + 4 options. Engaging topic.",
        f"Create a poll about: {topic} for a Web3/AI community"
    )
    return poll

async def _contest_organizer(tools, db, ctx):
    prize = ctx.get("prize", ctx.get("topic", "exclusive NFT or role"))
    contest = await _ai(
        _PERSONA + "\nWrite a Telegram contest announcement. Clear rules, exciting prize, deadline.",
        f"Organize a community contest with prize: {prize}"
    )
    return contest


# ─────────────────────────────────────────────────────────────────────────────
# ── DEPARTMENT 5: ANALYTICS (agents 56–65) ───────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

async def _performance_tracker(tools, db, ctx):
    stats = await db.get_stats()
    return stats

async def _dm_response_analyzer(tools, db, ctx):
    stats = await db.get_stats()
    sent = stats.get("messages_sent", 0)
    resp = stats.get("responses_received", 0)
    rate = round(resp / sent * 100, 1) if sent else 0
    analysis = await _ai(
        _PERSONA,
        f"DM stats: {sent} sent, {resp} responses ({rate}%). "
        "Is this good for Web3 cold outreach? 2-sentence assessment + 1 tip.",
        150
    )
    return {"sent": sent, "responses": resp, "rate": f"{rate}%", "analysis": analysis}

async def _group_growth_tracker(tools, db, ctx):
    dialogs = await tools.get_dialogs()
    groups = [d for d in dialogs if d.get("type") in ("group","supergroup")]
    channels = [d for d in dialogs if d.get("type") == "channel"]
    return {
        "total_groups": len(groups),
        "total_channels": len(channels),
        "top_groups": [{"name": g.get("title",""),"members": g.get("members",0)} for g in groups[:5]]
    }

async def _engagement_rate_calculator(tools, db, ctx):
    stats = await db.get_stats()
    posts = stats.get("posts_made", 0)
    engagements = stats.get("engagements_received", 0)
    rate = round(engagements / posts * 100, 1) if posts else 0
    return {"posts": posts, "engagements": engagements, "engagement_rate": f"{rate}%"}

async def _conversion_tracker(tools, db, ctx):
    stats = await db.get_stats()
    dms = stats.get("messages_sent", 0)
    jobs_applied = stats.get("jobs_applied", 0)
    groups_joined = stats.get("groups_joined", 0)
    return {
        "dms_sent": dms,
        "groups_joined": groups_joined,
        "jobs_applied": jobs_applied,
        "conversion_note": "Each DM = potential collaboration; each group = 10+ potential contacts"
    }

async def _roi_calculator(tools, db, ctx):
    stats = await db.get_stats()
    time_saved = stats.get("messages_sent", 0) * 3  # ~3 min per manual DM
    roi = await _ai(
        _PERSONA + "\nBe a strategic advisor.",
        f"Bot stats: {json.dumps(stats)}. "
        "Calculate: hours saved, potential ROI if 5% of outreach converts to a $500/month gig. "
        "Short, sharp, 3 bullet points.",
        200
    )
    return {"stats": stats, "roi_analysis": roi}

async def _reach_estimator(tools, db, ctx):
    dialogs = await tools.get_dialogs()
    total_reach = sum(d.get("members", 0) for d in dialogs if d.get("type") in ("group","supergroup","channel"))
    return {
        "estimated_reach": total_reach,
        "groups": len([d for d in dialogs if d.get("type") in ("group","supergroup")]),
        "channels": len([d for d in dialogs if d.get("type") == "channel"]),
    }

async def _trend_performance_tracker(tools, db, ctx):
    r = await web_tools.web_search("web3 AI community manager salary rate 2026", num=3)
    snippets = " ".join(x.get("snippet","")[:100] for x in r[:2])
    rates = await _ai(
        _PERSONA,
        f"Market rates for Web3 CM/Ambassador roles in 2026: {snippets}\nSummarise in 2 bullet points.",
        150
    )
    return {"market_rates": rates}

async def _competitor_growth_tracker(tools, db, ctx):
    r = await web_tools.web_search("top web3 community managers twitter followers 2026", num=4)
    snippets = " ".join(x.get("snippet","")[:100] for x in r[:3])
    analysis = await _ai(
        _PERSONA,
        f"Competitor analysis for Web3 community managers: {snippets}\n"
        "What should Ashiq do differently? 2 bullet points.",
        150
    )
    return {"competitor_analysis": analysis}

async def _campaign_performance_reporter(tools, db, ctx):
    stats = await db.get_stats()
    report = await _ai(
        _PERSONA + "\nWrite a concise performance report. Use metrics. Be direct.",
        f"Write a campaign performance report based on: {json.dumps(stats)}\n"
        "Format: 3 wins, 2 improvements needed.",
        300
    )
    return {"report": report, "raw_stats": stats}


# ─────────────────────────────────────────────────────────────────────────────
# ── DEPARTMENT 6: STRATEGY (agents 66–75) ────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

async def _daily_goal_setter(tools, db, ctx):
    stats = await db.get_stats()
    goals = await _ai(
        _PERSONA + "\nSet smart daily goals. Be specific and achievable.",
        f"Set 5 daily goals for Ashiq's autonomous Telegram bot based on current stats: {json.dumps(stats)}\n"
        "Format: numbered list. Each goal: action + metric.",
        300
    )
    return goals

async def _priority_optimizer(tools, db, ctx):
    tasks = ctx.get("tasks", ["hunt jobs", "join groups", "send DMs", "post content", "engage community"])
    stats = await db.get_stats()
    priorities = await _ai(
        _PERSONA + "\nRank tasks by ROI. Be strategic and data-driven.",
        f"Rank these tasks by priority for Ashiq today: {', '.join(tasks)}\n"
        f"Current stats: {json.dumps(stats)}\n"
        "Return ranked list with 1-line reason for each.",
        300
    )
    return priorities

async def _timing_advisor(tools, db, ctx):
    action = ctx.get("action", ctx.get("topic", "posting in Telegram groups"))
    advice = await _ai(
        _PERSONA + "\nYou know Web3 community engagement patterns.",
        f"Best times (UTC) to do '{action}' for maximum engagement in Web3/AI communities? "
        "3 specific time windows with reason.",
        200
    )
    return advice

async def _audience_segmenter(tools, db, ctx):
    contacts = await db.get_contacts()
    total = len(contacts)
    segments = await _ai(
        _PERSONA,
        f"Ashiq has {total} contacts in his Telegram network. "
        "Suggest 4 audience segments (e.g. founders, developers, investors, community members) "
        "and ideal outreach message for each. Brief bullet format.",
        300
    )
    return {"total_contacts": total, "segments": segments}

async def _approach_selector(tools, db, ctx):
    goal = ctx.get("goal", ctx.get("topic", "get a community manager role"))
    approach = await _ai(
        _PERSONA + "\nYou are a strategic advisor for Web3 careers.",
        f"Best 3-step approach to achieve: {goal}\n"
        "Given Ashiq's strengths: 16K followers, 6K community, active in Web3/AI. "
        "Be tactical and specific.",
        300
    )
    return approach

async def _opportunity_scorer(tools, db, ctx):
    opportunities = ctx.get("opportunities", [])
    if not opportunities:
        r = await web_tools.web_search("web3 AI ambassador CM role 2026 apply", num=5)
        opportunities = [x.get("title","") for x in r[:5]]
    scored = await _ai(
        _PERSONA + "\nScore opportunities 1-10 by: pay potential, legitimacy, alignment with Ashiq's brand.",
        f"Score these opportunities for Ashiq:\n" + "\n".join(f"- {o}" for o in opportunities),
        300
    )
    return {"opportunities": opportunities, "scores": scored}

async def _campaign_planner(tools, db, ctx):
    campaign_goal = ctx.get("goal", ctx.get("topic", "land 2 new ambassador roles this week"))
    plan = await _ai(
        _PERSONA + "\nCreate an actionable campaign plan. Day-by-day breakdown.",
        f"Campaign goal: {campaign_goal}\n"
        "Create a 7-day campaign plan using: Telegram outreach, group joining, content posting, DMs. "
        "Be specific about what to do each day.",
        500
    )
    return plan

async def _budget_allocator(tools, db, ctx):
    hours = ctx.get("hours_per_day", 4)
    allocation = await _ai(
        _PERSONA,
        f"Ashiq has {hours} hours/day for his bot. Allocate time across: "
        "discovery, outreach, content creation, community management, analytics. "
        "Return as percentages with brief rationale.",
        200
    )
    return allocation

async def _pivot_advisor(tools, db, ctx):
    stats = await db.get_stats()
    sent = stats.get("messages_sent", 0)
    resp = stats.get("responses_received", 0)
    rate = resp / sent if sent else 0
    advice = await _ai(
        _PERSONA + "\nGive honest strategic pivot advice.",
        f"Current DM response rate: {rate:.1%} ({resp}/{sent}). "
        f"Groups joined: {stats.get('groups_joined',0)}. "
        "Should Ashiq pivot his strategy? What should he change? 2 specific actionable suggestions.",
        200
    )
    return {"current_rate": f"{rate:.1%}", "advice": advice}

async def _weekly_planner(tools, db, ctx):
    week_plan = await _ai(
        _PERSONA + "\nPlan the week for an autonomous Telegram bot.",
        "Create a weekly plan for Ashiq's autonomous bot. Mon-Sun. "
        "Each day: primary action + secondary action + metric to hit. "
        "Focus on: ambassador roles, community growth, job applications, relationship building.",
        500
    )
    return week_plan


# ─────────────────────────────────────────────────────────────────────────────
# ── DEPARTMENT 7: QUALITY CONTROL (agents 76–85) ─────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

async def _tone_checker(tools, db, ctx):
    message = ctx.get("content", ctx.get("message", ctx.get("topic", "")))
    if not message:
        return {"ok": True, "note": "No message to check"}
    check = await _ai(
        _PERSONA + "\nCheck tone of a message. Be direct about issues.",
        f"Check tone of this message:\n'{message}'\n"
        "Rate: professional (1-10), human (1-10), spammy risk (1-10). One improvement suggestion.",
        150
    )
    return {"message_preview": message[:80], "tone_check": check}

async def _spam_risk_checker(tools, db, ctx):
    message = ctx.get("content", ctx.get("message", ctx.get("topic", "")))
    if not message:
        return {"spam_risk": "low", "note": "No message provided"}
    check = await _ai(
        _PERSONA,
        f"Is this message at risk of being flagged as spam by Telegram?\n'{message}'\n"
        "Answer: risk level (low/medium/high) and specific red flags if any.",
        150
    )
    return {"spam_check": check}

async def _personalization_validator(tools, db, ctx):
    dm = ctx.get("content", ctx.get("message", ctx.get("topic", "")))
    target = ctx.get("target_name", "the recipient")
    if not dm:
        return {"valid": False, "note": "No message to validate"}
    validation = await _ai(
        _PERSONA,
        f"Does this DM feel genuinely personalized for {target}? Or does it feel generic?\n'{dm}'\n"
        "Answer: personalization score (1-10) and specific suggestion to improve.",
        150
    )
    return {"validation": validation}

async def _brand_consistency_checker(tools, db, ctx):
    content = ctx.get("content", ctx.get("topic", ""))
    if not content:
        return {"consistent": True, "note": "No content to check"}
    check = await _ai(
        _PERSONA,
        f"Does this content match Ashiq's brand? (Professional Web3/AI expert, 16K followers, community builder)\n"
        f"Content: '{content[:300]}'\n"
        "Brand match score (1-10) and one note.",
        100
    )
    return {"brand_check": check}

async def _grammar_fixer(tools, db, ctx):
    text = ctx.get("content", ctx.get("message", ctx.get("topic", "")))
    if not text:
        return {"fixed": "No text provided"}
    fixed = await _ai(
        _PERSONA + "\nFix grammar and typos only. Do NOT change the meaning or tone.",
        f"Fix grammar in: '{text}'\nReturn ONLY the corrected text.",
        300
    )
    return {"original": text[:100], "fixed": fixed}

async def _length_optimizer(tools, db, ctx):
    text = ctx.get("content", ctx.get("message", ctx.get("topic", "")))
    target_type = ctx.get("type", "telegram_dm")
    if not text:
        return {"note": "No text to optimize"}
    optimized = await _ai(
        _PERSONA + f"\nOptimize length for: {target_type}. Ideal lengths: DM=50-150 words, post=100-300 words, announcement=50-100 words.",
        f"Is this the right length? If not, trim/expand it:\n'{text[:400]}'\nReturn optimized version.",
        350
    )
    return {"optimized": optimized}

async def _clarity_improver(tools, db, ctx):
    text = ctx.get("content", ctx.get("topic", ""))
    if not text:
        return {"note": "No content provided"}
    improved = await _ai(
        _PERSONA + "\nImprove clarity. Simpler words, shorter sentences. Keep the core message.",
        f"Make this clearer:\n'{text[:400]}'\nReturn improved version.",
        350
    )
    return {"improved": improved}

async def _authenticity_checker(tools, db, ctx):
    message = ctx.get("content", ctx.get("topic", ""))
    if not message:
        return {"authentic": True, "note": "No message to check"}
    check = await _ai(
        _PERSONA,
        f"Does this sound like a real human or an obvious AI bot?\n'{message}'\n"
        "Authenticity score (1-10). If <7, give specific fix.",
        150
    )
    return {"authenticity": check}

async def _duplicate_detector(tools, db, ctx):
    new_msg = ctx.get("content", ctx.get("topic", ""))
    if not new_msg:
        return {"duplicate": False, "note": "No message to check"}
    recent = await db.get_recent_sent_messages(limit=10) if hasattr(db, 'get_recent_sent_messages') else []
    if not recent:
        return {"duplicate": False, "note": "No history to compare"}
    check = await _ai(
        _PERSONA,
        f"Is this message too similar to recent ones?\nNew: '{new_msg[:200]}'\n"
        f"Recent: {json.dumps([r.get('text','')[:100] for r in recent[:5]])}\n"
        "Similar: yes/no. If yes, suggest variation.",
        150
    )
    return {"check": check}

async def _compliance_auditor(tools, db, ctx):
    action = ctx.get("action", ctx.get("topic", "sending DMs"))
    audit = await _ai(
        _PERSONA + "\nYou know Telegram ToS and ethical outreach practices.",
        f"Is this action compliant with Telegram ToS and ethical outreach standards: {action}?\n"
        "Risk: low/medium/high. One note.",
        100
    )
    return {"action": action, "compliance": audit}


# ─────────────────────────────────────────────────────────────────────────────
# ── DEPARTMENT 8: COMMUNITY MANAGEMENT (agents 86–95) ────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

async def _community_health_monitor(tools, db, ctx):
    dialogs = await tools.get_dialogs()
    groups = [d for d in dialogs if d.get("type") in ("group","supergroup")]
    health = {"total_groups": len(groups), "active_groups": 0, "silent_groups": 0}
    for g in groups[:10]:
        hist = await tools.get_chat_history(group_id=g["id"])
        if hist:
            last_msg_date = hist[0].get("date","")
            health["active_groups"] += 1
        else:
            health["silent_groups"] += 1
    health["health_score"] = round(health["active_groups"] / max(health["total_groups"],1) * 100)
    return health

async def _spam_detector(tools, db, ctx):
    group_id = ctx.get("group_id")
    if not group_id:
        return {"detected": 0, "note": "No group specified"}
    msgs = await tools.get_chat_history(group_id=group_id)
    spam_patterns = ["click here", "100x", "guaranteed profit", "send $", "moon", "🚀🚀🚀"]
    spam_msgs = [m for m in msgs if any(p in (m.get("text","")).lower() for p in spam_patterns)]
    return {"total_messages": len(msgs), "spam_detected": len(spam_msgs),
            "spam_samples": [m.get("text","")[:80] for m in spam_msgs[:3]]}

async def _sentiment_monitor(tools, db, ctx):
    group_id = ctx.get("group_id")
    if not group_id:
        dialogs = await tools.get_dialogs()
        groups = [d for d in dialogs if d.get("type") in ("group","supergroup")]
        if groups:
            group_id = groups[0]["id"]
        else:
            return {"sentiment": "unknown", "note": "No groups found"}
    msgs = await tools.get_chat_history(group_id=group_id)
    texts = " | ".join(m.get("text","")[:100] for m in msgs[:10] if m.get("text"))
    sentiment = await _ai(
        _PERSONA,
        f"What is the overall sentiment in this community? Messages: {texts}\n"
        "Sentiment: positive/neutral/negative. Brief reason. Max 2 sentences.",
        150
    )
    return {"group_id": group_id, "sentiment": sentiment}

async def _topic_moderator(tools, db, ctx):
    off_topic = ctx.get("off_topic_examples", ["unrelated spam", "political arguments"])
    response = await _ai(
        _PERSONA + "\nWrite a polite, firm moderation message.",
        f"Write a mod message addressing off-topic posts: {', '.join(off_topic)}\n"
        "Remind rules gently. 2 sentences.",
        100
    )
    return response

async def _knowledge_base_builder(tools, db, ctx):
    topic = ctx.get("topic", "Web3 community management FAQ")
    faq = await _ai(
        _PERSONA + "\nBuild a community knowledge base entry.",
        f"Create 5 FAQ entries for: {topic}\n"
        "Format: Q: ... A: ... (Keep each answer to 1-2 sentences)",
        400
    )
    return faq

async def _ama_coordinator(tools, db, ctx):
    guest = ctx.get("guest_name", ctx.get("topic", "a Web3 founder"))
    ama = await _ai(
        _PERSONA + "\nPlan an AMA session.",
        f"Plan a 30-min AMA with {guest} for Ashiq's community.\n"
        "Include: 5 opening questions, 3 community questions, closing CTA. Brief format.",
        400
    )
    return ama

async def _milestone_tracker(tools, db, ctx):
    stats = await db.get_stats()
    milestones = []
    if stats.get("messages_sent", 0) >= 100:
        milestones.append("100 DMs sent!")
    if stats.get("groups_joined", 0) >= 50:
        milestones.append("50 groups joined!")
    if stats.get("jobs_applied", 0) >= 10:
        milestones.append("10 jobs applied!")
    if not milestones:
        milestones.append("Keep going — milestones coming soon!")
    return {"milestones_reached": milestones, "stats": stats}

async def _member_recognition_agent(tools, db, ctx):
    msg = await _ai(
        _PERSONA + "\nWrite a community shoutout message. Warm, genuine, specific.",
        "Write a shoutout for a top community member in Ashiq's Web3/AI group. "
        "Make it feel personal and special without naming anyone specific. "
        "Add a CTA for others to get involved too.",
        200
    )
    return msg

async def _conflict_resolver(tools, db, ctx):
    conflict = ctx.get("conflict", ctx.get("topic", "two members arguing about a project"))
    resolution = await _ai(
        _PERSONA + "\nWrite a diplomatic community conflict resolution message.",
        f"Resolve this community conflict: {conflict}\n"
        "Be fair, calm, decisive. Remind of community rules. Max 3 sentences.",
        200
    )
    return resolution

async def _community_reporter(tools, db, ctx):
    stats = await db.get_stats()
    dialogs = await tools.get_dialogs()
    groups = [d for d in dialogs if d.get("type") in ("group","supergroup","channel")]
    report = await _ai(
        _PERSONA,
        f"Write a brief community status report:\n"
        f"- Total groups/channels: {len(groups)}\n"
        f"- Bot stats: {json.dumps(stats)}\n"
        "Format: 3 bullet points covering health, activity, opportunities.",
        200
    )
    return {"report": report, "groups": len(groups), "stats": stats}


# ─────────────────────────────────────────────────────────────────────────────
# ── DEPARTMENT 9: TECHNICAL SUPPORT (agents 96–100) ──────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

async def _error_recovery_agent(tools, db, ctx):
    error = ctx.get("error", "unknown error")
    recovery = await _ai(
        _PERSONA + "\nYou are a technical troubleshooter.",
        f"Error occurred: {error}\nSuggest 2 quick recovery steps. Be specific.",
        150
    )
    return {"error": error, "recovery_plan": recovery}

async def _rate_limit_guardian(tools, db, ctx):
    stats = await db.get_stats()
    sent_today = stats.get("messages_sent_today", 0)
    hourly_limit = Config.MAX_DM_PER_HOUR
    status = "safe" if sent_today < hourly_limit * 8 else "near limit"
    suggestion = "Continue normally" if status == "safe" else f"Slow down — sent {sent_today} DMs today"
    return {"status": status, "sent_today": sent_today, "daily_limit": hourly_limit * 8,
            "suggestion": suggestion}

async def _retry_coordinator(tools, db, ctx):
    failed_actions = ctx.get("failed_actions", [])
    retry_plan = []
    for action in failed_actions[:3]:
        retry_plan.append({"action": action, "retry_in_seconds": 30, "max_attempts": 3})
    return {"retry_queue": retry_plan, "total": len(failed_actions)}

async def _session_health_checker(tools, db, ctx):
    try:
        dialogs = await tools.get_dialogs()
        return {"session": "healthy", "dialogs_accessible": len(dialogs), "status": "✅ All systems go"}
    except Exception as e:
        return {"session": "degraded", "error": str(e), "status": "⚠️ Session issue"}

async def _system_optimizer(tools, db, ctx):
    status = router_status()
    stats = await db.get_stats()
    optimization = await _ai(
        _PERSONA + "\nSystem optimizer — find bottlenecks and suggest fixes.",
        f"AI router status:\n{status}\n\nBot stats: {json.dumps(stats)}\n"
        "Top 2 system optimizations to run faster/smarter.",
        200
    )
    return {"router_status": status, "optimization_tips": optimization}


# ─────────────────────────────────────────────────────────────────────────────
# ── Orchestra class ───────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

_ALL_AGENTS_DEFS = [
    # Dept 1 — Discovery
    (1,  "web3_project_scout",        "Discovery",  "Find new Web3 projects", _web3_project_scout),
    (2,  "ai_project_scout",          "Discovery",  "Find AI startups", _ai_project_scout),
    (3,  "job_opportunity_finder",    "Discovery",  "Find job openings", _job_opportunity_finder),
    (4,  "telegram_group_finder",     "Discovery",  "Find TG groups", _telegram_group_finder),
    (5,  "twitter_trend_scanner",     "Discovery",  "Scan trending X topics", _twitter_trend_scanner),
    (6,  "hackathon_finder",          "Discovery",  "Find hackathons & bounties", _hackathon_finder),
    (7,  "airdrop_detector",          "Discovery",  "Detect airdrop opportunities", _airdrop_detector),
    (8,  "dao_opportunity_finder",    "Discovery",  "Find DAO contributor roles", _dao_opportunity_finder),
    (9,  "defi_protocol_scanner",     "Discovery",  "Scan DeFi protocols", _defi_protocol_scanner),
    (10, "nft_project_scout",         "Discovery",  "Scout NFT projects", _nft_project_scout),
    (11, "ambassador_program_finder", "Discovery",  "Find ambassador programs", _ambassador_program_finder),
    (12, "moderator_role_finder",     "Discovery",  "Find mod/CM roles", _moderator_role_finder),
    (13, "content_creator_finder",    "Discovery",  "Find content creator roles", _content_creator_role_finder),
    (14, "remote_dev_job_finder",     "Discovery",  "Find remote dev jobs", _remote_dev_job_finder),
    (15, "partnership_finder",        "Discovery",  "Find partnership ops", _partnership_opportunity_finder),
    # Dept 2 — Research
    (16, "project_deep_analyzer",     "Research",   "Deep-dive project analysis", _project_deep_analyzer),
    (17, "founder_researcher",        "Research",   "Research founders/CEOs", _founder_researcher),
    (18, "team_validator",            "Research",   "Validate team credentials", _team_validator),
    (19, "market_position_analyzer",  "Research",   "Analyze market position", _market_position_analyzer),
    (20, "community_size_analyzer",   "Research",   "Estimate community size", _community_size_analyzer),
    (21, "social_proof_checker",      "Research",   "Check social credibility", _social_proof_checker),
    (22, "tokenomics_analyzer",       "Research",   "Analyze tokenomics", _tokenomics_analyzer),
    (23, "roadmap_reviewer",          "Research",   "Review project roadmap", _roadmap_reviewer),
    (24, "competitor_mapper",         "Research",   "Map competitors", _competitor_mapper),
    (25, "opportunity_risk_assessor", "Research",   "Assess opportunity risks", _opportunity_risk_assessor),
    # Dept 3 — Content
    (26, "dm_composer",               "Content",    "Write personalized DMs", _dm_composer),
    (27, "group_post_writer",         "Content",    "Write group posts", _group_post_writer),
    (28, "announcement_writer",       "Content",    "Write announcements", _announcement_writer),
    (29, "pitch_writer",              "Content",    "Write pitches", _pitch_writer),
    (30, "twitter_thread_writer",     "Content",    "Write Twitter threads", _twitter_thread_writer),
    (31, "bio_optimizer",             "Content",    "Optimize profile bios", _bio_optimizer),
    (32, "cover_letter_writer",       "Content",    "Write cover letters", _cover_letter_writer),
    (33, "newsletter_writer",         "Content",    "Write newsletters", _newsletter_writer),
    (34, "content_repurposer",        "Content",    "Repurpose content", _content_repurposer),
    (35, "hashtag_researcher",        "Content",    "Research best hashtags", _hashtag_researcher),
    (36, "emoji_optimizer",           "Content",    "Optimize emoji usage", _emoji_optimizer),
    (37, "cta_writer",                "Content",    "Write calls-to-action", _cta_writer),
    (38, "story_writer",              "Content",    "Write personal stories", _story_writer),
    (39, "educational_post_writer",   "Content",    "Write educational posts", _educational_post_writer),
    (40, "meme_caption_writer",       "Content",    "Write meme captions", _meme_caption_writer),
    # Dept 4 — Outreach
    (41, "strategic_dm_sender",       "Outreach",   "Send strategic DMs", _strategic_dm_sender),
    (42, "group_joiner",              "Outreach",   "Join relevant groups", _group_joiner),
    (43, "channel_poster",            "Outreach",   "Post to channels", _channel_poster),
    (44, "community_engager",         "Outreach",   "Engage in communities", _community_engager),
    (45, "follow_up_manager",         "Outreach",   "Manage follow-ups", _follow_up_manager),
    (46, "relationship_builder",      "Outreach",   "Build key relationships", _relationship_builder),
    (47, "collaboration_initiator",   "Outreach",   "Initiate collaborations", _collaboration_initiator),
    (48, "network_expander",          "Outreach",   "Expand network", _network_expander),
    (49, "event_announcer",           "Outreach",   "Announce events/AMAs", _event_announcer),
    (50, "welcome_sender",            "Outreach",   "Welcome new members", _welcome_sender),
    (51, "feedback_requester",        "Outreach",   "Request community feedback", _feedback_requester),
    (52, "testimonial_collector",     "Outreach",   "Collect testimonials", _testimonial_collector),
    (53, "referral_activator",        "Outreach",   "Activate referrals", _referral_activator),
    (54, "group_poll_creator",        "Outreach",   "Create community polls", _group_poll_creator),
    (55, "contest_organizer",         "Outreach",   "Organize contests", _contest_organizer),
    # Dept 5 — Analytics
    (56, "performance_tracker",       "Analytics",  "Track overall performance", _performance_tracker),
    (57, "dm_response_analyzer",      "Analytics",  "Analyze DM responses", _dm_response_analyzer),
    (58, "group_growth_tracker",      "Analytics",  "Track group growth", _group_growth_tracker),
    (59, "engagement_rate_calc",      "Analytics",  "Calculate engagement rates", _engagement_rate_calculator),
    (60, "conversion_tracker",        "Analytics",  "Track conversions", _conversion_tracker),
    (61, "roi_calculator",            "Analytics",  "Calculate ROI", _roi_calculator),
    (62, "reach_estimator",           "Analytics",  "Estimate total reach", _reach_estimator),
    (63, "trend_tracker",             "Analytics",  "Track trend performance", _trend_performance_tracker),
    (64, "competitor_growth_tracker", "Analytics",  "Track competitor growth", _competitor_growth_tracker),
    (65, "campaign_reporter",         "Analytics",  "Report campaign results", _campaign_performance_reporter),
    # Dept 6 — Strategy
    (66, "daily_goal_setter",         "Strategy",   "Set daily goals", _daily_goal_setter),
    (67, "priority_optimizer",        "Strategy",   "Optimize task priorities", _priority_optimizer),
    (68, "timing_advisor",            "Strategy",   "Advise on optimal timing", _timing_advisor),
    (69, "audience_segmenter",        "Strategy",   "Segment audiences", _audience_segmenter),
    (70, "approach_selector",         "Strategy",   "Select best approach", _approach_selector),
    (71, "opportunity_scorer",        "Strategy",   "Score opportunities", _opportunity_scorer),
    (72, "campaign_planner",          "Strategy",   "Plan campaigns", _campaign_planner),
    (73, "budget_allocator",          "Strategy",   "Allocate time budget", _budget_allocator),
    (74, "pivot_advisor",             "Strategy",   "Advise strategic pivots", _pivot_advisor),
    (75, "weekly_planner",            "Strategy",   "Plan the week ahead", _weekly_planner),
    # Dept 7 — Quality Control
    (76, "tone_checker",              "QC",         "Check message tone", _tone_checker),
    (77, "spam_risk_checker",         "QC",         "Check spam risk", _spam_risk_checker),
    (78, "personalization_validator", "QC",         "Validate personalization", _personalization_validator),
    (79, "brand_consistency_checker", "QC",         "Check brand consistency", _brand_consistency_checker),
    (80, "grammar_fixer",             "QC",         "Fix grammar/typos", _grammar_fixer),
    (81, "length_optimizer",          "QC",         "Optimize message length", _length_optimizer),
    (82, "clarity_improver",          "QC",         "Improve clarity", _clarity_improver),
    (83, "authenticity_checker",      "QC",         "Check human authenticity", _authenticity_checker),
    (84, "duplicate_detector",        "QC",         "Detect duplicate content", _duplicate_detector),
    (85, "compliance_auditor",        "QC",         "Audit for compliance", _compliance_auditor),
    # Dept 8 — Community
    (86, "community_health_monitor",  "Community",  "Monitor community health", _community_health_monitor),
    (87, "spam_detector",             "Community",  "Detect spam messages", _spam_detector),
    (88, "sentiment_monitor",         "Community",  "Monitor community sentiment", _sentiment_monitor),
    (89, "topic_moderator",           "Community",  "Moderate off-topic posts", _topic_moderator),
    (90, "knowledge_base_builder",    "Community",  "Build community FAQ", _knowledge_base_builder),
    (91, "ama_coordinator",           "Community",  "Coordinate AMAs", _ama_coordinator),
    (92, "milestone_tracker",         "Community",  "Track milestones", _milestone_tracker),
    (93, "member_recognition_agent",  "Community",  "Recognize top members", _member_recognition_agent),
    (94, "conflict_resolver",         "Community",  "Resolve conflicts", _conflict_resolver),
    (95, "community_reporter",        "Community",  "Report community stats", _community_reporter),
    # Dept 9 — Support
    (96,  "error_recovery_agent",     "Support",    "Recover from errors", _error_recovery_agent),
    (97,  "rate_limit_guardian",      "Support",    "Guard against rate limits", _rate_limit_guardian),
    (98,  "retry_coordinator",        "Support",    "Coordinate retries", _retry_coordinator),
    (99,  "session_health_checker",   "Support",    "Check session health", _session_health_checker),
    (100, "system_optimizer",         "Support",    "Optimise system performance", _system_optimizer),
]


class Orchestra:
    """
    100-Agent AI Orchestra.

    Usage:
        orch = Orchestra(tools, db)
        result = await orch.run("hunt web3 ambassador roles")
        result = await orch.run("analyze project XYZ", ctx={"project_name": "XYZ"})
    """

    DEPT_AGENTS = {
        "Discovery": list(range(1, 16)),
        "Research":  list(range(16, 26)),
        "Content":   list(range(26, 41)),
        "Outreach":  list(range(41, 56)),
        "Analytics": list(range(56, 66)),
        "Strategy":  list(range(66, 76)),
        "QC":        list(range(76, 86)),
        "Community": list(range(86, 96)),
        "Support":   list(range(96, 101)),
    }

    def __init__(self, tools, db):
        self.tools = tools
        self.db = db
        self._agents: dict[int, Agent] = {}
        for aid, name, dept, goal, fn in _ALL_AGENTS_DEFS:
            self._agents[aid] = Agent(id=aid, name=name, dept=dept, goal=goal, fn=fn)
        self._run_count = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def agent_count(self) -> int:
        return len(self._agents)

    def agents_by_dept(self) -> dict:
        summary = {}
        for dept, ids in self.DEPT_AGENTS.items():
            summary[dept] = len(ids)
        return summary

    def get_agent(self, agent_id: int) -> Optional[Agent]:
        return self._agents.get(agent_id)

    def toggle_agent(self, agent_id: int, enabled: bool):
        if agent_id in self._agents:
            self._agents[agent_id].enabled = enabled

    async def run(
        self,
        task: str,
        ctx: dict | None = None,
        max_agents: int = 12,
        progress_cb: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """
        Main entry: orchestrator selects agents, runs them concurrently,
        synthesizes results into a final answer.

        Args:
            task: Natural language task
            ctx: Optional context dict (project_name, topic, target_name, etc.)
            max_agents: Max agents to activate (default 12 for speed)
            progress_cb: Optional async callback(msg) for live updates
        """
        self._run_count += 1
        ctx = ctx or {}
        ctx.setdefault("topic", task)

        async def _progress(msg: str):
            if progress_cb:
                try:
                    await progress_cb(msg)
                except Exception:
                    pass

        await _progress(f"🧠 Orchestrator analyzing task with {self.agent_count()} agents...")

        # Step 1: Orchestrator selects which agents to run
        selected_ids = await self._orchestrate(task, ctx, max_agents)

        if not selected_ids:
            selected_ids = [1, 3, 11, 26, 56, 66, 99]  # sensible defaults

        await _progress(
            f"⚡ Activating {len(selected_ids)} agents:\n"
            + ", ".join(self._agents[i].name for i in selected_ids if i in self._agents)
        )

        # Step 2: Run selected agents concurrently (up to 6 at a time to respect AI slot limit)
        results: list[AgentResult] = []
        batch_size = 6
        for batch_start in range(0, len(selected_ids), batch_size):
            batch = selected_ids[batch_start:batch_start + batch_size]
            tasks = [
                self._agents[aid].run(self.tools, self.db, ctx)
                for aid in batch
                if aid in self._agents
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in batch_results:
                if isinstance(r, AgentResult):
                    results.append(r)
                elif isinstance(r, Exception):
                    results.append(AgentResult(0, "unknown", "unknown", ok=False, error=str(r)))

            if batch_start + batch_size < len(selected_ids):
                await _progress(f"✅ Batch {batch_start//batch_size + 1} complete — continuing...")

        # Step 3: Synthesize all results
        await _progress("🔮 Synthesizing results...")
        final = await self._synthesize(task, results)

        return final

    async def run_dept(
        self,
        dept: str,
        ctx: dict | None = None,
        progress_cb: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """Run all agents in a specific department."""
        ctx = ctx or {}
        ctx.setdefault("topic", dept)
        ids = self.DEPT_AGENTS.get(dept, [])
        if not ids:
            return f"Unknown department: {dept}"

        if progress_cb:
            await progress_cb(f"🚀 Running all {len(ids)} {dept} agents...")

        tasks = [self._agents[aid].run(self.tools, self.db, ctx) for aid in ids if aid in self._agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        clean = [r for r in results if isinstance(r, AgentResult)]
        return await self._synthesize(f"Run {dept} department", clean)

    async def run_full(
        self,
        ctx: dict | None = None,
        progress_cb: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """Run the full 100-agent orchestra — one agent per dept at a time."""
        ctx = ctx or {}
        all_results: list[AgentResult] = []
        depts = list(self.DEPT_AGENTS.keys())

        for dept in depts:
            ids = self.DEPT_AGENTS[dept][:3]  # top 3 from each dept for speed
            if progress_cb:
                await progress_cb(f"🔥 [{dept}] running {len(ids)} agents...")
            tasks = [self._agents[aid].run(self.tools, self.db, ctx) for aid in ids if aid in self._agents]
            batch = await asyncio.gather(*tasks, return_exceptions=True)
            all_results.extend(r for r in batch if isinstance(r, AgentResult))
            await asyncio.sleep(0.5)

        if progress_cb:
            await progress_cb(f"🔮 All {len(all_results)} agents done. Synthesizing...")

        return await self._synthesize("full 100-agent orchestra run", all_results)

    def status(self) -> str:
        enabled = sum(1 for a in self._agents.values() if a.enabled)
        lines = [
            f"🎼 Orchestra Status — {enabled}/{self.agent_count()} agents enabled | Run #{self._run_count}",
            ""
        ]
        for dept, ids in self.DEPT_AGENTS.items():
            enabled_in_dept = sum(1 for i in ids if self._agents.get(i, Agent(0,"","","",lambda *a:None)).enabled)
            bar = "🟢" * enabled_in_dept + "⭕" * (len(ids) - enabled_in_dept)
            lines.append(f"  {dept:<12} {bar}  {enabled_in_dept}/{len(ids)}")
        lines.append("")
        lines.append(router_status())
        return "\n".join(lines)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _orchestrate(self, task: str, ctx: dict, max_agents: int) -> list[int]:
        """Ask the orchestrator AI which agents to activate for this task."""
        agent_list = "\n".join(
            f"{a.id}: [{a.dept}] {a.name} — {a.goal}"
            for a in self._agents.values()
            if a.enabled
        )
        raw = await _ai(
            "You are the orchestrator of a 100-agent AI system. "
            "Select the optimal agents for the given task. "
            "Return ONLY a JSON array of agent IDs (integers), e.g. [1,3,16,26,56]. "
            f"Select between 5 and {max_agents} agents. Prioritise relevance and diversity of departments.",
            f"Task: {task}\nContext: {json.dumps(ctx)}\n\nAvailable agents:\n{agent_list}\n\n"
            f"Select up to {max_agents} most relevant agent IDs. Return only the JSON array.",
            500
        )
        try:
            m = re.search(r'\[[\d,\s]+\]', raw)
            if m:
                ids = json.loads(m.group())
                return [i for i in ids if isinstance(i, int) and 1 <= i <= 100][:max_agents]
        except Exception:
            pass
        # Fallback: keyword-based selection
        return self._keyword_select(task, max_agents)

    def _keyword_select(self, task: str, max_n: int) -> list[int]:
        """Fallback: select agents based on keywords in the task."""
        task_lower = task.lower()
        selected = set()
        keyword_map = {
            ("hunt", "find", "search", "discover", "scout"): [1,2,3,4,11,12],
            ("job", "apply", "hire", "work", "career"):      [3,13,14,32,61],
            ("dm", "message", "send", "outreach"):            [26,41,45,77,78],
            ("group", "join", "channel"):                     [4,42,43,44,86],
            ("post", "content", "write", "create"):           [27,28,38,39,79,82],
            ("news", "trend", "update"):                      [5,33,39,63],
            ("stats", "status", "analytics", "report"):       [56,57,58,65,95],
            ("plan", "strategy", "goal"):                     [66,67,70,72,75],
            ("analyze", "research", "review"):                [16,17,21,22,23],
            ("community", "moderate", "spam"):                [86,87,88,89,94],
            ("error", "fix", "retry", "health"):              [96,97,98,99],
        }
        for keywords, agent_ids in keyword_map.items():
            if any(k in task_lower for k in keywords):
                selected.update(agent_ids)
        if not selected:
            selected = {1, 3, 11, 26, 56, 66, 99, 100}
        return sorted(selected)[:max_n]

    async def _synthesize(self, task: str, results: list[AgentResult]) -> str:
        """Synthesize all agent results into a coherent final response."""
        ok_results = [r for r in results if r.ok and r.data]
        failed = [r for r in results if not r.ok]

        if not ok_results:
            fail_summary = " | ".join(f"{r.name}: {r.error[:50]}" for r in failed[:3])
            return f"⚠️ All agents failed. Errors: {fail_summary}"

        # Build a summary of results for the synthesizer
        result_text = ""
        for r in ok_results[:15]:  # cap to avoid token overflow
            data_str = str(r.data)[:300] if r.data else ""
            result_text += f"\n[{r.dept}/{r.name}]: {data_str}"

        synthesis = await _ai(
            _PERSONA + "\nYou are the final synthesizer of a 100-agent AI orchestra. "
            "Your job: combine all agent findings into ONE clear, actionable response. "
            "Use bullet points. Be direct. Include specific actions and results. "
            "Start with the most important finding. End with 'Next action:'",
            f"Task: {task}\n\nAgent results ({len(ok_results)} agents succeeded, {len(failed)} failed):\n"
            f"{result_text}\n\n"
            "Synthesize into a sharp, actionable summary. Max 400 words.",
            600
        )

        # Stats footer
        total_ms = sum(r.duration_ms for r in results)
        footer = (
            f"\n\n─\n"
            f"🎼 *{len(ok_results)}/{len(results)} agents* succeeded in {total_ms//1000}s"
        )

        return synthesis + footer
