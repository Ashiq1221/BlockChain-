"""
Agent 2 — Group Discovery
Hunts for relevant Telegram groups on the web and inside Telegram itself,
scores their relevance, joins them, and persists results.
"""
import asyncio
from telegram_agents.base_agent import BaseAgent
from telegram_agents.tools import ai_tools, web_tools, telegram_tools


class GroupDiscoveryAgent(BaseAgent):
    name = "GroupDiscovery"
    emoji = "🔍"

    async def run(self, goal: str = "", topics: list[str] | None = None, join: bool = True, **kwargs):
        if not topics:
            if goal:
                raw = ai_tools.think(
                    system_addon="Extract search topics from a goal. Return comma-separated keywords only.",
                    user_prompt=f"Goal: {goal}\n\nTopics:",
                )
                topics = [t.strip() for t in raw.split(",") if t.strip()]
            else:
                topics = ["developer", "blockchain", "remote jobs"]

        self.log(f"Searching groups for topics: {topics}")
        all_groups: list[dict] = []

        for topic in topics:
            # Web search for public t.me links
            web_groups = await web_tools.find_telegram_groups_online(topic)
            self.log(f"Web found {len(web_groups)} groups for '{topic}'")
            all_groups.extend(web_groups)

            # Search inside Telegram
            tg_groups = await telegram_tools.search_public_groups(self.client, topic, limit=10)
            self.log(f"Telegram found {len(tg_groups)} groups for '{topic}'")
            all_groups.extend(tg_groups)

        # Deduplicate
        seen = set()
        unique = []
        for g in all_groups:
            key = g.get("username") or str(g.get("tg_id", ""))
            if key and key not in seen:
                seen.add(key)
                unique.append(g)

        self.log(f"Total unique groups: {len(unique)}")

        # Score and filter by relevance
        scored = []
        for g in unique:
            title = g.get("title", "") + " " + g.get("snippet", "")
            score = ai_tools.score_relevance(title, goal or " ".join(topics))
            g["score"] = score
            g["category"] = ai_tools.classify(title, ["jobs", "networking", "tech", "crypto", "news", "other"])
            scored.append(g)

        scored.sort(key=lambda x: x["score"], reverse=True)

        # Save to DB and optionally join
        joined_count = 0
        for g in scored[:30]:
            await self.db.upsert_group(
                tg_id=g.get("tg_id", hash(g.get("username", ""))),
                username=g.get("username", ""),
                title=g.get("title", ""),
                members=g.get("members", 0),
                category=g.get("category", "other"),
            )

            if join and g.get("username") and g["score"] >= 6:
                success = await telegram_tools.join_chat(self.client, g["username"])
                if success:
                    await self.db.upsert_group(
                        tg_id=g.get("tg_id", hash(g["username"])),
                        joined=1,
                    )
                    joined_count += 1
                    self.log_success(f"Joined: {g['title']} (@{g['username']})")
                await asyncio.sleep(2)

        self.log_success(f"Discovery complete. Found {len(scored)} groups, joined {joined_count}.")
        await self.db.log_event("group_discovery", {"found": len(scored), "joined": joined_count, "topics": topics})
        return scored
