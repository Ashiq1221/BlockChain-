"""
Agent 11 — Opportunity Hunter
Searches the web & X (Twitter) for:
  - Ambassador programs
  - Community Manager (CM) roles
  - Moderator positions
  - Content Creator openings
  - New Web3 / AI projects needing community

Then finds their Telegram, joins, DMs the right people, and applies.
Runs fully autonomously — zero human input.
"""
import asyncio
import re
import json
from datetime import datetime
from telegram_agents.base_agent import BaseAgent
from telegram_agents.tools import ai_tools, web_tools, telegram_tools

# ── Search queries ────────────────────────────────────────────────────────────
SEARCH_QUERIES = [
    # Ambassador
    "Web3 crypto ambassador program 2025 apply telegram",
    "AI project ambassador role hiring 2025 site:twitter.com OR site:t.me",
    "blockchain ambassador program open applications telegram contact",

    # Community Manager
    "Web3 community manager hiring 2025 telegram DM",
    "crypto project CM role open 2025 contact telegram",
    "AI startup community manager position telegram",

    # Moderator
    "telegram moderator wanted Web3 crypto 2025",
    "crypto project moderator hiring apply telegram",
    "Web3 discord telegram moderator open role 2025",

    # Content Creator
    "Web3 content creator collab 2025 telegram",
    "crypto AI project content creator partnership telegram",
    "blockchain content creator ambassador apply 2025",

    # New projects
    "new Web3 project launch 2025 community roles telegram",
    "new AI crypto project hiring community team telegram 2025",
    "new DeFi project ambassador moderator CM apply telegram",
]

ROLE_TEMPLATES = {
    "ambassador": """Hi! I came across {project}'s ambassador program and I'm very interested in applying.

I'm an active Web3 community member with experience in growing crypto communities. I'm passionate about {project}'s mission and would love to represent the project.

What I bring:
• Active presence across Web3 Telegram communities
• Experience in content creation and community engagement
• Genuine interest in the Web3/AI space

Could you share more details about the ambassador program? I'd love to contribute!""",

    "community_manager": """Hi! I noticed {project} is looking for a Community Manager and I'd like to apply.

I have solid experience managing crypto/Web3 Telegram communities — handling member engagement, moderation, announcements, and growing active communities from the ground up.

I'm available immediately and very interested in working with {project}. Can we discuss this opportunity?""",

    "moderator": """Hi! I saw {project} is looking for Telegram moderators and I'm interested.

I'm an experienced Web3 community member who understands the space well. I'm active daily on Telegram, familiar with moderation best practices, and genuinely interested in {project}'s project.

I'd love to help moderate your community — happy to do a trial period too!""",

    "content_creator": """Hi! I'd love to collaborate with {project} as a content creator.

I create Web3/crypto content and I'm passionate about the space. I can produce:
• Educational posts and threads about {project}
• Community updates and announcements
• Engaging content that drives awareness

Would love to discuss a content partnership with the {project} team!""",

    "general": """Hi! I'm interested in joining the {project} team.

I'm an active Web3/AI community member looking to contribute. I have experience in community management, moderation, content creation, and ambassador roles.

Is {project} looking for any community contributors? I'd love to help!""",
}

USER_PROFILE = """
Web3 & AI enthusiast with hands-on experience in:
- Community management and growth (Telegram, Discord)
- Content creation for crypto projects
- Ambassador roles for blockchain projects
- Moderating active crypto communities
- Staying current with DeFi, NFT, AI trends
Available immediately. Passionate about Web3 and AI innovation.
"""


class OpportunityHunterAgent(BaseAgent):
    name = "OpportunityHunter"
    emoji = "🎯"

    async def run(self, goal: str = "", max_opportunities: int = 20, **kwargs):
        self.log("Starting opportunity hunt across Web3 / AI / X...")
        opportunities = []

        # ── Step 1: Search web for opportunities ──────────────────────────────
        for query in SEARCH_QUERIES:
            self.log(f"Searching: {query[:60]}...")
            results = await web_tools.web_search(query, num=5)
            for r in results:
                opp = await self._extract_opportunity(r)
                if opp:
                    opportunities.append(opp)
            await asyncio.sleep(1)

        # ── Step 2: Deduplicate by project name ───────────────────────────────
        seen = set()
        unique = []
        for o in opportunities:
            key = o.get("project", "").lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(o)

        self.log(f"Found {len(unique)} unique opportunities")

        # ── Step 3: Score and sort by relevance ───────────────────────────────
        scored = []
        for o in unique[:max_opportunities]:
            score = ai_tools.score_relevance(
                f"{o.get('project')} {o.get('role')} {o.get('description','')}",
                "Web3 AI crypto community ambassador moderator content creator"
            )
            o["score"] = score
            scored.append(o)
        scored.sort(key=lambda x: x["score"], reverse=True)

        # ── Step 4: For each opportunity — find TG and DM ─────────────────────
        applied = 0
        for opp in scored:
            if applied >= max_opportunities:
                break

            project  = opp.get("project", "Unknown Project")
            role     = opp.get("role", "general")
            tg_links = opp.get("telegram_links", [])
            url      = opp.get("url", "")

            self.log(f"Processing: {project} [{role}] score={opp['score']}")

            # Find Telegram contacts if not already found
            if not tg_links:
                tg_links = await self._find_telegram_contacts(project, url)

            if not tg_links:
                self.log(f"  No Telegram found for {project} — skipping")
                continue

            # Save opportunity to DB
            await self.db.save_job(
                title=f"{role.upper()} — {project}",
                company=project,
                description=opp.get("description", "")[:300],
                source=url,
            )

            # Join group and DM
            for tg in tg_links[:2]:
                success = await self._apply_via_telegram(tg, project, role)
                if success:
                    applied += 1
                    self.log_success(f"  Applied for {role} at {project} via {tg}")
                    break
                await asyncio.sleep(3)

            await asyncio.sleep(5)

        self.log_success(f"Opportunity hunt done. Found {len(scored)}, applied to {applied}.")
        await self.db.log_event("opportunity_hunt", {
            "found": len(scored),
            "applied": applied,
            "timestamp": str(datetime.now()),
        })
        return {"found": len(scored), "applied": applied}

    async def _extract_opportunity(self, search_result: dict) -> dict | None:
        """Use AI to extract structured opportunity data from a search result."""
        text = f"{search_result.get('title','')} {search_result.get('snippet','')}"
        url  = search_result.get("url", "")

        # Quick keyword filter
        keywords = ["ambassador", "community manager", "moderator", "content creator",
                    "cm role", "web3", "crypto", "blockchain", "defi", "ai project"]
        if not any(kw in text.lower() for kw in keywords):
            return None

        raw = ai_tools.think(
            system_addon="""Extract opportunity details from text. Return JSON only:
{
  "project": "project name",
  "role": "ambassador|community_manager|moderator|content_creator|general",
  "description": "brief description",
  "telegram_links": ["@username or t.me/link if found in text"]
}
If not a real opportunity, return: {"skip": true}""",
            user_prompt=f"URL: {url}\nText: {text}\n\nExtract JSON:",
            max_tokens=300,
        )

        try:
            match = re.search(r'\{.*?\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                if data.get("skip"):
                    return None
                data["url"] = url
                # Extract t.me links from URL/text
                tg_found = re.findall(r't\.me/[\w]+|@[\w]{5,}', text + " " + url)
                data["telegram_links"] = list(set(data.get("telegram_links", []) + tg_found))
                return data
        except Exception:
            pass
        return None

    async def _find_telegram_contacts(self, project: str, source_url: str) -> list[str]:
        """Search web to find the project's official Telegram."""
        contacts = []

        # Search for project Telegram
        queries = [
            f"{project} official telegram group",
            f"{project} crypto telegram t.me",
            f"site:t.me {project}",
        ]
        for q in queries[:2]:
            results = await web_tools.web_search(q, num=3)
            for r in results:
                found = re.findall(r't\.me/([\w]+)', r.get("url","") + r.get("snippet",""))
                contacts.extend([f"@{u}" for u in found if len(u) > 3])

        # Also check source page
        if source_url and "t.me" not in source_url:
            page = await web_tools.fetch_page(source_url)
            found = re.findall(r't\.me/([\w]+)', page)
            contacts.extend([f"@{u}" for u in found if len(u) > 3])

        return list(set(contacts))[:3]

    async def _apply_via_telegram(self, tg_contact: str, project: str, role: str) -> bool:
        """Join the group and DM or post the application."""
        # Clean username
        username = tg_contact.replace("@","").replace("t.me/","").strip()
        if not username or len(username) < 3:
            return False

        # Get the right message template
        template = ROLE_TEMPLATES.get(role, ROLE_TEMPLATES["general"])

        # Let AI personalize it
        message = ai_tools.think(
            system_addon="""You write short, genuine Telegram outreach messages for Web3/AI community roles.
Sound like a real human — enthusiastic but professional.
Keep it under 150 words. No emojis spam. No generic templates.""",
            user_prompt=f"""Project: {project}
Role applying for: {role}
My profile: {USER_PROFILE}
Base template: {template.format(project=project)}

Write a personalized, natural version:""",
            max_tokens=250,
        )

        # Try to join (if it's a group)
        try:
            joined = await telegram_tools.join_chat(self.client, username)
            if joined:
                await self.db.upsert_group(
                    tg_id=hash(username),
                    username=username,
                    title=project,
                    category="jobs",
                    joined=1,
                )
                await asyncio.sleep(3)
                # Post application in group
                msg = await telegram_tools.send_message(self.client, f"@{username}", message)
                if msg:
                    await self.db.log_message("out", hash(username), "group", message, msg.id)
                    return True
        except Exception:
            pass

        # Try DM directly
        try:
            msg = await telegram_tools.send_dm(self.client, f"@{username}", message)
            if msg:
                await self.db.log_message("out", hash(username), "user", message, msg.id)
                return True
        except Exception:
            pass

        return False
