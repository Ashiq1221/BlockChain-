"""
500 IQ Agentic Orchestrator
Full pipeline: Discover Projects → Join TG Group → Identify CEO/Founder → Craft DM → Send

General loop (every cycle): Observe → Think → Plan → Act → Reflect → Learn
Smart hunt (every Nth cycle): the full 10-step strategic pipeline above

Two rules that never break:
  1. NEVER auto-reply to incoming DMs from strangers
  2. NEVER post to groups on a timer with no strategic goal
"""
import asyncio
import json
import re
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from telegram_agents.tools import ai_tools, web_tools, telegram_tools
from telegram_agents.config import Config as _Cfg
from telegram_agents.tools.memory import Memory
from telegram_agents.tools.tool_registry import ToolRegistry
from telegram_agents.database import Database
from telegram_agents.config import Config
from telegram_agents.agent_factory import AgentFactory

console = Console()


# ── JSON extraction helpers ───────────────────────────────────────────────────

def _json_array(text: str) -> list:
    """Extract the first valid JSON array from an AI response."""
    start = text.find('[')
    if start < 0:
        return []
    end = text.rfind(']') + 1
    if end <= start:
        return []
    try:
        return json.loads(text[start:end])
    except Exception:
        return []


def _json_obj(text: str) -> dict | None:
    """Extract the first valid JSON object from an AI response."""
    start = text.find('{')
    if start < 0:
        return None
    end = text.rfind('}') + 1
    if end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except Exception:
        return None


# ── Constants ─────────────────────────────────────────────────────────────────

MASTER_GOAL = """
You are a 500 IQ autonomous agent managing a Telegram account for a Web3/AI developer.
Priority goals:
1. Find Web3/AI/blockchain projects actively hiring or seeking ambassadors, CM, mods
2. Join their Telegram groups, identify the CEO/founder/owner, send personalized outreach
3. Join relevant professional groups (blockchain, Python dev, remote jobs)
4. Apply to job postings found online
5. Post valuable content in groups only when it serves a clear networking goal

HARD RULES (never break):
- DO NOT auto-reply to incoming DMs from strangers
- DO NOT post to groups on a schedule without a strategic reason
- DO NOT sound like a bot — every message must sound human
- Rate limit: pause 5+ seconds between any sends
"""

DISCOVERY_QUERIES = [
    "web3 blockchain project hiring ambassador community manager 2026",
    "DeFi NFT AI project we are hiring moderator content creator 2026",
    "blockchain startup hiring remote developer python engineer 2026",
    "crypto project open roles ambassador social media manager 2026",
    "web3 AI project community lead content creator opening 2026",
    "site:t.me web3 project hiring community manager ambassador 2026",
    "telegram web3 group hiring team member 2026",
    "new crypto project launch team community builder 2026",
]

JOB_BOARD_QUERIES = [
    "site:cryptojobs.com community manager ambassador moderator remote 2026",
    "site:web3.career community manager ambassador content creator remote 2026",
    "site:remote3.co web3 AI blockchain community manager 2026",
    "site:wellfound.com web3 blockchain community manager ambassador remote",
    "crypto blockchain \"community manager\" OR \"ambassador\" apply telegram 2026",
    "web3 AI project hiring \"content creator\" OR \"social media manager\" remote 2026",
    "blockchain startup \"ambassador program\" apply 2026 telegram",
]

MY_PROFILE = (
    "NAME: Ashiq (@ashiq80) | Kashmir, India | fully remote\n"
    "STATS: 16,000+ Web3 Twitter/X followers (100% organic) | "
    "6,000+ member community (Telegram, Discord, OpenChat, DSCVR)\n"
    "PAST: EMC Protocol, ICPepeworld, Network3, LingoAI, RIDO, JarvisBot_AI\n"
    "SKILLS: Community Manager, Content Creator, Social Media Manager, "
    "AI prompt engineering, agentic AI systems, data annotation\n"
    "EDGE: builds autonomous AI systems — can automate growth, outreach, community ops"
)


# ── Agent Brain ───────────────────────────────────────────────────────────────

class AgentBrain:
    def __init__(self, tools: ToolRegistry, db: Database, memory: Memory, user_client=None):
        self.tools       = tools
        self.db          = db
        self.memory      = memory
        self.client      = user_client or tools.client
        self.cycle       = 0
        self.action_log: list[str] = []
        self._contacted: set[str]  = set()
        self._paused     = False
        self._hunt_every = 2
        self.factory     = AgentFactory()

    # ══════════════════════════════════════════════════════════════════════════
    #  500 IQ SMART HUNT PIPELINE
    # ══════════════════════════════════════════════════════════════════════════

    # ── Phase 1: DISCOVER ────────────────────────────────────────────────────

    async def discover_opportunities(self) -> list[dict]:
        """
        Source priority: X/Twitter API → Tavily (web_search) → scraping.
        Returns: [{"name","role","tg_username","website","description"}, ...]
        """
        parts = []

        # ── PRIMARY: X/Twitter developer API ────────────────────────────────
        if _Cfg.X_BEARER_TOKEN:
            console.print("    [dim cyan]X/Twitter live search...[/dim cyan]")
            x_text = await web_tools.x_search_jobs()
            if x_text and len(x_text) > 100:
                parts.append(f"[X/TWITTER LIVE]\n{x_text}")
                console.print(f"    [green]X/Twitter: {len(x_text)} chars[/green]")

        # ── SECONDARY: Tavily web search ─────────────────────────────────────
        console.print("    [dim]Tavily web search...[/dim]")
        snippets = []
        for q in DISCOVERY_QUERIES[:6]:
            results = await web_tools.web_search(q, num=6)
            for r in results:
                snippets.append(
                    f"Title: {r.get('title', '')}\n"
                    f"Snippet: {r.get('snippet', '')}\n"
                    f"URL: {r.get('url', '')}"
                )
        if snippets:
            parts.append("[WEB SEARCH]\n" + "\n---\n".join(snippets[:20]))
            console.print(f"    [green]Web: {len(snippets)} results[/green]")

        raw_text = "\n\n".join(parts)[:6000]
        if not raw_text:
            return []

        structured = ai_tools.think(
            system_addon=(
                "Extract Web3/AI/blockchain projects that are ACTIVELY hiring or seeking roles.\n"
                "Return ONLY valid JSON array (no markdown, no extra text):\n"
                '[{"name":"ProjectName","role":"developer|ambassador|CM|moderator|creator",'
                '"tg_username":"@handle_or_empty","website":"url_or_empty",'
                '"description":"one sentence about project + role"}]\n'
                "Rules:\n"
                "- Only include projects with a clear, real hiring/role signal\n"
                "- Max 10 entries, no duplicates\n"
                "- tg_username: only if you see t.me/ or @handle clearly mentioned, else empty string\n"
                "- description: include the SOURCE URL or tweet link if available"
            ),
            user_prompt=f"Data (from web search):\n{raw_text[:4000]}",
            max_tokens=1200,
        )

        projects = _json_array(structured)
        return [p for p in projects if isinstance(p, dict) and p.get("name") not in self._contacted]

    # ── Phase 1b: EXTRACT WEBSITE + SOCIAL LINKS ────────────────────────────

    async def extract_social_links(self, project: dict) -> dict:
        """
        Scrape project website for TG/Discord/X handles.
        Returns enriched social dict to merge into project.
        """
        website = project.get("website", "").strip()
        name    = project.get("name", "")
        out     = {"tg_from_web": "", "discord": "", "twitter": ""}

        if website and website.startswith("http"):
            console.print(f"    [dim]🌐 Scraping {website[:60]}...[/dim]")
            page = await web_tools.fetch_page(website)
            tg   = re.findall(r't\.me/(\w{3,32})', page)
            disc = re.findall(r'discord\.gg/(\w+)', page)
            twit = re.findall(r'(?:twitter|x)\.com/(\w+)', page)
            if tg:
                out["tg_from_web"] = tg[0]
            if disc:
                out["discord"] = f"discord.gg/{disc[0]}"
            if twit:
                skip = {"home", "intent", "share", "i", "search", "explore", "hashtag"}
                filtered = [t for t in twit if t.lower() not in skip]
                if filtered:
                    out["twitter"] = filtered[0]

        # Web-search fallback for TG if homepage had none
        if not out["tg_from_web"] and not project.get("tg_username"):
            results = await web_tools.web_search(
                f"{name} official telegram group t.me", num=4)
            for r in results:
                blob = r.get("url", "") + " " + r.get("snippet", "")
                tg   = re.findall(r't\.me/(\w{3,32})', blob)
                if tg and tg[0].lower() not in ("joinchat", "share", "s"):
                    out["tg_from_web"] = tg[0]
                    break

        if any(out.values()):
            console.print(
                f"    [green]Socials — TG:{out['tg_from_web'] or '—'} "
                f"Discord:{out['discord'] or '—'} X:@{out['twitter'] or '—'}[/green]"
            )
        return out

    # ── Phase 2: INFILTRATE ──────────────────────────────────────────────────

    async def infiltrate_project(self, project: dict) -> str | None:
        """
        Find and join the project's Telegram group via multiple strategies.
        Returns: username/id of the joined group, or None.
        """
        name    = project.get("name", "")
        tg_hint = project.get("tg_username", "").strip().lstrip("@t.me/")

        # Strategy A: direct join if we found a TG handle
        if tg_hint:
            ok = await telegram_tools.join_chat(self.client, tg_hint)
            if ok:
                console.print(f"    [green]✅ Joined @{tg_hint}[/green]")
                await asyncio.sleep(4)
                return tg_hint

        # Strategy B: find their group via web search
        groups = await web_tools.find_telegram_groups_online(name)
        for g in groups[:3]:
            u = g.get("username", "").strip().lstrip("@")
            if not u:
                continue
            ok = await telegram_tools.join_chat(self.client, u)
            if ok:
                console.print(f"    [green]✅ Joined @{u} (web find)[/green]")
                await asyncio.sleep(4)
                return u

        # Strategy C: Telegram's own global search
        try:
            hits = await telegram_tools.search_public_groups(self.client, name, limit=5)
            for h in hits:
                u = h.get("username", "")
                if not u:
                    continue
                ok = await telegram_tools.join_chat(self.client, u)
                if ok:
                    console.print(f"    [green]✅ Joined @{u} (TG search)[/green]")
                    await asyncio.sleep(4)
                    return u
        except Exception:
            pass

        return None

    # ── Phase 3: READ THE ROOM ───────────────────────────────────────────────

    async def read_room(self, chat_id: str) -> str:
        """Read recent group messages to understand project vibe and active users."""
        try:
            msgs  = await telegram_tools.get_chat_history(self.client, chat_id, limit=40)
            lines = [
                f"[user_{m.get('from_id', '')}]: {m.get('text', '')[:120]}"
                for m in msgs[:25]
            ]
            return "\n".join(lines)
        except Exception:
            return ""

    # ── Phase 4a: COLLECT ADMINS → IDENTIFY FOUNDER ─────────────────────────

    async def identify_from_admins(self, chat_id: str, project_name: str,
                                   room_context: str) -> dict | None:
        """
        Step 1: pull the admin list (small, authoritative).
        Step 2: AI picks the founder/CEO from admins.
        Step 3: fall back to full member scan if confidence too low.
        """
        admins = await telegram_tools.get_admins(self.client, chat_id)
        if admins:
            console.print(f"  [dim]👑 {len(admins)} admins found — scanning for founder[/dim]")
            raw = ai_tools.think(
                system_addon=(
                    "You are identifying the CEO, founder, or key decision maker of a Web3 project.\n"
                    "You are given the ADMIN LIST — these are the most authoritative members.\n\n"
                    "Signals (in priority order):\n"
                    "1. Name/username contains: founder, ceo, owner, lead, core, official, dev\n"
                    "2. Name closely matches the project name\n"
                    "3. They wrote authority-level messages (announcements, pinned posts)\n"
                    "4. Unique non-generic name that sounds like a founder\n\n"
                    "Return ONLY valid JSON (no markdown):\n"
                    '{"tg_id": 12345, "username": "handle_or_empty", "first_name": "Name", '
                    '"reason": "why", "confidence": 80}\n\n'
                    "If no admin looks like the founder (confidence < 45), return the single word: null"
                ),
                user_prompt=(
                    f"Project: {project_name}\n"
                    f"Admin list ({len(admins)} admins):\n{json.dumps(admins, indent=2)}\n\n"
                    f"Recent group messages:\n{room_context[:400]}"
                ),
                max_tokens=300,
            )
            raw_s = raw.strip()
            if raw_s.lower() not in ("null", "none", ""):
                result = _json_obj(raw_s)
                if result and int(result.get("confidence", 0)) >= 45:
                    result["_source"] = "admin_list"
                    return result

        console.print("  [dim]No clear founder in admins — scanning all members...[/dim]")
        result = await self.identify_decision_maker(chat_id, project_name, room_context)
        if result:
            result["_source"] = "member_scan"
        return result

    # ── Phase 4b: FIND FOUNDER'S PUBLIC TG USERNAME VIA WEB ─────────────────

    async def find_founder_telegram_username(self, person_name: str,
                                             project_name: str,
                                             twitter_handle: str = "") -> str:
        """Web-search for a founder's public Telegram username."""
        queries = [
            f'"{person_name}" {project_name} telegram t.me',
            f'{person_name} {project_name} founder CEO telegram',
        ]
        if twitter_handle:
            queries.insert(0, f'site:twitter.com {twitter_handle} telegram t.me')

        skip = {"joinchat", "share", "s", "iv", "addstickers"}
        for q in queries:
            results = await web_tools.web_search(q, num=3)
            for r in results:
                blob = r.get("url", "") + " " + r.get("snippet", "") + " " + r.get("title", "")
                tg   = re.findall(r't\.me/(\w{3,32})', blob)
                for handle in tg:
                    if handle.lower() not in skip:
                        return handle
        return ""

    # ── Phase 4: IDENTIFY CEO / FOUNDER ─────────────────────────────────────

    async def identify_decision_maker(self, chat_id: str, project_name: str,
                                      room_context: str) -> dict | None:
        """
        Harvest group members → AI identifies the CEO/founder/owner.
        Returns: {"tg_id","username","first_name","reason","confidence"} or None.
        """
        members = await telegram_tools.get_group_members(self.client, chat_id, limit=150)
        if not members:
            return None

        raw = ai_tools.think(
            system_addon=(
                "You are a detective identifying the CEO, founder, owner, or key decision maker "
                "of a Web3 project from its Telegram group.\n\n"
                "Signals to look for (in order of importance):\n"
                "1. Username or name contains: founder, ceo, owner, lead, core, official, admin, dev\n"
                "2. Name closely matches the project name\n"
                "3. They posted announcements or authority-level messages in the group chat\n"
                "4. Single unique name that sounds like a founder (rare name pattern)\n"
                "5. Low user ID (early Telegram accounts often belong to founders)\n\n"
                "Return ONLY valid JSON (no markdown):\n"
                '{"tg_id": 12345, "username": "handle_or_empty", "first_name": "Name", '
                '"reason": "specific reason you chose them", "confidence": 75}\n\n'
                "If confidence < 35, return the single word: null"
            ),
            user_prompt=(
                f"Project: {project_name}\n\n"
                f"Recent group messages (who's talking like an authority):\n{room_context[:700]}\n\n"
                f"Full member list ({len(members)} members — first 80 shown):\n"
                + json.dumps(members[:80], indent=2)
            ),
            max_tokens=400,
        )

        raw_s = raw.strip()
        if raw_s.lower() in ("null", "none", ""):
            return None
        result = _json_obj(raw_s)
        if result and int(result.get("confidence", 0)) >= 35:
            return result
        return None

    # ── Phase 5: CRAFT PERSONALIZED DM ──────────────────────────────────────

    def craft_outreach_dm(self, target: dict, project: dict, room_context: str) -> str:
        """AI writes a hyper-personalized DM using Ashiq's real stats."""
        role = project.get("role", "community/content")
        stat = (
            "16K Twitter followers"
            if "social" in role or "content" in role or "marketing" in role
            else "6K-member community"
            if "community" in role or "moderator" in role
            else "autonomous agentic AI systems"
        )
        return ai_tools.think(
            system_addon=(
                f"You are writing a Telegram DM for Ashiq, a Web3/AI community specialist.\n\n"
                f"ASHIQ'S PROFILE:\n{MY_PROFILE}\n\n"
                f"RULES — ALL must be followed:\n"
                f"- MAX 3 sentences — brevity is confidence\n"
                f"- Open with something SPECIFIC about the project (not 'I saw your project')\n"
                f"- Drop ONE concrete stat that matches their need: {stat}\n"
                f"- End with ONE soft, specific question — not 'are you hiring?'\n"
                f"- NO emojis, NO hashtags, NO 'Dear', NO 'Hi there!', NO 'I came across'\n"
                f"- Sign off: Ashiq | @ashiq80\n"
                f"- Return ONLY the message text — no quotes, no extra lines"
            ),
            user_prompt=(
                f"Project: {project.get('name')}\n"
                f"Role needed: {role}\n"
                f"What they do: {project.get('description', '')}\n"
                f"Recipient: {target.get('first_name', '')} (@{target.get('username', '')})\n"
                f"Why likely founder: {target.get('reason', '')}\n"
                f"Group vibe: {room_context[:200]}\n\n"
                "Write the DM:"
            ),
            max_tokens=220,
        )

    # ── JOB APPLICATION PIPELINE ─────────────────────────────────────────────

    async def find_and_apply_to_jobs(self) -> int:
        """
        Dedicated job board pipeline:
          1. Search crypto job boards via Firecrawl + Tavily
          2. AI extracts structured listings
          3. Save new jobs to DB
          4. Craft personalized application → find TG contact → DM
        Returns number of applications sent.
        """
        console.print(Rule("[bold yellow]💼 JOB APPLICATION CYCLE[/bold yellow]"))
        applied = 0

        # Step 1: Collect raw text from job boards
        all_snippets: list[str] = []
        for q in JOB_BOARD_QUERIES[:5]:
            results = await web_tools.web_search(q, num=5)
            for r in results:
                page_text = ""
                url = r.get("url", "")
                if url and url.startswith("http"):
                    page_text = await web_tools.fetch_page(url)
                all_snippets.append(
                    f"Title: {r.get('title', '')}\n"
                    f"Snippet: {r.get('snippet', '')}\n"
                    f"URL: {url}\n"
                    f"Content: {page_text[:600]}"
                )
            await asyncio.sleep(1)

        if not all_snippets:
            console.print("[yellow]No job board results this cycle.[/yellow]")
            return 0

        # Step 2: AI extracts structured job listings
        raw = "\n---\n".join(all_snippets[:15])
        jobs_found = ai_tools.extract_jobs(raw)
        console.print(f"  [cyan]→ {len(jobs_found)} job listings extracted[/cyan]")

        # Get already-applied URLs to avoid duplication
        existing_jobs = await self.db.get_jobs()
        applied_urls  = {j.get("url", "") for j in existing_jobs if j.get("applied")}
        seen_urls     = {j.get("url", "") for j in existing_jobs}

        for job in jobs_found[:10]:
            title   = job.get("title", "").strip()
            company = job.get("company", "").strip()
            desc    = job.get("description", "")
            url     = job.get("url", "")

            if not title or not company:
                continue
            if url in applied_urls:
                console.print(f"  [dim]Already applied: {title} @ {company}[/dim]")
                continue

            console.print(f"\n  [bold magenta]◆ {title}[/bold magenta]  [dim]{company}[/dim]")

            # Step 3: Save to DB if new
            if url not in seen_urls:
                await self.db.save_job(
                    title=title, company=company,
                    description=desc[:500], url=url, source="job_board",
                )
                seen_urls.add(url)

            # Step 4a: Find the hiring contact's Telegram
            tg_contact = ""
            if url and url.startswith("http"):
                page = await web_tools.fetch_page(url)
                tg_hits = re.findall(r't\.me/(\w{3,32})', page)
                skip = {"joinchat", "share", "s", "iv", "addstickers"}
                tg_hits = [t for t in tg_hits if t.lower() not in skip]
                if tg_hits:
                    tg_contact = tg_hits[0]

            if not tg_contact:
                search_results = await web_tools.web_search(
                    f"{company} official telegram t.me hiring apply", num=3)
                for sr in search_results:
                    blob = sr.get("url", "") + " " + sr.get("snippet", "")
                    tg_hits = re.findall(r't\.me/(\w{3,32})', blob)
                    tg_hits = [t for t in tg_hits if t.lower() not in {"joinchat","share","s","iv"}]
                    if tg_hits:
                        tg_contact = tg_hits[0]
                        break

            if not tg_contact:
                console.print(f"    [dim]No TG contact found for {company} — saved to DB only[/dim]")
                continue

            # Step 4b: Craft and send application
            msg = ai_tools.craft_job_application(job, MY_PROFILE)
            if not msg or len(msg) < 20 or msg.startswith("["):
                continue

            sent = await telegram_tools.send_dm(self.client, f"@{tg_contact}", msg)
            if sent:
                # Mark applied in DB
                fresh_jobs = await self.db.get_jobs()
                for jrow in fresh_jobs:
                    if jrow.get("url") == url:
                        await self.db.mark_job_applied(jrow["id"], msg[:200])
                        break
                await self.db.log_message("out", 0, "user", msg, 0)
                console.print(
                    f"    [bold green]✅ Applied → @{tg_contact} | {title} @ {company}[/bold green]"
                )
                applied += 1
                self.action_log.append(
                    f"[{datetime.now().strftime('%H:%M')}] Applied: {title} @ {company} → @{tg_contact}"
                )
                await asyncio.sleep(Config.RATE_LIMIT_SLEEP * 5)

        console.print(f"[bold yellow]💼 Job cycle done — {applied} applications sent[/bold yellow]")
        return applied

    # ── Phase 6: SEND + LOG ──────────────────────────────────────────────────

    async def send_outreach(self, target: dict, project: dict, msg: str) -> bool:
        if not msg or len(msg) < 15 or msg.startswith("["):
            return False

        tg_id    = target.get("tg_id") or target.get("user_id")
        username = target.get("username", "")

        sent = False
        try:
            if username:
                r = await telegram_tools.send_dm(self.client, f"@{username}", msg)
                sent = bool(r)
            if not sent and tg_id:
                r = await telegram_tools.send_dm(self.client, int(tg_id), msg)
                sent = bool(r)
        except Exception as e:
            console.print(f"    [red]DM error: {e}[/red]")

        if sent:
            await self.db.log_message("out", tg_id or 0, "user", msg, 0)
            name = project.get("name", "")
            who  = target.get("first_name", username)
            console.print(f"    [bold green]✉️  Sent to {who} at {name}[/bold green]")
            console.print(f'    [dim]"{msg[:90]}...[/dim]')

        return sent

    # ── FULL 10-STEP PIPELINE ────────────────────────────────────────────────

    def _log_step(self, step: int, label: str, detail: str = ""):
        icons = {1:"🔍",2:"🌐",3:"📡",4:"👁",5:"👑",6:"🕵️",7:"🔗",8:"✍️",9:"✉️",10:"📋"}
        icon = icons.get(step, "▸")
        line = f"  [cyan]Step {step}[/cyan] {icon}  [bold]{label}[/bold]"
        if detail:
            line += f"  [dim]{detail}[/dim]"
        console.print(line)

    def _log_outcome(self, project_name: str, outcome: str, target: dict | None):
        ts  = datetime.now().strftime("%H:%M")
        who = f"@{target.get('username', '?')}" if target else "—"
        self.action_log.append(f"[{ts}] {project_name} → {outcome} ({who})")

    async def smart_hunt_cycle(self) -> int:
        """
        10-step autonomous outreach pipeline:
          1. Find project          6. Search founder/team
          2. Extract website       7. Find public TG username
          3. Find TG/Discord/X     8. Generate personalized DM
          4. Join Telegram         9. Send DM
          5. Collect admins       10. Log outcome
        Returns number of DMs successfully sent.
        """
        console.print(Rule("[bold cyan]🧠 500 IQ SMART HUNT — 10-step pipeline[/bold cyan]"))

        self._log_step(1, "Discovering projects", "web search + X/Twitter")
        projects = await self.discover_opportunities()
        if not projects:
            console.print("[yellow]No new projects found this cycle.[/yellow]")
            return 0
        console.print(f"  [cyan]→ {len(projects)} candidate projects[/cyan]")

        contacted = 0
        for project in projects[:8]:
            name = project.get("name", "unknown")
            role = project.get("role", "role")
            console.print(f"\n  [bold magenta]◆ {name}[/bold magenta]  [dim]{role}[/dim]")

            try:
                self._log_step(2, "Extracting website", project.get("website", "none"))
                socials = await self.extract_social_links(project)
                project.update(socials)

                self._log_step(3, "Social links found",
                    f"TG:{project.get('tg_from_web') or project.get('tg_username') or '—'}  "
                    f"Discord:{project.get('discord') or '—'}  "
                    f"X:@{project.get('twitter') or '—'}")

                if project.get("tg_from_web") and not project.get("tg_username"):
                    project["tg_username"] = project["tg_from_web"]

                self._log_step(4, "Joining Telegram group")
                chat_id = await self.infiltrate_project(project)
                if not chat_id:
                    console.print("  [yellow]No public group found — skipping[/yellow]")
                    self._log_outcome(name, "no_group", None)
                    continue

                self._log_step(5, "Collecting admins/owners")
                room = await self.read_room(chat_id)

                self._log_step(6, "Identifying founder/CEO")
                target = await self.identify_from_admins(chat_id, name, room)
                if not target:
                    console.print("  [yellow]No clear founder/CEO found — skipping[/yellow]")
                    self._log_outcome(name, "no_founder", None)
                    continue

                fname = target.get("first_name", "?")
                uname = target.get("username", "")
                conf  = target.get("confidence", 0)
                src   = target.get("_source", "unknown")
                console.print(
                    f"  [green]Found: {fname} (@{uname}) "
                    f"{conf}% confidence via {src}[/green]"
                )
                console.print(f"  [dim]  Reason: {target.get('reason', '')[:80]}[/dim]")

                key = f"{name}__{target.get('tg_id', uname)}"
                if key in self._contacted:
                    console.print("  [dim]Already contacted — skipping[/dim]")
                    continue

                if not uname:
                    self._log_step(7, "Searching for public TG username", fname)
                    uname = await self.find_founder_telegram_username(
                        fname, name, project.get("twitter", "")
                    )
                    if uname:
                        target["username"] = uname
                        console.print(f"  [green]Found TG: @{uname}[/green]")
                    else:
                        console.print("  [dim]No public TG username found — will try by ID[/dim]")
                else:
                    self._log_step(7, "TG username", f"@{uname} (from group)")

                self._log_step(8, "Generating personalized DM")
                msg = self.craft_outreach_dm(target, project, room)

                self._log_step(9, "Sending DM", f"to {fname} (@{uname or '?'})")
                sent = await self.send_outreach(target, project, msg)

                outcome = "dm_sent" if sent else "dm_failed"
                self._log_step(10, "Outcome", outcome)
                self._log_outcome(name, outcome, target)

                if sent:
                    contacted += 1
                    self._contacted.add(key)
                    await self.memory.remember(
                        key=f"outreach_{key}",
                        value=f"DM to {fname} at {name} for {role}: {msg[:120]}",
                        memory_type="outreach",
                        score=1.0,
                    )

                await asyncio.sleep(Config.RATE_LIMIT_SLEEP * 5)

            except Exception as e:
                console.print(f"  [red]Error on {name}: {e}[/red]")
                self._log_outcome(name, f"error: {e}", None)
                continue

        for p in projects[:8]:
            self._contacted.add(p.get("name", ""))

        console.print(f"\n[bold green]Hunt complete — {contacted} DMs sent this cycle[/bold green]")
        return contacted

    # ══════════════════════════════════════════════════════════════════════════
    #  GENERAL OBSERVE → THINK → PLAN → ACT LOOP
    # ══════════════════════════════════════════════════════════════════════════

    _GENERAL_BLOCKED = {"post_in_group", "post_to_all_groups", "send_dm",
                        "reply_to_dm", "send_to_username"}

    async def observe(self) -> str:
        stats  = await self.db.get_stats()
        groups = await self.db.get_groups(joined=True)
        jobs   = await self.db.get_jobs(applied=False)
        best   = await self.memory.best_strategies()
        return (
            f"STATE (cycle {self.cycle}) — {datetime.now().strftime('%H:%M %d/%m')}:\n"
            f"Groups joined: {len(groups)} | Jobs pending: {len(jobs)} | "
            f"Messages sent: {stats.get('messages_sent', 0)} | "
            f"Outreach this session: {len(self._contacted)}\n\n"
            f"TOP STRATEGIES:\n{best}\n\n"
            f"RECENT ACTIONS:\n" + "\n".join(self.action_log[-5:] or ["None yet"])
        )

    def think(self, obs: str) -> str:
        return ai_tools.think(
            system_addon=MASTER_GOAL + "\nThink in 2 sentences then output: CONCLUSION: [what to do now]",
            user_prompt=f"STATE:\n{obs}\n\nTOOLS:\n{self.tools.descriptions}\n\nReason:",
            max_tokens=300,
        )

    def plan(self, thought: str, obs: str) -> list[dict]:
        raw = ai_tools.think(
            system_addon=(
                "Convert reasoning into a JSON action plan.\n"
                "Return ONLY a JSON array, no markdown:\n"
                '[{"step":1,"reason":"why","tool":"tool_name","args":{"k":"v"}}]\n'
                "Max 4 steps. Only use available tools.\n"
                "DO NOT plan post_in_group, send_dm, reply_to_dm — the smart hunt handles sends."
            ),
            user_prompt=(
                f"THOUGHT:\n{thought}\n\n"
                f"STATE:\n{obs}\n\n"
                f"TOOLS:\n{self.tools.descriptions}\n\n"
                "JSON:"
            ),
            max_tokens=500,
        )
        steps    = _json_array(raw)
        filtered = [s for s in steps if isinstance(s, dict) and "tool" in s]
        return filtered or [{"step": 1, "reason": "Check state", "tool": "get_stats", "args": {}}]

    async def act(self, plan: list[dict]) -> list[dict]:
        results = []
        for step in plan:
            tool   = step.get("tool", "")
            args   = step.get("args", {})
            reason = step.get("reason", "")

            if tool in self._GENERAL_BLOCKED:
                console.print(f"  [yellow]⚠ Blocked {tool} in general loop — use /hunt for sends[/yellow]")
                results.append({"step": step, "result": {"ok": False, "error": "blocked"}})
                continue

            console.print(f"  [cyan]▶ [{tool}][/cyan] {reason}")
            result = await self.tools.call(tool, **args)
            results.append({"step": step, "result": result})

            ts     = datetime.now().strftime("%H:%M")
            ok_str = "✅" if result.get("ok") else "❌"
            self.action_log.append(f"[{ts}] {tool} → {ok_str}")

            if result.get("ok"):
                out = result.get("result", "")
                console.print(f"    [green]✅ {str(out)[:80]}[/green]")
            else:
                console.print(f"    [red]❌ {result.get('error', '?')}[/red]")

            await asyncio.sleep(2)
        return results

    async def reflect(self, obs: str, results: list[dict]) -> str:
        summary = json.dumps([
            {"tool": r["step"]["tool"], "ok": r["result"].get("ok"),
             "out": str(r["result"].get("result", ""))[:80]}
            for r in results
        ])
        return ai_tools.think(
            system_addon="Analyze what happened in 2 sentences. What to do differently next cycle?",
            user_prompt=f"STATE: {obs[:250]}\nRESULTS: {summary}\nAnalysis:",
            max_tokens=150,
        )

    async def learn(self, reflection: str, results: list[dict]):
        for r in results:
            score = 1.0 if r["result"].get("ok") else -0.5
            await self.memory.remember(
                key=f"tool_{r['step']['tool']}_c{self.cycle}",
                value=f"{r['step']['tool']}: {'ok' if r['result'].get('ok') else 'fail'}",
                memory_type="tool_performance",
                score=score,
            )
        if reflection and not reflection.startswith("["):
            await self.memory.remember(
                key=f"strategy_c{self.cycle}",
                value=reflection[:200],
                memory_type="strategy",
                score=0,
            )

    async def handle_inbox(self):
        """Log unread count — NEVER auto-reply to strangers."""
        try:
            dialogs = await telegram_tools.get_dialogs(self.client, limit=20)
            unread  = [d for d in dialogs if d.get("unread", 0) > 0]
            if unread:
                console.print(f"  [yellow]📬 {len(unread)} unread — reply manually if needed[/yellow]")
        except Exception as e:
            console.print(f"  [red]Inbox check: {e}[/red]")

    def _sleep_minutes(self, results: list[dict]) -> int:
        if not results:
            return 20
        rate = sum(1 for r in results if r["result"].get("ok")) / len(results)
        return 10 if rate >= 0.8 else (20 if rate >= 0.5 else 30)

    # ══════════════════════════════════════════════════════════════════════════
    #  MAIN AUTONOMOUS LOOP
    # ══════════════════════════════════════════════════════════════════════════

    async def run_forever(self):
        console.print(Panel(
            "[bold magenta]🧠 500 IQ AGENTIC ORCHESTRATOR — ONLINE[/bold magenta]\n\n"
            "[white]Every cycle:[/white]\n"
            "  Observe → Think → Plan → Act → Reflect → Learn\n\n"
            "[white]Every 3rd cycle (SMART HUNT):[/white]\n"
            "  🔍 Discover projects via web + X/Twitter\n"
            "  📡 Find & join their Telegram group\n"
            "  👁  Read the room\n"
            "  🎯 Identify CEO / Founder\n"
            "  ✍️  Craft personalized DM\n"
            "  ✉️  Send outreach\n\n"
            "[dim]No auto-replies. No random posts. Only strategic sends.[/dim]",
            border_style="magenta",
        ))

        while True:
            if self._paused:
                await asyncio.sleep(10)
                continue

            self.cycle += 1
            console.print(Rule(f"[bold]CYCLE {self.cycle} — {datetime.now().strftime('%H:%M:%S')}[/bold]"))

            try:
                if self.cycle % self._hunt_every == 0:
                    await self.smart_hunt_cycle()

                # Job application cycle: every 3rd cycle, offset from hunt
                if self.cycle % 3 == 0:
                    await self.find_and_apply_to_jobs()

                obs        = await self.observe()
                thought    = self.think(obs)
                console.print(f"[dim italic]{thought[:200]}[/dim italic]")
                plan       = self.plan(thought, obs)
                results    = await self.act(plan)
                await self.handle_inbox()

                agent_reports = await self.factory.tick(self)
                if agent_reports:
                    console.print(f"  [dim cyan]Agents: {' | '.join(agent_reports)}[/dim cyan]")

                reflection = await self.reflect(obs, results)
                await self.learn(reflection, results)

                sleep_min = self._sleep_minutes(results)
                console.print(f"[dim]💤 Sleeping {sleep_min} min[/dim]")
                await asyncio.sleep(sleep_min * 60)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                console.print(f"[red]Cycle {self.cycle} crashed: {e}[/red]")
                await asyncio.sleep(300)
