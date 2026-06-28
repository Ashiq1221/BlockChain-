"""
Agent 11 — Opportunity Hunter (robust rewrite)
Finds ambassador / CM / moderator / content creator / Web3 & AI roles,
locates their Telegram, and sends a personalized application DM.
"""
import asyncio
import re
from datetime import datetime
from telegram_agents.base_agent import BaseAgent
from telegram_agents.tools import ai_tools, web_tools, telegram_tools

# ── What to search ────────────────────────────────────────────────────────────
SEARCHES = [
    ("ambassador",        "web3 crypto ambassador program 2025 apply telegram"),
    ("ambassador",        "blockchain AI ambassador program hiring 2025 telegram contact"),
    ("community_manager", "web3 crypto community manager CM hiring 2025 telegram"),
    ("community_manager", "AI project community manager role 2025 apply telegram"),
    ("moderator",         "telegram moderator wanted crypto web3 2025 apply"),
    ("moderator",         "web3 project moderator hiring 2025 telegram DM"),
    ("content_creator",   "web3 crypto content creator collab 2025 telegram"),
    ("content_creator",   "AI blockchain content creator partnership apply 2025"),
    ("ambassador",        "new DeFi project ambassador program open 2025"),
    ("ambassador",        "new AI crypto project ambassador apply telegram 2025"),
    ("community_manager", "new web3 startup community team hiring telegram 2025"),
    ("moderator",         "new crypto project telegram moderator open role 2025"),
]

# ── Message templates ─────────────────────────────────────────────────────────
TEMPLATES = {
    "ambassador": (
        "Hi! I'm interested in joining {project}'s ambassador program. "
        "I'm an active Web3 community member passionate about blockchain and AI. "
        "I'd love to help grow {project}'s community and spread awareness. "
        "Could you share details about the ambassador program? 🙏"
    ),
    "community_manager": (
        "Hi! I saw {project} is looking for a Community Manager. "
        "I have hands-on experience managing Web3 Telegram communities — "
        "engagement, moderation, announcements, and growth. "
        "I'm available immediately and genuinely excited about {project}. Can we talk?"
    ),
    "moderator": (
        "Hi! I'd love to be a moderator for {project}. "
        "I'm daily-active on Telegram, understand the Web3 space well, "
        "and can keep the community clean and welcoming. "
        "Happy to do a trial period — let me know!"
    ),
    "content_creator": (
        "Hi! I'd love to collaborate with {project} as a content creator. "
        "I create Web3/crypto content and would love to help grow {project}'s presence "
        "through posts, threads, and community updates. "
        "Can we discuss a collab? 🚀"
    ),
    "general": (
        "Hi! I'm a Web3/AI enthusiast looking to contribute to {project}. "
        "I have experience in community management, moderation, and content creation. "
        "Is there any open role or way I can help? Would love to be part of the team!"
    ),
}


class OpportunityHunterAgent(BaseAgent):
    name = "OpportunityHunter"
    emoji = "🎯"

    async def run(self, goal: str = "", max_apply: int = 15, **kwargs):
        self.log(f"Hunting ambassador/CM/mod/creator roles in Web3 & AI...")
        total_found = 0
        total_applied = 0

        for role, query in SEARCHES:
            if total_applied >= max_apply:
                break

            self.log(f"[{role}] Searching: {query[:55]}...")
            results = await web_tools.web_search(query, num=6)

            if not results:
                self.log_warn(f"  No results for query — skipping")
                await asyncio.sleep(2)
                continue

            self.log(f"  Got {len(results)} results")

            for result in results:
                if total_applied >= max_apply:
                    break

                title   = result.get("title", "")
                snippet = result.get("snippet", "")
                url     = result.get("url", "")
                text    = f"{title} {snippet} {url}"

                # Extract project name
                project = await self._extract_project_name(title, snippet)
                if not project or len(project) < 2:
                    continue

                total_found += 1

                # Find Telegram links directly in search result
                tg_usernames = self._extract_tg_links(text)

                # If none found, search specifically for project TG
                if not tg_usernames:
                    tg_usernames = await self._search_project_telegram(project)

                if not tg_usernames:
                    self.log(f"  No TG found for {project}")
                    continue

                self.log(f"  → {project} [{role}] TG: {tg_usernames[:2]}")

                # Save to DB
                await self.db.save_job(
                    title=f"{role.upper()} @ {project}",
                    company=project,
                    description=snippet[:300],
                    source=url,
                )

                # Apply via Telegram
                applied = await self._apply(project, role, tg_usernames[:2])
                if applied:
                    total_applied += 1
                    self.log_success(f"  ✅ Applied for {role} at {project}")

                await asyncio.sleep(4)

            await asyncio.sleep(2)

        self.log_success(f"Done. Found {total_found} opportunities, applied to {total_applied}.")
        await self.db.log_event("opportunity_hunt", {
            "found": total_found,
            "applied": total_applied,
            "ts": str(datetime.now()),
        })
        return {"found": total_found, "applied": total_applied}

    def _extract_tg_links(self, text: str) -> list[str]:
        """Extract @username or t.me/username from any text."""
        found = []
        # t.me/username links
        for m in re.findall(r't\.me/([\w]{4,})', text):
            if m not in ("joinchat","s","share","addstickers"):
                found.append(m)
        # @username mentions
        for m in re.findall(r'@([\w]{5,})', text):
            found.append(m)
        return list(dict.fromkeys(found))  # deduplicate preserving order

    async def _extract_project_name(self, title: str, snippet: str) -> str:
        """Use AI to extract the project/company name."""
        result = ai_tools.think(
            system_addon="Extract the crypto/Web3/AI project or company name from text. Return ONLY the name, nothing else. Max 4 words.",
            user_prompt=f"Title: {title}\nSnippet: {snippet[:200]}\n\nProject name:",
            max_tokens=20,
        )
        name = result.strip().strip('"').strip("'")
        # Reject generic words
        if any(w in name.lower() for w in ["unknown","none","n/a","error","project","crypto","web3"]):
            return ""
        return name[:50]

    async def _search_project_telegram(self, project: str) -> list[str]:
        """Find a project's Telegram via web search."""
        queries = [
            f"{project} official telegram",
            f"{project} telegram group t.me",
        ]
        found = []
        for q in queries:
            results = await web_tools.web_search(q, num=3)
            for r in results:
                text = r.get("url","") + " " + r.get("snippet","") + " " + r.get("title","")
                found.extend(self._extract_tg_links(text))
            if found:
                break
        return list(dict.fromkeys(found))[:3]

    async def _apply(self, project: str, role: str, tg_usernames: list[str]) -> bool:
        """Send application to Telegram group or DM."""
        template = TEMPLATES.get(role, TEMPLATES["general"])
        base_msg = template.format(project=project)

        # Personalize with AI
        message = ai_tools.think(
            system_addon="Rewrite this Telegram outreach message to sound more natural and human. Keep it under 120 words. No hashtags.",
            user_prompt=f"Base message:\n{base_msg}\n\nNatural version:",
            max_tokens=200,
        )

        for username in tg_usernames:
            username = username.lstrip("@").strip()
            if not username or len(username) < 4:
                continue
            try:
                # Try joining as group first
                joined = await telegram_tools.join_chat(self.client, username)
                await asyncio.sleep(3)
                if joined:
                    msg = await telegram_tools.send_message(self.client, f"@{username}", message)
                    if msg:
                        await self.db.log_message("out", hash(username), "group", message, msg.id)
                        return True
            except Exception:
                pass

            try:
                # Try as direct user DM
                msg = await telegram_tools.send_dm(self.client, f"@{username}", message)
                if msg:
                    await self.db.log_message("out", hash(username), "user", message, msg.id)
                    return True
            except Exception:
                pass

        return False
