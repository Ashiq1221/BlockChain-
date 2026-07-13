"""
Agent 5 — Content Agent
Generates and publishes posts in joined Telegram groups.
Adapts tone and style per group category.
"""
import asyncio
from telegram_agents.base_agent import BaseAgent
from telegram_agents.tools import ai_tools, telegram_tools
from telegram_agents.config import Config


STYLE_MAP = {
    "jobs":       "recruitment announcement, clear and compelling",
    "networking": "warm, community-focused, inviting discussion",
    "tech":       "insightful and technical, backed by data",
    "crypto":     "confident, market-aware, forward-looking",
    "news":       "factual, concise, neutral",
    "other":      "friendly and engaging",
}


class ContentAgent(BaseAgent):
    name = "ContentAgent"
    emoji = "📝"

    async def run(
        self,
        goal: str = "",
        topic: str | None = None,
        group_ids: list[int] | None = None,
        post_to_all: bool = False,
        max_groups: int = 5,
        **kwargs,
    ):
        if not topic:
            topic = ai_tools.think(
                system_addon="Extract the main content topic from a goal. Return 3-8 words only.",
                user_prompt=f"Goal: {goal}\n\nTopic:",
            )

        self.log(f"Content topic: {topic}")

        # Resolve target groups
        if group_ids:
            groups = [g for g in await self.db.get_groups(joined=True) if g["tg_id"] in group_ids]
        elif post_to_all:
            groups = await self.db.get_groups(joined=True)
        else:
            all_groups = await self.db.get_groups(joined=True)
            # Pick highest-member groups that match topic
            scored = []
            for g in all_groups:
                score = ai_tools.score_relevance(g.get("title", ""), topic)
                scored.append((score, g))
            scored.sort(key=lambda x: x[0], reverse=True)
            groups = [g for _, g in scored[:max_groups]]

        if not groups:
            self.log_warn("No joined groups to post to.")
            return {"posted": 0}

        posted_count = 0
        for group in groups:
            category = group.get("category", "other")
            style = STYLE_MAP.get(category, STYLE_MAP["other"])
            group_context = f"Group: {group.get('title')} | Category: {category} | Members: {group.get('members', '?')}"

            post_text = ai_tools.generate_post(topic, group_context, style)

            try:
                msg = await telegram_tools.send_message(self.client, group["tg_id"], post_text)
                if msg:
                    posted_count += 1
                    await self.db.log_message("out", group["tg_id"], "group", post_text, msg.id)
                    await self.db.upsert_group(group["tg_id"], last_post=str(msg.date))
                    self.log_success(f"Posted to: {group['title']}")
                await asyncio.sleep(Config.RATE_LIMIT_SLEEP * 3)
            except Exception as e:
                self.log_error(f"Post failed in {group.get('title')}: {e}")

        self.log_success(f"Content published to {posted_count}/{len(groups)} groups.")
        await self.db.log_event("content_post", {"topic": topic, "posted": posted_count})
        return {"posted": posted_count, "topic": topic}
